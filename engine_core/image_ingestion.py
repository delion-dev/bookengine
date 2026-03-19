from __future__ import annotations

"""S6B Image Asset Ingestion — AG-IM

Processes ext/usr/ai source images that were placed into the ingested/ staging
directories during the offline asset collection round, registers cleared copies,
writes per-anchor provenance JSON, and updates image_manifest.json.

eng-type assets (table/chart/SVG rendered by the engine) are NOT processed here;
they are handled automatically in S7.
"""

import shutil
from pathlib import Path
from typing import Any

from .book_state import load_book_db
from .common import ensure_dir, now_iso, read_json, write_json
from .contracts import resolve_stage_contract, validate_inputs
from .gates import evaluate_gate
from .memory import update_chapter_memory
from .stage import transition_stage
from .work_order import issue_work_order


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

_INGESTION_SOURCE_DIRS = ("ext", "usr", "ai")
_ALLOWED_EXTENSIONS = {".jpg", ".jpeg", ".png", ".webp", ".svg"}

# source_mode values that require offline asset collection
_COLLECTION_REQUIRED_MODES = {"external_image", "ai_generated_image", "video_embed", "technical_asset"}


# ---------------------------------------------------------------------------
# Internal helpers — chapter selection
# ---------------------------------------------------------------------------

def _pending_s6b_chapters(book_root: Path) -> list[str]:
    payload = load_book_db(book_root)
    return [
        chapter_id
        for chapter_id in payload["chapter_sequence"]
        if payload["chapters"][chapter_id]["stages"].get("S6B", {}).get("status") in {
            "pending", "in_progress", "gate_failed"
        }
    ]


# ---------------------------------------------------------------------------
# Internal helpers — ingested file discovery
# ---------------------------------------------------------------------------

def _scan_ingested_dir(ingested_chapter_root: Path) -> dict[str, list[Path]]:
    """Return {source_code: [file_path, ...]} for all files under ingested/{chapter}/."""
    found: dict[str, list[Path]] = {src: [] for src in _INGESTION_SOURCE_DIRS}
    for src in _INGESTION_SOURCE_DIRS:
        src_dir = ingested_chapter_root / src
        if src_dir.is_dir():
            found[src] = sorted(
                p for p in src_dir.iterdir()
                if p.is_file() and p.suffix.lower() in _ALLOWED_EXTENSIONS
            )
    return found


def _match_anchor_to_ingested(
    anchor_id: str,
    source_dir_files: list[Path],
) -> Path | None:
    """Return the first ingested file whose name starts with anchor_id."""
    for path in source_dir_files:
        if path.name.startswith(anchor_id):
            return path
    return None


# ---------------------------------------------------------------------------
# Internal helpers — cleared asset registration
# ---------------------------------------------------------------------------

def _cleared_filename(anchor_id: str, ext: str) -> str:
    """Derive ASSET_{CHAPTER}_{TYPE}_{SEQ}_v001.ext from anchor_id."""
    parts = anchor_id.split("_")
    if len(parts) >= 3:
        chapter = parts[0]
        anchor_type = parts[1]
        seq = parts[2]
        return f"ASSET_{chapter}_{anchor_type}_{seq}_v001{ext}"
    return f"ASSET_{anchor_id}_v001{ext}"


def _copy_to_cleared(
    src_file: Path,
    cleared_dir: Path,
    anchor_id: str,
) -> Path:
    """Copy ingested file to cleared/ with canonical naming. Returns cleared path."""
    dest_name = _cleared_filename(anchor_id, src_file.suffix.lower())
    dest = ensure_dir(cleared_dir) / dest_name
    if not dest.exists():
        shutil.copy2(src_file, dest)
    return dest


# ---------------------------------------------------------------------------
# Internal helpers — provenance JSON
# ---------------------------------------------------------------------------

