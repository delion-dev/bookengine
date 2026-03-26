from __future__ import annotations

import json
import re
import time
from pathlib import Path
from typing import Any

from .ag01_engine import execute_s4_pipeline
from .book_state import load_book_db
from .common import PLATFORM_CORE_ROOT, count_words, now_iso, read_json, read_text, write_json, write_text
from .contracts import get_stage_output, resolve_stage_contract, validate_inputs
from .context_packs import build_context_bundle
from .gates import evaluate_gate
from .memory import update_chapter_memory
from .model_gateway import (
    ModelGatewayError,
    generate_text,
    grounded_research,
)
from .model_policy import resolve_stage_route
from .source_trust import partition_sources_for_citation
from .stage import transition_stage
from .subsection_nodes import build_section_nodes, write_node_manifest
from .targets import get_chapter_target
from .work_order import issue_work_order
from .section_labels import SECTION_ORDER, display_section_label, section_marker, strip_leading_section_heading


# ---------------------------------------------------------------------------
# Execution limits — loaded from stage_execution_policies.json (S4 entry)
# Fallback to conservative defaults if the file is unavailable.
# ---------------------------------------------------------------------------

def _s4_execution_limits() -> dict[str, Any]:
    payload = read_json(PLATFORM_CORE_ROOT / "stage_execution_policies.json", default={}) or {}
    s4 = payload.get("stages", {}).get("S4", {})
    limits = s4.get("execution_limits") or payload.get("default_execution_limits") or {}
    return {
        "max_expansions": int(limits.get("max_expansions", 3)),
        "network_recovery_passes": int(limits.get("network_recovery_passes", 1)),
        "network_recovery_cooldown_seconds": int(limits.get("network_recovery_cooldown_seconds", 20)),
    }


MAX_S4_EXPANSIONS: int = _s4_execution_limits()["max_expansions"]
MAX_NETWORK_RECOVERY_PASSES: int = _s4_execution_limits()["network_recovery_passes"]
NETWORK_RECOVERY_COOLDOWN_SECONDS: int = _s4_execution_limits()["network_recovery_cooldown_seconds"]


def _s4_output_bundle(book_id: str, book_root: Path, chapter_id: str) -> dict[str, str]:
    """Return resolved output paths for S4 using semantic named keys.

    Uses get_stage_output() — no index dependency; safe against output reordering.
    """
    _keys = ("draft1_prose", "node_manifest", "segment_plan",
             "narrative_design", "density_audit", "session_report")
    return {
        key: get_stage_output(book_id, book_root, "S4", key, chapter_id)
        for key in _keys
    }


def _missing_s4_outputs(book_id: str, book_root: Path, chapter_id: str) -> list[str]:
    bundle = _s4_output_bundle(book_id, book_root, chapter_id)
    return [path for path in bundle.values() if not Path(path).exists()]


def _has_all_s4_outputs(book_id: str, book_root: Path, chapter_id: str) -> bool:
    return not _missing_s4_outputs(book_id, book_root, chapter_id)


def _legacy_s4_anchored_path(book_root: Path, chapter_id: str) -> Path:
    return book_root / "manuscripts" / "_draft1" / f"{chapter_id}_draft1.md"


def _can_backfill_s4_outputs(book_id: str, book_root: Path, chapter_id: str) -> bool:
    bundle = _s4_output_bundle(book_id, book_root, chapter_id)
    missing = {Path(path).name for path in _missing_s4_outputs(book_id, book_root, chapter_id)}
    backfillable = {
        Path(bundle["draft1_prose"]).name,
        Path(bundle["node_manifest"]).name,
        Path(bundle["segment_plan"]).name,
        Path(bundle["narrative_design"]).name,
        Path(bundle["density_audit"]).name,
        Path(bundle["session_report"]).name,
    }
    prose_source_exists = Path(bundle["draft1_prose"]).exists() or _legacy_s4_anchored_path(book_root, chapter_id).exists()
    return bool(missing) and missing.issubset(backfillable) and prose_source_exists


def _pending_s4_chapters(book_id: str, book_root: Path) -> list[str]:
    payload = load_book_db(book_root)
    return [
        chapter_id
        for chapter_id in payload["chapter_sequence"]
        if payload["chapters"][chapter_id]["stages"]["S4"]["status"] in {"pending", "in_progress"}
        or (
            payload["chapters"][chapter_id]["stages"]["S4"]["status"] == "completed"
            and bool(_missing_s4_outputs(book_id, book_root, chapter_id))
        )
        or (
            payload["chapters"][chapter_id]["stages"]["S4"]["status"] == "gate_failed"
            and _has_all_s4_outputs(book_id, book_root, chapter_id)
        )
    ]


def _all_s4_chapters(book_root: Path) -> list[str]:
    payload = load_book_db(book_root)
    return list(payload["chapter_sequence"])


def _strip_anchor_markup(text: str) -> str:
    cleaned = re.sub(r"<!-- ANCHOR_START.*?<!-- ANCHOR_END id=\"[^\"]+\" -->", "", text, flags=re.DOTALL)
    cleaned = re.sub(r"\[ANCHOR_SLOT:[^\]]+\]\s*", "", cleaned)
    cleaned = re.sub(r"\n{3,}", "\n\n", cleaned)
    return cleaned.strip()


def _draft1_section_texts(draft_text: str) -> dict[str, str]:
    sections: dict[str, str] = {}
    for index, section_key in enumerate(SECTION_ORDER):
        heading = next(
            (
                marker
                for marker in (section_marker(section_key), f"## {section_key.title()}")
                if marker in draft_text
            ),
            None,
        )
        if not heading:
            continue
        after = draft_text.split(heading, 1)[1]
        next_positions = []
        for other_key in SECTION_ORDER[index + 1:]:
            for candidate in (section_marker(other_key), f"## {other_key.title()}"):
                position = after.find(f"\n{candidate}\n")
                if position >= 0:
                    next_positions.append(position)
        body = after[: min(next_positions)] if next_positions else after
        sections[section_key] = _strip_anchor_markup(body.strip())
    return sections


def _anchor_ids_for_backfill(raw_guide_contract: dict[str, Any], section_key: str) -> list[str]:
    placement = f"after_section:{section_key.title()}"
    return [
        anchor.get("anchor_id", "")
        for anchor in raw_guide_contract.get("anchor_contract", [])
        if anchor.get("placement") == placement and anchor.get("anchor_id")
    ]


def _legacy_s4_segment_plan(
    chapter: dict[str, Any],
    research_entry: dict[str, Any],
    source_types: list[str],
    chapter_target: dict[str, Any],
    raw_guide_contract: dict[str, Any],
    section_texts: dict[str, str],
) -> dict[str, Any]:
    budgets = _section_word_budget(chapter_target)
    reader_segment = _reader_segment_for_writer(research_entry)
    evidence_targets = raw_guide_contract.get("evidence_targets", [])
    local_notes = raw_guide_contract.get("local_notes", [])
    segments: list[dict[str, Any]] = []
    for sequence, section_key in enumerate(("hook", "context", "insight", "takeaway"), start=1):
        section_text = section_texts.get(section_key, "")
        target_words = count_words(section_text) or budgets[section_key]
        segments.append(
            {
                "segment_id": f"S4:{chapter['chapter_id']}:{section_key}",
                "chapter_id": chapter["chapter_id"],
                "chapter_title": chapter["title"],
                "sequence": sequence,
                "section_key": section_key,
                "section_heading": section_key.title(),
                "segment_index": 1,
                "target_words": target_words,
                "claim_intent": _guide_section_purpose(raw_guide_contract, section_key)
                or f"Preserve the approved {section_key} payoff from the legacy draft.",
                "evidence_slot": evidence_targets[(sequence - 1) % len(evidence_targets)] if evidence_targets else "",
                "source_hint": source_types[(sequence - 1) % len(source_types)] if source_types else "",
                "local_note": local_notes[(sequence - 1) % len(local_notes)] if local_notes else "",
                "reader_payoff": reader_segment.get("reader_payoff", ""),
                "reader_focus": reader_segment.get("focus", ""),
                "anchor_obligation_ids": _anchor_ids_for_backfill(raw_guide_contract, section_key),
                "research_questions": list(research_entry.get("research_questions", [])),
                "source_types": list(source_types),
            }
        )
    return {
        "version": "1.0",
        "generated_at": now_iso(),
        "stage_id": "S4",
        "chapter_id": chapter["chapter_id"],
        "chapter_title": chapter["title"],
        "target_words": chapter_target["target_words"],
        "draft1_floor": chapter_target["stage_progress_floors"]["S4_draft1_min_words"],
        "desired_total": max(
            count_words("\n\n".join(section_texts.get(key, "") for key in ("hook", "context", "insight", "takeaway"))),
            budgets["desired_total"],
        ),
        "reader_segment": reader_segment,
        "segments": segments,
    }


