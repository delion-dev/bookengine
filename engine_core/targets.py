from __future__ import annotations

from functools import lru_cache
from typing import Any

from .common import PLATFORM_CORE_ROOT, now_iso, read_json


@lru_cache(maxsize=1)
def _load_word_target_policy() -> dict[str, Any]:
    payload = read_json(PLATFORM_CORE_ROOT / "word_target_policy.json", default=None)
    if payload is None:
        raise FileNotFoundError(
            f"Missing word target policy: {PLATFORM_CORE_ROOT / 'word_target_policy.json'}"
        )
    return payload


def _base_target(part: str, chapter_id: str) -> int:
    cfg = _load_word_target_policy()
    base_targets: dict[str, int] = cfg.get("base_targets", {})
    if chapter_id == "intro":
        return int(base_targets.get("intro", 2200))
    if chapter_id == "outro":
        return int(base_targets.get("outro", 1800))
    for part_key in ("CINEMA", "HISTORY", "TRAVEL", "TASTE"):
        if part_key in part and part_key in base_targets:
            return int(base_targets[part_key])
    return int(base_targets.get("default", 1800))


def _adjustments(chapter: dict[str, Any]) -> tuple[int, list[str]]:
    cfg = _load_word_target_policy()
    adj = cfg.get("adjustments", {})
    title = chapter["title"]
    part = chapter.get("part", "")
    notes = chapter.get("notes", [])
    delta = 0
    rationale: list[str] = []

    if "[HOT ISSUE]" in title:
        delta += int(adj.get("hot_issue_topic", 450))
        rationale.append("hot_issue_topic")
    if ":" in title:
        delta += int(adj.get("subtitle_present", 120))
        rationale.append("subtitle_present")
    if "&" in title or "와" in title:
        delta += int(adj.get("multi_subject_scope", 120))
        rationale.append("multi_subject_scope")
    if len(notes) >= 1:
        per_item = int(adj.get("supplementary_note_per_item", 120))
        max_delta = int(adj.get("supplementary_note_max_delta", 240))
        delta += min(max_delta, len(notes) * per_item)
        rationale.append("supplementary_note_signal")

    location_kw_map: dict[str, list[str]] = adj.get("location_keywords", {})
    location_kw = location_kw_map.get("TRAVEL", ["청령포", "장릉", "천문대", "선돌"])
    if "TRAVEL" in part and any(keyword in title for keyword in location_kw):
        delta += int(adj.get("location_specific_guidance", 180))
        rationale.append("location_specific_guidance")

    rec_kw_map: dict[str, list[str]] = adj.get("recommendation_keywords", {})
    rec_kw = rec_kw_map.get("TASTE", ["투어", "챌린지", "막걸리", "카페"])
    if "TASTE" in part and any(keyword in title for keyword in rec_kw):
        delta += int(adj.get("practical_recommendation_density", 120))
        rationale.append("practical_recommendation_density")

    return delta, rationale


def _anchor_budget(part: str, chapter_id: str, target_words: int, chapter: dict[str, Any]) -> int:
    cfg = _load_word_target_policy()
    budgets: dict[str, Any] = cfg.get("anchor_budgets", {})
    default_budget = int(budgets.get("default", 2))

    if chapter_id in {"intro", "outro"}:
        return int(budgets.get(chapter_id, default_budget))

    if "TRAVEL" in part:
        return int(budgets.get("TRAVEL", 3))

    if "TASTE" in part:
        taste_cfg = budgets.get("TASTE", {})
        if isinstance(taste_cfg, dict):
            threshold = int(taste_cfg.get("high_word_threshold", 2000))
            high_budget = int(taste_cfg.get("high_word_budget", 3))
            return high_budget if target_words >= threshold else int(taste_cfg.get("default", default_budget))
        return int(taste_cfg)

    if "HISTORY" in part:
        hist_cfg = budgets.get("HISTORY", {})
        if isinstance(hist_cfg, dict):
            hot_budget = int(hist_cfg.get("hot_issue", 3))
            threshold = int(hist_cfg.get("high_word_threshold", 2700))
            if "[HOT ISSUE]" in chapter["title"] or target_words >= threshold:
                return hot_budget
            return int(hist_cfg.get("default", default_budget))
        return int(hist_cfg)

    if "CINEMA" in part:
        cinema_cfg = budgets.get("CINEMA", {})
        if isinstance(cinema_cfg, dict):
            hot_budget = int(cinema_cfg.get("hot_issue", 3))
            return hot_budget if "[HOT ISSUE]" in chapter["title"] else int(cinema_cfg.get("default", default_budget))
        return int(cinema_cfg)

    return default_budget


def _stage_progress_floors(target_words: int) -> dict[str, int]:
    cfg = _load_word_target_policy()
    floors = cfg.get("stage_progress_floors", {})
    s4_ratio = float(floors.get("S4_draft1_ratio", 0.90))
    s4_min = int(floors.get("S4_draft1_min_words", 900))
    s5_ratio = float(floors.get("S5_draft2_ratio", 0.92))
    s8_ratio = float(floors.get("S8_final_ratio", 0.95))

    s4_floor = max(s4_min, round(target_words * s4_ratio))
    s5_floor = max(s4_floor, round(target_words * s5_ratio))
    s8_floor = max(s5_floor, round(target_words * s8_ratio))
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
    cfg = _load_word_target_policy()
    word_range = cfg.get("word_range", {})
    min_ratio = float(word_range.get("min_ratio", 0.85))
    max_ratio = float(word_range.get("max_ratio", 1.15))
    chars_per_word = float(word_range.get("chars_per_word_estimate", 2.2))

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
                "min_words": round(target_words * min_ratio),
                "max_words": round(target_words * max_ratio),
                "target_chars_estimate": round(target_words * chars_per_word),
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
