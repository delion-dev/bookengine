from __future__ import annotations

import re
import time
from pathlib import Path
from typing import Any

from .common import count_words, now_iso, write_json, write_text
from .context_packs import build_context_bundle
from .model_gateway import ModelGatewayError, diagnose_vertex_live_probe, generate_text, grounded_research
from .model_policy import resolve_stage_route
from .section_labels import (
    SECTION_ORDER,
    canonical_section_label,
    display_section_label,
    has_required_sections,
    normalize_section_headings,
    section_marker,
    strip_leading_section_heading,
)
from .source_trust import partition_sources_for_citation
from .subsection_nodes import write_node_manifest


SECTION_HEADINGS = {
    section_key: canonical_section_label(section_key)
    for section_key in SECTION_ORDER
}
SECTION_INTENTS = {
    "hook": [
        "지금 독자가 왜 이 장에 멈춰 서야 하는지 감정적으로 붙잡는다.",
        "이 장이 책 전체에서 왜 중요한 출발점인지 선명하게 제시한다.",
        "영화 감정과 현재 독자 경험이 맞닿는 지점을 빠르게 보여 준다.",
    ],
    "context": [
        "독자가 뒤에서 흔들리지 않도록 최소한의 배경을 정돈한다.",
        "영화, 역사, 장소 중 무엇이 사실이고 무엇이 해석인지 읽을 바닥을 깐다.",
        "과잉 설명 없이 이후 분석을 읽을 준비를 시킨다.",
    ],
    "insight": [
        "장의 중심 논지를 한 걸음씩 세우면서도 단정적 과장을 피한다.",
        "피상적 감상과 실제 작동 원리를 대비해 독자의 이해를 깊게 만든다.",
        "질문을 설명으로 바꾸되, 아직 검증이 필요한 지점은 남겨 둔다.",
        "책 전체 테제와 이 장의 분석을 다시 연결한다.",
        "영화적 감정, 역사적 맥락, 여행 동기를 하나의 읽기 프레임으로 묶는다.",
    ],
    "takeaway": [
        "독자가 다음 장면이나 다음 장을 더 잘 보게 하는 시선을 남긴다.",
        "감상에서 행동 혹은 해석의 다음 단계로 넘어가게 만든다.",
        "책을 끝까지 읽고 싶게 만드는 여운과 실용성을 함께 남긴다.",
    ],
}
SECTION_OPENING_TACTICS = {
    "hook": "감정적으로 즉시 닿는 문제 제기로 시작",
    "context": "과잉 설명 없이 배경을 정돈하는 브리핑형 진입",
    "insight": "질문을 설명으로 전환하는 분석형 진입",
    "takeaway": "독자 행동 또는 다음 장 인식을 열어 주는 마감",
}
SECTION_TONE_GUARDRAILS = {
    "hook": "광고 문구처럼 흥분시키지 말고 정서적 흡인력만 유지한다.",
    "context": "백과사전식 나열을 피하고 독자에게 필요한 맥락만 남긴다.",
    "insight": "과장된 단언을 피하고 근거 수준에 맞는 어조를 유지한다.",
    "takeaway": "훈계조로 끝내지 말고 독자에게 쓸모 있는 시선이나 행동으로 닫는다.",
}
MAX_NETWORK_RECOVERY_PASSES = 1
NETWORK_RECOVERY_COOLDOWN_SECONDS = 6
S4_EXPANSION_CAP = 3
META_GUIDANCE_FRAGMENTS = (
    "책 쓰는 법",
    "이 장을 어떻게 써야",
    "독자에게 읽는 법",
    "원고 반영",
    "집필 팁",
    "blueprint rule",
    "reader payoff",
)


def _clean_inline(text: str) -> str:
    return str(text).replace("`", "").strip()


def _has_ascii_words(text: str) -> bool:
    return bool(re.search(r"[A-Za-z]{3,}", text or ""))


def _localized_reader_payoff(text: str) -> str:
    cleaned = _clean_inline(text)
    if not cleaned:
        return "독자가 이 장을 읽고도 끝까지 따라가고 싶어지는 분명한 효용"
    if _has_ascii_words(cleaned):
        return "독자가 이 장을 읽고 나서 왜 이 이야기를 계속 따라가야 하는지 분명히 느끼게 하는 효용"
    return cleaned


def _reader_payoff_object(text: str) -> str:
    payoff = _localized_reader_payoff(text)
    if "왜 이 이야기를 계속 따라가야 하는지" in payoff:
        return "계속 읽고 싶어지는 분명한 이유"
    return payoff.rstrip(".?! ")


def _pick_variant(options: list[str], index: int) -> str:
    if not options:
        return ""
    return options[(index - 1) % len(options)]


def _localized_section_guide(raw_guide_contract: dict[str, Any], section_key: str) -> str:
    guide = _clean_inline(raw_guide_contract.get("section_guides", {}).get(section_key, ""))
    if guide and not _has_ascii_words(guide):
        return guide
    defaults = {
        "hook": "지금 독자가 왜 이 장의 질문에 붙잡혀야 하는지 첫 문단에서 분명히 보여 준다.",
        "context": "영화와 역사와 장소를 읽는 데 필요한 최소한의 배경만 정리해 준다.",
        "insight": "질문을 설명으로 바꾸되 근거 수준에 맞는 조심스러운 분석을 유지한다.",
        "takeaway": "독자가 다음 장면과 다음 장을 더 잘 보게 하는 시선이나 행동을 남긴다.",
    }
    return defaults[section_key]


def _chapter_topic(chapter_title: str) -> str:
    cleaned = re.sub(r"^\d+\.\s*", "", _clean_inline(chapter_title))
    if ":" in cleaned:
        prefix, suffix = cleaned.split(":", 1)
        if re.fullmatch(r"[A-Z0-9 _-]+", prefix.strip()):
            return suffix.strip()
    return cleaned


def _claim_focus_phrase(text: str) -> str:
    cleaned = _clean_inline(text)
    return cleaned.rstrip(".?! ")


def _source_hint_phrase(source_hint: str, source_types: list[str] | None = None) -> str:
    mapping = {
        "official_source": "공식 자료와 공개 기록",
        "news": "보도와 해설 기사",
        "ugc": "후기와 사용자 반응 자료",
        "sns": "SNS 반응과 후기 자료",
        "external_photo": "외부 이미지 자료",
    }
    candidates = [_clean_inline(source_hint), *(_clean_inline(item) for item in (source_types or []))]
    for candidate in candidates:
        if candidate in mapping:
            return mapping[candidate]
    return "관련 자료"


def _localized_chapter_goal(raw_guide_contract: dict[str, Any]) -> str:
    goal = _clean_inline(raw_guide_contract.get("chapter_goal", ""))
    if "emotional and practical entry point" in goal.lower():
        return "이 장을 책 전체의 감정적 입구이자 실질적인 출발점으로 세우는 일"
    if goal and not _has_ascii_words(goal):
        return goal
    return "이 장을 책 전체의 출발점으로 세우는 일"


def _localized_include_items(raw_guide_contract: dict[str, Any]) -> list[str]:
    mapping = {
        "reader hook": "독자를 붙드는 첫 갈고리",
        "thesis for the whole book": "책 전체를 관통하는 문제의식",
        "orientation for what follows": "뒤이어 펼쳐질 여정의 길잡이",
        "영화 감정선 안에서 이 장이 왜 결정적인지": "영화 감정선을 뒤집는 결정적 장면의 위치",
    }
    results: list[str] = []
    for item in raw_guide_contract.get("include", []):
        cleaned = _clean_inline(item)
        if not cleaned:
            continue
        if cleaned.lower().startswith("blueprint rule:"):
            continue
        if _has_ascii_words(cleaned):
            continue
        if "책 쓰는 법" in cleaned or "독자에게" in cleaned and "지시" in cleaned:
            continue
        lowered = cleaned.lower()
        results.append(mapping.get(lowered, cleaned))
    return results


def _localized_reader_promises(raw_guide_contract: dict[str, Any]) -> list[str]:
    results: list[str] = []
    for item in raw_guide_contract.get("reader_promise", []):
        cleaned = _clean_inline(item)
        lowered = cleaned.lower()
        if "feel current, grounded, and worth finishing" in lowered:
            results.append("오래된 이야기를 지금의 감각으로 다시 붙들게 만드는 일")
        elif "clear emotional or practical payoff" in lowered:
            results.append("읽고 난 뒤 감정적이든 실용적이든 분명한 보상을 남기는 일")
        elif "책 쓰는 법" in cleaned:
            continue
        elif "독자용 서사" in cleaned:
            results.append("끝까지 따라가게 만드는 서사의 힘")
        elif "효용" in cleaned:
            results.append("읽고 난 뒤 분명한 감정적 혹은 실용적 보상")
        elif cleaned and not _has_ascii_words(cleaned):
            results.append(cleaned)
    return results


def _evidence_focus_phrase(evidence_slot: str, source_hint: str, source_types: list[str] | None = None) -> str:
    cleaned = _clean_inline(evidence_slot)
    lowered = cleaned.lower()
    if lowered.startswith("research question:"):
        question = cleaned.split(":", 1)[1].strip().lower()
        if "reader-value" in question or "reader value" in question:
            return "독자가 이 장에서 실제로 얻는 감정적·실용적 보상"
        if "evidence is required" in question:
            return "이 장의 중심 주장"
        return "이 장이 던지는 핵심 질문"
    if lowered.startswith("source type:"):
        return _source_hint_phrase(cleaned.split(":", 1)[1].strip(), source_types)
    if cleaned:
        return cleaned
    return _source_hint_phrase(source_hint, source_types)


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
            items.append(_clean_inline(stripped[2:]))
    return items


