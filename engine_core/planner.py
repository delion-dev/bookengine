from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

from .anchors import build_anchor_plan_for_chapter, get_chapter_policy
from .book_state import load_book_db
from .common import read_json, read_text, write_json, write_text
from .contracts import validate_inputs
from .gates import evaluate_gate
from .memory import update_book_memory, update_chapter_memory
from .stage import transition_stage
from .targets import get_chapter_target
from .work_order import issue_work_order
from .section_labels import display_section_label


_MARKDOWN_H2_PATTERN = re.compile(r"(?m)^## ([^\n]+)\s*$")
_BLUEPRINT_CHAPTER_PATTERN = re.compile(
    r"^- `(?P<chapter_id>[^`]+)` \| `(?P<part>[^`]+)` \| (?P<title>.*?) \| target `(?P<target>[^`]+)` \| anchors `(?P<anchors>[^`]+)`$"
)


def _markdown_sections(text: str) -> dict[str, str]:
    matches = list(_MARKDOWN_H2_PATTERN.finditer(text))
    if not matches:
        return {}
    sections: dict[str, str] = {}
    for index, match in enumerate(matches):
        heading = match.group(1).strip()
        start = match.end()
        end = matches[index + 1].start() if index + 1 < len(matches) else len(text)
        sections[heading] = text[start:end].strip()
    return sections


def _bullet_lines(section_text: str, max_items: int = 8) -> list[str]:
    items: list[str] = []
    for raw_line in section_text.splitlines():
        line = raw_line.strip()
        if line.startswith("- "):
            items.append(line[2:].strip())
        if len(items) >= max_items:
            break
    return items


def _chapter_blueprint_map(section_text: str) -> dict[str, dict[str, Any]]:
    chapter_map: dict[str, dict[str, Any]] = {}
    current_chapter_id: str | None = None
    for raw_line in section_text.splitlines():
        line = raw_line.rstrip()
        stripped = line.strip()
        match = _BLUEPRINT_CHAPTER_PATTERN.match(stripped)
        if match:
            current_chapter_id = match.group("chapter_id")
            chapter_map[current_chapter_id] = {
                "chapter_id": current_chapter_id,
                "part": match.group("part"),
                "title": match.group("title").strip(),
                "target": match.group("target"),
                "anchors": match.group("anchors"),
                "notes": [],
            }
            continue
        if current_chapter_id and stripped.startswith("- note:"):
            chapter_map[current_chapter_id]["notes"].append(stripped.split(":", 1)[1].strip())
    return chapter_map


def _blueprint_digest(blueprint_text: str) -> dict[str, Any]:
    sections = _markdown_sections(blueprint_text)
    return {
        "mission": _bullet_lines(sections.get("Mission", ""), max_items=6),
        "structural_strategy": _bullet_lines(sections.get("Structural Strategy", ""), max_items=6),
        "writing_rules": _bullet_lines(sections.get("Writing Rules", ""), max_items=8),
        "reader_lenses": _bullet_lines(sections.get("Reader Lenses by Part", ""), max_items=8),
        "chapter_map": _chapter_blueprint_map(sections.get("Chapters", "")),
    }


def _part_blueprint_lens(blueprint_digest: dict[str, Any], part: str | None) -> str:
    label = part or ""
    for item in blueprint_digest.get("reader_lenses", []):
        if "CINEMA" in label and "CINEMA" in item:
            return item
        if "HISTORY" in label and "HISTORY" in item:
            return item
        if "TRAVEL" in label and "TRAVEL" in item:
            return item
        if "TASTE" in label and "TASTE" in item:
            return item
        if label == "INTRO" and "CINEMA" in item:
            return item
    return ""


def _chapter_blueprint_notes(
    blueprint_digest: dict[str, Any],
    chapter_id: str,
) -> list[str]:
    entry = blueprint_digest.get("chapter_map", {}).get(chapter_id, {})
    notes = entry.get("notes", [])
    return [str(item) for item in notes if str(item).strip()]


def _reader_segment_for_part(book_config: dict[str, Any], part: str | None) -> dict[str, str]:
    default_segment = {
        "segment_id": "general_reader",
        "focus": book_config.get("audience", "general reader"),
        "reader_payoff": "A clear emotional or practical payoff.",
    }
    segments = {
        item.get("segment_id"): item
        for item in book_config.get("audience_segments", [])
        if isinstance(item, dict) and item.get("segment_id")
    }
    label = part or ""
    if "CINEMA" in label:
        return segments.get("film_culture_reader", default_segment)
    if "HISTORY" in label:
        return segments.get("history_factcheck_reader", default_segment)
    if "TRAVEL" in label:
        return segments.get("travel_execution_reader", default_segment)
    if "TASTE" in label:
        return segments.get("local_taste_reader", default_segment)
    return default_segment


