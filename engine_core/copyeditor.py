from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from functools import lru_cache

from .book_state import load_book_db
from .common import PLATFORM_CORE_ROOT, count_words, read_json, read_text, write_text
from .targets import get_chapter_target
from .contracts import validate_inputs
from .gates import evaluate_gate
from .manuscript_integrity import find_body_meta_markers, find_internal_heading_residue, sanitize_reader_manuscript
from .memory import update_chapter_memory
from .section_labels import SECTION_ORDER, find_section_marker, normalize_section_headings, required_section_markers
from .stage import transition_stage
from .work_order import issue_work_order

REQUIRED_SECTIONS = required_section_markers()


@lru_cache(maxsize=1)
def _load_style_rules() -> dict:
    """Load style red-flags and replacements from style_rules.json. Cached."""
    return read_json(PLATFORM_CORE_ROOT / "style_rules.json", default={}) or {}


def _style_red_flags() -> list[str]:
    return list(_load_style_rules().get("red_flags", ["무조건", "절대", "완벽한", "최고의", "엄청난"]))


def _style_replacements() -> dict[str, str]:
    return dict(_load_style_rules().get("replacements", {
        "무조건": "가급적", "절대": "쉽게", "완벽한": "탄탄한", "최고의": "인상적인", "엄청난": "큰",
    }))


STYLE_RED_FLAGS: list[str] = _style_red_flags()
STYLE_REPLACEMENTS: dict[str, str] = _style_replacements()


def _pending_s8_chapters(book_root: Path) -> list[str]:
    payload = load_book_db(book_root)
    return [
        chapter_id
        for chapter_id in payload["chapter_sequence"]
        if payload["chapters"][chapter_id]["stages"]["S8"]["status"] in {"pending", "in_progress", "gate_failed"}
        or (
            payload["chapters"][chapter_id]["stages"]["S8"]["status"] == "completed"
            and (
                not (book_root / "manuscripts" / "_draft5" / f"{chapter_id}_draft5.md").exists()
                or not (book_root / "manuscripts" / "_draft5" / f"{chapter_id}_proofreading_report.md").exists()
            )
        )
    ]


def _all_s8_chapters(book_root: Path) -> list[str]:
    payload = load_book_db(book_root)
    return [
        chapter_id
        for chapter_id in payload["chapter_sequence"]
        if payload["chapters"][chapter_id]["stages"]["S8"]["status"] in {"completed", "gate_failed"}
    ]


def _normalize_style(text: str) -> str:
    normalized = text
    for source, target in STYLE_REPLACEMENTS.items():
        normalized = normalized.replace(source, target)
    return normalized


def _section_payload(text: str, heading: str) -> str:
    section_key = next((key for key in SECTION_ORDER if find_section_marker(text, key) == heading), None)
    marker = find_section_marker(text, section_key) if section_key else None
    if not marker or marker not in text:
        return ""
    after = text.split(marker, 1)[1]
    next_markers = [find_section_marker(text, key) for key in SECTION_ORDER if key != section_key]
    cut_positions = []
    for next_marker in next_markers:
        if next_marker:
            token = f"\n{next_marker}\n"
            position = after.find(token)
            if position >= 0:
                cut_positions.append(position)
    if cut_positions:
        after = after[: min(cut_positions)]
    return after.strip()


def _structure_checks(text: str) -> dict[str, Any]:
    heading_map = {
        section_key: find_section_marker(text, section_key)
        for section_key in SECTION_ORDER
    }
    missing = [REQUIRED_SECTIONS[index] for index, section_key in enumerate(SECTION_ORDER) if not heading_map[section_key]]
    empty = [
        REQUIRED_SECTIONS[index]
        for index, section_key in enumerate(SECTION_ORDER)
        if heading_map[section_key] and not _section_payload(text, heading_map[section_key])
    ]
    start_count = text.count("<!-- ANCHOR_START")
    end_count = text.count("<!-- ANCHOR_END")
    slot_count = text.count("[ANCHOR_SLOT:")
    return {
        "missing_sections": missing,
        "empty_sections": empty,
        "anchor_start_count": start_count,
        "anchor_end_count": end_count,
        "anchor_slot_count": slot_count,
        "balanced_anchors": start_count == end_count,
        "passed": not missing and not empty and start_count == end_count and slot_count == 0,
    }


