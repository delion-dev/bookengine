from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

from .anchors import build_anchor_policy
from .common import now_iso, read_json, read_text, write_json, write_text
from .contracts import validate_inputs
from .gates import evaluate_gate
from .stage import transition_stage
from .targets import build_word_targets


def _extract_working_title(toc_seed: str) -> str:
    match = re.search(r"##\s+📂\s+도서명\(가제\):\s+\[(.+?)\]", toc_seed)
    if match:
        return match.group(1).strip()
    return "Untitled Book"


def _infer_audience(proposal_text: str) -> str:
    if "2030" in proposal_text:
        return "2030 trend-aware general readers"
    return "general readers"


def _audience_segments() -> list[dict[str, str]]:
    return [
        {
            "segment_id": "film_culture_reader",
            "focus": "영화 화제성과 배우/연출 해석을 빠르게 이해하고 싶은 독자",
            "reader_payoff": "영화를 보고 대화할 언어와 해석 프레임 확보",
        },
        {
            "segment_id": "history_factcheck_reader",
            "focus": "실제 기록과 영화적 각색의 차이를 알고 싶은 독자",
            "reader_payoff": "사실, 해석, 연출을 구분하는 검증 감각 확보",
        },
        {
            "segment_id": "travel_execution_reader",
            "focus": "영월 성지순례를 실제로 계획하려는 독자",
            "reader_payoff": "방문 동선, 현장 포인트, 감상 포인트를 바로 가져감",
        },
        {
            "segment_id": "local_taste_reader",
            "focus": "로컬 음식과 분위기까지 한 권에서 경험하고 싶은 독자",
            "reader_payoff": "먹고 머무는 선택까지 연결되는 실용 정보 확보",
        },
    ]


def _rights_policy() -> dict[str, Any]:
    return {
        "commercial_publication_context": True,
        "news_text_policy": "paraphrase_only_with_limited_quote_exception",
        "ugc_policy": "consent_or_aggregation_required",
        "film_still_and_press_photo_policy": "written_permission_or_safe_replacement_required",
        "external_photo_policy": "self_shot_or_public_license_preferred",
        "map_service_policy": "license_check_before_direct_screenshot_use",
        "appendix_reference_index_required": True,
    }


def _infer_tone(proposal_text: str) -> list[str]:
    tone = []
    if "가볍고도 깊이 있게" in proposal_text:
        tone.append("light_but_insightful")
    if "에디토리얼" in proposal_text or "잡지" in proposal_text:
        tone.append("editorial_magazine")
    tone.append("fact_checked")
    tone.append("travel_culture_hybrid")
    return tone


def _extract_parts(intake_manifest: dict[str, Any]) -> list[dict[str, Any]]:
    return intake_manifest.get("parts_detected", [])


def _extract_chapters(intake_manifest: dict[str, Any]) -> list[dict[str, Any]]:
    return intake_manifest.get("chapters_detected", [])


def _book_config(
    book_id: str,
    display_name: str,
    book_root: Path,
    intake_manifest: dict[str, Any],
    proposal_text: str,
    toc_seed: str,
) -> dict[str, Any]:
    return {
        "version": "1.0",
        "generated_at": now_iso(),
        "book_id": book_id,
        "display_name": display_name,
        "book_root": str(book_root),
        "working_title": _extract_working_title(toc_seed),
        "audience": _infer_audience(proposal_text),
        "tone_profile": _infer_tone(proposal_text),
        "creator": "Codex Book Engine",
        "publisher": "Codex Book Engine",
        "language": "ko-KR",
        "pipeline": {
            "book_level_stages": ["S-1", "S0", "S1", "S2", "S9"],
            "chapter_level_stages": ["S3", "S4", "S4A", "S5", "S6", "S6A", "S7", "S8", "S8A"],
        },
        "chapter_count": len(_extract_chapters(intake_manifest)),
        "part_count": len(_extract_parts(intake_manifest)),
        "audience_segments": _audience_segments(),
        "rights_policy": _rights_policy(),
    }


