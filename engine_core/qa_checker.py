from __future__ import annotations

"""SQA / AG-QA — Publication Quality Assurance

Pre-publication gate that aggregates quality signals from all chapters and
produces a go/no-go clearance decision before S9 publication build.

Checks performed:
  1. manuscript_completeness   — every chapter has a draft5 (or draft6) file
  2. anchor_slot_clean         — no [ANCHOR_SLOT:] tokens remain in publication drafts
  3. meta_block_clean          — no <!-- META_BLOCK --> residue in publication drafts
  4. word_count_floor_met      — each chapter meets its S4 minimum word count floor
  5. image_asset_clearance     — image_manifest items are cleared or documented pending
  6. reference_index_complete  — reference_index has entries for all chapters
  7. stage_pipeline_ready      — all chapters at S8+ completed (S8A optional)

Output artifacts:
  publication/qa/publication_clearance_report.json  — machine-readable verdict
  publication/qa/qa_report.md                       — human-readable report
"""

from pathlib import Path
from typing import Any

from .book_state import CHAPTER_STAGE_SEQUENCE, load_book_db
from .common import count_words, ensure_dir, now_iso, read_json, write_json, write_text
from .contracts import resolve_stage_contract
from .gates import evaluate_gate
from .manuscript_integrity import find_meta_block_residue
from .stage import transition_stage
from .work_order import issue_work_order


# ---------------------------------------------------------------------------
# Thresholds
# ---------------------------------------------------------------------------

_MIN_WORD_FLOOR = 300          # absolute minimum if WORD_TARGETS.json is missing
_REQUIRED_CHAPTER_STAGE = "S8"  # chapters must reach at least this stage
_OPTIONAL_CHAPTER_STAGE = "S8A" # completing this counts as "enhanced"


# ---------------------------------------------------------------------------
# Individual checks
# ---------------------------------------------------------------------------

def _check_manuscript_completeness(
    book_root: Path, chapter_sequence: list[str]
) -> dict[str, Any]:
    missing: list[str] = []
    sources: dict[str, str] = {}
    for chapter_id in chapter_sequence:
        draft6 = book_root / "manuscripts" / "_draft6" / f"{chapter_id}_draft6.md"
        draft5 = book_root / "manuscripts" / "_draft5" / f"{chapter_id}_draft5.md"
        if draft6.exists():
            sources[chapter_id] = "draft6"
        elif draft5.exists():
            sources[chapter_id] = "draft5"
        else:
            missing.append(chapter_id)
    return {
        "check": "manuscript_completeness",
        "passed": not missing,
        "missing_chapters": missing,
        "sources": sources,
        "detail": f"{len(chapter_sequence) - len(missing)}/{len(chapter_sequence)} chapters have publication drafts",
    }


def _check_anchor_slot_clean(
    book_root: Path, chapter_sequence: list[str]
) -> dict[str, Any]:
    dirty: list[str] = []
    for chapter_id in chapter_sequence:
        for stage_dir, suffix in [("_draft6", "_draft6.md"), ("_draft5", "_draft5.md")]:
            path = book_root / "manuscripts" / stage_dir / f"{chapter_id}{suffix}"
            if path.exists():
                text = path.read_text(encoding="utf-8")
                if "[ANCHOR_SLOT:" in text:
                    dirty.append(chapter_id)
                break
    return {
        "check": "anchor_slot_clean",
        "passed": not dirty,
        "dirty_chapters": dirty,
        "detail": f"{len(dirty)} chapter(s) contain unresolved [ANCHOR_SLOT:] tokens",
    }


def _check_meta_block_clean(
    book_root: Path, chapter_sequence: list[str]
) -> dict[str, Any]:
    dirty: list[dict[str, Any]] = []
    for chapter_id in chapter_sequence:
        for stage_dir, suffix in [("_draft6", "_draft6.md"), ("_draft5", "_draft5.md")]:
            path = book_root / "manuscripts" / stage_dir / f"{chapter_id}{suffix}"
            if path.exists():
                text = path.read_text(encoding="utf-8")
                result = find_meta_block_residue(text)
                if result["meta_block_count"] > 0:
                    dirty.append({
                        "chapter_id": chapter_id,
                        "meta_block_count": result["meta_block_count"],
                        "meta_block_ids": result["meta_block_ids"],
                    })
                break
    return {
        "check": "meta_block_clean",
        "passed": not dirty,
        "dirty_chapters": dirty,
        "detail": f"{len(dirty)} chapter(s) contain META_BLOCK residue",
    }