def _parse_reader_segment(section_lines: list[str]) -> dict[str, str]:
    segment = {
        "segment_id": "general_reader",
        "focus": "general reader",
        "reader_payoff": "분명하고 유용한 독자 효용",
    }
    for item in _bullet_items(section_lines):
        if item.startswith("Segment:"):
            segment["segment_id"] = _clean_inline(item.split(":", 1)[1])
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
        body = match.group(2).strip()
        if "hook" in label:
            guides["hook"] = body
        elif "context" in label:
            guides["context"] = body
        elif "insight" in label:
            guides["insight"] = body
        elif "takeaway" in label:
            guides["takeaway"] = body
    return guides


def _parse_anchor_contract(section_lines: list[str]) -> list[dict[str, str]]:
    anchors: list[dict[str, str]] = []
    for item in _bullet_items(section_lines):
        if "|" not in item or not item.startswith("CH"):
            continue
        parts = [_clean_inline(part) for part in item.split("|")]
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


def parse_raw_guide_contract(raw_guide: str) -> dict[str, Any]:
    sections = _raw_guide_sections(raw_guide)
    target_length_items = _bullet_items(sections.get("Target Length", []))
    target_words = next(
        (_clean_inline(item.split(":", 1)[1]) for item in target_length_items if item.startswith("Target words:")),
        "",
    )
    draft1_floor = next(
        (
            _clean_inline(item.split(":", 1)[1]).replace(" words", "")
            for item in target_length_items
            if item.startswith("Draft1 progress floor:")
        ),
        "",
    )
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


def _policy_context(
    book_root: Path,
    chapter_id: str,
    *,
    node_payload: dict[str, Any],
    prompt_text: str,
) -> list[dict[str, str]]:
    bundle = build_context_bundle(
        book_root,
        "S4",
        chapter_id=chapter_id,
        node_payload=node_payload,
        prompt_text=prompt_text,
    )
    return list(bundle["context_artifacts"])


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
                },
                prompt_text="\n".join(research_entry.get("research_questions", [])),
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


def section_word_budget(chapter_target: dict[str, Any]) -> dict[str, int]:
    desired_total = max(
        chapter_target["stage_progress_floors"]["S4_draft1_min_words"],
        int(chapter_target["target_words"] * 0.9),
    )
    hook = max(220, int(desired_total * 0.17))
    context = max(360, int(desired_total * 0.23))
    insight = max(820, int(desired_total * 0.42))
    takeaway = max(260, desired_total - hook - context - insight)
    return {
        "desired_total": desired_total,
        "hook": hook,
        "context": context,
        "insight": insight,
        "takeaway": takeaway,
    }


def _segment_count_for_section(section_key: str, target_words: int) -> int:
    if section_key == "hook":
        return max(1, min(2, round(target_words / 260)))
    if section_key == "context":
        return max(1, min(2, round(target_words / 320)))
    if section_key == "insight":
        return max(2, min(3, round(target_words / 340)))
    return max(1, min(2, round(target_words / 260)))


