from __future__ import annotations

from typing import Any

from .common import now_iso


NEWS_LIKE_TYPES = {"news", "news_explainer", "critic_review", "recent_news"}
SOCIAL_LIKE_TYPES = {"social_trend", "recent_ugc", "recent_review"}
ACADEMIC_LIKE_TYPES = {"primary_history_source", "scholarly_reference"}
OFFICIAL_INFO_TYPES = {"official_source", "official_film_info", "official_tourism", "official_local_info"}


def _classify_visual_rights(entry: dict[str, Any], image_item: dict[str, Any] | None) -> dict[str, Any]:
    source_mode = (image_item or {}).get("source_mode", entry.get("source_kind"))
    if entry.get("source_kind") == "structured_visual":
        return {
            "risk_level": "low",
            "rights_category": "engine_structured_visual",
            "usage_policy": "direct_use_allowed",
            "required_action": "appendix provenance only",
            "clearance_status": "internal_render_ok",
            "reason": "engine rendered visual asset without third-party image reuse",
        }
    if entry.get("source_kind") == "ai_generated_image" or source_mode == "ai_generated_image":
        return {
            "risk_level": "medium",
            "rights_category": "ai_generated_visual",
            "usage_policy": "allowed_with_provenance_and_safety_check",
            "required_action": "record model, prompt, revision, likeness/trademark review",
            "clearance_status": "provenance_required",
            "reason": "AI image may be publishable, but provenance and likeness review are mandatory",
        }
    if source_mode in {"external_image", "video_embed"} or entry.get("source_type") in {"EP", "TD", "VE"}:
        return {
            "risk_level": "high",
            "rights_category": "third_party_visual_asset",
            "usage_policy": "permission_or_replacement_required",
            "required_action": "obtain written permission or replace with self-shot/public-license/illustration",
            "clearance_status": "permission_required",
            "reason": "third-party image/video reuse in commercial publishing needs license or explicit permission",
        }
    return {
        "risk_level": "medium",
        "rights_category": "manual_or_unspecified_visual",
        "usage_policy": "manual_review_required",
        "required_action": "confirm origin, rights note, and commercial use compatibility",
        "clearance_status": "needs_manual_review",
        "reason": "visual source mode is not fully resolved",
    }


def _classify_text_rights(entry: dict[str, Any]) -> dict[str, Any]:
    source_type = entry.get("source_type", "")
    if source_type in NEWS_LIKE_TYPES:
        return {
            "risk_level": "medium",
            "rights_category": "news_or_review_text",
            "usage_policy": "paraphrase_only_with_short_quote_exception",
            "required_action": "rewrite in house style, keep attribution, limit direct quote length",
            "clearance_status": "paraphrase_required",
            "reason": "facts are usable but article expression and composition remain copyrighted",
        }
    if source_type in SOCIAL_LIKE_TYPES:
        return {
            "risk_level": "high",
            "rights_category": "user_generated_content",
            "usage_policy": "consent_or_aggregation_only",
            "required_action": "obtain consent, anonymize, or convert into aggregate statistics/insights",
            "clearance_status": "consent_required",
            "reason": "UGC and individual commentary may trigger copyright, privacy, and portrait/publicity concerns",
        }
    if source_type in OFFICIAL_INFO_TYPES:
        return {
            "risk_level": "medium",
            "rights_category": "official_information_or_press_material",
            "usage_policy": "facts_may_be_cited_visual_assets_need_separate_clearance",
            "required_action": "use facts via paraphrase; if press photos/stills are used, obtain distributor or owner approval",
            "clearance_status": "commercial_terms_check_required",
            "reason": "official facts can guide text, but promotional visuals often need separate publishing approval",
        }
    if source_type in ACADEMIC_LIKE_TYPES:
        return {
            "risk_level": "low",
            "rights_category": "historical_or_scholarly_reference",
            "usage_policy": "citation_and_paraphrase_allowed",
            "required_action": "preserve citation accuracy and append to reference index",
            "clearance_status": "citation_required",
            "reason": "scholarly/historical sources are generally safe when properly cited and paraphrased",
        }
    if source_type == "map_service":
        return {
            "risk_level": "medium",
            "rights_category": "map_service_content",
            "usage_policy": "derived_use_preferred",
            "required_action": "avoid direct tile/screenshot reuse unless licensed; prefer derived schematic/map note",
            "clearance_status": "license_check_required",
            "reason": "map service screenshots and tiles usually have platform-specific reuse restrictions",
        }
    return {
        "risk_level": "medium",
        "rights_category": "general_external_reference",
        "usage_policy": "paraphrase_and_attribute",
        "required_action": "confirm citation accuracy and avoid verbatim copying",
        "clearance_status": "review_required",
        "reason": "external reference is usable only through attribution-safe paraphrase and source tracking",
    }