def _style_findings(text: str) -> list[str]:
    findings: list[str] = []
    for token in STYLE_RED_FLAGS:
        if token in text:
            findings.append(f"style_red_flag:{token}")
    for heading in find_internal_heading_residue(text):
        findings.append(f"internal_heading_residue:{heading}")
    for marker in find_body_meta_markers(text):
        findings.append(f"body_meta_marker:{marker}")
    if "_이 초고는" in text:
        findings.append("internal_tone_line_residue")
    return findings


def _return_stage(structure: dict[str, Any], style_findings: list[str]) -> str | None:
    if structure["missing_sections"] or structure["empty_sections"]:
        return "S4"
    if not structure["balanced_anchors"] or structure["anchor_slot_count"] > 0:
        return "S7"
    if style_findings:
        return "S8"
    return None


def _render_draft5(draft4: str) -> tuple[str, list[str]]:
    promoted = _normalize_style(draft4)
    cleaned, removed = sanitize_reader_manuscript(promoted, target_label="DRAFT5")
    return normalize_section_headings(cleaned), removed


def _render_proofreading_report(
    chapter: dict[str, Any],
    structure: dict[str, Any],
    style_findings: list[str],
    removed_sections: list[str],
    return_stage: str | None,
    word_count_result: dict[str, Any] | None = None,
) -> str:
    wc = word_count_result or {}
    word_floor_pass = wc.get("floor_passed", True)
    lines = [
        f"# PROOFREADING_REPORT: {chapter['chapter_id']} | {chapter['title']}",
        "",
        "## Verdict",
        "- Copyedit gate: pass" if not return_stage and word_floor_pass else "- Copyedit gate: fail",
        f"- Style issues remaining: {len(style_findings)}",
        f"- Return stage: {return_stage or 'none'}",
        "",
        "## Structure Integrity",
        f"- Missing sections: {', '.join(structure['missing_sections']) if structure['missing_sections'] else 'none'}",
        f"- Empty sections: {', '.join(structure['empty_sections']) if structure['empty_sections'] else 'none'}",
        f"- Anchor start/end balanced: {structure['balanced_anchors']}",
        f"- Anchor slot residues: {structure['anchor_slot_count']}",
        "",
        "## Style Review",
        "- Tone target: editorial travel-culture hybrid",
        "- Style drift markers:",
    ]
    if style_findings:
        for item in style_findings:
            lines.append(f"- {item}")
    else:
        lines.append("- none")

    lines.extend(
        [
            "",
            "## Word Count",
            f"- Measured words: {wc.get('measured', 'n/a')}",
            f"- Floor (S8 final): {wc.get('floor', 'n/a')}",
            f"- Word floor status: {'pass' if word_floor_pass else 'FAIL — below S8 final draft minimum'}",
        ]
    )

    lines.extend(
        [
            "",
            "## Technical Format",
            f"- Internal sections removed: {len(removed_sections)}",
        ]
    )
    for item in removed_sections:
        lines.append(f"- removed {item}")

    lines.extend(
        [
            "",
            "## Return Policy",
            f"- If this stage fails, return to `{return_stage or 'none'}`.",
            "- S4 for missing narrative structure, S7 for visual integration residue, S8 for style drift.",
            "- Word floor failure requires content expansion before S8 can pass.",
        ]
    )
    return "\n".join(lines) + "\n"