def _legacy_s4_narrative_design(
    chapter: dict[str, Any],
    raw_guide_contract: dict[str, Any],
    segment_plan: dict[str, Any],
) -> dict[str, Any]:
    designs: list[dict[str, Any]] = []
    previous_heading = ""
    for segment in segment_plan.get("segments", []):
        designs.append(
            {
                "segment_id": segment["segment_id"],
                "section_key": segment["section_key"],
                "opening_tactic": f"Preserve the accepted {segment['section_heading']} opening from the legacy draft.",
                "continuity_bridge": (
                    f"Connect naturally from the previous `{previous_heading}` section without restating it."
                    if previous_heading
                    else "Open cleanly and orient the reader without extra meta setup."
                ),
                "tension_release_note": "Keep the draft reader-facing and structurally faithful to the raw guide.",
                "tone_guardrail": "Do not add unsupported certainty while reconstructing legacy artifacts.",
                "forbidden_drift_topics": raw_guide_contract.get("exclude", []),
            }
        )
        previous_heading = segment["section_heading"]
    return {
        "version": "1.0",
        "generated_at": now_iso(),
        "stage_id": "S4",
        "chapter_id": chapter["chapter_id"],
        "chapter_title": chapter["title"],
        "segments": designs,
    }


def _backfilled_s4_node_manifest(
    chapter: dict[str, Any],
    research_entry: dict[str, Any],
    source_types: list[str],
    chapter_target: dict[str, Any],
    raw_guide: str,
    section_texts: dict[str, str],
    existing_manifest: dict[str, Any] | None,
) -> dict[str, Any]:
    raw_guide_contract = _parse_raw_guide_contract(raw_guide)
    section_targets = _section_word_budget(chapter_target)
    fallback_nodes = build_section_nodes(
        "S4",
        chapter["chapter_id"],
        chapter["title"],
        section_targets=section_targets,
        research_questions=research_entry.get("research_questions", []),
        source_types=source_types,
    )
    existing_nodes = {
        item.get("section_key"): item
        for item in (existing_manifest or {}).get("nodes", [])
        if isinstance(item, dict) and item.get("section_key")
    }
    nodes: list[dict[str, Any]] = []
    for fallback_node in fallback_nodes:
        section_key = fallback_node["section_key"]
        merged = dict(fallback_node)
        if section_key in existing_nodes:
            merged.update(existing_nodes[section_key])
        section_text = section_texts.get(section_key, "")
        merged["target_words"] = merged.get("target_words") or section_targets.get(section_key)
        merged["research_questions"] = list(merged.get("research_questions") or research_entry.get("research_questions", []))
        merged["source_types"] = list(merged.get("source_types") or source_types)
        merged["status"] = merged.get("status") or "completed"
        merged["updated_at"] = now_iso()
        merged["note"] = merged.get("note") or "legacy_stage_output_backfill"
        merged["output_text"] = section_text
        merged["output_words"] = count_words(section_text)
        nodes.append(merged)

    if existing_manifest:
        live_node_count = existing_manifest.get("live_node_count")
        fallback_node_count = existing_manifest.get("fallback_node_count")
        execution_mode = existing_manifest.get("execution_mode", "subsection_nodes_sequential")
        grounded_enabled = bool(existing_manifest.get("grounded_enabled"))
    else:
        live_node_count = len(nodes)
        fallback_node_count = 0
        execution_mode = "legacy_draft_backfill"
        grounded_enabled = False
    if not isinstance(live_node_count, int):
        live_node_count = len([node for node in nodes if node.get("status") == "completed"])
    if not isinstance(fallback_node_count, int):
        fallback_node_count = len(nodes) - live_node_count

    payload = {
        "version": "1.0",
        "generated_at": now_iso(),
        "stage_id": "S4",
        "chapter_id": chapter["chapter_id"],
        "chapter_title": chapter["title"],
        "execution_mode": execution_mode,
        "target_words": chapter_target["target_words"],
        "raw_guide_excerpt": (existing_manifest or {}).get("raw_guide_excerpt", raw_guide[:1200]),
        "raw_guide_contract": (existing_manifest or {}).get("raw_guide_contract", raw_guide_contract),
        "grounded_enabled": grounded_enabled,
        "node_count": len(nodes),
        "live_node_count": live_node_count,
        "fallback_node_count": fallback_node_count,
        "expansion_count": (existing_manifest or {}).get("expansion_count", 0),
        "expansion_cap": (existing_manifest or {}).get("expansion_cap", MAX_S4_EXPANSIONS),
        "nodes": nodes,
    }
    if not existing_manifest:
        payload["backfilled_from_legacy_stage_output"] = True
        payload["backfill_origin"] = "draft1_section_reconstruction"
    return payload


def _chapter_context(book_db: dict[str, Any], chapter_id: str) -> dict[str, Any]:
    chapter = book_db["chapters"][chapter_id]
    return {
        "chapter_id": chapter_id,
        "title": chapter["title"],
        "part": chapter.get("part"),
        "notes": chapter.get("notes", []),
    }


def _research_entry(research_plan: dict[str, Any], chapter_id: str) -> dict[str, Any]:
    for chapter in research_plan.get("chapters", []):
        if chapter["chapter_id"] == chapter_id:
            return chapter
    raise KeyError(f"Missing research entry for {chapter_id}")


def _source_types_for_chapter(source_queue: dict[str, Any], chapter_id: str) -> list[str]:
    source_types: list[str] = []
    for item in source_queue.get("items", []):
        if item["chapter_id"] != chapter_id:
            continue
        source_type = item["source_type"]
        if source_type not in source_types:
            source_types.append(source_type)
    return source_types


def _source_queue_items_for_chapter(source_queue: dict[str, Any], chapter_id: str) -> list[dict[str, Any]]:
    return [
        item
        for item in source_queue.get("items", [])
        if item["chapter_id"] == chapter_id
    ]


def _reader_segment_for_writer(research_entry: dict[str, Any]) -> dict[str, str]:
    segment = research_entry.get("reader_segment")
    if isinstance(segment, dict) and segment.get("segment_id"):
        return segment
    return {
        "segment_id": "general_reader",
        "focus": "general reader",
        "reader_payoff": "A clear emotional or practical payoff.",
    }


def _rights_constraints_for_writer(
    research_entry: dict[str, Any],
    source_queue_items: list[dict[str, Any]],
) -> list[str]:
    constraints = research_entry.get("rights_constraints")
    if isinstance(constraints, list) and constraints:
        return [str(item) for item in constraints]

    merged: list[str] = []
    for item in source_queue_items:
        for note in item.get("rights_constraints", []):
            text = str(note)
            if text not in merged:
                merged.append(text)
    return merged


def _raw_guide_sections(raw_guide: str) -> dict[str, list[str]]:
    sections: dict[str, list[str]] = {}
    current = "_preamble"
    sections[current] = []
    for line in raw_guide.splitlines():
        if line.startswith("## "):
            current = line[3:].strip()
            sections.setdefault(current, [])
            continue
        sections.setdefault(current, []).append(line.rstrip())
    return sections