def _reader_segment_for_chapter(
    research_entry: dict[str, Any],
    book_config: dict[str, Any],
    part: str | None,
) -> dict[str, str]:
    segment = research_entry.get("reader_segment")
    if isinstance(segment, dict) and segment.get("segment_id"):
        return segment
    return _reader_segment_for_part(book_config, part)


def _rights_guardrails(book_config: dict[str, Any], part: str | None) -> list[str]:
    policy = book_config.get("rights_policy", {})
    rules = [
        "Every external source or visual candidate must remain traceable in the appendix reference index.",
    ]
    if policy.get("news_text_policy"):
        rules.append("Article text must be paraphrased; keep direct quotation minimal and attributable.")
    if policy.get("ugc_policy"):
        rules.append("SNS or UGC references require consent, anonymization, or aggregation before publication use.")
    if policy.get("film_still_and_press_photo_policy"):
        rules.append("Film stills and press photos need written permission or a safe replacement visual.")
    if policy.get("external_photo_policy"):
        rules.append("Prefer self-shot, public-license, or explicitly permitted images.")
    if policy.get("map_service_policy"):
        rules.append("Map screenshots need license review before direct inclusion.")
    label = part or ""
    if "TRAVEL" in label or "TASTE" in label:
        rules.append("Local visit, opening-hour, and menu claims should stay framed as current-check items until verified.")
    return rules


def _rights_guardrails_for_chapter(
    research_entry: dict[str, Any],
    book_config: dict[str, Any],
    part: str | None,
) -> list[str]:
    rules = research_entry.get("rights_constraints")
    if isinstance(rules, list) and rules:
        return [str(item) for item in rules]
    return _rights_guardrails(book_config, part)


def _chapter_dependency_map(chapter_sequence: list[str]) -> list[dict[str, Any]]:
    dependencies: list[dict[str, Any]] = []
    for index, chapter_id in enumerate(chapter_sequence):
        dependency = {
            "chapter_id": chapter_id,
            "depends_on": chapter_sequence[index - 1] if index > 0 else None,
            "unlocks": chapter_sequence[index + 1] if index + 1 < len(chapter_sequence) else None,
        }
        dependencies.append(dependency)
    return dependencies


def _find_research_entry(research_plan: dict[str, Any], chapter_id: str) -> dict[str, Any]:
    for chapter in research_plan.get("chapters", []):
        if chapter["chapter_id"] == chapter_id:
            return chapter
    raise KeyError(f"Missing research plan entry for {chapter_id}")


