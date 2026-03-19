from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from .anchor_scope import anchor_scope_integrity, strip_anchor_blocks
from .anchors import inject_anchor_blocks
from .book_state import load_book_db
from .common import now_iso, read_json, read_text, write_json, write_text
from .contracts import resolve_stage_contract, validate_inputs
from .gates import evaluate_gate
from .memory import update_chapter_memory
from .stage import transition_stage
from .work_order import issue_work_order


def _s4a_output_bundle(book_id: str, book_root: Path, chapter_id: str) -> dict[str, str]:
    outputs = resolve_stage_contract(book_id, book_root, "S4A", chapter_id)["outputs"]
    return {
        "draft1": outputs[0],
        "anchor_injection_report": outputs[1],
        "anchor_scope_report": outputs[2],
    }


def _missing_s4a_outputs(book_id: str, book_root: Path, chapter_id: str) -> list[str]:
    bundle = _s4a_output_bundle(book_id, book_root, chapter_id)
    return [path for path in bundle.values() if not Path(path).exists()]


def _pending_s4a_chapters(book_id: str, book_root: Path) -> list[str]:
    payload = load_book_db(book_root)
    return [
        chapter_id
        for chapter_id in payload["chapter_sequence"]
        if payload["chapters"][chapter_id]["stages"]["S4A"]["status"] in {"pending", "in_progress", "gate_failed"}
        or (
            payload["chapters"][chapter_id]["stages"]["S4A"]["status"] == "completed"
            and bool(_missing_s4a_outputs(book_id, book_root, chapter_id))
        )
    ]


def _all_s4a_chapters(book_root: Path) -> list[str]:
    payload = load_book_db(book_root)
    return list(payload["chapter_sequence"])


def _promote_anchor_ready_heading(prose_text: str) -> str:
    lines = prose_text.splitlines()
    if lines and lines[0].startswith("# DRAFT1_PROSE"):
        if ":" in lines[0]:
            _, suffix = lines[0].split(":", 1)
            lines[0] = f"# DRAFT1:{suffix}"
        else:
            lines[0] = "# DRAFT1"
    return "\n".join(lines).rstrip() + "\n"


def _anchor_injection_report(
    chapter: dict[str, Any],
    prose_path: Path,
    draft1_path: Path,
    anchor_plan: dict[str, Any],
) -> dict[str, Any]:
    anchors = anchor_plan.get("anchors", []) if isinstance(anchor_plan, dict) else []
    return {
        "version": "1.0",
        "generated_at": now_iso(),
        "stage_id": "S4A",
        "chapter_id": chapter["chapter_id"],
        "chapter_title": chapter["title"],
        "source_prose_path": str(prose_path),
        "output_draft1_path": str(draft1_path),
        "anchor_count": len(anchors),
        "anchor_ids": [anchor.get("anchor_id") for anchor in anchors],
        "anchor_types": sorted({anchor.get("anchor_type") for anchor in anchors if anchor.get("anchor_type")}),
    }


def _anchor_scope_report(
    chapter: dict[str, Any],
    integrity: Any,
    *,
    passed: bool,
) -> dict[str, Any]:
    return {
        "version": "1.0",
        "generated_at": now_iso(),
        "stage_id": "S4A",
        "chapter_id": chapter["chapter_id"],
        "chapter_title": chapter["title"],
        "passed": passed,
        "before_anchor_count": integrity.before_anchor_count,
        "after_anchor_count": integrity.after_anchor_count,
        "non_anchor_sha1_before": integrity.non_anchor_sha1_before,
        "non_anchor_sha1_after": integrity.non_anchor_sha1_after,
        "diff_preview": integrity.diff_preview,
    }