def _bullet_items(lines: list[str]) -> list[str]:
    items: list[str] = []
    for line in lines:
        stripped = line.strip()
        if stripped.startswith("- "):
            items.append(stripped[2:].strip())
    return items


def _parse_reader_segment(section_lines: list[str]) -> dict[str, str]:
    segment = {
        "segment_id": "",
        "focus": "",
        "reader_payoff": "",
    }
    for item in _bullet_items(section_lines):
        if item.startswith("Segment:"):
            segment["segment_id"] = item.split(":", 1)[1].strip().strip("`")
        elif item.startswith("Focus:"):
            segment["focus"] = item.split(":", 1)[1].strip()
        elif item.startswith("Reader payoff:"):
            segment["reader_payoff"] = item.split(":", 1)[1].strip()
    return segment


def _parse_section_guides(section_lines: list[str]) -> dict[str, str]:
    guides: dict[str, str] = {}
    for item in _bullet_items(section_lines):
        match = re.match(r"\d+\.\s*([^:]+):\s*(.+)", item)
        if not match:
            continue
        label = match.group(1).strip().lower()
        if "hook" in label:
            guides["hook"] = match.group(2).strip()
        elif "context" in label:
            guides["context"] = match.group(2).strip()
        elif "insight" in label:
            guides["insight"] = match.group(2).strip()
        elif "takeaway" in label:
            guides["takeaway"] = match.group(2).strip()
    return guides


def _parse_anchor_contract(section_lines: list[str]) -> list[dict[str, str]]:
    anchors: list[dict[str, str]] = []
    for item in _bullet_items(section_lines):
        if "`" not in item or "|" not in item:
            continue
        parts = [part.strip().strip("`") for part in item.split("|")]
        if len(parts) < 5:
            continue
        anchors.append(
            {
                "anchor_id": parts[0],
                "anchor_type": parts[1],
                "placement": parts[2],
                "asset_mode": parts[3],
                "appendix_ref_id": parts[4].replace("ref", "").strip(),
            }
        )
    return anchors


def _parse_raw_guide_contract(raw_guide: str) -> dict[str, Any]:
    sections = _raw_guide_sections(raw_guide)
    target_length_items = _bullet_items(sections.get("Target Length", []))
    target_words = next((item.split(":", 1)[1].strip(" `") for item in target_length_items if item.startswith("Target words:")), "")
    draft1_floor = next((item.split(":", 1)[1].strip(" `").replace(" words", "") for item in target_length_items if item.startswith("Draft1 progress floor:")), "")
    return {
        "chapter_goal": next(iter(_bullet_items(sections.get("Chapter Goal", []))), ""),
        "reader_promise": _bullet_items(sections.get("Reader Promise", [])),
        "reader_segment": _parse_reader_segment(sections.get("Reader Segment", [])),
        "section_guides": _parse_section_guides(sections.get("Section Guides", [])),
        "evidence_targets": _bullet_items(sections.get("Evidence Targets", [])),
        "local_notes": _bullet_items(sections.get("Local Notes", [])),
        "include": _bullet_items(sections.get("Include", [])),
        "exclude": _bullet_items(sections.get("Exclude", [])),
        "visual_opportunities": _bullet_items(sections.get("Visual Opportunities", [])),
        "rights_guardrails": _bullet_items(sections.get("Rights and Source Guardrails", [])),
        "visual_source_priority": _bullet_items(sections.get("Visual Source Priority", [])),
        "output_reminder": _bullet_items(sections.get("Output Reminder", [])),
        "anchor_contract": _parse_anchor_contract(sections.get("Anchor Contract", [])),
        "target_words": target_words,
        "draft1_floor": draft1_floor,
        "raw_excerpt": raw_guide[:1200],
    }


def _guide_section_purpose(raw_guide_contract: dict[str, Any], section_key: str) -> str:
    return str(raw_guide_contract.get("section_guides", {}).get(section_key, "")).strip()


def _guide_driven_fallback(
    base_text: str,
    raw_guide_contract: dict[str, Any],
    section_key: str,
) -> str:
    extras: list[str] = []
    purpose = _guide_section_purpose(raw_guide_contract, section_key)
    if purpose:
        extras.append(f"{purpose}라는 감각이 문장 안에서 자연스럽게 살아나야 한다.")
    include_items = raw_guide_contract.get("include", [])
    if include_items:
        extras.append(f"특히 {include_items[0]} 같은 지점을 놓치지 않고 짚어 주는 편이 좋다.")
    if section_key == "takeaway":
        promises = raw_guide_contract.get("reader_promise", [])
        if promises:
            extras.append(f"끝내 독자에게 남아야 할 감정은 {promises[-1]}에 가깝다.")
    if section_key == "insight":
        evidence_targets = raw_guide_contract.get("evidence_targets", [])
        if evidence_targets:
            extras.append(f"이 대목을 더 깊게 읽게 만드는 질문은 {evidence_targets[0]} 같은 문제의식과 맞닿아 있다.")
    if not extras:
        return base_text
    return f"{base_text}\n\n{' '.join(extras)}"


def _tone_line(part: str | None) -> str:
    label = part or ""
    if "CINEMA" in label:
        return "이 초고는 영화적 감정의 작동 방식을 읽어내는 에디토리얼 문체를 유지한다."
    if "HISTORY" in label:
        return "이 초고는 기록과 해석을 구분하면서도 읽는 재미를 유지하는 균형을 목표로 한다."
    if "TRAVEL" in label:
        return "이 초고는 현장감과 실용성을 동시에 살리는 로컬 가이드 톤을 유지한다."
    if "TASTE" in label:
        return "이 초고는 여행의 여운과 지역의 맛을 연결하는 감각적인 문체를 유지한다."
    return "이 초고는 책 전체의 문제의식을 독자 친화적인 어조로 여는 역할을 맡는다."


def _hook_text(chapter: dict[str, Any]) -> str:
    title = chapter["title"]
    part = chapter.get("part", "")
    if "CINEMA" in part:
        return (
            "스크린에 한 인물의 얼굴이 오래 남는 순간에는 늘 이유가 있다. "
            f"{title}은 화려한 사건보다 배우의 표정과 호흡이 어떻게 장면의 정서를 끌고 가는지에서 출발한다. "
            "관객이 반복해서 곱씹는 순간의 감정선을 따라가며, 왜 그 얼굴이 곧 하나의 서사가 되는지 차분히 풀어 간다."
        )
    if "HISTORY" in part:
        return (
            "오래된 기록을 다시 펼칠 때 중요한 것은 사실의 목록보다 그 사실이 지금 왜 다시 읽혀야 하는가이다. "
            f"{title}은 익숙한 역사 서술의 표면을 걷어 내고, 기록과 해석이 만나는 지점을 독자가 스스로 감각하도록 돕는다."
        )
    if "TRAVEL" in part:
        return (
            "영화의 여운이 실제 장소의 공기와 만나는 순간, 여행은 단순한 이동이 아니라 감정의 연장선이 된다. "
            f"{title}은 어디를 가야 하는지보다 그 장소를 어떤 마음으로 마주해야 하는지를 먼저 붙잡는다."
        )
    if "TASTE" in part:
        return (
            "장면의 감정이 식탁 위의 온기로 이어질 때, 한 편의 이야기는 비로소 생활의 감각을 얻는다. "
            f"{title}은 감상의 끝을 맛과 거리의 리듬으로 이어 붙이며 독자의 여정을 한층 입체적으로 만든다."
        )
    return (
        f"{title}은 책 전체를 여는 첫 호흡처럼 작동한다. "
        "지금 독자가 왜 이 이야기에 깊이 끌리는지, 그리고 그 몰입이 어떤 해석과 여정으로 이어지는지를 먼저 붙든다."
    )