def _build_blueprint_markdown(
    config: dict[str, Any],
    intake_manifest: dict[str, Any],
    word_targets: dict[str, Any],
    anchor_policy: dict[str, Any],
) -> str:
    parts = _extract_parts(intake_manifest)
    chapters = _extract_chapters(intake_manifest)
    target_map = {chapter["chapter_id"]: chapter for chapter in word_targets["chapters"]}
    anchor_map = {chapter["chapter_id"]: chapter for chapter in anchor_policy["chapters"]}
    lines = [
        f"# BOOK_BLUEPRINT: {config['working_title']}",
        "",
        "## Mission",
        f"- Book ID: `{config['book_id']}`",
        f"- Audience: `{config['audience']}`",
        f"- Tone profile: `{', '.join(config['tone_profile'])}`",
        "- Core promise: 한 권으로 영화 해석, 역사 팩트체크, 성지순례 동선, 로컬 맛 경험까지 연결한다.",
        "",
        "## Structural Strategy",
        "- 영화 해석, 역사 팩트체크, 성지순례 동선, 로컬 문화 경험이 한 권 안에서 자연스럽게 이어지게 설계한다.",
        "- 챕터 흐름은 독자용 초고 -> 교정/사실 반영 -> anchor 삽입 -> 시각 설계 -> 자산 수집 연동 -> 시각 렌더 -> 출판의 순서를 따른다.",
        "- reader-facing prose는 책 내용을 직접 쓰고, 집필 방법론이나 운영 메모는 sidecar나 meta block으로만 남긴다.",
        "",
        "## Reader Lenses by Part",
        "- `PART 1 / CINEMA`: 영화 팬과 대중 독자가 바로 써먹을 해석 언어를 제공한다.",
        "- `PART 2 / HISTORY`: 영화적 각색과 실제 기록의 차이를 검증 가능한 형태로 풀어준다.",
        "- `PART 3 / TRAVEL`: 장소의 감정선과 실제 방문 포인트를 함께 제공한다.",
        "- `PART 4 / TASTE`: 지역의 음식과 체류 경험을 구체적인 선택지로 바꿔준다.",
        "",
        "## Parts",
    ]
    for part in parts:
        lines.append(f"- `{part['part_id']}`: {part['title']}")

    lines.extend(["", "## Chapters"])
    for chapter in chapters:
        target = target_map[chapter["chapter_id"]]
        anchor_entry = anchor_map[chapter["chapter_id"]]
        lines.append(
            f"- `{chapter['chapter_id']}` | `{chapter['part']}` | {chapter['title']} | "
            f"target `{target['target_words']} words` | anchors `{anchor_entry['anchor_budget']}`"
        )
        for note in chapter.get("notes", []):
            lines.append(f"  - note: {note}")

    lines.extend(
        [
            "",
            "## Length Plan",
            f"- Total target words: `{word_targets['total_target_words']}`",
            "- Chapter targets are locked at S0 and revised only through architecture rerun.",
            "- AG-01 draft1 target is a substantive draft and should aim at >= 90% of chapter target words.",
            "",
            "## Anchor System",
            "- Standard grammar: HTML comment anchor blocks with explicit type, placement, asset mode, and appendix reference id.",
            "- Every chapter reserves anchor budget before draft writing begins.",
            "- External images and AI-generated visuals must be mirrored in appendix reference tracking.",
            "- Travel and taste chapters should prefer safe visual sourcing hierarchy over uncontrolled third-party image dependency.",
            "",
            "## Rights and Source Strategy",
            "- News and review articles inform facts, but final prose must be rewritten in-house rather than copied.",
            "- User-generated content must be licensed, consented, anonymized, or transformed into aggregate insight.",
            "- Film stills, press photos, and third-party visuals require explicit permission or safe replacement.",
            "- All external and AI-generated materials must remain traceable through the appendix reference index.",
            "",
            "## Visual Fallback Hierarchy",
            "- Prefer self-shot or self-created materials first.",
            "- If unavailable, prefer public-license/public-domain assets.",
            "- If still unavailable, use written-permission assets.",
            "- If clearance remains uncertain, replace with illustration, structured visual, or provenance-safe AI image.",
            "",
            "## Writing Rules",
            "- Every chapter must have a clear reader hook within the opening section.",
            "- Do not explain how the chapter should be written; write the chapter content itself.",
            "- Historical or trend claims must be routed to research/citation artifacts before publication.",
            "- Travel and food recommendations must stay concrete, location-aware, and non-generic.",
            "- Chapter endings should convert context into action, reflection, or itinerary value.",
            "- Travel and taste chapters should always answer where, why, when, and how the reader should actually go or order.",
            "- Cinema chapters should describe scene, performance, still-cut mood, and real-place linkage directly in the prose.",
            "- Offline asset collection is a separate round and must bind appendix reference ids, file naming rules, and cleared storage paths.",
        ]
    )
    return "\n".join(lines) + "\n"