def _part_lens(part: str | None, blueprint_part_lens: str = "") -> dict[str, Any]:
    label = part or ""
    if "CINEMA" in label:
        return {
            "chapter_goal": "영화의 핵심 장면과 배우의 해석을 실제 장면 분석과 성지순례 동기로 연결되는 독자용 서사로 쓴다.",
            "include": [
                "구체적인 장면과 배우 또는 연출 해석",
                "영화 감정선 안에서 이 장이 왜 결정적인지",
                "스틸컷이나 실제 장소와 연결될 수 있는 현장 감각",
                "관객이 직접 영월을 찾고 싶어지는 감정적 동선",
            ],
            "exclude": [
                "책 쓰는 법을 설명하는 메타 문장",
                "근거 없는 팬심 찬양",
                "장면 분석 없는 줄거리 요약",
                "독자에게 읽는 방법을 지시하는 문장",
            ],
            "visuals": [
                "스틸컷 vs 실제 장소 비교 패널",
                "장면 기반 연기/감정 비교 표",
            ],
            "blueprint_lens": blueprint_part_lens,
        }
    if "HISTORY" in label:
        return {
            "chapter_goal": "영화적 각색과 실제 기록의 차이를 검증 가능한 근거와 현재적 의미로 풀어 쓴다.",
            "include": [
                "안정된 사료 기반의 연표와 사실관계",
                "대중이 오해하기 쉬운 지점의 정정",
                "지금 읽어도 현재적인 권력 감각과 인간 심리",
            ],
            "exclude": [
                "검증되지 않은 설화를 단정적으로 쓰는 것",
                "맥락 없는 단정",
                "백과사전식 건조한 나열",
            ],
            "visuals": [
                "사건 연표 다이어그램",
                "실록 vs 영화 비교 표",
            ],
            "blueprint_lens": blueprint_part_lens,
        }
    if "TRAVEL" in label:
        return {
            "chapter_goal": "영화 촬영지에 대한 관심을 실제 방문 동선과 현장 감정이 살아 있는 여행 서사로 바꾼다.",
            "include": [
                "현재 방문 동선, 접근, 시간 정보",
                "현장에서 떠올려야 할 영화 장면과 감정",
                "실제 장소에서 바로 써먹을 실용 팁",
            ],
            "exclude": [
                "관광 브로슈어 같은 문구",
                "영화 속 허구를 물리적 사실처럼 쓰는 것",
                "맥락 없는 리스트형 소개",
            ],
            "visuals": [
                "현장 동선 지도 또는 장소 클러스터",
                "장면 vs 실제 장소 비교 패널",
            ],
            "blueprint_lens": blueprint_part_lens,
        }
    if "TASTE" in label:
        return {
            "chapter_goal": "영화 감상의 여운을 영월의 구체적인 음식과 체류 경험으로 이어지는 현장형 원고로 쓴다.",
            "include": [
                "메뉴와 지역 맥락",
                "왜 이 음식이 책의 감정선과 맞물리는지",
                "가격대나 방문 시나리오",
            ],
            "exclude": [
                "맥락 없는 맛집 수사",
                "비지역적이고 평평한 카페 소개",
                "근거 없는 추천",
            ],
            "visuals": [
                "미니 동선/예산 표",
                "로컬 맛 비교 카드",
            ],
            "blueprint_lens": blueprint_part_lens,
        }
    return {
        "chapter_goal": "책 전체의 감정적 입구이자 성지순례 동기를 여는 서문으로 쓴다.",
        "include": [
            "독자가 바로 몰입할 감정적 문제 제기",
            "책 전체를 관통하는 논지",
            "영화, 역사, 여행, 로컬 경험으로 이어질 입구",
        ],
        "exclude": [
            "추상적인 인트로",
            "갈 곳을 제시하지 않는 요약",
            "근거 없는 과장",
        ],
        "visuals": [
            "책 여정 지도",
        ],
        "blueprint_lens": blueprint_part_lens,
    }