def _context_text(chapter: dict[str, Any], research_entry: dict[str, Any]) -> str:
    notes = chapter.get("notes", [])
    reader_segment = _reader_segment_for_writer(research_entry)
    note_line = ""
    if notes:
        note_line = f" 또한 {notes[0]} 같은 현장 메모는 장면의 공기와 거리감을 살리는 중요한 디테일이 된다."
    return (
        f"영화의 정서가 설득력을 얻는 순간은 {reader_segment.get('focus', '핵심 맥락')}가 허공에 뜨지 않고 시대와 장소의 감각 위에 단단히 놓일 때다. "
        f"그래서 이 대목에서는 정보의 양보다 {reader_segment.get('reader_payoff', '분명한 독자 효용')}와 맞닿는 좌표를 먼저 세우는 편이 더 중요하다."
        f"{note_line}"
    )


def _insight_text(chapter: dict[str, Any], research_entry: dict[str, Any], source_types: list[str]) -> str:
    reader_segment = _reader_segment_for_writer(research_entry)
    return (
        "결정적인 것은 익숙한 감상을 되풀이하는 일이 아니라, 한 장면이 왜 그렇게 오래 남는지 얼굴과 침묵과 거리의 작동 방식을 따라가 보는 일이다. "
        f"{chapter['title']}은 단순한 정보 항목이 아니라 영화와 역사, 여행과 팬덤을 한 프레임 안에서 묶어 내는 장면으로 읽힐 필요가 있다. "
        f"그럴 때 비로소 {reader_segment.get('reader_payoff', '이제 이 장면을 다르게 보게 되었다')}에 가까운 감각도 자연스럽게 따라온다."
    )


def _takeaway_text(chapter: dict[str, Any]) -> str:
    part = chapter.get("part", "")
    if "TRAVEL" in part or "TASTE" in part:
        return (
            "장을 덮을 즈음 독자는 다음 걸음을 자연스럽게 떠올리게 되어야 한다. "
            "실제 방문 동선과 머무는 시간대, 감상을 이어 가는 방식이 한 줄의 장면처럼 남을 때 이 장의 실용성과 여운이 함께 살아난다."
        )
    return (
        "장 끝에 남아야 하는 것은 요약문이 아니라 한 걸음 더 깊어진 해석의 감각이다. "
        "지금 붙잡은 정서와 질문이 다음 장으로 자연스럽게 이어질 때, 책 전체의 독법도 함께 선명해진다."
    )


def _policy_context(
    book_root: Path,
    chapter_id: str | None = None,
    *,
    node_payload: dict[str, Any] | None = None,
    prompt_text: str = "",
    extra_artifacts: list[dict[str, str]] | None = None,
) -> list[dict[str, str]]:
    bundle = build_context_bundle(
        book_root,
        "S4",
        chapter_id=chapter_id,
        node_payload=node_payload,
        prompt_text=prompt_text,
    )
    artifacts = list(bundle["context_artifacts"])
    if extra_artifacts:
        artifacts.extend(extra_artifacts)
    return artifacts