def run_copyedit(
    book_id: str,
    book_root: Path,
    chapter_id: str | None = None,
    *,
    rerun_completed: bool = False,
) -> dict[str, Any]:
    style_guide = read_text(book_root / "_master" / "STYLE_GUIDE.md")
    quality_criteria = read_text(book_root / "_master" / "QUALITY_CRITERIA.md")
    if not style_guide or not quality_criteria:
        raise FileNotFoundError("S8 requires STYLE_GUIDE.md and QUALITY_CRITERIA.md.")

    book_db = load_book_db(book_root)
    target_chapters = [chapter_id] if chapter_id else (
        _all_s8_chapters(book_root) if rerun_completed else _pending_s8_chapters(book_root)
    )
    if not target_chapters:
        return {
            "stage_id": "S8",
            "status": "no_op",
            "message": "No pending S8 chapters found.",
        }

    results = []
    for current_chapter_id in target_chapters:
        contract_status = validate_inputs(book_id, book_root, "S8", current_chapter_id)
        if not contract_status["valid"]:
            raise FileNotFoundError(f"S8 inputs missing for {current_chapter_id}: {contract_status['missing_inputs']}")

        chapter = {
            "chapter_id": current_chapter_id,
            "title": book_db["chapters"][current_chapter_id]["title"],
        }
        draft4_path = book_root / "manuscripts" / "_draft4" / f"{current_chapter_id}_draft4.md"
        draft5_path = book_root / "manuscripts" / "_draft5" / f"{current_chapter_id}_draft5.md"
        proofreading_report_path = book_root / "manuscripts" / "_draft5" / f"{current_chapter_id}_proofreading_report.md"
        current_status = book_db["chapters"][current_chapter_id]["stages"]["S8"]["status"]
        missing_outputs = [path for path in (draft5_path, proofreading_report_path) if not path.exists()]
        if current_status == "gate_failed":
            transition_stage(
                book_root,
                "S8",
                "pending",
                current_chapter_id,
                note="AG-05 copyedit rerun requested.",
            )
            transition_stage(
                book_root,
                "S8",
                "in_progress",
                current_chapter_id,
                note="AG-05 copyedit restarted.",
            )
        elif current_status == "completed" and rerun_completed:
            transition_stage(
                book_root,
                "S8",
                "in_progress",
                current_chapter_id,
                note="AG-05 copyedit rerun requested for refreshed draft4.",
            )
        elif current_status != "completed":
            transition_stage(
                book_root,
                "S8",
                "in_progress",
                current_chapter_id,
                note="AG-05 copyedit started.",
            )
        elif missing_outputs:
            transition_stage(
                book_root,
                "S8",
                "in_progress",
                current_chapter_id,
                note="AG-05 copyedit regeneration started from missing outputs.",
            )

        draft4 = read_text(draft4_path)
        draft5, removed_sections = _render_draft5(draft4)
        structure = _structure_checks(draft5)
        style_findings = _style_findings(draft5)
        return_stage = _return_stage(structure, style_findings)

        # Measure word count against S8 final floor — preventive gate at generation time.
        word_targets = read_json(book_root / "_master" / "WORD_TARGETS.json", default={}) or {}
        measured_words = count_words(draft5)
        s8_floor = 180
        try:
            target_entry = get_chapter_target(word_targets, current_chapter_id)
            s8_floor = target_entry.get("stage_progress_floors", {}).get(
                "S8_final_draft_min_words",
                target_entry.get("stage_progress_floors", {}).get("S4_draft1_min_words", s8_floor),
            )
        except (KeyError, TypeError):
            pass
        word_count_result = {
            "measured": measured_words,
            "floor": s8_floor,
            "floor_passed": measured_words >= s8_floor,
        }
        if not word_count_result["floor_passed"] and not return_stage:
            return_stage = "S8"  # Flag for content expansion

        proofreading_report = _render_proofreading_report(
            chapter,
            structure,
            style_findings,
            removed_sections,
            return_stage,
            word_count_result,
        )

        write_text(draft5_path, draft5)
        write_text(proofreading_report_path, proofreading_report)

        update_chapter_memory(
            book_root,
            current_chapter_id,
            summary=f"Draft5 copyedited for {chapter['title']}",
            claims=[
                "Internal production-only sections removed from draft4.",
                "Structure and style gate evaluated for final manuscript handoff.",
            ],
            unresolved_issues=style_findings,
            visual_notes=[],
        )

        gate_result = evaluate_gate(book_id, book_root, "S8", current_chapter_id)
        if not gate_result["passed"]:
            transition_stage(
                book_root,
                "S8",
                "gate_failed",
                current_chapter_id,
                note=json.dumps(gate_result, ensure_ascii=False),
            )
            results.append(
                {
                    "chapter_id": current_chapter_id,
                    "status": "gate_failed",
                    "gate_result": gate_result,
                }
            )
            continue

        transition_stage(
            book_root,
            "S8",
            "completed",
            current_chapter_id,
            note="AG-05 copyedit completed.",
        )
        results.append(
            {
                "chapter_id": current_chapter_id,
                "status": "completed",
                "outputs": [
                    str(draft5_path),
                    str(proofreading_report_path),
                ],
                "removed_internal_sections": removed_sections,
                "gate_result": gate_result,
            }
        )

    work_order = issue_work_order(book_id, book_root)
    return {
        "stage_id": "S8",
        "requested_chapters": target_chapters,
        "results": results,
        "work_order": {
            "order_id": work_order["order_id"],
            "priority_queue_size": len(work_order["priority_queue"]),
            "first_items": work_order["priority_queue"][:5],
        },
    }