def _section_guides(
    chapter: dict[str, Any],
    lens: dict[str, Any],
    blueprint_digest: dict[str, Any],
) -> list[dict[str, str]]:
    title = chapter["title"]
    part = chapter.get("part", "") or ""
    chapter_notes = _chapter_blueprint_notes(blueprint_digest, chapter["chapter_id"])
    note_hint = chapter_notes[0] if chapter_notes else ""
    part_lens = lens.get("blueprint_lens", "")
    if "CINEMA" in part:
        return [
            {
                "section": f"1. {display_section_label('hook')}",
                "purpose": f"'{title}'의 핵심 장면이나 배우의 표정, 시선, 침묵에서 바로 시작해 독자가 스크린 안으로 끌려 들어가게 한다.",
            },
            {
                "section": f"2. {display_section_label('context')}",
                "purpose": "그 장면을 읽기 위해 꼭 필요한 영화 정보, 수용 반응, 역사적 배경만 최소한으로 정리한다.",
            },
            {
                "section": f"3. {display_section_label('insight')}",
                "purpose": f"연기, 연출, 관객 반응, 실제 장소 감각이 어떻게 겹쳐지는지 실제 내용으로 풀어 쓴다. {part_lens}".strip(),
            },
            {
                "section": f"4. {display_section_label('takeaway')}",
                "purpose": f"독자가 영월이나 실제 장소를 떠올리며 다음 장 또는 성지순례 동선으로 자연스럽게 움직이게 한다. {note_hint}".strip(),
            },
        ]
    if "HISTORY" in part:
        return [
            {
                "section": f"1. {display_section_label('hook')}",
                "purpose": f"'{title}'에서 가장 강한 역사적 질문이나 오해 지점을 앞세워 지금 읽어야 할 이유를 만든다.",
            },
            {
                "section": f"2. {display_section_label('context')}",
                "purpose": "사료, 연표, 인물 관계의 최소 구조를 정리해 영화와 실제 기록을 구분할 기반을 깐다.",
            },
            {
                "section": f"3. {display_section_label('insight')}",
                "purpose": "실록과 해석, 영화적 각색이 어디에서 갈라지는지 구체적인 사례로 풀어 쓴다.",
            },
            {
                "section": f"4. {display_section_label('takeaway')}",
                "purpose": "역사적 구분이 오늘의 독자에게 어떤 감정적 혹은 지적 효용을 주는지 남긴다.",
            },
        ]
    if "TRAVEL" in part:
        return [
            {
                "section": f"1. {display_section_label('hook')}",
                "purpose": f"'{title}'의 현장 공기나 장면 기억에서 출발해 독자가 지금 그곳에 가고 싶게 만든다.",
            },
            {
                "section": f"2. {display_section_label('context')}",
                "purpose": "장소의 실제 위치, 동선, 접근성, 영화 속 맥락을 독자 친화적으로 정리한다.",
            },
            {
                "section": f"3. {display_section_label('insight')}",
                "purpose": "영화 속 장면과 실제 장소의 간극, 겹침, 체험 포인트를 현장감 있게 풀어 쓴다.",
            },
            {
                "section": f"4. {display_section_label('takeaway')}",
                "purpose": f"독자가 책을 들고 직접 떠날 수 있도록 촬영지 감상 포인트와 실용 팁을 남긴다. {note_hint}".strip(),
            },
        ]
    if "TASTE" in part:
        return [
            {
                "section": f"1. {display_section_label('hook')}",
                "purpose": f"'{title}'의 음식이나 공간이 왜 영화의 여운과 어울리는지 감각적으로 시작한다.",
            },
            {
                "section": f"2. {display_section_label('context')}",
                "purpose": "메뉴, 위치, 분위기, 지역 맥락을 정리해 독자가 실제 선택을 상상할 수 있게 한다.",
            },
            {
                "section": f"3. {display_section_label('insight')}",
                "purpose": "맛과 장소가 영화 감상 이후의 감정선과 어떻게 이어지는지 구체적으로 풀어 쓴다.",
            },
            {
                "section": f"4. {display_section_label('takeaway')}",
                "purpose": f"독자가 주문·방문·체류를 실제로 결정할 수 있게 실용 포인트를 남긴다. {note_hint}".strip(),
            },
        ]
    return [
        {
            "section": f"1. {display_section_label('hook')}",
            "purpose": f"'{title}' 안의 가장 강한 감정과 질문을 붙들어 책 전체로 들어가는 문을 연다.",
        },
        {
            "section": f"2. {display_section_label('context')}",
            "purpose": "영화, 역사, 실제 장소를 함께 읽기 위한 배경만 정리하고 메타 해설은 피한다.",
        },
        {
            "section": f"3. {display_section_label('insight')}",
            "purpose": "책 전체를 관통하는 감정과 질문이 어디에서 살아나는지 실제 내용으로 풀어 쓴다.",
        },
        {
            "section": f"4. {display_section_label('takeaway')}",
            "purpose": "독자가 다음 장으로 넘어가거나 실제 장소를 찾고 싶어지게 만드는 실전 포인트를 남긴다.",
        },
    ]