def run_anchor_injection(
    book_id: str,
    book_root: Path,
    chapter_id: str | None = None,
    *,
    rerun_completed: bool = False,
) -> dict[str, Any]:
    book_db = load_book_db(book_root)
    target_chapters = (
        [chapter_id]
        if chapter_id
        else (_all_s4a_chapters(book_root) if rerun_completed else _pending_s4a_chapters(book_id, book_root))
    )
    if not target_chapters:
        return {
            "stage_id": "S4A",
            "status": "no_op",
            "message": "No pending S4A chapters found." if not rerun_completed else "No S4A chapters found for rerun.",
        }

    results = []
    for current_chapter_id in target_chapters:
        contract_status = validate_inputs(book_id, book_root, "S4A", current_chapter_id)
        if not contract_status["valid"]:
            raise FileNotFoundError(f"S4A inputs missing for {current_chapter_id}: {contract_status['missing_inputs']}")

        chapter = {
            "chapter_id": current_chapter_id,
            "title": book_db["chapters"][current_chapter_id]["title"],
            "part": book_db["chapters"][current_chapter_id].get("part"),
        }
        current_status = book_db["chapters"][current_chapter_id]["stages"]["S4A"]["status"]
        if rerun_completed and current_status == "completed":
            transition_stage(
                book_root,
                "S4A",
                "in_progress",
                current_chapter_id,
                note="AG-01B anchor injection full rerun started.",
            )
        elif current_status == "gate_failed":
            transition_stage(
                book_root,
                "S4A",
                "pending",
                current_chapter_id,
                note="AG-01B anchor injection rerun requested.",
            )
            transition_stage(
                book_root,
                "S4A",
                "in_progress",
                current_chapter_id,
                note="AG-01B anchor injection restarted.",
            )
        elif current_status != "completed":
            transition_stage(
                book_root,
                "S4A",
                "in_progress",
                current_chapter_id,
                note="AG-01B anchor injection started.",
            )

        contract = resolve_stage_contract(book_id, book_root, "S4A", current_chapter_id)
        prose_path = Path(contract["inputs"][0])
        anchor_plan = read_json(Path(contract["inputs"][1]), default=None)
        if anchor_plan is None:
            raise FileNotFoundError(f"Missing anchor plan for {current_chapter_id}")
        output_bundle = _s4a_output_bundle(book_id, book_root, current_chapter_id)
        draft1_path = Path(output_bundle["draft1"])
        prose_text = _promote_anchor_ready_heading(read_text(prose_path))
        anchored_text = inject_anchor_blocks(prose_text, anchor_plan)
        integrity = anchor_scope_integrity(prose_text, anchored_text)
        prose_sha_before = strip_anchor_blocks(prose_text)
        prose_sha_after = strip_anchor_blocks(anchored_text)
        scope_passed = (
            prose_sha_before == prose_sha_after
            and integrity.after_anchor_count > 0
        )
        injection_report = _anchor_injection_report(chapter, prose_path, draft1_path, anchor_plan)
        scope_report = _anchor_scope_report(chapter, integrity, passed=scope_passed)

        write_text(draft1_path, anchored_text)
        write_json(Path(output_bundle["anchor_injection_report"]), injection_report)
        write_json(Path(output_bundle["anchor_scope_report"]), scope_report)

        update_chapter_memory(
            book_root,
            current_chapter_id,
            summary=f"Draft1 anchor blocks injected for {chapter['title']}",
            claims=[
                "Canonical anchor blocks were injected into the prose-only draft1 artifact.",
                "Anchor-scope integrity was checked to preserve non-anchor manuscript text.",
            ],
            unresolved_issues=[] if scope_passed else ["anchor_scope_integrity_failed"],
            visual_notes=injection_report["anchor_ids"],
        )

        gate_result = evaluate_gate(book_id, book_root, "S4A", current_chapter_id)
        declared_outputs = list(output_bundle.values())
        if not gate_result["passed"]:
            transition_stage(
                book_root,
                "S4A",
                "gate_failed",
                current_chapter_id,
                note=json.dumps(gate_result, ensure_ascii=False),
            )
            results.append(
                {
                    "chapter_id": current_chapter_id,
                    "status": "gate_failed",
                    "outputs": declared_outputs,
                    "gate_result": gate_result,
                }
            )
            continue

        transition_stage(
            book_root,
            "S4A",
            "completed",
            current_chapter_id,
            note="AG-01B anchor injection completed.",
        )
        results.append(
            {
                "chapter_id": current_chapter_id,
                "status": "completed",
                "outputs": declared_outputs,
                "output": str(draft1_path),
                "gate_result": gate_result,
                "anchor_count": injection_report["anchor_count"],
            }
        )

    work_order = issue_work_order(book_id, book_root)
    return {
        "stage_id": "S4A",
        "requested_chapters": target_chapters,
        "results": results,
        "work_order": {
            "order_id": work_order["order_id"],
            "priority_queue_size": len(work_order["priority_queue"]),
            "first_items": work_order["priority_queue"][:5],
        },
    }