def assess_rights_entry(
    entry: dict[str, Any],
    image_item: dict[str, Any] | None = None,
) -> dict[str, Any]:
    if entry.get("reference_domain") == "visual_anchor":
        result = _classify_visual_rights(entry, image_item)
    else:
        result = _classify_text_rights(entry)
    return {
        "reference_id": entry.get("reference_id"),
        "chapter_id": entry.get("chapter_id"),
        "reference_domain": entry.get("reference_domain"),
        "source_type": entry.get("source_type"),
        "source_kind": entry.get("source_kind"),
        "appendix_required": entry.get("appendix_required", True),
        "url_or_identifier": entry.get("url_or_identifier", ""),
        "source_name": entry.get("source_name", ""),
        "title": entry.get("title", ""),
        **result,
    }


def build_chapter_rights_review(
    chapter: dict[str, Any],
    reference_entries: list[dict[str, Any]],
    image_items: list[dict[str, Any]],
) -> dict[str, Any]:
    image_lookup = {item.get("appendix_reference_id"): item for item in image_items}
    reviewed_items = [
        assess_rights_entry(entry, image_lookup.get(entry.get("reference_id")))
        for entry in reference_entries
    ]

    risk_counts = {"high": 0, "medium": 0, "low": 0}
    blocking_items: list[dict[str, Any]] = []
    required_actions: list[str] = []
    for item in reviewed_items:
        risk_counts[item["risk_level"]] = risk_counts.get(item["risk_level"], 0) + 1
        if item["risk_level"] == "high":
            blocking_items.append(
                {
                    "reference_id": item["reference_id"],
                    "category": item["rights_category"],
                    "required_action": item["required_action"],
                }
            )
        if item["required_action"] not in required_actions:
            required_actions.append(item["required_action"])

    verdict = "pass_with_actions"
    if blocking_items:
        verdict = "manual_clearance_required"

    return {
        "version": "1.0",
        "generated_at": now_iso(),
        "chapter_id": chapter["chapter_id"],
        "chapter_title": chapter["title"],
        "review_scope": {
            "text_reference_reviewed": True,
            "visual_reference_reviewed": True,
            "commercial_publication_context": True,
            "portrait_privacy_review_required_for_ugc_or_faces": True,
        },
        "summary": {
            "total_items": len(reviewed_items),
            "high_risk_count": risk_counts.get("high", 0),
            "medium_risk_count": risk_counts.get("medium", 0),
            "low_risk_count": risk_counts.get("low", 0),
            "blocking_item_count": len(blocking_items),
        },
        "verdict": verdict,
        "required_actions": required_actions,
        "blocking_items": blocking_items,
        "items": reviewed_items,
        "policy_notes": [
            "news and reviews must be paraphrased rather than copied verbatim",
            "ugc requires consent, anonymization, or aggregate/statistical transformation",
            "third-party visuals require explicit permission or replacement with safe alternatives",
            "all external and ai-generated materials must remain traceable via appendix reference index",
        ],
    }


def apply_image_manifest_rights_annotations(
    image_items: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    updated: list[dict[str, Any]] = []
    for item in image_items:
        source_mode = item.get("source_mode")
        annotated = dict(item)
        if source_mode in {"table", "chart", "summary_box", "callout", "timeline", "network", "footnote", "code_block"}:
            annotated["rights_status"] = "internal_structured_ok"
            annotated["clearance_action"] = "appendix provenance only"
        elif source_mode == "ai_generated_image":
            annotated["rights_status"] = "provenance_required"
            annotated["clearance_action"] = "record model, prompt, revision, likeness/trademark review"
        elif source_mode in {"external_image", "video_embed"}:
            annotated["rights_status"] = "permission_required"
            annotated["clearance_action"] = "written permission or safe replacement required"
        else:
            annotated["rights_status"] = "needs_manual_review"
            annotated["clearance_action"] = "confirm origin and commercial use compatibility"
        annotated["rights_reviewed_at"] = now_iso()
        annotated["rights_review_stage"] = "S5"
        updated.append(annotated)
    return updated