def _render_raw_guide(
    book_id: str,
    chapter: dict[str, Any],
    chapter_notes: list[str],
    blueprint_digest: dict[str, Any],
    audience: str,
    audience_segment: dict[str, str],
    working_title: str,
    research_entry: dict[str, Any],
    chapter_target: dict[str, Any],
    anchor_plan: dict[str, Any],
    rights_guardrails: list[str],
    visual_source_priority: list[str],
) -> str:
    blueprint_part_lens = _part_blueprint_lens(blueprint_digest, chapter.get("part"))
    chapter_blueprint_notes = _chapter_blueprint_notes(blueprint_digest, chapter["chapter_id"])
    merged_notes = list(dict.fromkeys([*chapter_blueprint_notes, *chapter_notes]))
    lens = _part_lens(chapter.get("part"), blueprint_part_lens)
    section_guides = _section_guides(chapter, lens, blueprint_digest)
    mission_lines = blueprint_digest.get("mission", [])
    structural_strategy = blueprint_digest.get("structural_strategy", [])
    writing_rules = blueprint_digest.get("writing_rules", [])
    lines = [
        f"# RAW GUIDE: {chapter['chapter_id']} | {chapter['title']}",
        "",
        f"- Book ID: `{book_id}`",
        f"- Working Title: `{working_title}`",
        f"- Part: `{chapter.get('part', '')}`",
        f"- Audience Lens: `{audience}`",
        "",
        "## Blueprint Alignment",
    ]
    for item in mission_lines[:3]:
        lines.append(f"- {item}")
    if blueprint_part_lens:
        lines.append(f"- Part lens: {blueprint_part_lens}")
    for item in structural_strategy[:2]:
        lines.append(f"- Strategy: {item}")

    lines.extend(
        [
            "",
            "## Chapter Goal",
            f"- {lens['chapter_goal']}",
            "",
            "## Target Length",
            f"- Target words: `{chapter_target['target_words']}`",
            f"- Target range: `{chapter_target['min_words']} - {chapter_target['max_words']}`",
            f"- Draft1 progress floor: `{chapter_target['stage_progress_floors']['S4_draft1_min_words']}` words",
            "",
            "## Reader Promise",
            f"- `{chapter['title']}`를 독자용 서사로 끝까지 읽히게 만든다.",
            "- 책 쓰는 법이 아니라 실제 영화·역사·장소·여행의 내용을 쓴다.",
            "- 장을 덮었을 때 감정적 혹은 실용적 한 가지 효용이 분명하게 남아야 한다.",
            "",
            "## Reader Segment",
            f"- Segment: `{audience_segment['segment_id']}`",
            f"- Focus: {audience_segment['focus']}",
            f"- Reader payoff: {audience_segment['reader_payoff']}",
            "",
            "## Section Guides",
        ]
    )
    for item in section_guides:
        lines.append(f"- {item['section']}: {item['purpose']}")

    lines.extend(["", "## Evidence Targets"])
    for question in research_entry.get("research_questions", []):
        lines.append(f"- Research question: {question}")
    for source_type in research_entry.get("source_types", []):
        lines.append(f"- Source type: {source_type}")

    if merged_notes:
        lines.extend(["", "## Local Notes"])
        for note in merged_notes:
            lines.append(f"- {note}")

    lines.extend(["", "## Include"])
    for item in lens["include"]:
        lines.append(f"- {item}")
    for item in writing_rules[:3]:
        lines.append(f"- Blueprint rule: {item}")

    lines.extend(["", "## Exclude"])
    for item in lens["exclude"]:
        lines.append(f"- {item}")
    if "CINEMA" in str(chapter.get("part", "")) or chapter.get("part") == "INTRO":
        lines.append("- 독자에게 이 장을 어떻게 읽어야 하는지 지시하는 문장을 쓰지 않는다.")

    lines.extend(["", "## Visual Opportunities"])
    for item in lens["visuals"]:
        lines.append(f"- {item}")

    lines.extend(["", "## Rights and Source Guardrails"])
    for item in rights_guardrails:
        lines.append(f"- {item}")

    lines.extend(["", "## Visual Source Priority"])
    for item in visual_source_priority:
        lines.append(f"- {item}")

    lines.extend(
        [
            "",
            "## Anchor Contract",
            f"- Anchor budget: `{anchor_plan['anchor_budget']}`",
            "- Standard syntax: `ANCHOR_START -> ANCHOR_SLOT -> ANCHOR_END`",
        ]
    )
    for anchor in anchor_plan.get("anchors", []):
        lines.append(
            f"- `{anchor['anchor_id']}` | `{anchor['anchor_type']}` | `{anchor['placement']}` | "
            f"`{anchor['asset_mode']}` | ref `{anchor['appendix_ref_id']}`"
        )

    lines.extend(
        [
            "",
            "## Output Reminder",
            "- Draft for AG-01 must stay structurally faithful to this guide.",
            "- Any unsupported claim should remain a research task, not a completed assertion.",
            "- Anchor insertion은 S4A에서만 수행하며, prose-only 초고는 본문 흐름을 먼저 완성해야 한다.",
            "- 이후 시각화와 오프라인 자산 수집은 anchor block 범위에서만 진행된다.",
        ]
    )
    return "\n".join(lines) + "\n"


def _pending_s3_chapters(book_root: Path) -> list[str]:
    payload = load_book_db(book_root)
    return [
        chapter_id
        for chapter_id in payload["chapter_sequence"]
        if payload["chapters"][chapter_id]["stages"]["S3"]["status"] == "pending"
    ]