def _check_word_count_floors(
    book_root: Path, chapter_sequence: list[str], word_targets: dict[str, Any]
) -> dict[str, Any]:
    below_floor: list[dict[str, Any]] = []
    chapter_targets = {ch["chapter_id"]: ch for ch in word_targets.get("chapters", [])}

    for chapter_id in chapter_sequence:
        floor = _MIN_WORD_FLOOR
        target_entry = chapter_targets.get(chapter_id, {})
        floors = target_entry.get("stage_progress_floors", {})
        floor = floors.get("S4_draft1_min_words", floor)

        # Find best available draft
        text = None
        for stage_dir, suffix in [("_draft6", "_draft6.md"), ("_draft5", "_draft5.md")]:
            path = book_root / "manuscripts" / stage_dir / f"{chapter_id}{suffix}"
            if path.exists():
                text = path.read_text(encoding="utf-8")
                break

        measured = count_words(text) if text else 0
        if measured < floor:
            below_floor.append({
                "chapter_id": chapter_id,
                "measured_words": measured,
                "floor": floor,
            })

    return {
        "check": "word_count_floor_met",
        "passed": not below_floor,
        "below_floor": below_floor,
        "detail": f"{len(below_floor)} chapter(s) below minimum word count floor",
    }


def _check_image_asset_clearance(
    book_root: Path, chapter_sequence: list[str], image_manifest: dict[str, Any]
) -> dict[str, Any]:
    items = image_manifest.get("items", []) if isinstance(image_manifest, dict) else []
    chapter_items = [i for i in items if i.get("chapter_id") in set(chapter_sequence)]

    uncleared: list[dict[str, Any]] = []
    for item in chapter_items:
        source_mode = item.get("source_mode", "")
        ingestion_source = item.get("ingestion_source", "")
        status = item.get("ingestion_status", "pending")
        rights = item.get("rights_status", "")

        # engine-rendered visuals (eng) are handled in S7, skip
        if ingestion_source == "eng" or source_mode not in {
            "external_image", "ai_generated_image", "video_embed", "technical_asset"
        }:
            continue

        if status not in {"cleared"} or rights not in {"cleared", "public_domain", "ai_generated_ok"}:
            uncleared.append({
                "anchor_id": item.get("anchor_id"),
                "chapter_id": item.get("chapter_id"),
                "ingestion_status": status,
                "rights_status": rights,
            })

    return {
        "check": "image_asset_clearance",
        "passed": not uncleared,
        "uncleared_assets": uncleared,
        "total_image_items": len(chapter_items),
        "detail": f"{len(uncleared)} image asset(s) not fully cleared",
    }


def _check_reference_index_complete(
    book_root: Path, chapter_sequence: list[str], reference_index: dict[str, Any]
) -> dict[str, Any]:
    if not isinstance(reference_index, dict):
        return {
            "check": "reference_index_complete",
            "passed": False,
            "detail": "reference_index.json missing or invalid",
            "missing_chapters": chapter_sequence,
        }
    indexed_chapters = {ch.get("chapter_id") for ch in reference_index.get("chapters", [])}
    missing = [cid for cid in chapter_sequence if cid not in indexed_chapters]
    return {
        "check": "reference_index_complete",
        "passed": not missing,
        "missing_chapters": missing,
        "detail": f"{len(chapter_sequence) - len(missing)}/{len(chapter_sequence)} chapters indexed",
    }


def _check_stage_pipeline_ready(
    book_root: Path, chapter_sequence: list[str], book_db: dict[str, Any]
) -> dict[str, Any]:
    not_ready: list[dict[str, Any]] = []
    enhanced: list[str] = []

    for chapter_id in chapter_sequence:
        stages = book_db["chapters"][chapter_id]["stages"]
        required_status = stages.get(_REQUIRED_CHAPTER_STAGE, {}).get("status")
        optional_status = stages.get(_OPTIONAL_CHAPTER_STAGE, {}).get("status")

        if required_status != "completed":
            not_ready.append({
                "chapter_id": chapter_id,
                "required_stage": _REQUIRED_CHAPTER_STAGE,
                "status": required_status,
            })
        elif optional_status == "completed":
            enhanced.append(chapter_id)

    return {
        "check": "stage_pipeline_ready",
        "passed": not not_ready,
        "not_ready": not_ready,
        "enhanced_chapters": enhanced,
        "detail": (
            f"{len(chapter_sequence) - len(not_ready)}/{len(chapter_sequence)} chapters at S8+; "
            f"{len(enhanced)} with S8A polish"
        ),
    }


# ---------------------------------------------------------------------------
# Aggregator
# ---------------------------------------------------------------------------

