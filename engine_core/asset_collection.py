from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from .book_state import load_book_db
from .common import ensure_dir, now_iso, read_json, write_json, write_text
from .contracts import resolve_stage_contract, validate_inputs
from .gates import evaluate_gate
from .memory import update_chapter_memory
from .stage import transition_stage
from .work_order import issue_work_order


_EXTENSION_HINTS = {
    "external_image": ".jpg",
    "ai_generated_image": ".png",
    "video_embed": ".txt",
    "technical_asset": ".svg",
}


def _missing_s6a_outputs(book_id: str, book_root: Path, chapter_id: str) -> list[str]:
    outputs = resolve_stage_contract(book_id, book_root, "S6A", chapter_id)["outputs"]
    return [path for path in outputs if not Path(path).exists()]


def _pending_s6a_chapters(book_id: str, book_root: Path) -> list[str]:
    payload = load_book_db(book_root)
    return [
        chapter_id
        for chapter_id in payload["chapter_sequence"]
        if payload["chapters"][chapter_id]["stages"]["S6A"]["status"] in {"pending", "in_progress", "gate_failed"}
        or (
            payload["chapters"][chapter_id]["stages"]["S6A"]["status"] == "completed"
            and bool(_missing_s6a_outputs(book_id, book_root, chapter_id))
        )
    ]


def _chapter_reference_entries(reference_index: dict[str, Any], chapter_id: str) -> list[dict[str, Any]]:
    for chapter in reference_index.get("chapters", []):
        if chapter.get("chapter_id") == chapter_id:
            return chapter.get("entries", [])
    return []


def _chapter_image_items(image_manifest: dict[str, Any], chapter_id: str) -> list[dict[str, Any]]:
    return [item for item in image_manifest.get("items", []) if item.get("chapter_id") == chapter_id]


def _detect_existing_assets(book_root: Path, target_dir: str, file_stub: str) -> list[str]:
    asset_dir = ensure_dir(book_root / target_dir)
    detected = sorted(
        str(path.relative_to(book_root)).replace("\\", "/")
        for path in asset_dir.glob(f"{file_stub}_v*.*")
        if path.is_file()
    )
    return detected