def run_raw_guides(
    book_id: str,
    book_root: Path,
    chapter_id: str | None = None,
) -> dict[str, Any]:
    contract_status = validate_inputs(book_id, book_root, "S3", chapter_id or "intro")
    if not contract_status["valid"]:
        raise FileNotFoundError(f"S3 inputs missing: {contract_status['missing_inputs']}")

    book_db = load_book_db(book_root)
    research_plan = read_json(book_root / "research" / "research_plan.json", default=None)
    book_config = read_json(book_root / "_master" / "BOOK_CONFIG.json", default=None)
    word_targets = read_json(book_root / "_master" / "WORD_TARGETS.json", default=None)
    anchor_policy = read_json(book_root / "_master" / "ANCHOR_POLICY.json", default=None)
    blueprint_path = book_root / "_master" / "BOOK_BLUEPRINT.md"
    blueprint_text = read_text(blueprint_path)
    blueprint_digest = _blueprint_digest(blueprint_text)
    if research_plan is None or book_config is None or word_targets is None or anchor_policy is None:
        raise FileNotFoundError("S3 requires research_plan.json, BOOK_CONFIG.json, WORD_TARGETS.json, and ANCHOR_POLICY.json.")

    target_chapters = [chapter_id] if chapter_id else _pending_s3_chapters(book_root)
    if not target_chapters:
        return {
            "stage_id": "S3",
            "status": "no_op",
            "message": "No pending S3 chapters found.",
        }

    update_book_memory(
        book_root,
        core_message=f"{book_config['working_title']} should blend cinema, history, travel, and local culture into a single reader journey.",
        reader_persona=book_config["audience"],
        chapter_dependencies=_chapter_dependency_map(book_db["chapter_sequence"]),
    )

    results = []
    for current_chapter_id in target_chapters:
        chapter = book_db["chapters"][current_chapter_id]
        current_status = chapter["stages"]["S3"]["status"]
        if current_status != "completed":
            transition_stage(
                book_root,
                "S3",
                "in_progress",
                current_chapter_id,
                note="AG-00 raw guide generation started.",
            )
        research_entry = _find_research_entry(research_plan, current_chapter_id)
        chapter_target = get_chapter_target(word_targets, current_chapter_id)
        chapter_policy = get_chapter_policy(anchor_policy, current_chapter_id)
        reader_segment = _reader_segment_for_chapter(research_entry, book_config, chapter.get("part"))
        rights_guardrails = _rights_guardrails_for_chapter(research_entry, book_config, chapter.get("part"))
        anchor_plan = build_anchor_plan_for_chapter(
            book_id,
            {
                "chapter_id": current_chapter_id,
                "title": chapter["title"],
                "part": chapter.get("part"),
            },
            chapter_target,
            chapter_policy,
        )
        raw_guide = _render_raw_guide(
            book_id,
            {
                "chapter_id": current_chapter_id,
                "title": chapter["title"],
                "part": chapter.get("part"),
            },
            chapter.get("notes", []),
            blueprint_digest,
            book_config["audience"],
            reader_segment,
            book_config["working_title"],
            research_entry,
            chapter_target,
            anchor_plan,
            rights_guardrails,
            book_config.get("visual_source_priority", []),
        )
        output_path = book_root / "manuscripts" / "_raw" / f"{current_chapter_id}_raw.md"
        anchor_plan_path = book_root / "manuscripts" / "_raw" / f"{current_chapter_id}_anchor_plan.json"
        write_text(output_path, raw_guide)
        write_json(anchor_plan_path, anchor_plan)

        update_chapter_memory(
            book_root,
            current_chapter_id,
            summary=f"Raw guide ready for {chapter['title']}",
            claims=[],
            citations_summary=research_entry.get("source_types", []),
            unresolved_issues=research_entry.get("research_questions", []),
            visual_notes=[anchor["anchor_type"] for anchor in anchor_plan.get("anchors", [])],
        )

        gate_result = evaluate_gate(book_id, book_root, "S3", current_chapter_id)
        if not gate_result["passed"]:
            transition_stage(
                book_root,
                "S3",
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
            "S3",
            "completed",
            current_chapter_id,
            note="AG-00 raw guide generation completed.",
        )
        results.append(
                {
                    "chapter_id": current_chapter_id,
                    "status": "completed",
                    "outputs": [
                        str(output_path),
                        str(anchor_plan_path),
                    ],
                    "gate_result": gate_result,
                }
            )

    work_order = issue_work_order(book_id, book_root)
    return {
        "stage_id": "S3",
        "requested_chapters": target_chapters,
        "results": results,
        "work_order": {
            "order_id": work_order["order_id"],
            "priority_queue_size": len(work_order["priority_queue"]),
            "first_items": work_order["priority_queue"][:5],
        },
    }