def _run_all_checks(
    book_id: str, book_root: Path
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    book_db = load_book_db(book_root)
    chapter_sequence: list[str] = book_db.get("chapter_sequence", [])

    word_targets = read_json(book_root / "_master" / "WORD_TARGETS.json", default={}) or {}
    image_manifest = read_json(book_root / "research" / "image_manifest.json", default={}) or {}
    reference_index = read_json(book_root / "research" / "reference_index.json", default={}) or {}

    checks = [
        _check_manuscript_completeness(book_root, chapter_sequence),
        _check_anchor_slot_clean(book_root, chapter_sequence),
        _check_meta_block_clean(book_root, chapter_sequence),
        _check_word_count_floors(book_root, chapter_sequence, word_targets),
        _check_image_asset_clearance(book_root, chapter_sequence, image_manifest),
        _check_reference_index_complete(book_root, chapter_sequence, reference_index),
        _check_stage_pipeline_ready(book_root, chapter_sequence, book_db),
    ]

    passed_count = sum(1 for c in checks if c["passed"])
    failed_checks = [c["check"] for c in checks if not c["passed"]]
    overall_pass = not failed_checks

    meta = {
        "chapter_count": len(chapter_sequence),
        "checks_total": len(checks),
        "checks_passed": passed_count,
        "checks_failed": len(failed_checks),
        "failed_checks": failed_checks,
        "verdict": "PASS" if overall_pass else "FAIL",
        "overall_pass": overall_pass,
    }
    return checks, meta


# ---------------------------------------------------------------------------
# Report renderers
# ---------------------------------------------------------------------------

def _render_clearance_report(
    book_id: str, checks: list[dict[str, Any]], meta: dict[str, Any]
) -> dict[str, Any]:
    return {
        "version": "1.0",
        "generated_at": now_iso(),
        "book_id": book_id,
        "stage_id": "SQA",
        **meta,
        "checks": checks,
    }


def _render_qa_report_md(
    book_id: str, checks: list[dict[str, Any]], meta: dict[str, Any]
) -> str:
    verdict_emoji = "✅" if meta["overall_pass"] else "❌"
    lines = [
        f"# QA Report — {book_id}",
        "",
        f"- Generated: `{now_iso()}`",
        f"- Stage: `SQA / AG-QA`",
        f"- Verdict: **{meta['verdict']}** {verdict_emoji}",
        f"- Checks: {meta['checks_passed']}/{meta['checks_total']} passed",
        "",
        "## Check Results",
        "",
        "| Check | Status | Detail |",
        "| --- | --- | --- |",
    ]
    for check in checks:
        status = "✅ PASS" if check["passed"] else "❌ FAIL"
        detail = check.get("detail", "")
        lines.append(f"| `{check['check']}` | {status} | {detail} |")

    if meta["failed_checks"]:
        lines.extend([
            "",
            "## Failed Checks — Action Required",
            "",
        ])
        for check in checks:
            if check["passed"]:
                continue
            lines.append(f"### `{check['check']}`")
            lines.append(f"> {check.get('detail', '')}")
            lines.append("")
            for key, val in check.items():
                if key in {"check", "passed", "detail"}:
                    continue
                if isinstance(val, list) and val:
                    lines.append(f"**{key}:**")
                    for item in val[:10]:
                        lines.append(f"- {item}")
                elif val:
                    lines.append(f"**{key}:** {val}")
            lines.append("")

    lines.extend([
        "## Gate Decision",
        "",
        f"**`publication_clearance`**: {'PASS — ready for S9 publication build' if meta['overall_pass'] else 'FAIL — resolve issues above before running S9'}",
        "",
    ])
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------

def run_publication_qa(
    book_id: str,
    book_root: Path,
    chapter_id: str | None = None,  # unused, kept for uniform handler signature
) -> dict[str, Any]:
    """Run all QA checks and produce clearance report + markdown report."""
    book_db = load_book_db(book_root)
    current_status = book_db.get("book_level_stages", {}).get("SQA", {}).get("status", "pending")

    if current_status == "gate_failed":
        transition_stage(book_root, "SQA", "pending", note="AG-QA QA rerun requested.")
        transition_stage(book_root, "SQA", "in_progress", note="AG-QA QA restarted.")
    elif current_status != "completed":
        transition_stage(book_root, "SQA", "in_progress", note="AG-QA QA started.")

    checks, meta = _run_all_checks(book_id, book_root)

    clearance_report = _render_clearance_report(book_id, checks, meta)
    qa_report_md = _render_qa_report_md(book_id, checks, meta)

    qa_dir = ensure_dir(book_root / "publication" / "qa")
    report_path = qa_dir / "publication_clearance_report.json"
    md_path = qa_dir / "qa_report.md"
    write_json(report_path, clearance_report)
    write_text(md_path, qa_report_md)

    gate_result = evaluate_gate(book_id, book_root, "SQA")
    if not gate_result["passed"]:
        transition_stage(
            book_root, "SQA", "gate_failed",
            note=f"QA FAIL: {meta['failed_checks']}"
        )
        return {
            "stage_id": "SQA",
            "status": "gate_failed",
            "verdict": meta["verdict"],
            "failed_checks": meta["failed_checks"],
            "report_path": str(report_path),
            "md_path": str(md_path),
            "gate_result": gate_result,
        }

    transition_stage(book_root, "SQA", "completed", note="AG-QA QA clearance passed.")
    work_order = issue_work_order(book_id, book_root)
    return {
        "stage_id": "SQA",
        "status": "completed",
        "verdict": meta["verdict"],
        "checks_passed": meta["checks_passed"],
        "checks_total": meta["checks_total"],
        "report_path": str(report_path),
        "md_path": str(md_path),
        "gate_result": gate_result,
        "work_order": {
            "order_id": work_order["order_id"],
            "priority_queue_size": len(work_order["priority_queue"]),
        },
    }