def _build_provenance(
    anchor_id: str,
    ingestion_source: str,
    cleared_path: str,
    ingested_path: str,
    asset_request: dict[str, Any],
    image_item: dict[str, Any],
) -> dict[str, Any]:
    caption = asset_request.get("caption", "")
    rights_status = image_item.get("rights_status") or asset_request.get("rights_status", "")
    source_block: dict[str, Any] = {}
    if ingestion_source == "ext":
        source_block = {
            "url": image_item.get("provenance", {}).get("ext", {}).get("url", ""),
            "site_name": image_item.get("provenance", {}).get("ext", {}).get("site_name", ""),
            "retrieved_at": image_item.get("provenance", {}).get("ext", {}).get("retrieved_at", ""),
            "rights_note": image_item.get("provenance", {}).get("ext", {}).get("rights_note", ""),
            "clearance_status": image_item.get("provenance", {}).get("ext", {}).get("clearance_status", "permission_required"),
            "clearance_evidence": image_item.get("provenance", {}).get("ext", {}).get("clearance_evidence", ""),
        }
    elif ingestion_source == "usr":
        source_block = {
            "original_filename": image_item.get("provenance", {}).get("usr", {}).get("original_filename", ""),
            "upload_session": image_item.get("provenance", {}).get("usr", {}).get("upload_session", ""),
            "user_rights_declaration": image_item.get("provenance", {}).get("usr", {}).get("user_rights_declaration", "owned"),
            "usage_note": image_item.get("provenance", {}).get("usr", {}).get("usage_note", ""),
        }
    elif ingestion_source == "ai":
        source_block = {
            "model": image_item.get("provenance", {}).get("ai", {}).get("model", ""),
            "prompt_summary": image_item.get("provenance", {}).get("ai", {}).get("prompt_summary", ""),
            "prompt_full": image_item.get("provenance", {}).get("ai", {}).get("prompt_full", ""),
            "generation_session": image_item.get("provenance", {}).get("ai", {}).get("generation_session", now_iso()),
            "revision": image_item.get("provenance", {}).get("ai", {}).get("revision", 1),
            "likeness_review": image_item.get("provenance", {}).get("ai", {}).get("likeness_review", "needs_review"),
            "trademark_review": image_item.get("provenance", {}).get("ai", {}).get("trademark_review", "needs_review"),
            "usage_note": image_item.get("provenance", {}).get("ai", {}).get("usage_note", ""),
        }

    return {
        "version": "1.0",
        "generated_at": now_iso(),
        "anchor_id": anchor_id,
        "ingestion_source": ingestion_source,
        "ingested_path": ingested_path,
        "cleared_path": cleared_path,
        "appendix_ref_id": asset_request.get("appendix_ref_id", ""),
        "caption": caption,
        "rights_status": rights_status or ("ai_generated_ok" if ingestion_source == "ai" else "permission_required"),
        "provenance_complete": bool(source_block),
        ingestion_source: source_block,
    }


# ---------------------------------------------------------------------------
# Internal helpers — image_manifest update
# ---------------------------------------------------------------------------

def _update_manifest_item(
    item: dict[str, Any],
    ingestion_source: str,
    ingested_path: str,
    cleared_path: str,
    provenance_path: str,
) -> None:
    """Mutate image_manifest item in-place with cleared status."""
    item["ingestion_source"] = ingestion_source
    item["ingestion_status"] = "cleared"
    item["ingested_path"] = ingested_path
    item["cleared_path"] = cleared_path
    item["provenance_path"] = provenance_path
    item["provenance_complete"] = True
    if ingestion_source == "ai":
        item["rights_status"] = "ai_generated_ok"
    elif item.get("rights_status") not in {"cleared", "public_domain", "ai_generated_ok"}:
        item["rights_status"] = "permission_required"


# ---------------------------------------------------------------------------
# Main per-chapter processing
# ---------------------------------------------------------------------------