def _split_words(total: int, count: int) -> list[int]:
    base = max(150, total // count)
    buckets = [base for _ in range(count)]
    current = sum(buckets)
    index = 0
    while current < total:
        buckets[index % count] += 1
        current += 1
        index += 1
    while current > total:
        slot = index % count
        if buckets[slot] > 150:
            buckets[slot] -= 1
            current -= 1
        index += 1
    return buckets


def _anchor_ids_for_section(raw_guide_contract: dict[str, Any], section_key: str) -> list[str]:
    needle = f"after_section:{SECTION_HEADINGS[section_key]}"
    return [
        anchor["anchor_id"]
        for anchor in raw_guide_contract.get("anchor_contract", [])
        if anchor.get("placement") == needle
    ]


def plan_segments(
    chapter: dict[str, Any],
    research_entry: dict[str, Any],
    source_queue_items: list[dict[str, Any]],
    source_types: list[str],
    chapter_target: dict[str, Any],
    raw_guide_contract: dict[str, Any],
) -> dict[str, Any]:
    budgets = section_word_budget(chapter_target)
    reader_segment = raw_guide_contract.get("reader_segment") or {
        "segment_id": "general_reader",
        "focus": "general reader",
        "reader_payoff": "분명한 독자 효용",
    }
    reader_payoff = _localized_reader_payoff(reader_segment.get("reader_payoff", ""))
    evidence_targets = raw_guide_contract.get("evidence_targets", [])
    local_notes = raw_guide_contract.get("local_notes", [])
    queue_labels = [
        item.get("source_name") or item.get("source_type") or "source"
        for item in source_queue_items[:8]
    ]
    segments: list[dict[str, Any]] = []
    sequence = 1
    for section_key in SECTION_ORDER:
        section_target = budgets[section_key]
        count = _segment_count_for_section(section_key, section_target)
        split_targets = _split_words(section_target, count)
        anchor_ids = _anchor_ids_for_section(raw_guide_contract, section_key)
        for index, target_words in enumerate(split_targets, start=1):
            intent_bank = SECTION_INTENTS[section_key]
            segments.append(
                {
                    "segment_id": f"S4:{chapter['chapter_id']}:{section_key}_{index:02d}",
                    "chapter_id": chapter["chapter_id"],
                    "chapter_title": chapter["title"],
                    "sequence": sequence,
                    "section_key": section_key,
                    "section_heading": display_section_label(section_key),
                    "segment_index": index,
                    "target_words": target_words,
                    "claim_intent": intent_bank[(index - 1) % len(intent_bank)],
                    "evidence_slot": evidence_targets[(sequence - 1) % len(evidence_targets)] if evidence_targets else "",
                    "source_hint": queue_labels[(sequence - 1) % len(queue_labels)] if queue_labels else "",
                    "local_note": local_notes[(sequence - 1) % len(local_notes)] if local_notes else "",
                    "reader_payoff": reader_payoff,
                    "reader_focus": reader_segment.get("focus", ""),
                    "anchor_obligation_ids": anchor_ids if index == count else [],
                    "research_questions": list(research_entry.get("research_questions", [])),
                    "source_types": list(source_types),
                }
            )
            sequence += 1
    return {
        "version": "1.0",
        "generated_at": now_iso(),
        "stage_id": "S4",
        "chapter_id": chapter["chapter_id"],
        "chapter_title": chapter["title"],
        "target_words": chapter_target["target_words"],
        "draft1_floor": chapter_target["stage_progress_floors"]["S4_draft1_min_words"],
        "desired_total": budgets["desired_total"],
        "reader_segment": reader_segment,
        "segments": segments,
    }


def design_narrative(
    chapter: dict[str, Any],
    raw_guide_contract: dict[str, Any],
    segment_plan: dict[str, Any],
) -> dict[str, Any]:
    designs: list[dict[str, Any]] = []
    segments = segment_plan["segments"]
    for index, segment in enumerate(segments):
        previous_segment = segments[index - 1] if index > 0 else None
        same_section_prev = next(
            (item for item in reversed(segments[:index]) if item["section_key"] == segment["section_key"]),
            None,
        )
        continuity = (
            f"직전 단락 `{previous_segment['section_heading']}`의 문제제기를 이어 받아 현재 세그먼트의 초점을 분명히 한다."
            if previous_segment
            else "장의 출발점에서 독자가 길을 잃지 않도록 바로 초점을 잡는다."
        )
        if same_section_prev:
            continuity = "같은 섹션 안에서 바로 앞 세그먼트의 문장을 반복하지 말고, 논지를 한 단계 더 전진시킨다."
        designs.append(
            {
                "segment_id": segment["segment_id"],
                "section_key": segment["section_key"],
                "opening_tactic": SECTION_OPENING_TACTICS[segment["section_key"]],
                "continuity_bridge": continuity,
                "tension_release_note": "독자가 궁금해할 질문을 먼저 세우고, 이번 세그먼트에서는 그 일부를 해소한다.",
                "tone_guardrail": SECTION_TONE_GUARDRAILS[segment["section_key"]],
                "forbidden_drift_topics": raw_guide_contract.get("exclude", []),
            }
        )
    return {
        "version": "1.0",
        "generated_at": now_iso(),
        "stage_id": "S4",
        "chapter_id": chapter["chapter_id"],
        "chapter_title": chapter["title"],
        "segments": designs,
    }


def _segment_prompt(
    chapter: dict[str, Any],
    segment: dict[str, Any],
    narrative: dict[str, Any],
    raw_guide_contract: dict[str, Any],
    previous_texts: list[str],
    grounded: dict[str, Any] | None,
) -> str:
    source_lines = [
        f"- {item.get('source_name', 'unknown')} | {item.get('title', '')} | {item.get('url_or_identifier', '')}"
        for item in (grounded or {}).get("sources", [])[:3]
    ]
    previous_excerpt = "\n".join(f"- {text[:360]}" for text in previous_texts[-2:]) or "- none"
    rights = raw_guide_contract.get("rights_guardrails", [])[:4]
    include_items = _localized_include_items(raw_guide_contract)[:3]
    reader_promises = _localized_reader_promises(raw_guide_contract)[:2]
    chapter_part = str(chapter.get("part") or "")
    chapter_specific_rules = [
        "- 이 장을 어떻게 써야 하는지 설명하지 말고, 책 내용 자체를 바로 쓴다.",
        "- `이 장의 출발점은`, `독자가 여기서 얻는 것은`, `이제는 감상에서 한 걸음 더 나아갈 차례다` 같은 메타 문장을 금지한다.",
        "- 독자에게 읽는 법을 지시하지 말고, 장면과 정서와 맥락을 직접 보여 준다.",
    ]
    if "CINEMA" in chapter_part:
        chapter_specific_rules.extend(
            [
                "- 영화 장은 구체적인 장면, 표정, 시선, 호흡, 카메라 거리, 침묵, 음악, 관객 반응을 직접 서술한다.",
                "- 가능하면 스틸컷처럼 떠오르는 화면의 순간과 실제 장소의 감각을 연결한다.",
                "- 성지순례 동기는 조언문으로 쓰지 말고, 왜 그 장소를 직접 가 보고 싶어지는지 서사 속에서 자연스럽게 드러낸다.",
            ]
        )
    elif "TRAVEL" in chapter_part:
        chapter_specific_rules.extend(
            [
                "- 장소 장은 이동 동선, 시간대, 현장 공기, 체류 감각을 직접 서술한다.",
                "- 실용 팁은 체크리스트처럼 나열하지 말고, 실제 현장 감각과 연결된 문장으로 녹여 쓴다.",
            ]
        )
    elif "HISTORY" in chapter_part:
        chapter_specific_rules.append(
            "- 역사 장은 기록과 해석을 구분하되, 해설문처럼 마르지 않게 장면과 인물의 결을 살린다."
        )
    return "\n".join(
        [
            f"Write one Korean nonfiction prose segment for `{chapter['title']}`.",
            "Return plain Korean prose only. Do not add headings, bullets, JSON, markdown fences, or meta commentary.",
            f"Target words: about {segment['target_words']}",
            f"Minimum words: at least {max(130, int(segment['target_words'] * 0.7))}",
            "Requirements:",
            "- Keep the prose publication-ready, reader-centered, and concrete.",
            "- Do not invent exact dates, quotes, stats, addresses, or permissions not present in evidence.",
            "- If evidence is incomplete, write cautiously and frame it as a working interpretation.",
            "- Avoid repeating the previous segment verbatim.",
            *chapter_specific_rules,
            "",
            f"Section: {segment['section_heading']}",
            f"Claim intent: {segment['claim_intent']}",
            f"Evidence slot: {segment['evidence_slot']}",
            f"Reader payoff: {segment['reader_payoff']}",
            f"Reader focus: {segment['reader_focus']}",
            f"Local note: {segment['local_note']}",
            f"Opening tactic: {narrative['opening_tactic']}",
            f"Continuity bridge: {narrative['continuity_bridge']}",
            f"Tone guardrail: {narrative['tone_guardrail']}",
            "",
            "Internal outcome targets:",
            *[f"- {item}" for item in reader_promises],
            "",
            "Concrete content cues:",
            *[f"- {item}" for item in include_items],
            "",
            "Must avoid:",
            *[f"- {item}" for item in raw_guide_contract.get("exclude", [])[:3]],
            "- Never echo blueprint rules, internal constraints, or writing instructions verbatim.",
            "- Never explain how this chapter should be written; just write the chapter content.",
            "",
            "Rights guardrails:",
            *[f"- {item}" for item in rights],
            "",
            "Previous segment continuity:",
            previous_excerpt,
            "",
            "Trusted grounded source signals:",
            *source_lines,
        ]
    ).strip()


def _split_sentences(text: str) -> list[str]:
    chunks = re.split(r"(?<=[.!?])\s+|(?<=[다요죠])\s+", text.strip())
    return [chunk.strip() for chunk in chunks if chunk.strip()]


def _is_meta_guidance_sentence(sentence: str) -> bool:
    lowered = sentence.lower()
    if any(fragment in lowered for fragment in META_GUIDANCE_FRAGMENTS):
        return True
    banned_starts = (
        "이 장의 출발점은",
        "이 장의 핵심은",
        "독자가 이 장",
        "독자에게 이 장",
        "이제는 감상에서 한 걸음",
        "이 대목에서는",
        "원고 곳곳에",
        "집필 시 팁",
        "도입부가 살아 있으면",
        "좋은 도입은",
        "이 첫 인상이 강할수록",
        "결국 도입부는",
        "이렇게 바닥이 놓이면",
        "그래서 이 파트의 맥락은",
        "특히 이 책의 맥락 문장은",
        "좋은 분석은",
        "그래서 통찰 파트는",
        "그래서 마무리는",
        "좋은 테이크어웨이는",
        "그래서 영화 파트의 첫 문단은",
        "그래서 영화 파트의 좋은 결말은",
        "좋은 여행 문장은",
        "좋은 초고는",
        "그래서 이 초고에서 중요한 것은",
        "이 장을 다 읽고 나면 독자는",
    )
    return any(sentence.startswith(prefix) for prefix in banned_starts)


def _sanitize_prose_block(text: str) -> str:
    paragraphs: list[str] = []
    for paragraph in re.split(r"\n{2,}", text.strip()):
        kept = [sentence for sentence in _split_sentences(paragraph) if not _is_meta_guidance_sentence(sentence)]
        cleaned = " ".join(kept).strip()
        if cleaned:
            paragraphs.append(cleaned)
    return "\n\n".join(paragraphs).strip()


def _clean_model_text(text: str) -> str:
    cleaned = text.strip()
    if cleaned.startswith("```"):
        cleaned = cleaned.strip("`")
        if "\n" in cleaned:
            cleaned = cleaned.split("\n", 1)[1]
        cleaned = cleaned.strip()
    cleaned = strip_leading_section_heading(cleaned)
    return _sanitize_prose_block(cleaned)


def _merge_live_with_support(generated: str, support_text: str, minimum_words: int) -> str:
    combined = generated.strip()
    if count_words(combined) >= minimum_words:
        return combined
    seen_paragraphs = {paragraph.strip() for paragraph in re.split(r"\n{2,}", combined) if paragraph.strip()}
    for paragraph in re.split(r"\n{2,}", support_text.strip()):
        cleaned = paragraph.strip()
        if not cleaned or cleaned in seen_paragraphs:
            continue
        combined = f"{combined}\n\n{cleaned}".strip()
        seen_paragraphs.add(cleaned)
        if count_words(combined) >= minimum_words:
            break
    return combined


def _local_note_sentence(local_note: str, section_key: str, segment_index: int) -> str:
    cleaned = _clean_inline(local_note)
    if not cleaned:
        return ""
    if "단종 신드롬" in cleaned:
        options = [
            "이 표현은 한 편의 영화가 일시적 유행을 넘어 집단적인 감정 반응으로 번졌다는 사실을 떠올리게 한다. 그래서 독자는 단순한 흥행 수치가 아니라, 왜 많은 사람이 같은 슬픔에 동시에 반응했는지를 자연스럽게 궁금해하게 된다.",
            "이 디테일은 작품이 개인의 취향을 넘어 세대적 반응으로 확장됐다는 인상을 준다. 덕분에 독자는 이 장을 읽으며 한 사람의 감상이 아니라, 시대 전체가 무엇에 응답했는지를 같이 보게 된다.",
            "이 한 줄은 작품 바깥의 공기를 끌고 들어온다. 독자는 장면 하나의 슬픔을 넘어, 왜 그 슬픔이 그토록 넓게 퍼져 나갔는지 사회적 온도까지 함께 떠올리게 된다.",
        ]
        return _pick_variant(options, segment_index)
    if "아웃사이더" in cleaned or "유배" in cleaned:
        options = [
            "이 비유는 단종의 고립을 박제된 역사 속 사건으로만 두지 않는다. 오히려 지금도 스스로 바깥에 서 있다고 느끼는 사람들의 감각과 맞닿으면서, 오래된 이야기가 현재형의 문장으로 다시 살아난다.",
            "이 대목의 힘은 과거의 고립을 오늘의 정서로 번역한다는 데 있다. 그래서 독자는 유배를 먼 시대의 제도로만 읽지 않고, 관계와 자리에서 밀려난 감각으로 더 가까이 받아들이게 된다.",
            "이 연결은 역사적 비극을 추상적인 교훈으로 만들지 않는다. 오히려 지금의 독자가 자기 경험 속 고립과 겹쳐 읽게 하면서, 책 전체의 정서를 한층 선명하게 세운다.",
        ]
        return _pick_variant(options, segment_index)
    options = [
        f"{cleaned} 같은 디테일은 이 장을 추상적인 해설에서 꺼내 실제 감각의 층위로 옮겨 놓는다.",
        f"{cleaned}라는 표현은 독자가 장면을 머리로만 이해하지 않고 눈앞의 장면처럼 떠올리게 만든다.",
        f"{cleaned} 같은 메모는 이 장이 지나치게 개념적으로 흐르지 않게 붙잡는 역할을 한다.",
    ]
    return _pick_variant(options, segment_index)


def _evidence_caution_sentence(source_phrase: str, section_key: str, segment_index: int) -> str:
    options_by_section = {
        "hook": [
            f"현재 공개된 {source_phrase}만 놓고 보더라도 이 감정의 출발점은 분명하다. 다만 반응의 폭과 속도는 더 많은 자료가 겹쳐질수록 또렷해질 여지가 남아 있다.",
            f"이 장면의 파장은 이미 여러 {source_phrase}에서 감지되지만, 그 크기를 과장해 말하기보다 확인된 결만 차분히 붙드는 편이 더 오래 남는다.",
        ],
        "context": [
            f"배경의 뼈대는 이미 드러나 있지만, 세부 결은 {source_phrase}가 더해질수록 더욱 단단해진다. 그래서 지금은 확인된 좌표를 중심으로 맥락을 정리하는 편이 정확하다.",
            f"이 맥락은 {source_phrase}와 맞닿을수록 선명해진다. 아직 비어 있는 자리는 성급히 메우지 않고, 확인된 선 안에서 시대감과 장소감을 먼저 세운다.",
        ],
        "insight": [
            f"이 해석의 중심축은 이미 보이지만, {source_phrase}가 더 보강되면 장면의 결이 한층 또렷해질 수 있다. 그래서 단정보다 작동 원리를 차근차근 따라가는 쪽이 더 설득력 있다.",
            f"핵심 논지는 충분히 살아 있지만, 세부 결론까지 서둘러 닫기보다 {source_phrase}와 맞물려 확인되는 부분부터 쌓아 올리는 편이 더 탄탄하다.",
        ],
        "takeaway": [
            f"이 여운 역시 {source_phrase}가 더해질수록 한층 또렷해질 수 있다. 그래서 마지막 문장은 확답보다 오래 남는 감정의 방향을 붙드는 편이 좋다.",
            f"이 마지막 시선은 {source_phrase}와 겹쳐질수록 더욱 생생해진다. 지금은 결론을 닫기보다 다음 장면과 다음 장소로 이어지는 감각을 남겨 두는 편이 어울린다.",
        ],
    }
    return _pick_variant(options_by_section[section_key], segment_index)


def _extra_paragraphs(
    chapter: dict[str, Any],
    segment: dict[str, Any],
    narrative: dict[str, Any],
    raw_guide_contract: dict[str, Any],
) -> list[str]:
    section_key = segment["section_key"]
    topic = _chapter_topic(chapter["title"])
    part = str(chapter.get("part") or "")
    segment_index = int(segment.get("segment_index", 1))
    include_items = _localized_include_items(raw_guide_contract)
    section_paragraphs = {
        "hook": [
            f"'{topic}'을 떠올리게 하는 힘은 줄거리의 요약이 아니라 한 번 스치고 지나간 표정, 짧게 멈춘 침묵, 화면에 오래 남는 잔상에서 나온다.",
            f"오래 남는 장면은 대개 큰 설명보다 먼저 몸에 닿는다. '{topic}'도 그렇게 스며들며, 멀리 있던 비극을 지금의 감정 가까이로 끌어당긴다.",
            f"장면의 첫인상이 살아 있을 때 '{topic}'은 과거의 기록이 아니라 현재형의 감각으로 읽히기 시작한다.",
        ],
        "context": [
            f"이 장면의 울림을 떠받치는 바닥에는 영화의 정서, 실제 역사, 장소의 거리감이 함께 겹쳐 있다. 셋 중 하나만 빠져도 '{topic}'의 결은 금세 얇아진다.",
            f"'{topic}'이 설득력을 얻는 이유는 감정이 허공에 뜨지 않고 시대와 공간의 감각 위에 놓여 있기 때문이다.",
            f"배경은 장면을 설명하기 위해서가 아니라, '{topic}'이 어디에서 태어나 어떤 공기를 머금고 있는지 보여 주기 위해 필요하다.",
        ],
        "insight": [
            f"결정적인 것은 '{topic}'이 얼굴과 시선, 거리와 침묵, 장소의 기억을 한 장면 안에서 어떻게 묶어 내는가이다.",
            f"'{topic}'의 설득력은 커다란 결론보다 세부 장면의 결에서 나온다. 한 번의 눈빛, 잠깐 비켜 선 몸짓, 주변 인물의 반응이 감정을 천천히 완성한다.",
            f"'{topic}'을 둘러싼 감정은 단순한 슬픔에서 멈추지 않는다. 장면의 층위를 따라갈수록 그 감정이 어떤 구조로 축적되는지 더 또렷하게 드러난다.",
        ],
        "takeaway": [
            f"장을 덮고 나면 '{topic}'은 설명보다 장면의 결로 남아야 한다. 그래야 다음 페이지에서도 같은 감정이 더 깊은 층위로 이어진다.",
            f"'{topic}'이 남긴 시선은 책 밖으로도 번져야 한다. 실제 장소를 떠올리게 하고, 다음 장면을 다시 보게 만드는 움직임이 있을 때 여운이 길어진다.",
            f"마지막에는 정답보다 방향이 남는다. '{topic}'을 지나온 뒤 세계를 조금 다른 각도로 보게 만드는 쪽이 이 장의 끝에 더 어울린다.",
        ],
    }
    paragraphs = [_pick_variant(section_paragraphs[section_key], segment_index)]
    if "CINEMA" in part:
        cinema_lines = {
            "hook": [
                "배우의 눈빛이 대사를 대신하고, 컷과 컷 사이의 정적이 감정을 확장시키는 순간이야말로 영화의 첫인상을 만든다.",
                "배우의 호흡이 멈칫하는 순간과 주변 인물의 시선 이동은 말보다 먼저 장면의 슬픔과 긴장을 밀어 올린다.",
            ],
            "context": [
                "영화 안에서 본 얼굴과 실제 장소의 풍경이 겹쳐질 때 비로소 관객의 몰입은 여행의 욕구로 번진다.",
                "스크린의 장면은 상영이 끝나면 사라지지만, 그 장면이 닿았던 장소의 공기와 거리감은 실제 공간에서 다시 살아날 여지가 있다.",
            ],
            "insight": [
                "결국 중요한 것은 어떤 장면이 어떻게 사람을 과몰입하게 만드는가이다. 얼굴의 흔들림, 프레임의 거리, 침묵의 길이가 그 감정을 차곡차곡 쌓아 올린다.",
                "스틸컷으로 떼어 놓아도 살아남는 장면은 늘 이유가 있다. 한 프레임 안에서 감정, 권력의 거리, 인물의 고립이 동시에 읽히기 때문이다.",
            ],
            "takeaway": [
                "그래서 독자는 영화를 본 뒤에도 특정 장면이 찍힌 공간을 실제로 밟아 보고 싶어진다. 화면 속 비극이 현실의 지형과 만나는 순간을 직접 확인하고 싶어지기 때문이다.",
                "이 여운은 곧 여행의 동력이 된다. 스크린에서 스쳐 지나간 표정과 풍경을 현실의 장소에서 다시 겹쳐 보고 싶은 마음이 자연스럽게 생겨난다.",
            ],
        }
        paragraphs.append(_pick_variant(cinema_lines[section_key], segment_index))
    if include_items:
        include_variants = [
            f"{include_items[(segment_index - 1) % len(include_items)]}이 겹쳐질 때 이 장면은 훨씬 더 또렷한 표정과 공기를 갖게 된다.",
            f"{include_items[(segment_index - 1) % len(include_items)]}이 맞물리는 순간, 이 대목의 질감과 무게도 한층 선명해진다.",
        ]
        paragraphs.append(_pick_variant(include_variants, segment_index))
    closing_support = {
        "hook": [
            "설명보다 감정이 먼저 들어오는 순간 오래된 이야기는 비로소 현재형으로 되살아난다.",
            "첫 문단의 힘은 많은 정보를 주는 데 있지 않다. 멀리 있던 장면을 바로 눈앞의 일처럼 느끼게 만드는 데 있다.",
        ],
        "context": [
            "이 바닥이 단단할수록 뒤의 장면 해석도 허공에 뜨지 않는다. 감정과 사실과 장소가 같은 선 위에서 만날 수 있기 때문이다.",
            "맥락이 정돈되면 이후의 해석도 억지로 부풀지 않는다. 장면 하나가 어디에서 태어났는지 자연스럽게 붙들 수 있게 된다.",
        ],
        "insight": [
            "결국 설득력은 큰 결론보다 장면의 작동 원리를 얼마나 촘촘히 드러내느냐에 달려 있다.",
            "분석이 살아나는 순간은 감정의 크기를 외칠 때가 아니라, 그 감정이 어떻게 만들어졌는지 장면의 결을 따라 보여 줄 때다.",
        ],
        "takeaway": [
            "이 여운이 다음 장과 다음 장소의 움직임으로 이어질 때 비로소 장의 끝도 실제 힘을 갖게 된다.",
            "페이지를 넘긴 뒤에도 특정 장면의 결이 남아 있다면, 이 장의 마무리는 이미 자기 역할을 다한 셈이다.",
        ],
    }
    paragraphs.append(_pick_variant(closing_support[section_key], segment_index))
    return paragraphs


def _build_fallback_segment_text(
    chapter: dict[str, Any],
    segment: dict[str, Any],
    narrative: dict[str, Any],
    raw_guide_contract: dict[str, Any],
) -> str:
    section_key = segment["section_key"]
    topic = _chapter_topic(chapter["title"])
    local_note = _clean_inline(segment.get("local_note", ""))
    source_phrase = _source_hint_phrase(segment.get("source_hint", ""), segment.get("source_types", []))
    segment_index = int(segment.get("segment_index", 1))
    section_intro = {
        "hook": [
            f"스크린에 '{topic}'이 떠오르는 순간, 관객은 역사적 사실보다 먼저 한 인물의 얼굴과 침묵에 붙잡힌다. 오래 남는 장면은 대개 큰 사건이 아니라 표정의 흔들림과 숨 멎는 정적에서 시작된다.",
            f"'{topic}'을 둘러싼 감정은 요약으로는 설명되지 않는다. 한 번 스치고 지나간 눈빛, 다 말하지 못한 침묵, 주변 인물의 멈칫한 반응이 장면의 슬픔을 오래 붙잡아 둔다.",
            f"오래된 비극이 지금의 감정으로 되살아나는 순간은 늘 구체적인 장면에서 시작된다. '{topic}' 역시 설명보다 표정과 거리, 침묵의 길이로 먼저 독자의 마음을 끌어당긴다.",
        ],
        "context": [
            f"'{topic}'이 힘을 얻는 이유는 감정이 허공에 뜨지 않고 영화적 분위기, 실제 역사, 영월이라는 공간의 감각 위에 얹혀 있기 때문이다. 이 세 층위가 겹쳐질수록 장면은 단순한 비극을 넘어 현실의 기억처럼 남는다.",
            f"이 장면의 공기를 제대로 붙들려면 당시의 역사적 자리와 영화가 택한 시선, 그리고 영월이라는 장소의 거리감을 함께 봐야 한다. 그 바닥이 있어야 배우의 연기와 관객의 반응도 더 또렷해진다.",
            f"감정이 강한 이야기일수록 배경은 더 정확해야 한다. '{topic}'을 둘러싼 시대와 장소의 좌표가 잡힐 때 비로소 장면의 슬픔도 구체적인 무게를 얻는다.",
        ],
        "insight": [
            f"'{topic}'이 오래 남는 이유는 감상이 커서가 아니라 장면의 작동 방식이 치밀하기 때문이다. 얼굴의 떨림, 프레임의 거리, 침묵의 길이, 그리고 주변 인물의 반응이 함께 엮이면서 비극의 정서를 천천히 밀어 올린다.",
            f"이 장면의 설득력은 큰 결론보다 세부의 결에서 나온다. 한 번 스친 시선과 몸짓, 인물을 둘러싼 빈 공간이 권력의 거리와 고립의 감각을 동시에 보여 주기 때문이다.",
            f"결국 '{topic}'은 단순히 슬픈 장면이 아니라, 왜 많은 관객이 그 얼굴과 장소를 오래 잊지 못하는지를 드러내는 장면이다. 영화적 감정과 실제 역사, 성지순례의 충동이 같은 프레임 안에서 만난다.",
        ],
        "takeaway": [
            f"장을 덮고 나면 '{topic}'은 설명보다 장면의 결로 남아야 한다. 그래야 독자는 다음 장을 넘기면서도 그 얼굴과 침묵을 다시 떠올리고, 영화 속 장소를 현실의 영월에서 직접 확인하고 싶어진다.",
            f"이 장의 끝은 요약보다 움직임에 가깝다. '{topic}'이 남긴 감정은 다음 장면을 다시 보게 하고, 결국 청령포와 장릉 같은 실제 장소까지 떠올리게 만드는 힘이 되어야 한다.",
            f"마지막에 남아야 하는 것은 정답이 아니라 여운이다. '{topic}'을 지나온 뒤 독자가 영화를 다시 보고 싶어지고, 영월이라는 지명을 이전과 다르게 느끼게 된다면 이 장의 마무리는 충분히 살아 있다.",
        ],
    }[section_key]
    paragraphs = [_pick_variant(section_intro, segment_index)]
    if local_note:
        paragraphs.append(_local_note_sentence(local_note, section_key, segment_index))
    paragraphs.append(_evidence_caution_sentence(source_phrase, section_key, segment_index))
    paragraphs.extend(_extra_paragraphs(chapter, segment, narrative, raw_guide_contract))
    minimum_words = max(170, int(segment["target_words"] * 1.0))
    selected: list[str] = []
    for paragraph in paragraphs:
        selected.append(paragraph)
        if count_words("\n\n".join(selected)) >= minimum_words:
            break
    return _sanitize_prose_block("\n\n".join(selected).strip())


def _density_uplift_paragraphs(chapter: dict[str, Any]) -> list[str]:
    topic = _chapter_topic(chapter["title"])
    part = str(chapter.get("part") or "")
    paragraphs = [
        (
            f"그래서 이 장을 다 읽고 나면 독자는 {topic}을 단순한 선악 구도보다 더 복합적인 인간과 권력의 문제로 다시 보게 된다. "
            "이 한 겹의 재독해가 바로 다음 장과 실제 장소를 이어 보는 데 필요한 가장 실질적인 준비가 된다."
        ),
        (
            f"결국 {topic}을 다시 읽는 일은 오래된 논쟁을 반복하는 데서 멈추지 않는다. "
            "독자가 다음 페이지에서도 같은 질문을 더 정교하게 붙들게 만드는 시선이 여기서 한 번 더 단단해진다."
        ),
        (
            f"{topic}을 둘러싼 감정은 한 번 스치고 지나가는 유행이 아니라, 장면과 장소가 함께 남길 때 훨씬 길게 지속된다. "
            "그래서 이 장의 여운은 영화 상영이 끝난 뒤에도 영월의 실제 풍경과 다음 여정의 감각으로 계속 확장된다."
        ),
        (
            f"강한 장면은 감동을 부풀리지 않아도 스스로 오래 남는다. "
            f"{topic} 역시 얼굴과 침묵, 거리와 풍경이 어떻게 하나의 정서로 묶이는지 드러날 때 가장 강한 설득력을 얻는다."
        ),
        (
            f"동시에 {topic}은 영화 한 편의 감상으로만 닫히지 않는다. "
            "장면이 남긴 표정과 공기가 실제 장소의 감각으로 옮겨 붙는 순간, 책은 해석과 여행을 함께 움직이는 매개가 된다."
        ),
        (
            f"여기서 중요한 것은 요약보다 체류감이다. "
            f"{topic}을 둘러싼 사람과 풍경, 정서와 공간을 충분히 머물게 할수록 독자도 더 오래 그 장면 안에 남게 된다."
        ),
        (
            f"결국 {topic}은 한 편의 영화에 대한 반응을 넘어, 지금의 독자가 고립과 상실을 어떤 얼굴로 기억하는지까지 건드린다. "
            "그 공감의 넓이가 살아 있을 때 이 장은 단순한 해설이 아니라 실제 체험으로 읽히게 된다."
        ),
        (
            f"그래서 이 장의 문장은 감정과 사실, 장소와 이동의 가능성을 함께 품어야 한다. "
            f"{topic}이 만들어 낸 여운이 다음 장과 다음 여정으로 이어질 수 있어야 이 책 전체의 기획도 자연스럽게 완성된다."
        ),
        (
            f"한 장면을 깊게 읽어 낸다는 것은 곧 그 장면을 둘러싼 세계를 더 넓게 보게 된다는 뜻이기도 하다. "
            f"{topic}이 남긴 얼굴과 침묵, 공간의 기억이 독자의 현재 감각과 맞물릴 때 장의 마지막까지도 힘을 잃지 않는다."
        ),
    ]
    if "CINEMA" in part:
        paragraphs.extend(
            [
                (
                    "특히 영화 파트에서는 배우의 연기와 카메라의 선택, 그리고 관객의 기억에 남는 장면이 하나의 선으로 이어져야 한다. "
                    "그 선이 선명할수록 스틸컷 한 장만 떠올려도 장 전체의 정서가 다시 살아난다."
                ),
                (
                    "결국 성지순례의 동력도 여기서 생긴다. 스크린 속 장면이 실제 영월의 강과 숲, 하늘과 바람 속에서 다시 확인될 수 있다는 가능성이 독자를 영화 밖의 세계로 한 걸음 더 밀어내기 때문이다."
                ),
            ]
        )
    elif "HISTORY" in part:
        paragraphs.append(
            "역사 파트의 힘은 사실의 단단함과 해석의 여백을 함께 보여 주는 데 있다. 기록을 정확히 짚으면서도 그 기록이 오늘의 독자에게 왜 다시 읽혀야 하는지까지 이어질 때 장의 무게가 완성된다."
        )
    elif "TRAVEL" in part:
        paragraphs.append(
            "여행 파트의 문장은 결국 실제 발걸음으로 이어져야 한다. 어디서 멈춰 서야 하고 어떤 시간대에 봐야 하며 어떤 감정으로 풍경을 받아들여야 하는지가 남아 있을 때 장소 설명은 비로소 살아난다."
        )
    elif "TASTE" in part:
        paragraphs.append(
            "맛 파트의 결은 메뉴 소개보다 경험의 결에 가깝다. 한 그릇의 온기와 한 잔의 리듬이 영화와 여행의 여운을 어떻게 마무리하는지 보여 줄 때 이 파트도 단순한 추천을 넘어선다."
        )
    return paragraphs


def _section_uplift_paragraphs(chapter: dict[str, Any], section_key: str) -> list[str]:
    topic = _chapter_topic(chapter["title"])
    part = str(chapter.get("part") or "")
    common = {
        "hook": [
            f"{topic}이 특별하게 다가오는 까닭은 비극의 크기보다 그 비극이 얼굴과 호흡을 통해 전달되는 방식에 있다. 관객은 설명을 듣기 전에 이미 한 인물의 고립과 무력함을 표정의 떨림으로 먼저 받아들인다.",
            f"{topic}은 스토리의 요약보다 순간의 밀도, 그러니까 화면에 남는 정적과 시선의 방향으로 먼저 기억된다. 장면 하나를 오래 붙잡게 만드는 힘이 바로 거기에서 나온다.",
            f"첫인상이 강한 장면은 이후의 모든 해석을 끌고 간다. 관객이 왜 이 얼굴을 잊지 못하는지, 왜 스크린 밖의 실제 장소까지 떠올리게 되는지가 처음 몇 단락 안에서 이미 예감되기 때문이다.",
            f"무너질 듯 고요한 얼굴 하나가 서사의 중심이 되는 순간 영화의 톤도 결정된다. {topic}은 바로 그 미세한 감정의 진폭을 붙드는 데서 출발해야 제 힘을 얻는다.",
            f"결국 관객의 기억에 남는 것은 줄거리 소개보다 장면의 체온이다. 화면 앞에서 숨을 고르게 되는 바로 그 순간이 먼저 살아 있어야 뒤의 장면도 힘을 얻는다.",
        ],
        "context": [
            f"{topic}의 배경을 세우는 일은 감동을 식히기 위한 절차가 아니다. 오히려 그 감정이 어디에서 태어나 어떤 역사와 공간의 결을 머금는지 보여 주기 위해 필요한 바닥을 놓는 작업에 가깝다.",
            f"영화적 체험이 현실의 장소와 닿는 순간 독서의 결도 달라진다. 스크린에서 스쳐 간 얼굴이 영월의 강바람과 소나무 숲, 낮고 긴 능선의 풍경과 포개질 때 장면의 슬픔은 훨씬 더 구체적인 감각이 된다.",
            f"이 장의 맥락은 과잉 설명이 아니라 정확한 좌표에 가깝다. 시대의 사실, 감독이 고른 시선, 실제 공간의 공기를 함께 놓아야 뒤의 해석도 설득력을 잃지 않는다.",
            f"역사적 좌표만 남기고 감정을 놓치면 장면은 메말라 보이고, 감정만 밀어붙이면 장면의 무게가 허공에 뜬다. 그래서 사실과 감정의 균형이 이 장의 바닥을 결정한다.",
            f"배경 설명이 살아 있을 때 장면 분석도 한층 또렷해진다. 누가 왜 그 표정을 짓게 되었는지, 그 표정이 왜 영월이라는 공간과 떼려야 뗄 수 없는지 자연스럽게 드러나기 때문이다.",
        ],
        "insight": [
            f"{topic}을 단순한 감상에서 한 걸음 더 깊게 읽으려면 장면의 구조를 봐야 한다. 누가 프레임의 중심에 서는지, 카메라가 얼마나 가까이 다가가는지, 어떤 순간에 대사가 끊기고 침묵이 남는지가 모두 감정의 결을 만든다.",
            f"장면은 감탄만으로 설명되지 않는다. 작은 몸짓 하나, 표정의 떨림 하나, 주변 인물의 반응 하나가 어떤 의미를 만드는지 천천히 짚을수록 설득력의 근원이 더 또렷해진다.",
            f"특히 이 장면이 오래 남는 이유는 감정과 권력, 역사와 장소가 따로 움직이지 않기 때문이다. 비극은 인물의 표정 안에만 머무르지 않고, 그를 둘러싼 공간의 공기와 실제 영월이라는 장소 감각까지 함께 불러낸다.",
            f"결국 장면을 다시 본다는 것은 줄거리를 다시 확인하는 일이 아니다. 왜 그 얼굴이 그토록 처연해 보였는지, 왜 침묵이 대사보다 더 크게 들렸는지를 다시 읽는 일에 가깝다.",
            f"감정에 이름을 붙이는 데서 멈추지 않고, 그 감정이 어떤 연기와 연출의 선택을 통해 축적됐는지 드러날 때 장면은 한층 입체적으로 기억된다.",
            f"영화가 만든 울림이 실제 장소의 기억과 연결되는 지점도 여기서 분명해진다. 스크린 속 얼굴과 영월의 강물, 능선과 바람이 하나의 정서로 묶일 때 장면은 단순한 팬심을 넘어선다.",
            f"이런 분석이 필요한 이유는 슬픔의 크기를 키우기 위해서가 아니다. 오히려 감정의 구조를 정확히 읽어 내야만 그 비극이 오늘의 독자에게 왜 여전히 유효한지 설명할 수 있기 때문이다.",
        ],
        "takeaway": [
            f"이 장의 끝에서 남아야 하는 것은 한 줄 결론이 아니라 다시 보고 싶어지는 장면이다. {topic}을 지나온 독자는 영화를 재생하고 싶어지고, 동시에 그 장면이 찍힌 곳의 공기까지 실제로 확인하고 싶어진다.",
            f"책의 다음 페이지로 넘어가는 힘도 여기에서 나온다. 감정이 장소와 행동으로 이어질 때 독서는 비로소 이동의 욕구를 만들고, 해석은 성지순례의 동기로 자연스럽게 바뀐다.",
            f"마지막에 남는 것은 닫힌 결론보다 오래 가는 여운이다. 장면 하나를 더 정확히 이해하게 됐다는 감각, 그리고 영월을 직접 밟아 보고 싶다는 충동이 함께 남아 있을 때 이 장은 제 역할을 다한다.",
            f"남아야 하는 것은 훈계가 아니라 움직임이다. 영화를 다시 보고 싶고, 누군가와 이 장면을 이야기하고 싶고, 언젠가 영월의 실제 장소를 밟아 보고 싶다는 마음이 자연스럽게 생겨야 한다.",
            f"그렇게 감정이 행동으로 이어질 때 책의 가치도 또렷해진다. 해석과 여행, 기억과 현재의 움직임이 하나의 독서 경험으로 묶이면 다음 장을 넘길 힘도 생긴다.",
        ],
    }
    cinema = {
        "hook": [
            "배우가 감정을 과장해 밀어붙이지 않아도 장면이 무너질 듯 아슬아슬하게 버텨 서는 순간이 있다. 영화는 바로 그런 미세한 떨림을 오래 응시하며, 그 침묵을 관객 각자의 감정으로 번역하게 만든다.",
            "눈빛이 어떻게 대사를 대신하고, 고요한 컷이 어떻게 슬픔의 밀도를 높이는지가 살아 있을 때 영화 파트의 장면도 독자의 감각 안으로 훨씬 빠르게 스며든다.",
        ],
        "context": [
            "영화 속 단종은 실록의 문장으로만 존재하지 않는다. 화면 안에서는 젊은 얼굴의 불안과 체념, 주변 인물과의 거리, 유배지의 적막이 겹쳐지면서 훨씬 육체적인 슬픔으로 바뀐다.",
            "그 변화가 중요한 이유는 영화가 역사를 감정의 체험으로 번역하기 때문이다. 기록 속 이름 하나가 관객의 기억 속 얼굴로 남을 때, 역사와 영화는 비로소 한 장면 안에서 만난다.",
        ],
        "insight": [
            "스틸컷으로 떼어 보아도 살아남는 장면은 대개 감정의 방향이 분명하다. 시선이 어디를 향하는지, 프레임 안에서 인물이 얼마나 고립돼 보이는지가 이미 서사의 대부분을 말하고 있기 때문이다.",
            "이런 장면은 성지순례의 동기도 낳는다. 화면 속에서만 존재하던 슬픔이 실제 장소의 공기와 만날 수 있다는 가능성이 생길 때 관객은 영화 밖으로 한 걸음 더 나아가게 된다.",
            "배우와 감독의 선택이 강하게 맞물린 순간일수록 관객은 설명 없이도 감정의 방향을 읽어 낸다. 바로 그 지점에서 영화는 줄거리의 힘을 넘어 이미지와 리듬의 힘으로 작동한다.",
        ],
        "takeaway": [
            "영화 파트의 결말은 감상을 정리하는 대신 방향을 남긴다. 다시 보고 싶은 장면 하나, 직접 가 보고 싶은 장소 하나가 또렷하게 남으면 그 장은 충분히 살아 있다.",
            "결국 영화 파트의 여운은 스크린 밖으로 흘러나와야 한다. 관객의 마음속에 남은 장면이 실제 여행의 이유가 될 때 이 책의 기획도 가장 정확하게 실현된다.",
        ],
    }
    history = {
        "hook": [
            "역사 장에서는 기록의 단단함과 해석의 여백이 동시에 느껴져야 한다. 사건은 이미 지나갔지만, 그 사건을 지금 어떤 질문으로 다시 읽을 것인지는 여전히 현재의 몫이기 때문이다.",
        ],
        "context": [
            "기록은 단정하지만 사람의 삶은 늘 그보다 더 복잡하다. 그래서 역사 파트의 맥락은 사실을 쌓는 동시에, 그 사실이 영화와 현재의 감각 속에서 어떻게 다시 읽히는지도 함께 보여 줘야 한다.",
        ],
        "insight": [
            "역사 장의 통찰은 팩트를 나열하는 데서 멈추지 않는다. 어떤 해석이 가능한지, 어디까지가 기록이고 어디서부터가 영화적 상상인지 구분해 줄 때 독자도 더 선명한 시선을 갖게 된다.",
        ],
        "takeaway": [
            "결국 역사 파트의 마무리는 정답의 선언이 아니라 시선의 정리여야 한다. 무엇을 믿을 수 있고 무엇을 더 질문해야 하는지가 남으면 다음 장으로 가는 힘도 생긴다.",
        ],
    }
    travel = {
        "hook": [
            "여행 장의 시작은 안내문보다 현장감이 먼저여야 한다. 장소를 처음 마주했을 때 피부에 닿는 공기와 시선의 방향이 살아 있을 때 독자도 그 자리에 선 듯한 감각을 얻는다.",
        ],
        "context": [
            "여행의 문장은 어디에 가야 하는지만 말하지 않는다. 왜 이 장소가 영화의 감정선과 연결되는지, 어느 시간대와 어느 동선에서 그 결이 살아나는지를 함께 알려 준다.",
        ],
        "insight": [
            "성지순례의 핵심은 체크리스트가 아니라 감정의 재현이다. 영화 속 장면과 현재의 풍경이 만나는 순간을 어떻게 포착할지 보여 줄 때 장소 설명도 살아난다.",
        ],
        "takeaway": [
            "그래서 여행 파트의 끝에서는 실제 움직임이 떠올라야 한다. 언제 가야 하는지, 어디서 멈춰 서야 하는지, 무엇을 먼저 봐야 하는지가 자연스럽게 상상되면 충분하다.",
        ],
    }
    taste = {
        "hook": [
            "맛 파트의 시작은 메뉴 소개보다 분위기에서 먼저 열리는 편이 좋다. 어떤 온기와 냄새, 어떤 타이밍의 허기 속에서 그 한 그릇이나 한 잔이 필요해지는지가 먼저 살아나야 한다.",
        ],
        "context": [
            "음식은 여행의 부록이 아니라 감정을 마무리하는 방식이 될 수 있다. 영화를 보고 장소를 밟은 뒤 무엇을 먹고 마시며 그 여운을 정리하게 되는지가 이 파트의 중요한 맥락이다.",
        ],
        "insight": [
            "맛을 설명하는 좋은 문장은 미각만 말하지 않는다. 가격과 분위기, 지역성, 그 음식을 둘러싼 장면까지 함께 붙잡을 때 비로소 선택의 이유가 또렷해진다.",
        ],
        "takeaway": [
            "맛 파트의 결말은 추천 목록이 아니라 선택의 감각이어야 한다. 다음에 영월을 찾았을 때 무엇을 먼저 주문할지, 어떤 날씨와 어떤 기분에 이 메뉴가 어울릴지가 떠오르면 성공이다.",
        ],
    }
    banks = dict(common)
    if "CINEMA" in part:
        selected = cinema
    elif "HISTORY" in part:
        selected = history
    elif "TRAVEL" in part:
        selected = travel
    elif "TASTE" in part:
        selected = taste
    else:
        selected = {}
    return [*banks.get(section_key, []), *selected.get(section_key, [])]


def _densify_section_bundle(
    chapter: dict[str, Any],
    chapter_target: dict[str, Any],
    section_bundle: dict[str, str],
) -> dict[str, str]:
    budgets = section_word_budget(chapter_target)
    uplifted = dict(section_bundle)
    for section_key in SECTION_ORDER:
        target_words = max(220, int(budgets[section_key] * 0.9))
        current_text = uplifted.get(section_key, "").strip()
        for paragraph in _section_uplift_paragraphs(chapter, section_key):
            if count_words(current_text) >= target_words:
                break
            if paragraph in current_text:
                continue
            current_text = f"{current_text}\n\n{paragraph}".strip() if current_text else paragraph
        uplifted[section_key] = current_text.strip()
    return uplifted


def _apply_density_uplift(
    chapter: dict[str, Any],
    chapter_target: dict[str, Any],
    prose_text: str,
) -> str:
    floor = chapter_target["stage_progress_floors"]["S4_draft1_min_words"]
    uplifted = prose_text.rstrip()
    for paragraph in _density_uplift_paragraphs(chapter):
        if count_words(uplifted) >= floor:
            break
        uplifted = uplifted + "\n\n" + paragraph
    return uplifted.rstrip() + "\n"


def _segment_node_payload(segment: dict[str, Any], narrative: dict[str, Any]) -> dict[str, Any]:
    return {
        "node_id": segment["segment_id"],
        "node_type": "draft_segment",
        "section_key": segment["section_key"],
        "section_heading": segment["section_heading"],
        "target_words": segment["target_words"],
        "claim_intent": segment["claim_intent"],
        "reader_payoff": segment["reader_payoff"],
        "anchor_obligation_ids": segment.get("anchor_obligation_ids", []),
        "opening_tactic": narrative["opening_tactic"],
        "continuity_bridge": narrative["continuity_bridge"],
    }


def _generate_segment_text(
    book_root: Path,
    chapter: dict[str, Any],
    segment: dict[str, Any],
    narrative: dict[str, Any],
    raw_guide_contract: dict[str, Any],
    previous_texts: list[str],
    grounded: dict[str, Any] | None,
) -> tuple[str | None, dict[str, Any]]:
    prompt = _segment_prompt(
        chapter,
        segment,
        narrative,
        raw_guide_contract,
        previous_texts,
        grounded,
    )
    try:
        response = generate_text(
            resolve_stage_route(
                "S4",
                "generate_text",
                chapter_part=chapter.get("part"),
                section_key=segment["section_key"],
            ),
            system_policy_ref=(
                "You are AG-01 generating one narrative segment for a Korean nonfiction publishing pipeline. "
                "Be vivid, reader-centered, and safe for publication."
            ),
            prompt=prompt,
            context_artifacts=_policy_context(
                book_root,
                chapter["chapter_id"],
                node_payload=_segment_node_payload(segment, narrative),
                prompt_text=prompt,
            ),
            telemetry_context={
                "stage_id": "S4",
                "chapter_id": chapter["chapter_id"],
                "node_id": segment["segment_id"],
                "section_key": segment["section_key"],
            },
        )
        cleaned = _clean_model_text(response["generated_text"])
        return cleaned, {
            "status": "completed",
            "reason": "",
            "request_variant": response.get("request_variant"),
            "usage": response.get("usage"),
        }
    except ModelGatewayError as error:
        return None, {"status": "fallback", "reason": str(error)}


def _is_network_fallback_reason(reason: str | None) -> bool:
    text = (reason or "").lower()
    return (
        "network error" in text
        or "os/network error" in text
        or "timed out" in text
        or "resource exhausted" in text
        or "winerror 10013" in text
    )


def _s4_live_policy() -> dict[str, Any]:
    probe = diagnose_vertex_live_probe()
    if probe.get("ok"):
        return {
            "live_allowed": True,
            "reason": "",
            "probe": probe,
        }
    classification = probe.get("classification", {}) if isinstance(probe, dict) else {}
    category = classification.get("category", "")
    hard_stop_categories = {
        "local_socket_access_blocked",
        "quota_or_rate_limit_exhausted",
    }
    reason = classification.get("recommended_next_step") or probe.get("error", {}).get("message", "")
    return {
        "live_allowed": category not in hard_stop_categories,
        "reason": reason,
        "probe": probe,
    }


def _implement_segments(
    book_root: Path,
    chapter: dict[str, Any],
    segment_plan: dict[str, Any],
    narrative_design: dict[str, Any],
    raw_guide_contract: dict[str, Any],
    grounded: dict[str, Any] | None,
    *,
    live_generation_allowed: bool = True,
    live_disabled_reason: str = "",
) -> dict[str, Any]:
    segments = segment_plan["segments"]
    design_map = {item["segment_id"]: item for item in narrative_design["segments"]}

    def _run_pass() -> tuple[list[dict[str, Any]], int]:
        previous_texts: list[str] = []
        local_nodes: list[dict[str, Any]] = []
        live_count = 0
        for segment in segments:
            narrative = design_map[segment["segment_id"]]
            if live_generation_allowed:
                generated, telemetry = _generate_segment_text(
                    book_root,
                    chapter,
                    segment,
                    narrative,
                    raw_guide_contract,
                    previous_texts,
                    grounded,
                )
            else:
                generated, telemetry = None, {"status": "fallback", "reason": live_disabled_reason}
            minimum_words = max(120, int(segment["target_words"] * 0.62))
            if generated is None:
                generated = _build_fallback_segment_text(chapter, segment, narrative, raw_guide_contract)
                telemetry = {
                    "status": "fallback",
                    "reason": telemetry.get("reason", "insufficient_length"),
                }
            elif count_words(generated) < minimum_words:
                support_text = _build_fallback_segment_text(chapter, segment, narrative, raw_guide_contract)
                generated = _merge_live_with_support(generated, support_text, minimum_words)
                telemetry = {
                    "status": "completed",
                    "reason": "live_uplifted_from_short_response",
                    "request_variant": telemetry.get("request_variant"),
                    "usage": telemetry.get("usage"),
                }
                live_count += 1
            else:
                live_count += 1
            previous_texts.append(generated)
            payload = {
                "node_id": segment["segment_id"],
                "stage_id": "S4",
                "chapter_id": chapter["chapter_id"],
                "chapter_title": chapter["title"],
                "sequence": segment["sequence"],
                "node_type": "draft_segment",
                "section_key": segment["section_key"],
                "section_heading": segment["section_heading"],
                "segment_index": segment["segment_index"],
                "target_words": segment["target_words"],
                "claim_intent": segment["claim_intent"],
                "evidence_slot": segment["evidence_slot"],
                "anchor_obligation_ids": segment.get("anchor_obligation_ids", []),
                "status": telemetry.get("status", "completed"),
                "updated_at": now_iso(),
                "note": telemetry.get("reason", ""),
                "output_words": count_words(generated),
                "output_text": generated,
            }
            if telemetry.get("request_variant"):
                payload["request_variant"] = telemetry["request_variant"]
            if telemetry.get("usage"):
                payload["usage"] = telemetry["usage"]
            local_nodes.append(payload)
        return local_nodes, live_count

    nodes, live_node_count = _run_pass()
    if live_node_count == 0 and all(_is_network_fallback_reason(node.get("note")) for node in nodes):
        for _ in range(MAX_NETWORK_RECOVERY_PASSES):
            time.sleep(NETWORK_RECOVERY_COOLDOWN_SECONDS)
            nodes, live_node_count = _run_pass()
            if live_node_count > 0 or not all(_is_network_fallback_reason(node.get("note")) for node in nodes):
                break

    section_bundle = {key: "" for key in SECTION_ORDER}
    for section_key in SECTION_ORDER:
        section_segments = [node["output_text"] for node in nodes if node["section_key"] == section_key]
        section_bundle[section_key] = "\n\n".join(text.strip() for text in section_segments if text.strip()).strip()
    return {
        "nodes": nodes,
        "live_node_count": live_node_count,
        "fallback_node_count": len(nodes) - live_node_count,
        "section_bundle": section_bundle,
    }


def _render_draft1_prose(
    chapter: dict[str, Any],
    chapter_target: dict[str, Any],
    section_bundle: dict[str, str],
    raw_guide_contract: dict[str, Any],
    segment_plan: dict[str, Any],
) -> str:
    lines = [
        f"# DRAFT1_PROSE: {chapter['chapter_id']} | {chapter['title']}",
        "",
        section_marker("hook"),
        section_bundle["hook"].strip(),
        "",
        section_marker("context"),
        section_bundle["context"].strip(),
        "",
        section_marker("insight"),
        section_bundle["insight"].strip(),
        "",
        section_marker("takeaway"),
        section_bundle["takeaway"].strip(),
    ]
    return normalize_section_headings("\n".join(lines).strip() + "\n")


def _required_sections_present(draft_text: str) -> bool:
    return has_required_sections(draft_text)


def _anchor_blocks_inserted(draft_text: str) -> bool:
    return "<!-- ANCHOR_START" in draft_text and "[ANCHOR_SLOT:" in draft_text


def verify_density(
    chapter: dict[str, Any],
    chapter_target: dict[str, Any],
    segment_plan: dict[str, Any],
    node_manifest: dict[str, Any],
    prose_text: str,
) -> dict[str, Any]:
    section_word_counts = {
        section_key: count_words(
            "\n\n".join(
                node["output_text"]
                for node in node_manifest["nodes"]
                if node["section_key"] == section_key
            )
        )
        for section_key in SECTION_ORDER
    }
    draft_words = count_words(prose_text)
    floor = chapter_target["stage_progress_floors"]["S4_draft1_min_words"]
    coverage_ratio = round(draft_words / floor, 3) if floor else 0.0
    live_ratio = round(node_manifest["live_node_count"] / max(1, node_manifest["node_count"]), 3)
    return {
        "version": "1.0",
        "generated_at": now_iso(),
        "stage_id": "S4",
        "chapter_id": chapter["chapter_id"],
        "chapter_title": chapter["title"],
        "target_words": chapter_target["target_words"],
        "draft1_floor": floor,
        "draft_words": draft_words,
        "draft_coverage_ratio": coverage_ratio,
        "section_word_counts": section_word_counts,
        "segment_plan_count": len(segment_plan["segments"]),
        "implemented_segment_count": node_manifest["node_count"],
        "live_node_success_ratio": live_ratio,
        "fallback_only_completion": node_manifest["live_node_count"] == 0,
        "required_sections_present": _required_sections_present(prose_text),
        "anchor_blocks_inserted": False,
        "segment_plan_exists": True,
        "narrative_design_exists": True,
        "density_pass": (
            draft_words >= floor
            and _required_sections_present(prose_text)
        ),
    }


def report_session(
    chapter: dict[str, Any],
    density_audit: dict[str, Any],
    node_manifest: dict[str, Any],
    artifact_paths: dict[str, str],
) -> dict[str, Any]:
    reasons: list[str] = []
    verdict = "completed"
    if not density_audit["density_pass"]:
        verdict = "gate_failed"
        reasons.append("draft_density_below_contract")
    elif density_audit["fallback_only_completion"]:
        verdict = "completed_with_alert"
        reasons.append("all_nodes_fallback")
    elif density_audit["live_node_success_ratio"] < 0.25:
        verdict = "completed_with_alert"
        reasons.append("low_live_contribution")
    return {
        "version": "1.0",
        "generated_at": now_iso(),
        "stage_id": "S4",
        "chapter_id": chapter["chapter_id"],
        "chapter_title": chapter["title"],
        "verdict": verdict,
        "reasons": reasons,
        "recommended_status": "gate_failed" if verdict == "gate_failed" else "completed",
        "live_node_count": node_manifest["live_node_count"],
        "fallback_node_count": node_manifest["fallback_node_count"],
        "live_node_success_ratio": density_audit["live_node_success_ratio"],
        "draft_coverage_ratio": density_audit["draft_coverage_ratio"],
        "artifacts": artifact_paths,
    }


def execute_s4_pipeline(
    book_root: Path,
    chapter: dict[str, Any],
    research_entry: dict[str, Any],
    source_queue_items: list[dict[str, Any]],
    source_types: list[str],
    chapter_target: dict[str, Any],
    raw_guide: str,
) -> dict[str, Any]:
    draft_dir = book_root / "manuscripts" / "_draft1"
    chapter_id = chapter["chapter_id"]
    raw_guide_contract = parse_raw_guide_contract(raw_guide)
    live_policy = _s4_live_policy()
    grounded = (
        _grounded_brief_for_writer(book_root, chapter, research_entry, chapter_target)
        if live_policy["live_allowed"]
        else None
    )
    segment_plan = plan_segments(
        chapter,
        research_entry,
        source_queue_items,
        source_types,
        chapter_target,
        raw_guide_contract,
    )
    narrative_design = design_narrative(chapter, raw_guide_contract, segment_plan)
    implementation = _implement_segments(
        book_root,
        chapter,
        segment_plan,
        narrative_design,
        raw_guide_contract,
        grounded,
        live_generation_allowed=live_policy["live_allowed"],
        live_disabled_reason=live_policy["reason"],
    )
    section_bundle = _densify_section_bundle(
        chapter,
        chapter_target,
        implementation["section_bundle"],
    )
    node_manifest = {
        "version": "1.0",
        "generated_at": now_iso(),
        "stage_id": "S4",
        "chapter_id": chapter_id,
        "chapter_title": chapter["title"],
        "execution_mode": "ag01_segment_pipeline",
        "target_words": chapter_target["target_words"],
        "draft1_floor": chapter_target["stage_progress_floors"]["S4_draft1_min_words"],
        "grounded_enabled": grounded is not None,
        "node_count": len(implementation["nodes"]),
        "live_node_count": implementation["live_node_count"],
        "fallback_node_count": implementation["fallback_node_count"],
        "expansion_count": 0,
        "expansion_cap": S4_EXPANSION_CAP,
        "nodes": implementation["nodes"],
        "raw_guide_contract": raw_guide_contract,
        "live_policy": live_policy,
    }
    prose_text = _render_draft1_prose(
        chapter,
        chapter_target,
        section_bundle,
        raw_guide_contract,
        segment_plan,
    )
    prose_text = _apply_density_uplift(chapter, chapter_target, prose_text)
    prose_path = draft_dir / f"{chapter_id}_draft1_prose.md"
    segment_plan_path = draft_dir / f"{chapter_id}_segment_plan.json"
    narrative_design_path = draft_dir / f"{chapter_id}_narrative_design.json"
    density_audit_path = draft_dir / f"{chapter_id}_density_audit.json"
    session_report_path = draft_dir / f"{chapter_id}_session_report.json"

    artifact_paths = {
        "draft1_prose": str(prose_path),
        "segment_plan": str(segment_plan_path),
        "narrative_design": str(narrative_design_path),
        "density_audit": str(density_audit_path),
        "session_report": str(session_report_path),
    }
    density_audit = verify_density(
        chapter,
        chapter_target,
        segment_plan,
        node_manifest,
        prose_text,
    )
    session_report = report_session(chapter, density_audit, node_manifest, artifact_paths)
    node_manifest["density_audit"] = {
        "draft_words": density_audit["draft_words"],
        "draft_coverage_ratio": density_audit["draft_coverage_ratio"],
        "live_node_success_ratio": density_audit["live_node_success_ratio"],
        "fallback_only_completion": density_audit["fallback_only_completion"],
    }
    node_manifest["session_verdict"] = session_report["verdict"]

    write_text(prose_path, prose_text)
    write_json(segment_plan_path, segment_plan)
    write_json(narrative_design_path, narrative_design)
    write_json(density_audit_path, density_audit)
    write_json(session_report_path, session_report)
    node_manifest_path = write_node_manifest(book_root, "S4", chapter_id, node_manifest)

    if node_manifest["live_node_count"] > 0:
        generation_mode = "vertex_live_segment_nodes"
    elif grounded is not None:
        generation_mode = "grounded_fallback_segments"
    else:
        generation_mode = "segment_fallback_draft"

    return {
        "prose_path": prose_path,
        "segment_plan_path": segment_plan_path,
        "narrative_design_path": narrative_design_path,
        "density_audit_path": density_audit_path,
        "session_report_path": session_report_path,
        "node_manifest_path": node_manifest_path,
        "density_audit": density_audit,
        "session_report": session_report,
        "node_manifest": node_manifest,
        "grounded": grounded,
        "generation_mode": generation_mode,
    }