def _grounded_brief_for_writer(
    book_root: Path,
    chapter: dict[str, Any],
    research_entry: dict[str, Any],
    chapter_target: dict[str, Any],
) -> dict[str, Any] | None:
    try:
        route = resolve_stage_route(
            "S4",
            "grounded_research",
            chapter_part=chapter.get("part"),
            grounding_required=True,
        )
        result = grounded_research(
            research_entry.get("research_questions", []),
            {
                "chapter_title": chapter["title"],
                "source_types": research_entry.get("source_types", []),
                "freshness_window_days": max(14, chapter_target["target_words"] // 120),
            },
            citation_required=True,
            system_policy_ref=(
                "You are AG-01 preparing a grounded writing brief for a Korean nonfiction book. "
                "Collect only attributable, reader-relevant evidence."
            ),
            context_artifacts=_policy_context(
                book_root,
                chapter["chapter_id"],
                node_payload={
                    "node_id": f"S4:{chapter['chapter_id']}:grounded_brief",
                    "node_type": "grounded_brief",
                    "section_key": "research",
                    "section_heading": "Research",
                    "research_questions": research_entry.get("research_questions", []),
                    "source_types": research_entry.get("source_types", []),
                    "local_goal": "Prepare a grounded brief for draft generation.",
                },
                prompt_text="\n".join(research_entry.get("research_questions", [])),
                extra_artifacts=[
                    {
                        "label": "grounded_brief_runtime",
                        "text": json.dumps(
                            {
                                "chapter_title": chapter["title"],
                                "source_types": research_entry.get("source_types", []),
                                "freshness_window_days": max(14, chapter_target["target_words"] // 120),
                            },
                            ensure_ascii=False,
                            indent=2,
                        ),
                    }
                ],
            ),
            provider_route=route,
            telemetry_context={
                "stage_id": "S4",
                "chapter_id": chapter["chapter_id"],
                "node_id": f"S4:{chapter['chapter_id']}:grounded_brief",
                "section_key": "research",
            },
        )
        partitioned = partition_sources_for_citation(result.get("sources", []))
        result["sources"] = partitioned["primary_sources"]
        result["supplemental_sources"] = partitioned["supplemental_sources"]
        result["trust_summary"] = partitioned["trust_summary"]
        return result
    except ModelGatewayError:
        return None


def _section_word_budget(chapter_target: dict[str, Any]) -> dict[str, int]:
    desired_total = max(
        chapter_target["stage_progress_floors"]["S4_draft1_min_words"] + 180,
        int(chapter_target["target_words"] * 0.3),
    )
    hook = max(90, int(desired_total * 0.16))
    context = max(120, int(desired_total * 0.22))
    insight = max(180, int(desired_total * 0.44))
    takeaway = max(90, desired_total - hook - context - insight)
    return {
        "desired_total": desired_total,
        "hook": hook,
        "context": context,
        "insight": insight,
        "takeaway": takeaway,
    }


def _section_bundle_word_count(section_bundle: dict[str, Any]) -> int:
    return sum(count_words(section_bundle.get(section, "")) for section in ("hook", "context", "insight", "takeaway"))


def _clean_model_section(text: str) -> str:
    cleaned = text.strip()
    if cleaned.startswith("```"):
        cleaned = cleaned.strip("`")
        if "\n" in cleaned:
            cleaned = cleaned.split("\n", 1)[1]
        cleaned = cleaned.strip()
    return strip_leading_section_heading(cleaned)


def _fallback_section_text(
    chapter: dict[str, Any],
    research_entry: dict[str, Any],
    source_types: list[str],
    section_key: str,
) -> str:
    if section_key == "hook":
        return _hook_text(chapter)
    if section_key == "context":
        return _context_text(chapter, research_entry)
    if section_key == "insight":
        return _insight_text(chapter, research_entry, source_types)
    return _takeaway_text(chapter)


def _is_network_fallback_reason(reason: str | None) -> bool:
    text = (reason or "").lower()
    return "network error" in text or "os/network error" in text or "timed out" in text or "resource exhausted" in text


def _generate_section_node(
    book_root: Path,
    chapter: dict[str, Any],
    research_entry: dict[str, Any],
    source_queue_items: list[dict[str, Any]],
    raw_guide_contract: dict[str, Any],
    node: dict[str, Any],
    section_bundle: dict[str, Any],
    grounded: dict[str, Any] | None,
) -> tuple[str | None, dict[str, Any]]:
    section_key = node["section_key"]
    target_words = node.get("target_words") or 0
    reader_segment = _reader_segment_for_writer(research_entry)
    rights_constraints = _rights_constraints_for_writer(research_entry, source_queue_items)
    section_purpose = _guide_section_purpose(raw_guide_contract, section_key)
    source_lines = [
        f"- {item.get('source_name', 'unknown')} | {item.get('title', '')} | {item.get('url_or_identifier', '')}"
        for item in (grounded or {}).get("sources", [])[:5]
    ]
    prompt = "\n".join(
        [
            f"Write only the `{section_key}` subsection for the Korean nonfiction chapter `{chapter['title']}`.",
            "Return plain Korean prose only. Do not add headings, bullets, JSON, markdown fences, or meta commentary.",
            f"Target words: about {target_words}",
            f"Minimum words: at least {max(140, int(target_words * 0.6))}",
            "Requirements:",
            "- Preserve fact caution. Do not invent exact numbers, quotes, dates, venue specifics, or dialogue.",
            "- Keep the tone publication-ready and reader-centered.",
            "- Hook should pull the reader in.",
            "- Context should orient and frame the chapter.",
            "- Insight should carry the main analysis.",
            "- Takeaway should leave the reader with a next lens, action, or reflection.",
            "- Use 2-4 full paragraphs when helpful instead of one compressed snippet.",
            "",
            f"Chapter part: {chapter.get('part', '')}",
            f"Raw guide chapter goal: {raw_guide_contract.get('chapter_goal', '')}",
            f"Raw guide section purpose: {section_purpose}",
            f"Reader segment focus: {reader_segment.get('focus', '')}",
            f"Reader payoff target: {reader_segment.get('reader_payoff', '')}",
            "Reader promise:",
            *[f"- {item}" for item in raw_guide_contract.get("reader_promise", [])[:3]],
            "",
            "Must include:",
            *[f"- {item}" for item in raw_guide_contract.get("include", [])[:4]],
            "",
            "Must avoid:",
            *[f"- {item}" for item in raw_guide_contract.get("exclude", [])[:4]],
            "",
            "Research questions:",
            *[f"- {question}" for question in research_entry.get("research_questions", [])],
            "",
            "Rights and source guardrails:",
            *[f"- {item}" for item in rights_constraints[:6]],
            "",
            "Already completed sections for continuity:",
            f"- Hook: {section_bundle.get('hook', '')[:900]}",
            f"- Context: {section_bundle.get('context', '')[:900]}",
            f"- Insight: {section_bundle.get('insight', '')[:1200]}",
            "",
            "Grounded source signals:",
            *source_lines,
        ]
    ).strip()
    try:
        response = generate_text(
            resolve_stage_route(
                "S4",
                "generate_text",
                chapter_part=chapter.get("part"),
                section_key=section_key,
            ),
            system_policy_ref=(
                "You are AG-01 generating one subsection node for a Korean book-writing engine. "
                "Stay concrete, lucid, and safe for publication."
            ),
            prompt=prompt,
            context_artifacts=_policy_context(
                book_root,
                chapter["chapter_id"],
                node_payload={
                    **node,
                    "research_questions": research_entry.get("research_questions", []),
                    "source_types": research_entry.get("source_types", []),
                    "reader_segment": reader_segment,
                    "rights_constraints": rights_constraints,
                    "raw_guide_contract": {
                        "chapter_goal": raw_guide_contract.get("chapter_goal", ""),
                        "section_purpose": section_purpose,
                        "reader_promise": raw_guide_contract.get("reader_promise", [])[:3],
                        "include": raw_guide_contract.get("include", [])[:4],
                        "exclude": raw_guide_contract.get("exclude", [])[:4],
                    },
                    "continuity_excerpt": json.dumps(
                        {
                            "hook": section_bundle.get("hook", "")[:400],
                            "context": section_bundle.get("context", "")[:400],
                            "insight": section_bundle.get("insight", "")[:400],
                        },
                        ensure_ascii=False,
                    ),
                    "local_goal": f"Write the {section_key} subsection with reader-facing payoff.",
                },
                prompt_text=prompt,
            ),
            generation_config={"temperature": 0.35, "maxOutputTokens": 3072},
            telemetry_context={
                "stage_id": "S4",
                "chapter_id": chapter["chapter_id"],
                "node_id": node["node_id"],
                "section_key": section_key,
            },
        )
    except ModelGatewayError as exc:
        return None, {"status": "fallback", "reason": str(exc)}
    generated = _clean_model_section(response["generated_text"])
    if not generated:
        return None, {"status": "fallback", "reason": "empty_response"}
    return generated, {
        "status": "completed",
        "request_variant": response.get("request_variant"),
        "usage": response.get("usage", {}),
        "output_words": count_words(generated),
    }


def _expand_section_text(
    book_root: Path,
    chapter: dict[str, Any],
    research_entry: dict[str, Any],
    source_queue_items: list[dict[str, Any]],
    raw_guide_contract: dict[str, Any],
    section_name: str,
    current_text: str,
    target_words: int,
    section_bundle: dict[str, Any],
    grounded: dict[str, Any] | None,
) -> str | None:
    current_words = count_words(current_text)
    if current_words >= target_words:
        return current_text

    reader_segment = _reader_segment_for_writer(research_entry)
    rights_constraints = _rights_constraints_for_writer(research_entry, source_queue_items)
    section_purpose = _guide_section_purpose(raw_guide_contract, section_name)
    source_lines = [
        f"- {item.get('source_name', 'unknown')} | {item.get('title', '')} | {item.get('url_or_identifier', '')}"
        for item in (grounded or {}).get("sources", [])[:5]
    ]
    prompt = "\n".join(
        [
            f"Expand only the `{section_name}` section for the chapter `{chapter['title']}`.",
            "Return plain Korean prose only. Do not include headings, bullets, JSON, or markdown fences.",
            f"Current section word count: {current_words}",
            f"Target section word count: about {target_words}",
            "Requirements:",
            "- Preserve the existing facts and tone.",
            "- Add detail, scene interpretation, context, and reader value without repeating sentences.",
            "- Do not invent exact numbers, quotes, dates, or locations beyond the grounded evidence.",
            "- If evidence is partial, write cautiously.",
            "",
            f"Raw guide chapter goal: {raw_guide_contract.get('chapter_goal', '')}",
            f"Raw guide section purpose: {section_purpose}",
            f"Reader segment focus: {reader_segment.get('focus', '')}",
            f"Reader payoff target: {reader_segment.get('reader_payoff', '')}",
            "Must include:",
            *[f"- {item}" for item in raw_guide_contract.get("include", [])[:4]],
            "",
            "Must avoid:",
            *[f"- {item}" for item in raw_guide_contract.get("exclude", [])[:4]],
            "",
            "Rights and source guardrails:",
            *[f"- {item}" for item in rights_constraints[:6]],
            "",
            f"Current {section_name} section:",
            current_text.strip(),
            "",
            "Other chapter sections for continuity:",
            f"Hook: {section_bundle.get('hook', '')[:900]}",
            f"Context: {section_bundle.get('context', '')[:900]}",
            f"Insight: {section_bundle.get('insight', '')[:1200]}",
            f"Takeaway: {section_bundle.get('takeaway', '')[:900]}",
            "",
            "Research questions:",
            *[f"- {question}" for question in research_entry.get("research_questions", [])],
            "",
            "Trusted grounded source signals:",
            *source_lines,
        ]
    ).strip()

    try:
        response = generate_text(
            resolve_stage_route(
                "S4",
                "generate_text",
                chapter_part=chapter.get("part"),
                section_key=section_name,
            ),
            system_policy_ref=(
                "You are AG-01 expanding one section of a Korean nonfiction chapter. "
                "Keep the voice editorial, concrete, and fact-cautious."
            ),
            prompt=prompt,
            context_artifacts=_policy_context(
                book_root,
                chapter["chapter_id"],
                node_payload={
                    "node_id": f"S4:{chapter['chapter_id']}:{section_name}:expand",
                    "node_type": "section_expansion",
                    "section_key": section_name,
                    "section_heading": section_name.title(),
                    "target_words": target_words,
                    "research_questions": research_entry.get("research_questions", []),
                    "source_types": research_entry.get("source_types", []),
                    "reader_segment": reader_segment,
                    "rights_constraints": rights_constraints,
                    "raw_guide_contract": {
                        "chapter_goal": raw_guide_contract.get("chapter_goal", ""),
                        "section_purpose": section_purpose,
                        "reader_promise": raw_guide_contract.get("reader_promise", [])[:3],
                        "include": raw_guide_contract.get("include", [])[:4],
                        "exclude": raw_guide_contract.get("exclude", [])[:4],
                    },
                    "source_text": current_text,
                    "continuity_excerpt": json.dumps(
                        {
                            "hook": section_bundle.get("hook", "")[:400],
                            "context": section_bundle.get("context", "")[:400],
                            "insight": section_bundle.get("insight", "")[:400],
                            "takeaway": section_bundle.get("takeaway", "")[:400],
                        },
                        ensure_ascii=False,
                    ),
                    "local_goal": f"Expand the {section_name} section without changing established facts.",
                },
                prompt_text=prompt,
            ),
            generation_config={"temperature": 0.4, "maxOutputTokens": 3072},
            telemetry_context={
                "stage_id": "S4",
                "chapter_id": chapter["chapter_id"],
                "node_id": f"S4:{chapter['chapter_id']}:{section_name}:expand",
                "section_key": section_name,
            },
        )
    except ModelGatewayError:
        return None
    expanded = _clean_model_section(response["generated_text"])
    return expanded if count_words(expanded) > current_words else current_text


def _expand_section_bundle_to_target(
    book_root: Path,
    chapter: dict[str, Any],
    research_entry: dict[str, Any],
    source_queue_items: list[dict[str, Any]],
    raw_guide_contract: dict[str, Any],
    chapter_target: dict[str, Any],
    section_bundle: dict[str, Any],
    grounded: dict[str, Any] | None,
) -> tuple[dict[str, Any], int]:
    budgets = _section_word_budget(chapter_target)
    total_words = _section_bundle_word_count(section_bundle)
    if total_words >= budgets["desired_total"]:
        return section_bundle, 0

    expansions_used = 0
    while total_words < budgets["desired_total"] and expansions_used < MAX_S4_EXPANSIONS:
        section_order = sorted(
            ("insight", "context", "takeaway", "hook"),
            key=lambda name: budgets[name] - count_words(section_bundle.get(name, "")),
            reverse=True,
        )
        progress_made = False
        for section_name in section_order:
            if expansions_used >= MAX_S4_EXPANSIONS:
                break
            current_words = count_words(section_bundle.get(section_name, ""))
            shortfall = budgets[section_name] - current_words
            if shortfall < 120:
                continue
            expanded = _expand_section_text(
                book_root,
                chapter,
                research_entry,
                source_queue_items,
                raw_guide_contract,
                section_name,
                section_bundle.get(section_name, ""),
                budgets[section_name],
                section_bundle,
                grounded,
            )
            expanded_words = count_words(expanded or "")
            if expanded and expanded_words > current_words:
                section_bundle[section_name] = expanded
                expansions_used += 1
                total_words = _section_bundle_word_count(section_bundle)
                progress_made = True
                if total_words >= budgets["desired_total"]:
                    break
        if not progress_made:
            break
    return section_bundle, expansions_used


def _render_draft1_from_sections(
    chapter: dict[str, Any],
    chapter_target: dict[str, Any],
    section_bundle: dict[str, Any],
) -> str:
    lines = [
        f"# DRAFT1: {chapter['chapter_id']} | {chapter['title']}",
        "",
        display_section_label("hook"),
        section_bundle["hook"].strip(),
        "",
        display_section_label("context"),
        section_bundle["context"].strip(),
        "",
        display_section_label("insight"),
        section_bundle["insight"].strip(),
        "",
        display_section_label("takeaway"),
        section_bundle["takeaway"].strip(),
    ]
    return "\n".join(lines).strip() + "\n"


def _compose_live_draft(
    book_root: Path,
    chapter: dict[str, Any],
    research_entry: dict[str, Any],
    source_queue_items: list[dict[str, Any]],
    source_types: list[str],
    chapter_target: dict[str, Any],
    raw_guide: str,
) -> tuple[str | None, dict[str, Any] | None, dict[str, Any]]:
    raw_guide_contract = _parse_raw_guide_contract(raw_guide)
    budgets = _section_word_budget(chapter_target)
    grounded = _grounded_brief_for_writer(book_root, chapter, research_entry, chapter_target)
    nodes = build_section_nodes(
        "S4",
        chapter["chapter_id"],
        chapter["title"],
        section_targets=budgets,
        research_questions=research_entry.get("research_questions", []),
        source_types=source_types,
    )
    section_bundle: dict[str, Any] = {
        "hook": "",
        "context": "",
        "insight": "",
        "takeaway": "",
        "raw_guide_contract": raw_guide_contract,
        "reader_segment": _reader_segment_for_writer(research_entry),
        "rights_guardrails": _rights_constraints_for_writer(research_entry, source_queue_items),
        "research_carryovers": research_entry.get("research_questions", []),
        "source_priorities": source_types,
    }
    live_node_count = 0
    for node in nodes:
        generated, telemetry = _generate_section_node(
            book_root,
            chapter,
            research_entry,
            source_queue_items,
            raw_guide_contract,
            node,
            section_bundle,
            grounded,
        )
        minimum_acceptable_words = max(80, int((node.get("target_words") or 0) * 0.35))
        if generated is None or count_words(generated) < minimum_acceptable_words:
            generated = _guide_driven_fallback(
                _fallback_section_text(chapter, research_entry, source_types, node["section_key"]),
                raw_guide_contract,
                node["section_key"],
            )
            telemetry = {
                "status": "fallback",
                "reason": telemetry.get("reason", "insufficient_length"),
            }
        else:
            live_node_count += 1
        section_bundle[node["section_key"]] = generated
        node["status"] = telemetry.get("status", "completed")
        node["updated_at"] = now_iso()
        node["note"] = telemetry.get("reason", "")
        node["output_words"] = count_words(generated)
        if telemetry.get("request_variant"):
            node["request_variant"] = telemetry["request_variant"]
        if telemetry.get("usage"):
            node["usage"] = telemetry["usage"]

    if live_node_count == 0 and all(_is_network_fallback_reason(node.get("note")) for node in nodes):
        for _ in range(MAX_NETWORK_RECOVERY_PASSES):
            time.sleep(NETWORK_RECOVERY_COOLDOWN_SECONDS)
            section_bundle = {
                "hook": "",
                "context": "",
                "insight": "",
                "takeaway": "",
                "raw_guide_contract": raw_guide_contract,
                "reader_segment": _reader_segment_for_writer(research_entry),
                "rights_guardrails": _rights_constraints_for_writer(research_entry, source_queue_items),
                "research_carryovers": research_entry.get("research_questions", []),
                "source_priorities": source_types,
            }
            live_node_count = 0
            for node in nodes:
                generated, telemetry = _generate_section_node(
                    book_root,
                    chapter,
                    research_entry,
                    source_queue_items,
                    raw_guide_contract,
                    node,
                    section_bundle,
                    grounded,
                )
                minimum_acceptable_words = max(80, int((node.get("target_words") or 0) * 0.35))
                if generated is None or count_words(generated) < minimum_acceptable_words:
                    generated = _guide_driven_fallback(
                        _fallback_section_text(chapter, research_entry, source_types, node["section_key"]),
                        raw_guide_contract,
                        node["section_key"],
                    )
                    telemetry = {
                        "status": "fallback",
                        "reason": telemetry.get("reason", "insufficient_length"),
                    }
                else:
                    live_node_count += 1
                section_bundle[node["section_key"]] = generated
                node["status"] = telemetry.get("status", "completed")
                node["updated_at"] = now_iso()
                node["note"] = telemetry.get("reason", "")
                node["output_words"] = count_words(generated)
                if telemetry.get("request_variant"):
                    node["request_variant"] = telemetry["request_variant"]
                if telemetry.get("usage"):
                    node["usage"] = telemetry["usage"]
            if live_node_count > 0 or not all(_is_network_fallback_reason(node.get("note")) for node in nodes):
                break

    section_bundle, expansion_count = _expand_section_bundle_to_target(
        book_root,
        chapter,
        research_entry,
        source_queue_items,
        raw_guide_contract,
        chapter_target,
        section_bundle,
        grounded,
    )
    manifest = {
        "version": "1.0",
        "generated_at": now_iso(),
        "stage_id": "S4",
        "chapter_id": chapter["chapter_id"],
        "chapter_title": chapter["title"],
        "execution_mode": "subsection_nodes_sequential",
        "target_words": chapter_target["target_words"],
        "raw_guide_excerpt": raw_guide[:1200],
        "raw_guide_contract": raw_guide_contract,
        "grounded_enabled": grounded is not None,
        "node_count": len(nodes),
        "live_node_count": live_node_count,
        "fallback_node_count": len(nodes) - live_node_count,
        "expansion_count": expansion_count,
        "expansion_cap": MAX_S4_EXPANSIONS,
        "nodes": nodes,
    }
    return _render_draft1_from_sections(chapter, chapter_target, section_bundle), grounded, manifest


def _render_draft1(
    chapter: dict[str, Any],
    research_entry: dict[str, Any],
    source_types: list[str],
    chapter_target: dict[str, Any],
) -> str:
    lines = [
        f"# DRAFT1: {chapter['chapter_id']} | {chapter['title']}",
        "",
        display_section_label("hook"),
        _hook_text(chapter),
        "",
        display_section_label("context"),
        _context_text(chapter, research_entry),
        "",
        display_section_label("insight"),
        _insight_text(chapter, research_entry, source_types),
        "",
        display_section_label("takeaway"),
        _takeaway_text(chapter),
    ]
    return "\n".join(lines).strip() + "\n"


def _draft_claims(chapter: dict[str, Any]) -> list[str]:
    part = chapter.get("part", "")
    if "CINEMA" in part:
        return [
            "The chapter reads performance as a narrative device rather than simple fandom admiration.",
            "The chapter positions audience reaction as a clue to how the film's emotion is built.",
        ]
    if "HISTORY" in part:
        return [
            "The chapter distinguishes historical record from dramatized interpretation.",
            "The chapter treats factual correction as part of the reader experience, not a detached appendix.",
        ]
    if "TRAVEL" in part:
        return [
            "The chapter turns cinematic memory into an on-site travel frame.",
            "The chapter links practical visit guidance with emotional payoff.",
        ]
    if "TASTE" in part:
        return [
            "The chapter frames local food as part of the narrative itinerary.",
            "The chapter avoids generic recommendation language by tying each stop to mood and context.",
        ]
    return [
        "The chapter opens the book's central question in a reader-facing way.",
        "The chapter prepares the reader to move from emotion to interpretation.",
    ]


def run_draft1(
    book_id: str,
    book_root: Path,
    chapter_id: str | None = None,
    *,
    rerun_completed: bool = False,
) -> dict[str, Any]:
    book_db = load_book_db(book_root)
    research_plan = read_json(book_root / "research" / "research_plan.json", default=None)
    source_queue = read_json(book_root / "research" / "source_queue.json", default=None)
    word_targets = read_json(book_root / "_master" / "WORD_TARGETS.json", default=None)
    if research_plan is None or source_queue is None or word_targets is None:
        raise FileNotFoundError("S4 requires research_plan.json, source_queue.json, and WORD_TARGETS.json.")

    target_chapters = (
        [chapter_id]
        if chapter_id
        else (_all_s4_chapters(book_root) if rerun_completed else _pending_s4_chapters(book_id, book_root))
    )
    if not target_chapters:
        return {
            "stage_id": "S4",
            "status": "no_op",
            "message": (
                "No pending, backfillable, or revalidatable S4 chapters found."
                if not rerun_completed
                else "No S4 chapters found for rerun."
            ),
        }

    results = []
    for current_chapter_id in target_chapters:
        contract_status = validate_inputs(book_id, book_root, "S4", current_chapter_id)
        if not contract_status["valid"]:
            raise FileNotFoundError(f"S4 inputs missing for {current_chapter_id}: {contract_status['missing_inputs']}")

        chapter = _chapter_context(book_db, current_chapter_id)
        current_status = book_db["chapters"][current_chapter_id]["stages"]["S4"]["status"]
        output_bundle = _s4_output_bundle(book_id, book_root, current_chapter_id)
        missing_outputs = _missing_s4_outputs(book_id, book_root, current_chapter_id)
        backfill_only = current_status == "completed" and _can_backfill_s4_outputs(book_id, book_root, current_chapter_id)
        revalidate_only = False
        if revalidate_only:
            gate_result = evaluate_gate(book_id, book_root, "S4", current_chapter_id)
            declared_outputs = list(output_bundle.values())
            if gate_result["passed"]:
                transition_stage(
                    book_root,
                    "S4",
                    "pending",
                    current_chapter_id,
                    note="AG-01 gate revalidation requested from existing artifacts.",
                )
                transition_stage(
                    book_root,
                    "S4",
                    "in_progress",
                    current_chapter_id,
                    note="AG-01 gate revalidation started from existing artifacts.",
                )
                transition_stage(
                    book_root,
                    "S4",
                    "completed",
                    current_chapter_id,
                    note="AG-01 gate revalidated from existing artifacts.",
                )
                results.append(
                    {
                        "chapter_id": current_chapter_id,
                        "status": "completed",
                        "repair_mode": "gate_revalidation",
                        "outputs": declared_outputs,
                        "node_manifest": output_bundle["node_manifest"],
                        "gate_result": gate_result,
                    }
                )
            else:
                results.append(
                    {
                        "chapter_id": current_chapter_id,
                        "status": "gate_failed",
                        "repair_mode": "gate_revalidation_failed",
                        "outputs": declared_outputs,
                        "node_manifest": output_bundle["node_manifest"],
                        "gate_result": gate_result,
                    }
                )
            continue

        if rerun_completed and current_status == "completed":
            transition_stage(
                book_root,
                "S4",
                "in_progress",
                current_chapter_id,
                note="AG-01 draft1 full rerun started from stabilized pipeline.",
            )
        elif current_status == "gate_failed":
            transition_stage(
                book_root,
                "S4",
                "pending",
                current_chapter_id,
                note="AG-01 draft1 rerun requested after gate fix.",
            )
            transition_stage(
                book_root,
                "S4",
                "in_progress",
                current_chapter_id,
                note="AG-01 draft1 generation restarted.",
            )
        elif current_status != "completed":
            transition_stage(
                book_root,
                "S4",
                "in_progress",
                current_chapter_id,
                note="AG-01 draft1 generation started.",
            )
        elif missing_outputs and not backfill_only:
            transition_stage(
                book_root,
                "S4",
                "in_progress",
                current_chapter_id,
                note="AG-01 draft1 regeneration started from missing outputs.",
            )
        research_entry = _research_entry(research_plan, current_chapter_id)
        source_queue_items = _source_queue_items_for_chapter(source_queue, current_chapter_id)
        source_types = _source_types_for_chapter(source_queue, current_chapter_id)
        chapter_target = get_chapter_target(word_targets, current_chapter_id)
        raw_guide = read_text(book_root / "manuscripts" / "_raw" / f"{current_chapter_id}_raw.md")
        anchor_plan = read_json(book_root / "manuscripts" / "_raw" / f"{current_chapter_id}_anchor_plan.json", default={"anchors": []})
        if backfill_only:
            prose_path = Path(output_bundle["draft1_prose"])
            legacy_path = _legacy_s4_anchored_path(book_root, current_chapter_id)
            source_path = prose_path if prose_path.exists() else legacy_path
            draft_text = read_text(source_path)
            prose_text = _strip_anchor_markup(draft_text)
            section_texts = _draft1_section_texts(prose_text)
            if len(section_texts) != 4:
                raise ValueError(f"S4 backfill requires four core sections in draft1 for {current_chapter_id}")
            raw_guide_contract = _parse_raw_guide_contract(raw_guide)
            segment_plan = _legacy_s4_segment_plan(
                chapter,
                research_entry,
                source_types,
                chapter_target,
                raw_guide_contract,
                section_texts,
            )
            narrative_design = _legacy_s4_narrative_design(chapter, raw_guide_contract, segment_plan)
            existing_node_manifest = read_json(Path(output_bundle["node_manifest"]), default=None)
            audit_node_manifest = _backfilled_s4_node_manifest(
                chapter,
                research_entry,
                source_types,
                chapter_target,
                raw_guide,
                section_texts,
                existing_node_manifest if isinstance(existing_node_manifest, dict) else None,
            )
            if not Path(output_bundle["node_manifest"]).exists():
                write_node_manifest(book_root, "S4", current_chapter_id, audit_node_manifest)
            if not prose_path.exists():
                write_text(prose_path, prose_text.rstrip() + "\n")
            if not Path(output_bundle["segment_plan"]).exists():
                write_json(Path(output_bundle["segment_plan"]), segment_plan)
            if not Path(output_bundle["narrative_design"]).exists():
                write_json(Path(output_bundle["narrative_design"]), narrative_design)
            artifact_paths = {
                "draft1_prose": output_bundle["draft1_prose"],
                "segment_plan": output_bundle["segment_plan"],
                "narrative_design": output_bundle["narrative_design"],
                "density_audit": output_bundle["density_audit"],
                "session_report": output_bundle["session_report"],
            }
            density_audit = {
                "version": "1.0",
                "generated_at": now_iso(),
                "stage_id": "S4",
                "chapter_id": current_chapter_id,
                "chapter_title": chapter["title"],
                "target_words": chapter_target["target_words"],
                "draft1_floor": chapter_target["stage_progress_floors"]["S4_draft1_min_words"],
                "draft_words": count_words(prose_text),
                "draft_coverage_ratio": round(
                    count_words(prose_text) / max(1, chapter_target["stage_progress_floors"]["S4_draft1_min_words"]),
                    3,
                ),
                "section_word_counts": {
                    section_key: count_words(section_texts.get(section_key, ""))
                    for section_key in ("hook", "context", "insight", "takeaway")
                },
                "segment_plan_count": len(segment_plan["segments"]),
                "implemented_segment_count": audit_node_manifest["node_count"],
                "live_node_success_ratio": round(
                    audit_node_manifest["live_node_count"] / max(1, audit_node_manifest["node_count"]),
                    3,
                ),
                "fallback_only_completion": (
                    audit_node_manifest["node_count"] > 0
                    and audit_node_manifest["live_node_count"] == 0
                ),
                "required_sections_present": all(
                    section_texts.get(section_key, "").strip()
                    for section_key in ("hook", "context", "insight", "takeaway")
                ),
                "anchor_blocks_inserted": False,
                "segment_plan_exists": True,
                "narrative_design_exists": True,
                "density_pass": (
                    count_words(prose_text) >= chapter_target["stage_progress_floors"]["S4_draft1_min_words"]
                    and all(section_texts.get(section_key, "").strip() for section_key in ("hook", "context", "insight", "takeaway"))
                ),
            }
            session_report = {
                "version": "1.0",
                "generated_at": now_iso(),
                "stage_id": "S4",
                "chapter_id": current_chapter_id,
                "chapter_title": chapter["title"],
                "verdict": "completed",
                "reasons": [],
                "recommended_status": "completed",
                "live_node_count": audit_node_manifest["live_node_count"],
                "fallback_node_count": audit_node_manifest["fallback_node_count"],
                "live_node_success_ratio": density_audit["live_node_success_ratio"],
                "draft_coverage_ratio": density_audit["draft_coverage_ratio"],
                "artifacts": artifact_paths,
            }
            if not Path(output_bundle["density_audit"]).exists():
                write_json(Path(output_bundle["density_audit"]), density_audit)
            if not Path(output_bundle["session_report"]).exists():
                write_json(Path(output_bundle["session_report"]), session_report)
            declared_outputs = list(output_bundle.values())
            update_chapter_memory(
                book_root,
                current_chapter_id,
                summary=f"S4 artifacts backfilled for {chapter['title']}",
                claims=[
                    "Legacy S4 outputs were reconstructed from the approved prose artifact.",
                    "Segment plan, narrative design, density audit, and session report were regenerated for contract completeness.",
                ],
                citations_summary=list(source_types),
                unresolved_issues=research_entry.get("research_questions", []),
                visual_notes=[],
            )
            transition_stage(
                book_root,
                "S4",
                "completed",
                current_chapter_id,
                note=f"AG-01 legacy output backfill completed: {', '.join(Path(path).name for path in missing_outputs)}",
            )
            results.append(
                {
                    "chapter_id": current_chapter_id,
                    "status": "completed",
                    "repair_mode": "artifact_backfill",
                    "repaired_outputs": [Path(path).name for path in missing_outputs],
                    "outputs": declared_outputs,
                    "node_manifest": output_bundle["node_manifest"],
                    "segment_plan": output_bundle["segment_plan"],
                    "narrative_design": output_bundle["narrative_design"],
                    "density_audit": output_bundle["density_audit"],
                    "session_report": output_bundle["session_report"],
                    "gate_result": {
                        "skipped": True,
                        "reason": "artifact_backfill_only",
                    },
                }
            )
            continue

        pipeline_result = execute_s4_pipeline(
            book_root,
            chapter,
            research_entry,
            source_queue_items,
            source_types,
            chapter_target,
            raw_guide,
        )
        grounded = pipeline_result["grounded"]
        node_manifest = pipeline_result["node_manifest"]
        generation_mode = pipeline_result["generation_mode"]
        output_path = pipeline_result["prose_path"]
        node_manifest_path = pipeline_result["node_manifest_path"]
        session_report = pipeline_result["session_report"]

        update_chapter_memory(
            book_root,
            current_chapter_id,
            summary=f"Draft1 ready for {chapter['title']} ({generation_mode})",
            claims=_draft_claims(chapter),
            citations_summary=[
                *source_types,
                *[
                    item.get("source_name", "")
                    for item in (grounded or {}).get("sources", [])[:4]
                    if item.get("source_name")
                ],
            ],
            unresolved_issues=research_entry.get("research_questions", []),
            visual_notes=[],
        )

        gate_result = evaluate_gate(book_id, book_root, "S4", current_chapter_id)
        declared_outputs = list(output_bundle.values())
        if not gate_result["passed"] or session_report.get("recommended_status") == "gate_failed":
            transition_stage(
                book_root,
                "S4",
                "gate_failed",
                current_chapter_id,
                note=json.dumps(gate_result, ensure_ascii=False),
            )
            results.append(
                {
                    "chapter_id": current_chapter_id,
                    "status": "gate_failed",
                    "outputs": declared_outputs,
                    "node_manifest": str(node_manifest_path),
                    "gate_result": gate_result,
                }
            )
            continue

        transition_stage(
            book_root,
            "S4",
            "completed",
            current_chapter_id,
            note=f"AG-01 draft1 generation completed ({session_report.get('verdict', 'completed')}).",
        )
        results.append(
                {
                    "chapter_id": current_chapter_id,
                    "status": "completed",
                    "outputs": declared_outputs,
                    "output": str(output_path),
                    "node_manifest": str(node_manifest_path),
                    "segment_plan": str(pipeline_result["segment_plan_path"]),
                    "narrative_design": str(pipeline_result["narrative_design_path"]),
                    "density_audit": str(pipeline_result["density_audit_path"]),
                    "session_report": str(pipeline_result["session_report_path"]),
                    "generation_mode": generation_mode,
                    "gate_result": gate_result,
                }
            )

    work_order = issue_work_order(book_id, book_root)
    return {
        "stage_id": "S4",
        "requested_chapters": target_chapters,
        "results": results,
        "work_order": {
            "order_id": work_order["order_id"],
            "priority_queue_size": len(work_order["priority_queue"]),
            "first_items": work_order["priority_queue"][:5],
        },
    }