def _build_style_guide_markdown(config: dict[str, Any]) -> str:
    lines = [
        "# STYLE_GUIDE",
        "",
        "## Voice",
        "- Conversational, sharp, and editorial.",
        "- Light on the surface but never shallow in analysis.",
        "- Avoid lecture tone and avoid fandom-only insider language.",
        "",
        "## Reader Promise",
        "- The reader should feel informed enough to watch, discuss, and travel with confidence.",
        "- Cultural context must be understandable without prior deep Joseon-history knowledge.",
        "",
        "## Part Modes",
        "- Cinema chapters: 배우와 연출의 작동 방식을 읽어 주는 에디토리얼 톤.",
        "- History chapters: 기록과 해석을 분리하는 검증형 톤.",
        "- Travel chapters: 현장감과 동선이 살아 있는 실행형 톤.",
        "- Taste chapters: 메뉴 선택과 분위기 판단에 도움이 되는 감각형 톤.",
        "",
        "## Formatting",
        "- Prefer short paragraphs and strong subhead rhythm.",
        "- Use lists for travel spots, comparison frames, and practical itineraries only when useful.",
        "- Keep citations and factual refreshes separable from the body draft.",
        "- Keep anchor blocks intact once injected; agents may change only caption intent through the approved API.",
        "",
        "## Rights-Safe Writing",
        "- Do not paste news or review prose verbatim into the manuscript.",
        "- Treat SNS/UGC as consented quotation, anonymized signal, or aggregate statistic only.",
        "- Do not describe a third-party still or photo as if it is cleared for print unless rights status is confirmed.",
        "- If rights are unclear, rewrite toward descriptive analysis or use structured/illustrated alternatives.",
        "",
        "## Value Amplification",
        "- Rewrite toward the reader's payoff without changing verified facts or chapter structure.",
        "- Upgrade generic exposition into scene-aware, experience-near prose where the draft already supports it.",
        "- Cinema and history chapters should feel observant and lucid; travel and taste chapters should feel situated and tactile.",
        "- Preserve the original claim order while making the prose feel more lived-in and less template-driven.",
        "",
        "## Prohibitions",
        "- No filler admiration language.",
        "- No unsupported trend claims.",
        "- No flat tourism brochure prose.",
        "",
        f"## Tone Tags\n- {', '.join(config['tone_profile'])}",
    ]
    return "\n".join(lines) + "\n"


def _build_quality_criteria_markdown(
    intake_manifest: dict[str, Any],
    word_targets: dict[str, Any],
) -> str:
    target_map = {chapter["chapter_id"]: chapter for chapter in word_targets["chapters"]}
    lines = [
        "# QUALITY_CRITERIA",
        "",
        "## Global Gates",
        "- Structure completeness",
        "- Factual claims traceable to research artifacts",
        "- Tone consistency with editorial travel-culture hybrid framing",
        "- Reader value present in every chapter",
        "- Value amplification must preserve facts while increasing immediacy and reader payoff",
        "- Commercial publication rights and clearance risk must be visible for external materials",
        "",
        "## Chapter Minimums",
    ]
    for chapter in _extract_chapters(intake_manifest):
        target = target_map[chapter["chapter_id"]]
        lines.append(
            f"- `{chapter['chapter_id']}`: hook, context, insight, takeaway, "
            f"target `{target['target_words']}` words, anchor budget `{target['anchor_budget']}`"
        )

    lines.extend(
        [
            "",
            "## Part-Specific Minimums",
            "- Cinema chapters must explain why the scene or performance matters, not just praise it.",
            "- History chapters must separate record, inference, and cinematic interpretation.",
            "- Travel chapters must include place meaning, visit cue, on-site tip, and caution or timing note.",
            "- Taste chapters must include menu hook, why order it, atmosphere cue, and practical choice guidance.",
            "",
            "## Visual / Reference Controls",
            "- Any external image must have appendix reference metadata.",
            "- Any AI-generated image must record model, prompt summary, and revision history.",
            "- Missing anchor appendix reference is a gate failure for visual stages.",
            "",
            "## Rights / Clearance Controls",
            "- News and review text must be paraphrased; direct quotation is exceptional and minimal.",
            "- UGC/SNS material requires consent, anonymization, or aggregate/statistical transformation.",
            "- Film stills, press photos, and third-party venue photos require written permission or safe replacement.",
            "- Map/service screenshots require license review before direct print reuse.",
            "",
            "## Return Conditions",
            "- Missing hook returns to AG-00 or AG-01",
            "- Unsupported claim returns to AG-RS or AG-02",
            "- Visual anchor mismatch returns to AG-03 or AG-04",
            "- Style drift returns to AG-05",
            "- Reader-value drift or flat exposition returns to AG-05A",
            "- High-risk rights item returns to AG-RS or AG-02 for clearance or replacement planning",
        ]
    )
    return "\n".join(lines) + "\n"


