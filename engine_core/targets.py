from __future__ import annotations

from typing import Any

from .common import now_iso


def _base_target(part: str, chapter_id: str) -> int:
    if chapter_id == "intro":
        return 2200
    if chapter_id == "outro":
        return 1800
    if "CINEMA" in part:
        return 2400
    if "HISTORY" in part:
        return 2500
    if "TRAVEL" in part:
        return 2100
    if "TASTE" in part:
        return 1900
    return 1800


def _adjustments(chapter: dict[str, Any]) -> tuple[int, list[str]]:
    title = chapter["title"]
    part = chapter.get("part", "")
    notes = chapter.get("notes", [])
    delta = 0
    rationale: list[str] = []

    if "[HOT ISSUE]" in title:
        delta += 450
        rationale.append("hot_issue_topic")
    if ":" in title:
        delta += 120
        rationale.append("subtitle_present")
    if "&" in title or "와" in title:
        delta += 120
        rationale.append("multi_subject_scope")
    if len(notes) >= 1:
        delta += min(240, len(notes) * 120)
        rationale.append("supplementary_note_signal")
    if "TRAVEL" in part and any(keyword in title for keyword in ["청령포", "장릉", "천문대", "선돌"]):
        delta += 180
        rationale.append("location_specific_guidance")
    if "TASTE" in part and any(keyword in title for keyword in ["투어", "챌린지", "막걸리", "카페"]):
        delta += 120
        rationale.append("practical_recommendation_density")

    return delta, rationale


def _anchor_budget(part: str, chapter_id: str, target_words: int, chapter: dict[str, Any]) -> int:
    if chapter_id in {"intro", "outro"}:
        return 2
    if "TRAVEL" in part:
        return 3
    if "TASTE" in part:
        return 3 if target_words >= 2000 else 2
    if "HISTORY" in part:
        return 3 if "[HOT ISSUE]" in chapter["title"] or target_words >= 2700 else 2
    if "CINEMA" in part:
        return 3 if "[HOT ISSUE]" in chapter["title"] else 2
    return 2


def _stage_progress_floors(target_words: int) -> dict[str, int]:
    s4_floor = max(900, round(target_words * 0.90))
    s5_floor = max(s4_floor, round(target_words * 0.92))
    s8_floor = max(s5_floor, round(target_words * 0.95))
    return {
        "S4_draft1_min_words": s4_floor,
        "S5_draft2_min_words": s5_floor,
        "S8_final_draft_min_words": s8_floor,
    }


def build_word_targets(
    book_id: str,
    working_title: str,
    intake_manifest: dict[str, Any],
) -> dict[str, Any]:
    chapter_targets: list[dict[str, Any]] = []
    total_target_words = 0

    for chapter in intake_manifest.get("chapters_detected", []):
        chapter_id = chapter["chapter_id"]
        part = chapter.get("part", "")
        base = _base_target(part, chapter_id)
        delta, rationale = _adjustments(chapter)
        target_words = base + delta
        total_target_words += target_words

        chapter_targets.append(
            {
                "chapter_id": chapter_id,
                "title": chapter["title"],
                "part": part,
                "target_words": target_words,
                "min_words": round(target_words * 0.85),
                "max_words": round(target_words * 1.15),
                "target_chars_estimate": round(target_words * 2.2),
                "anchor_budget": _anchor_budget(part, chapter_id, target_words, chapter),
                "stage_progress_floors": _stage_progress_floors(target_words),
                "rationale": ["base_target"] + rationale,
            }
        )

    return {
        "version": "1.0",
        "generated_at": now_iso(),
        "book_id": book_id,
        "working_title": working_title,
        "policy": {
            "lock_stage": "S0",
            "change_rule": "word targets may change only through architecture rerun or explicit config revision",
            "estimate_note": "target_chars_estimate is a planning heuristic for Korean manuscript production",
        },
        "total_target_words": total_target_words,
        "chapters": chapter_targets,
    }


def get_chapter_target(word_targets: dict[str, Any], chapter_id: str) -> dict[str, Any]:
    for chapter in word_targets.get("chapters", []):
        if chapter["chapter_id"] == chapter_id:
            return chapter
    raise KeyError(f"Missing word target for {chapter_id}")
