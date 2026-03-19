from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from .references import build_image_manifest, build_reference_appendix, build_reference_index
from .book_state import load_book_db
from .common import now_iso, read_json, read_text, write_json
from .contracts import validate_inputs
from .gates import evaluate_gate
from .stage import transition_stage


def _audience_segment_for_part(book_config: dict[str, Any], part: str | None) -> dict[str, str]:
    default_segment = {
        "segment_id": "general_reader",
        "focus": book_config.get("audience", "general reader"),
        "reader_payoff": "A clear and useful chapter outcome.",
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


def _rights_constraints(book_config: dict[str, Any], part: str | None) -> list[str]:
    policy = book_config.get("rights_policy", {})
    constraints = [
        "All external materials must be indexable in the appendix reference index.",
    ]
    if policy.get("news_text_policy"):
        constraints.append("News and article text must be paraphrased; direct quotation should stay minimal and attributable.")
    if policy.get("ugc_policy"):
        constraints.append("UGC or SNS content must be backed by consent, anonymization, or aggregation before publication use.")
    if policy.get("film_still_and_press_photo_policy"):
        constraints.append("Film stills and press photos require written permission or a safe replacement such as illustration.")
    if policy.get("external_photo_policy"):
        constraints.append("Prefer self-shot or public-license images over third-party captures.")
    if policy.get("map_service_policy"):
        constraints.append("Map screenshots or platform captures require license review before direct use.")
    label = part or ""
    if "TRAVEL" in label or "TASTE" in label:
        constraints.append("Location and menu facts should be refreshed against recent official or high-trust local sources.")
    return constraints


def _chapter_questions(chapter: dict[str, Any]) -> list[str]:
    title = chapter["title"]
    part = chapter.get("part", "")
    if "CINEMA" in part:
        return [
            f"What performance, directing, or reception evidence supports '{title}'?",
            f"What current discussion or controversy is attached to '{title}'?",
        ]
    if "HISTORY" in part:
        return [
            f"What primary or high-trust secondary sources validate the historical claims in '{title}'?",
            f"What misconceptions should be corrected for '{title}'?",
        ]
    if "TRAVEL" in part:
        return [
            f"What current visitor information, transport detail, or location guidance is needed for '{title}'?",
            f"What experiential angle should be verified for '{title}'?",
        ]
    if "TASTE" in part:
        return [
            f"What current menu, area, or local-food context is needed for '{title}'?",
            f"What recommendation details should be validated for '{title}'?",
        ]
    return [
        f"What evidence is required to support '{title}'?",
        f"What reader-value question should be answered for '{title}'?",
    ]


def _freshness_window_days(book_config: dict[str, Any], part: str | None) -> int:
    policy = book_config.get("freshness_policy", {})
    label = part or ""
    if "TRAVEL" in label or "TASTE" in label:
        return int(policy.get("travel_and_local_info_days", 30))
    return int(policy.get("news_and_trend_days", 14))


def _source_types_for_part(part: str) -> list[str]:
    if "CINEMA" in part:
        return ["official_film_info", "news", "critic_review", "social_trend"]
    if "HISTORY" in part:
        return ["primary_history_source", "scholarly_reference", "news_explainer"]
    if "TRAVEL" in part:
        return ["official_tourism", "map_service", "recent_news", "recent_ugc"]
    if "TASTE" in part:
        return ["map_service", "official_local_info", "recent_review", "recent_news"]
    return ["official_source", "news"]


def _slot_profile_for_source_type(chapter: dict[str, Any], source_type: str) -> dict[str, Any]:
    title = chapter["title"]
    part = chapter.get("part", "") or ""
    if part == "INTRO":
        if source_type == "official_source":
            return {
                "claim_role": "opening_factual_baseline",
                "verification_goal": f"Validate the official film baseline and any official context that supports the opening framing of '{title}'.",
                "preferred_source_profile": [
                    "official_distributor_or_press",
                    "official_box_office_or_film_database",
                ],
                "query_hint": f"{title} official film information distributor press box office",
                "section_alignment": ["Context", "Insight"],
                "usage_constraint": "Use only attributable facts; paraphrase in house style and separate any still/photo usage from text citation.",
            }
        if source_type == "news":
            return {
                "claim_role": "current_reaction_and_trend_signal",
                "verification_goal": f"Validate current audience reaction, trend, or controversy framing used in the opening of '{title}'.",
                "preferred_source_profile": [
                    "high_trust_culture_news",
                    "reported_trend_feature",
                ],
                "query_hint": f"{title} current audience reaction trend controversy coverage",
                "section_alignment": ["Hook", "Takeaway"],
                "usage_constraint": "Do not copy article phrasing; use paraphrase and keep only minimal attributable quotation.",
            }
    if "CINEMA" in part:
        mapping = {
            "official_film_info": {
                "claim_role": "film_production_and_release_baseline",
                "verification_goal": f"Confirm official cast, release, distributor, production, and officially published facts for '{title}'.",
                "preferred_source_profile": ["official_distributor_or_press", "official_film_database"],
                "query_hint": f"{title} official cast release distributor press",
                "section_alignment": ["Context", "Insight"],
                "usage_constraint": "Use facts only; any official visuals require separate permission review.",
            },
            "news": {
                "claim_role": "current_issue_or_reception_signal",
                "verification_goal": f"Confirm current issues, reception, or controversy linked to '{title}'.",
                "preferred_source_profile": ["high_trust_news", "culture_desk_reporting"],
                "query_hint": f"{title} current controversy reception article",
                "section_alignment": ["Hook", "Insight"],
                "usage_constraint": "Paraphrase only and keep direct quotation minimal.",
            },
            "critic_review": {
                "claim_role": "critical_interpretation_support",
                "verification_goal": f"Capture attributable critical interpretation relevant to '{title}'.",
                "preferred_source_profile": ["critic_review", "reported_feature"],
                "query_hint": f"{title} critic review interpretation",
                "section_alignment": ["Insight"],
                "usage_constraint": "Prefer paraphrased critical insight over long quotation.",
            },
            "social_trend": {
                "claim_role": "audience_signal_or_social_buzz",
                "verification_goal": f"Track social buzz or audience signal for '{title}' without depending on individual UGC reuse.",
                "preferred_source_profile": ["aggregated_social_signal", "reported_social_trend"],
                "query_hint": f"{title} social buzz trend audience reaction",
                "section_alignment": ["Hook", "Takeaway"],
                "usage_constraint": "Use consented, anonymized, or aggregated signals only.",
            },
        }
        if source_type in mapping:
            return mapping[source_type]
    if "HISTORY" in part:
        mapping = {
            "primary_history_source": {
                "claim_role": "primary_record_baseline",
                "verification_goal": f"Validate the core historical facts or timeline for '{title}' using primary or near-primary records.",
                "preferred_source_profile": ["primary_record", "official_archive"],
                "query_hint": f"{title} primary historical record official archive",
                "section_alignment": ["Context", "Insight"],
                "usage_constraint": "Preserve citation accuracy and distinguish record from interpretation.",
            },
            "scholarly_reference": {
                "claim_role": "secondary_interpretation_support",
                "verification_goal": f"Collect scholarly interpretation that helps contextualize '{title}'.",
                "preferred_source_profile": ["scholarly_reference", "museum_or_research_institute"],
                "query_hint": f"{title} scholarly interpretation research paper",
                "section_alignment": ["Insight"],
                "usage_constraint": "Prefer paraphrased interpretation and clearly separate inference from record.",
            },
            "news_explainer": {
                "claim_role": "reader_friendly_fact_translation",
                "verification_goal": f"Find high-trust explainers that help modern readers understand '{title}' accurately.",
                "preferred_source_profile": ["explainer_feature", "high_trust_news"],
                "query_hint": f"{title} explainer historical context",
                "section_alignment": ["Hook", "Takeaway"],
                "usage_constraint": "Use as explanatory support, not as sole proof of historical claims.",
            },
        }
        if source_type in mapping:
            return mapping[source_type]
    if "TRAVEL" in part:
        mapping = {
            "official_tourism": {
                "claim_role": "visitor_information_baseline",
                "verification_goal": f"Confirm official access, hours, and visitor-facing information for '{title}'.",
                "preferred_source_profile": ["official_tourism_site", "official_local_government"],
                "query_hint": f"{title} official tourism hours access",
                "section_alignment": ["Context", "Takeaway"],
                "usage_constraint": "Refresh against current official information before publication.",
            },
            "map_service": {
                "claim_role": "location_and_route_support",
                "verification_goal": f"Support route, area, and location guidance for '{title}' without relying on unlicensed screenshots.",
                "preferred_source_profile": ["licensed_map_service_metadata", "official_address_listing"],
                "query_hint": f"{title} address route map listing",
                "section_alignment": ["Context"],
                "usage_constraint": "Prefer derived route notes or schematic maps over direct map screenshot reuse.",
            },
            "recent_news": {
                "claim_role": "recent_operational_change_signal",
                "verification_goal": f"Check whether recent closures, changes, or operational updates affect '{title}'.",
                "preferred_source_profile": ["high_trust_local_news", "official_notice"],
                "query_hint": f"{title} recent closure update notice",
                "section_alignment": ["Takeaway"],
                "usage_constraint": "Use only current and attributable operational updates.",
            },
            "recent_ugc": {
                "claim_role": "visitor_experience_signal",
                "verification_goal": f"Capture visitor experience signals for '{title}' through aggregate trend rather than direct individual reuse.",
                "preferred_source_profile": ["aggregated_review_signal", "consented_ugc"],
                "query_hint": f"{title} recent visitor review trend",
                "section_alignment": ["Hook", "Takeaway"],
                "usage_constraint": "Do not reuse identifiable UGC without consent; prefer aggregation.",
            },
        }
        if source_type in mapping:
            return mapping[source_type]
    if "TASTE" in part:
        mapping = {
            "map_service": {
                "claim_role": "location_and_route_support",
                "verification_goal": f"Confirm area, access, and mapping context for '{title}'.",
                "preferred_source_profile": ["licensed_map_service_metadata", "official_listing"],
                "query_hint": f"{title} location route listing",
                "section_alignment": ["Context"],
                "usage_constraint": "Prefer derived route notes over direct screenshot reuse.",
            },
            "official_local_info": {
                "claim_role": "local_information_baseline",
                "verification_goal": f"Confirm official local information that supports '{title}'.",
                "preferred_source_profile": ["official_local_listing", "official_tourism_site"],
                "query_hint": f"{title} official local information",
                "section_alignment": ["Context", "Takeaway"],
                "usage_constraint": "Refresh operational details before publication.",
            },
            "recent_review": {
                "claim_role": "current_visit_or_menu_signal",
                "verification_goal": f"Check recent visit or menu-related signals for '{title}' without reusing individual review text directly.",
                "preferred_source_profile": ["aggregated_review_signal", "reported_local_feature"],
                "query_hint": f"{title} recent review menu trend",
                "section_alignment": ["Hook", "Takeaway"],
                "usage_constraint": "Aggregate or paraphrase only; do not copy individual reviews.",
            },
            "recent_news": {
                "claim_role": "recent_operational_change_signal",
                "verification_goal": f"Check whether recent local news affects '{title}'.",
                "preferred_source_profile": ["high_trust_local_news", "official_notice"],
                "query_hint": f"{title} recent local update notice",
                "section_alignment": ["Takeaway"],
                "usage_constraint": "Use only attributable and current operational information.",
            },
        }
        if source_type in mapping:
            return mapping[source_type]
    return {
        "claim_role": f"{source_type}_support",
        "verification_goal": f"Collect attributable support for '{title}' via {source_type}.",
        "preferred_source_profile": ["high_trust_source"],
        "query_hint": f"{title} {source_type}",
        "section_alignment": ["Context", "Insight"],
        "usage_constraint": "Keep claims attributable and publication-safe.",
    }


def _reference_slots_for_chapter(
    chapter: dict[str, Any],
    source_types: list[str],
    book_config: dict[str, Any],
) -> list[dict[str, Any]]:
    slots: list[dict[str, Any]] = []
    freshness_window_days = _freshness_window_days(book_config, chapter.get("part"))
    for index, source_type in enumerate(source_types, start=1):
        slot_profile = _slot_profile_for_source_type(chapter, source_type)
        slots.append(
            {
                "reference_id": f"REF_{chapter['chapter_id'].upper()}_{index:03d}",
                "source_type": source_type,
                "priority": "high" if source_type in {"official_tourism", "primary_history_source", "official_film_info", "official_source"} else "medium",
                "claim_role": slot_profile["claim_role"],
                "verification_goal": slot_profile["verification_goal"],
                "preferred_source_profile": slot_profile["preferred_source_profile"],
                "query_hint": slot_profile["query_hint"],
                "section_alignment": slot_profile["section_alignment"],
                "usage_constraint": slot_profile["usage_constraint"],
                "freshness_window_days": freshness_window_days,
                "verification_mode": "grounded_required",
            }
        )
    return slots


def _citation_scaffold(chapters: list[dict[str, Any]]) -> dict[str, Any]:
    return {
        "version": "1.0",
        "generated_at": now_iso(),
        "chapters": [
            {
                "chapter_id": chapter["chapter_id"],
                "citations": [],
                "status": "needs_research_attachment",
            }
            for chapter in chapters
        ],
    }


def run_research_plan(book_id: str, book_root: Path) -> dict[str, Any]:
    contract_status = validate_inputs(book_id, book_root, "S2")
    if not contract_status["valid"]:
        raise FileNotFoundError(f"S2 inputs missing: {contract_status['missing_inputs']}")

    current_status = load_book_db(book_root)["book_level_stages"]["S2"]["status"]
    if current_status != "completed":
        transition_stage(book_root, "S2", "in_progress", note="AG-RS research planning started.")

    intake_manifest = read_json(book_root / "_inputs" / "intake_manifest.json", default=None)
    book_config = read_json(book_root / "_master" / "BOOK_CONFIG.json", default=None)
    anchor_policy = read_json(book_root / "_master" / "ANCHOR_POLICY.json", default=None)
    proposal_text = read_text(book_root / "_inputs" / "proposal.md")
    toc_seed = read_text(book_root / "_inputs" / "toc_seed.md")
    if intake_manifest is None or book_config is None or anchor_policy is None:
        raise FileNotFoundError("Research plan requires intake manifest, book config, and anchor policy.")

    chapters = []
    queue_items = []
    for chapter in intake_manifest.get("chapters_detected", []):
        questions = _chapter_questions(chapter)
        source_types = _source_types_for_part(chapter.get("part", ""))
        reader_segment = _audience_segment_for_part(book_config, chapter.get("part"))
        rights_constraints = _rights_constraints(book_config, chapter.get("part"))
        reference_slots = _reference_slots_for_chapter(chapter, source_types, book_config)
        chapters.append(
            {
                "chapter_id": chapter["chapter_id"],
                "title": chapter["title"],
                "part": chapter.get("part"),
                "research_questions": questions,
                "source_types": source_types,
                "reference_slots": reference_slots,
                "reader_segment": reader_segment,
                "rights_constraints": rights_constraints,
            }
        )
        for slot in reference_slots:
            queue_items.append(
                {
                    "chapter_id": chapter["chapter_id"],
                    "reference_id": slot["reference_id"],
                    "source_type": slot["source_type"],
                    "priority": slot["priority"],
                    "claim_role": slot["claim_role"],
                    "verification_goal": slot["verification_goal"],
                    "preferred_source_profile": slot["preferred_source_profile"],
                    "query_hint": slot["query_hint"],
                    "section_alignment": slot["section_alignment"],
                    "freshness_window_days": slot["freshness_window_days"],
                    "verification_mode": slot["verification_mode"],
                    "usage_constraint": slot["usage_constraint"],
                    "reader_segment": reader_segment,
                    "reader_segment_id": reader_segment["segment_id"],
                    "rights_notes": rights_constraints[:2],
                    "rights_constraints": rights_constraints,
                }
            )

    research_plan = {
        "version": "1.0",
        "generated_at": now_iso(),
        "book_id": book_id,
        "working_title": book_config["working_title"],
        "audience": book_config["audience"],
        "audience_segments": book_config.get("audience_segments", []),
        "rights_policy": book_config.get("rights_policy", {}),
        "visual_source_priority": book_config.get("visual_source_priority", []),
        "freshness_policy": {
            "travel_and_local_info_days": 30,
            "news_and_trend_days": 14,
            "historical_reference_policy": "use highest-trust stable sources and annotate interpretation"
        },
        "proposal_signal": proposal_text[:500],
        "toc_signal": toc_seed[:500],
        "chapters": chapters,
    }

    source_queue = {
        "version": "1.0",
        "generated_at": now_iso(),
        "book_id": book_id,
        "rights_policy": book_config.get("rights_policy", {}),
        "visual_source_priority": book_config.get("visual_source_priority", []),
        "items": queue_items,
    }
    citations = _citation_scaffold(chapters)
    reference_index = build_reference_index(book_id, research_plan, anchor_policy)
    image_manifest = build_image_manifest(book_id, anchor_policy)
    reference_appendix = build_reference_appendix(book_id, reference_index, image_manifest, citations)

    write_json(book_root / "research" / "research_plan.json", research_plan)
    write_json(book_root / "research" / "source_queue.json", source_queue)
    write_json(book_root / "research" / "citations.json", citations)
    write_json(book_root / "research" / "reference_index.json", reference_index)
    write_json(book_root / "research" / "image_manifest.json", image_manifest)
    (book_root / "publication" / "appendix").mkdir(parents=True, exist_ok=True)
    (book_root / "publication" / "appendix" / "REFERENCE_INDEX.md").write_text(reference_appendix, encoding="utf-8")

    gate_result = evaluate_gate(book_id, book_root, "S2")
    if not gate_result["passed"]:
        transition_stage(book_root, "S2", "gate_failed", note=json.dumps(gate_result, ensure_ascii=False))
        return {
            "stage_id": "S2",
            "status": "gate_failed",
            "gate_result": gate_result,
        }

    transition_stage(book_root, "S2", "completed", note="AG-RS research planning completed.")
    return {
        "stage_id": "S2",
        "status": "completed",
        "outputs": [
            str(book_root / "research" / "research_plan.json"),
            str(book_root / "research" / "source_queue.json"),
            str(book_root / "research" / "citations.json"),
            str(book_root / "research" / "reference_index.json"),
            str(book_root / "research" / "image_manifest.json"),
            str(book_root / "publication" / "appendix" / "REFERENCE_INDEX.md"),
        ],
        "gate_result": gate_result,
    }