def _asset_request_rows(
    book_root: Path,
    chapter: dict[str, Any],
    visual_plan: dict[str, Any],
    reference_entries: list[dict[str, Any]],
    image_items: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    reference_map = {entry.get("reference_id"): entry for entry in reference_entries}
    image_map = {item.get("appendix_reference_id"): item for item in image_items}
    rows: list[dict[str, Any]] = []

    for anchor in visual_plan.get("anchors", []):
        appendix_ref_id = anchor.get("appendix_ref_id")
        image_item = image_map.get(appendix_ref_id, {})
        reference_entry = reference_map.get(appendix_ref_id, {})
        source_mode = str(image_item.get("source_mode") or anchor.get("source_mode") or anchor.get("asset_mode") or "")
        collection_required = source_mode in {"external_image", "ai_generated_image", "video_embed", "technical_asset"}
        target_stub = str(
            image_item.get("target_filename_stub")
            or f"ASSET_{chapter['chapter_id'].upper()}_{anchor.get('anchor_type', 'ASSET')}_001"
        )
        target_dir = str(
            image_item.get("planned_storage_dir")
            or f"publication/assets/cleared/{chapter['chapter_id']}"
        )
        filename_ext = _EXTENSION_HINTS.get(source_mode, ".dat")
        target_filename = f"{target_stub}_v001{filename_ext}"
        detected_files = _detect_existing_assets(book_root, target_dir, target_stub)
        if collection_required and detected_files:
            binding_status = "cleared_file_detected"
        elif collection_required:
            binding_status = "awaiting_offline_collection"
        else:
            binding_status = "in_pipeline_render_only"

        rows.append(
            {
                "anchor_id": anchor.get("anchor_id"),
                "anchor_type": anchor.get("anchor_type"),
                "caption": anchor.get("caption"),
                "appendix_ref_id": appendix_ref_id,
                "image_id": image_item.get("image_id"),
                "source_mode": source_mode,
                "asset_mode": anchor.get("asset_mode"),
                "collection_required": collection_required,
                "binding_status": binding_status,
                "offline_owner": "manual_offline_round" if collection_required else "core_engine",
                "target_dir": target_dir,
                "target_filename_stub": target_stub,
                "target_filename": target_filename,
                "detected_files": detected_files,
                "rights_status": image_item.get("rights_status"),
                "required_action": reference_entry.get("required_action"),
                "clearance_status": reference_entry.get("clearance_status"),
                "required_fields": reference_entry.get("required_fields", []),
                "appendix_required": reference_entry.get("appendix_required", True),
                "binding_preference": "use_cleared_asset_first" if collection_required else "use_engine_render",
            }
        )
    return rows


def _render_asset_collection_manifest(
    book_id: str,
    chapter: dict[str, Any],
    visual_plan: dict[str, Any],
    asset_requests: list[dict[str, Any]],
) -> dict[str, Any]:
    return {
        "version": "1.0",
        "generated_at": now_iso(),
        "book_id": book_id,
        "stage_id": "S6A",
        "chapter_id": chapter["chapter_id"],
        "chapter_title": chapter["title"],
        "render_strategy": visual_plan.get("render_strategy"),
        "offline_asset_round_required": any(item["collection_required"] for item in asset_requests),
        "naming_rule": "ASSET_{CHAPTER}_{ANCHORTYPE}_{SEQ}_v001.ext",
        "default_storage_root": f"publication/assets/cleared/{chapter['chapter_id']}",
        "asset_requests": asset_requests,
    }


def _render_asset_collection_handoff(chapter: dict[str, Any], manifest: dict[str, Any]) -> str:
    lines = [
        f"# ASSET COLLECTION HANDOFF: {chapter['chapter_id']} | {chapter['title']}",
        "",
        f"- Generated at: `{manifest['generated_at']}`",
        "- Stage: `S6A / AG-AS`",
        "- Naming rule: `ASSET_{CHAPTER}_{ANCHORTYPE}_{SEQ}_v001.ext`",
        f"- Default storage root: `{manifest['default_storage_root']}`",
        f"- Offline collection required: `{manifest['offline_asset_round_required']}`",
        "",
        "## Requests",
        "| Anchor | Type | Source Mode | Appendix Ref | Target Filename | Binding Status |",
        "| --- | --- | --- | --- | --- | --- |",
    ]
    for item in manifest.get("asset_requests", []):
        lines.append(
            f"| `{item['anchor_id']}` | `{item['anchor_type']}` | `{item['source_mode']}` | "
            f"`{item['appendix_ref_id']}` | `{item['target_filename']}` | `{item['binding_status']}` |"
        )
    lines.extend(
        [
            "",
            "## Rules",
            "- `appendix_ref_id`와 실제 자산 파일명은 반드시 1:1로 추적 가능해야 한다.",
            "- 저작권/라이선스 검토는 offline round에서 해결하되, 결과는 reference index와 image manifest에 다시 반영한다.",
            "- 수집된 파일이 있으면 이후 `S7`은 placeholder 대신 cleared asset을 우선 바인딩한다.",
        ]
    )
    return "\n".join(lines).rstrip() + "\n"


def run_asset_collection(
    book_id: str,
    book_root: Path,
    chapter_id: str | None = None,
) -> dict[str, Any]:
    reference_index = read_json(book_root / "research" / "reference_index.json", default=None)
    image_manifest = read_json(book_root / "research" / "image_manifest.json", default=None)
    if reference_index is None or image_manifest is None:
        raise FileNotFoundError("S6A requires reference_index.json and image_manifest.json.")

    book_db = load_book_db(book_root)
    target_chapters = [chapter_id] if chapter_id else _pending_s6a_chapters(book_id, book_root)
    if not target_chapters:
        return {
            "stage_id": "S6A",
            "status": "no_op",
            "message": "No pending S6A chapters found.",
        }

    results = []
    for current_chapter_id in target_chapters:
        contract_status = validate_inputs(book_id, book_root, "S6A", current_chapter_id)
        if not contract_status["valid"]:
            raise FileNotFoundError(f"S6A inputs missing for {current_chapter_id}: {contract_status['missing_inputs']}")

        chapter = {
            "chapter_id": current_chapter_id,
            "title": book_db["chapters"][current_chapter_id]["title"],
            "part": book_db["chapters"][current_chapter_id].get("part"),
        }
        current_status = book_db["chapters"][current_chapter_id]["stages"]["S6A"]["status"]
        if current_status == "gate_failed":
            transition_stage(book_root, "S6A", "pending", current_chapter_id, note="AG-AS asset collection rerun requested.")
            transition_stage(book_root, "S6A", "in_progress", current_chapter_id, note="AG-AS asset collection restarted.")
        elif current_status != "completed":
            transition_stage(book_root, "S6A", "in_progress", current_chapter_id, note="AG-AS asset collection handoff started.")

        contract = resolve_stage_contract(book_id, book_root, "S6A", current_chapter_id)
        visual_plan = read_json(Path(contract["inputs"][1]), default=None)
        if visual_plan is None:
            raise FileNotFoundError(f"Missing visual plan for {current_chapter_id}")
        reference_entries = _chapter_reference_entries(reference_index, current_chapter_id)
        image_items = _chapter_image_items(image_manifest, current_chapter_id)
        asset_requests = _asset_request_rows(book_root, chapter, visual_plan, reference_entries, image_items)
        manifest = _render_asset_collection_manifest(book_id, chapter, visual_plan, asset_requests)
        handoff_text = _render_asset_collection_handoff(chapter, manifest)

        manifest_path = Path(contract["outputs"][0])
        handoff_path = Path(contract["outputs"][1])
        write_json(manifest_path, manifest)
        write_text(handoff_path, handoff_text)

        update_chapter_memory(
            book_root,
            current_chapter_id,
            summary=f"Offline asset collection handoff ready for {chapter['title']}",
            claims=[
                "Appendix ref, target filename, and target directory were locked for every anchor-level asset request.",
                "Offline-cleared assets can now be dropped into the canonical cleared asset directory.",
            ],
            citations_summary=[item["appendix_ref_id"] for item in asset_requests],
            unresolved_issues=[
                f"offline_asset_pending:{item['anchor_id']}"
                for item in asset_requests
                if item["collection_required"] and item["binding_status"] != "cleared_file_detected"
            ],
            visual_notes=[item["anchor_id"] for item in asset_requests],
        )

        gate_result = evaluate_gate(book_id, book_root, "S6A", current_chapter_id)
        if not gate_result["passed"]:
            transition_stage(book_root, "S6A", "gate_failed", current_chapter_id, note=json.dumps(gate_result, ensure_ascii=False))
            results.append(
                {
                    "chapter_id": current_chapter_id,
                    "status": "gate_failed",
                    "gate_result": gate_result,
                }
            )
            continue

        transition_stage(book_root, "S6A", "completed", current_chapter_id, note="AG-AS asset collection handoff completed.")
        results.append(
            {
                "chapter_id": current_chapter_id,
                "status": "completed",
                "outputs": [str(manifest_path), str(handoff_path)],
                "offline_asset_request_count": sum(1 for item in asset_requests if item["collection_required"]),
                "cleared_asset_count": sum(1 for item in asset_requests if item["binding_status"] == "cleared_file_detected"),
                "gate_result": gate_result,
            }
        )

    work_order = issue_work_order(book_id, book_root)
    return {
        "stage_id": "S6A",
        "requested_chapters": target_chapters,
        "results": results,
        "work_order": {
            "order_id": work_order["order_id"],
            "priority_queue_size": len(work_order["priority_queue"]),
            "first_items": work_order["priority_queue"][:5],
        },
    }