def _process_chapter(
    book_id: str,
    book_root: Path,
    chapter_id: str,
    asset_collection_manifest: dict[str, Any],
    image_manifest: dict[str, Any],
) -> dict[str, Any]:
    ingested_chapter_root = book_root / "publication" / "assets" / "ingested" / chapter_id
    cleared_dir = ensure_dir(book_root / "publication" / "assets" / "cleared" / chapter_id)

    ingested_files = _scan_ingested_dir(ingested_chapter_root)

    asset_requests: list[dict[str, Any]] = asset_collection_manifest.get("asset_requests", [])
    image_items_by_anchor = {
        item.get("anchor_id"): item
        for item in image_manifest.get("items", [])
        if item.get("chapter_id") == chapter_id
    }

    processed: list[dict[str, Any]] = []
    pending: list[str] = []
    errors: list[str] = []

    for req in asset_requests:
        anchor_id: str = req.get("anchor_id") or ""
        source_mode: str = req.get("source_mode") or ""

        if source_mode not in _COLLECTION_REQUIRED_MODES:
            # eng-type or pipeline-only: skip
            continue

        # Determine ingestion_source from asset_mode / source_mode
        if source_mode == "ai_generated_image":
            candidate_sources = ["ai"]
        else:
            candidate_sources = ["ext", "usr"]

        matched_src_code: str | None = None
        matched_file: Path | None = None
        for src_code in candidate_sources:
            f = _match_anchor_to_ingested(anchor_id, ingested_files.get(src_code, []))
            if f:
                matched_src_code = src_code
                matched_file = f
                break

        image_item = image_items_by_anchor.get(anchor_id, {})

        if matched_file is None:
            # Check if a cleared file already exists (pre-placed by user)
            existing_cleared = sorted(cleared_dir.glob(f"ASSET_{anchor_id.replace('_', '_', 2)}_v*.* "))
            existing_cleared = sorted(cleared_dir.glob(f"ASSET_*_v001.*"))
            # Try a more targeted search
            parts = anchor_id.split("_")
            if len(parts) >= 3:
                stub = f"ASSET_{parts[0]}_{parts[1]}_{parts[2]}_v"
                existing_cleared = sorted(cleared_dir.glob(f"{stub}*.*"))
            else:
                existing_cleared = []

            if existing_cleared:
                # Already cleared from a previous run or manual placement
                cleared_path = str(existing_cleared[0])
                prov_path = str(cleared_dir / f"{anchor_id}_provenance.json")
                if not Path(prov_path).exists():
                    ingestion_source = "ext"
                    prov = _build_provenance(
                        anchor_id, ingestion_source, cleared_path, "", req, image_item
                    )
                    write_json(Path(prov_path), prov)
                if image_item:
                    _update_manifest_item(image_item, "ext", "", cleared_path, prov_path)
                processed.append({
                    "anchor_id": anchor_id,
                    "status": "cleared_pre_existing",
                    "cleared_path": cleared_path,
                })
            else:
                pending.append(anchor_id)
                if image_item and image_item.get("ingestion_status") not in {"cleared"}:
                    image_item["ingestion_status"] = "pending"
            continue

        # Copy to cleared/
        try:
            cleared_file = _copy_to_cleared(matched_file, cleared_dir, anchor_id)
            ingested_rel = str(matched_file.relative_to(book_root)).replace("\\", "/")
            cleared_rel = str(cleared_file.relative_to(book_root)).replace("\\", "/")
            prov_path = str(cleared_dir / f"{anchor_id}_provenance.json")

            prov = _build_provenance(
                anchor_id,
                matched_src_code,
                cleared_rel,
                ingested_rel,
                req,
                image_item,
            )
            write_json(Path(prov_path), prov)

            if image_item:
                _update_manifest_item(
                    image_item, matched_src_code, ingested_rel, cleared_rel, prov_path
                )

            processed.append({
                "anchor_id": anchor_id,
                "ingestion_source": matched_src_code,
                "ingested_path": ingested_rel,
                "cleared_path": cleared_rel,
                "provenance_path": prov_path,
                "status": "cleared",
            })
        except Exception as exc:
            errors.append(f"{anchor_id}: {exc}")

    return {
        "chapter_id": chapter_id,
        "processed_count": len(processed),
        "pending_count": len(pending),
        "error_count": len(errors),
        "processed": processed,
        "pending_anchor_ids": pending,
        "errors": errors,
    }


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------