def run_architecture(book_id: str, book_root: Path) -> dict[str, Any]:
    contract_status = validate_inputs(book_id, book_root, "S0")
    if not contract_status["valid"]:
        raise FileNotFoundError(f"S0 inputs missing: {contract_status['missing_inputs']}")

    intake_manifest = read_json(book_root / "_inputs" / "intake_manifest.json", default=None)
    if intake_manifest is None:
        raise FileNotFoundError("Missing intake manifest for architecture stage.")

    proposal_text = read_text(book_root / "_inputs" / "proposal.md")
    toc_seed = read_text(book_root / "_inputs" / "toc_seed.md")

    book_db = read_json(book_root / "db" / "book_db.json", default={})
    current_status = book_db.get("book_level_stages", {}).get("S0", {}).get("status")
    if current_status != "completed":
        transition_stage(book_root, "S0", "in_progress", note="AG-AR architecture generation started.")

    config = _book_config(
        book_id,
        intake_manifest["display_name"],
        book_root,
        intake_manifest,
        proposal_text,
        toc_seed,
    )
    word_targets = build_word_targets(book_id, config["working_title"], intake_manifest)
    anchor_policy = build_anchor_policy(book_id, config["working_title"], intake_manifest, word_targets)
    config["manuscript_targets"] = {
        "total_target_words": word_targets["total_target_words"],
        "lock_stage": "S0",
        "draft1_target_ratio": 0.9,
        "draft2_target_ratio": 0.92,
        "final_draft_target_ratio": 0.95,
    }
    config["anchor_system"] = {
        "catalog_version": anchor_policy["catalog_version"],
        "total_anchor_budget": anchor_policy["total_anchor_budget"],
        "grammar_type": anchor_policy["grammar"]["block_type"],
    }
    config["reference_policy"] = anchor_policy["reference_policy"]
    config["visual_source_priority"] = anchor_policy.get("visual_source_priority", [])

    write_json(book_root / "_master" / "BOOK_CONFIG.json", config)
    write_json(book_root / "_master" / "WORD_TARGETS.json", word_targets)
    write_json(book_root / "_master" / "ANCHOR_POLICY.json", anchor_policy)
    write_text(book_root / "_master" / "BOOK_BLUEPRINT.md", _build_blueprint_markdown(config, intake_manifest, word_targets, anchor_policy))
    write_text(book_root / "_master" / "STYLE_GUIDE.md", _build_style_guide_markdown(config))
    write_text(book_root / "_master" / "QUALITY_CRITERIA.md", _build_quality_criteria_markdown(intake_manifest, word_targets))

    gate_result = evaluate_gate(book_id, book_root, "S0")
    if not gate_result["passed"]:
        transition_stage(book_root, "S0", "gate_failed", note=json.dumps(gate_result, ensure_ascii=False))
        return {
            "stage_id": "S0",
            "status": "gate_failed",
            "gate_result": gate_result,
        }

    transition_stage(book_root, "S0", "completed", note="AG-AR architecture generation completed.")
    return {
        "stage_id": "S0",
        "status": "completed",
        "outputs": [
            str(book_root / "_master" / "BOOK_CONFIG.json"),
            str(book_root / "_master" / "WORD_TARGETS.json"),
            str(book_root / "_master" / "ANCHOR_POLICY.json"),
            str(book_root / "_master" / "BOOK_BLUEPRINT.md"),
            str(book_root / "_master" / "STYLE_GUIDE.md"),
            str(book_root / "_master" / "QUALITY_CRITERIA.md"),
        ],
        "gate_result": gate_result,
    }