def run_image_ingestion(
    book_id: str,
    book_root: Path,
    chapter_id: str | None = None,
) -> dict[str, Any]:
    image_manifest_path = book_root / "research" / "image_manifest.json"
    image_manifest = read_json(image_manifest_path, default=None)
    if image_manifest is None:
        raise FileNotFoundError("S6B requires research/image_manifest.json.")

    book_db = load_book_db(book_root)
    target_chapters = [chapter_id] if chapter_id else _pending_s6b_chapters(book_root)
    if not target_chapters:
        return {
            "stage_id": "S6B",
            "status": "no_op",
            "message": "No pending S6B chapters found.",
        }

    results: list[dict[str, Any]] = []

    for current_chapter_id in target_chapters:
        contract_status = validate_inputs(book_id, book_root, "S6B", current_chapter_id)
        if not contract_status["valid"]:
            raise FileNotFoundError(
                f"S6B inputs missing for {current_chapter_id}: {contract_status['missing_inputs']}"
            )

        current_status = book_db["chapters"][current_chapter_id]["stages"].get("S6B", {}).get("status", "pending")
        if current_status == "gate_failed":
            transition_stage(book_root, "S6B", "pending", current_chapter_id, note="AG-IM image ingestion rerun requested.")
            transition_stage(book_root, "S6B", "in_progress", current_chapter_id, note="AG-IM image ingestion restarted.")
        elif current_status != "completed":
            transition_stage(book_root, "S6B", "in_progress", current_chapter_id, note="AG-IM image ingestion started.")

        contract = resolve_stage_contract(book_id, book_root, "S6B", current_chapter_id)
        asset_collection_manifest = read_json(Path(contract["inputs"][0]), default=None)
        if asset_collection_manifest is None:
            raise FileNotFoundError(
                f"S6B missing asset_collection_manifest for {current_chapter_id}: {contract['inputs'][0]}"
            )

        chapter_result = _process_chapter(
            book_id, book_root, current_chapter_id, asset_collection_manifest, image_manifest
        )

        # Write ingestion_report.json (contract output[2])
        report = {
            "version": "1.0",
            "generated_at": now_iso(),
            "book_id": book_id,
            "stage_id": "S6B",
            "chapter_id": current_chapter_id,
            "processed_count": chapter_result["processed_count"],
            "pending_count": chapter_result["pending_count"],
            "error_count": chapter_result["error_count"],
            "processed": chapter_result["processed"],
            "pending_anchor_ids": chapter_result["pending_anchor_ids"],
            "errors": chapter_result["errors"],
        }
        report_path = Path(contract["outputs"][2])
        write_json(report_path, report)

        # Persist updated image_manifest (mutations were in-place)
        write_json(image_manifest_path, image_manifest)

        update_chapter_memory(
            book_root,
            current_chapter_id,
            summary=f"S6B image ingestion: {chapter_result['processed_count']} cleared, {chapter_result['pending_count']} pending",
            claims=[
                f"Cleared {chapter_result['processed_count']} image asset(s) with provenance records.",
                f"{chapter_result['pending_count']} anchor(s) still awaiting offline asset files.",
            ],
            citations_summary=[],
            unresolved_issues=[
                f"image_asset_pending:{aid}" for aid in chapter_result["pending_anchor_ids"]
            ],
            visual_notes=[item["anchor_id"] for item in chapter_result["processed"]],
        )

        gate_result = evaluate_gate(book_id, book_root, "S6B", current_chapter_id)
        if not gate_result["passed"]:
            transition_stage(
                book_root, "S6B", "gate_failed", current_chapter_id,
                note=f"ingested={chapter_result['processed_count']} pending={chapter_result['pending_count']}"
            )
            results.append({
                "chapter_id": current_chapter_id,
                "status": "gate_failed",
                "chapter_result": chapter_result,
                "gate_result": gate_result,
            })
            continue

        transition_stage(book_root, "S6B", "completed", current_chapter_id, note="AG-IM image ingestion completed.")
        results.append({
            "chapter_id": current_chapter_id,
            "status": "completed",
            "chapter_result": chapter_result,
            "gate_result": gate_result,
        })

    work_order = issue_work_order(book_id, book_root)
    return {
        "stage_id": "S6B",
        "requested_chapters": target_chapters,
        "results": results,
        "work_order": {
            "order_id": work_order["order_id"],
            "priority_queue_size": len(work_order["priority_queue"]),
            "first_items": work_order["priority_queue"][:5],
        },
    }
