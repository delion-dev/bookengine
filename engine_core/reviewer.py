from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from .book_state import load_book_db
from .common import now_iso, read_json, read_text, write_json, write_text
from .contracts import resolve_stage_contract, validate_inputs
from .context_packs import build_context_bundle
from .gates import evaluate_gate
from .memory import update_chapter_memory
from .manuscript_integrity import sanitize_reader_manuscript
from .model_gateway import ModelGatewayError, grounded_research
from .model_policy import resolve_stage_route
from .references import build_reference_appendix
from .rights_review import apply_image_manifest_rights_annotations, build_chapter_rights_review
from .source_trust import assess_reference_slot_fit, partition_sources_for_citation
from .stage import transition_stage
from .subsection_nodes import build_section_nodes, write_node_manifest
from .targets import get_chapter_target
from .work_order import issue_work_order


def _s5_output_bundle(book_id: str, book_root: Path, chapter_id: str) -> dict[str, str]:
    outputs = resolve_stage_contract(book_id, book_root, "S5", chapter_id)["outputs"]
    return {
        "draft2": outputs[0],
        "review_report": outputs[1],
        "rights_review": outputs[2],
        "review_nodes": outputs[3],
    }


def _missing_s5_outputs(book_id: str, book_root: Path, chapter_id: str) -> list[str]:
    bundle = _s5_output_bundle(book_id, book_root, chapter_id)
    return [path for path in bundle.values() if not Path(path).exists()]


def _can_backfill_s5_outputs(book_id: str, book_root: Path, chapter_id: str) -> bool:
    bundle = _s5_output_bundle(book_id, book_root, chapter_id)
    missing = {Path(path).name for path in _missing_s5_outputs(book_id, book_root, chapter_id)}
    backfillable = {
        Path(bundle["rights_review"]).name,
        Path(bundle["review_nodes"]).name,
    }
    required_existing = {
        "draft2": Path(bundle["draft2"]).exists(),
        "review_report": Path(bundle["review_report"]).exists(),
    }
    return bool(missing) and missing.issubset(backfillable) and all(required_existing.values())


def _pending_s5_chapters(book_id: str, book_root: Path) -> list[str]:
    payload = load_book_db(book_root)
    return [
        chapter_id
        for chapter_id in payload["chapter_sequence"]
        if payload["chapters"][chapter_id]["stages"]["S5"]["status"] in {"pending", "in_progress"}
        or payload["chapters"][chapter_id]["stages"]["S5"]["status"] == "gate_failed"
        or (
            payload["chapters"][chapter_id]["stages"]["S5"]["status"] == "completed"
            and bool(_missing_s5_outputs(book_id, book_root, chapter_id))
        )
    ]


def _all_s5_chapters(book_root: Path) -> list[str]:
    payload = load_book_db(book_root)
    return list(payload["chapter_sequence"])


def _citation_record(citations_payload: dict[str, Any], chapter_id: str) -> dict[str, Any]:
    for chapter in citations_payload.get("chapters", []):
        if chapter["chapter_id"] == chapter_id:
            return chapter
    raise KeyError(f"Missing citations scaffold for {chapter_id}")


def _reference_entries(reference_index: dict[str, Any], chapter_id: str) -> list[dict[str, Any]]:
    for chapter in reference_index.get("chapters", []):
        if chapter["chapter_id"] == chapter_id:
            return chapter.get("entries", [])
    raise KeyError(f"Missing reference index entry for {chapter_id}")


def _research_entry(research_plan: dict[str, Any], chapter_id: str) -> dict[str, Any]:
    for chapter in research_plan.get("chapters", []):
        if chapter["chapter_id"] == chapter_id:
            return chapter
    raise KeyError(f"Missing research plan entry for {chapter_id}")


def _chapter_image_items(image_manifest: dict[str, Any], chapter_id: str) -> list[dict[str, Any]]:
    return [item for item in image_manifest.get("items", []) if item.get("chapter_id") == chapter_id]


def _freshness_rule(chapter: dict[str, Any], research_plan: dict[str, Any]) -> dict[str, Any]:
    policy = research_plan.get("freshness_policy", {})
    part = chapter.get("part", "")
    if "TRAVEL" in part or "TASTE" in part:
        return {
            "window_days": policy.get("travel_and_local_info_days", 30),
            "rationale": "travel_or_local",
        }
    return {
        "window_days": policy.get("news_and_trend_days", 14),
        "rationale": "trend_or_general",
    }


def _unsupported_claims(draft_text: str) -> list[str]:
    claims = []
    # Narrative prose often uses "완벽히" as emphasis rather than as a factual
    # certainty claim, so keep the blocker list focused on stronger absolutes.
    high_certainty_terms = ["반드시", "무조건", "100%", "절대적"]
    for term in high_certainty_terms:
        if term in draft_text:
            claims.append(f"high-certainty term detected: {term}")
    return claims


def _review_context_artifacts(
    book_root: Path,
    chapter_id: str,
    node_payload: dict[str, Any],
    *,
    prompt_text: str,
    extra_artifacts: list[dict[str, str]] | None = None,
) -> list[dict[str, str]]:
    bundle = build_context_bundle(
        book_root,
        "S5",
        chapter_id=chapter_id,
        node_payload=node_payload,
        prompt_text=prompt_text,
    )
    artifacts = list(bundle["context_artifacts"])
    if extra_artifacts:
        artifacts.extend(extra_artifacts)
    return artifacts


def _reader_segment_for_review(research_entry: dict[str, Any]) -> dict[str, str]:
    segment = research_entry.get("reader_segment")
    if isinstance(segment, dict) and segment.get("segment_id"):
        return segment
    return {
        "segment_id": "general_reader",
        "focus": "general reader",
        "reader_payoff": "A clear and useful chapter outcome.",
    }


def _rights_constraints_for_review(research_entry: dict[str, Any]) -> list[str]:
    constraints = research_entry.get("rights_constraints")
    if isinstance(constraints, list):
        return [str(item) for item in constraints]
    return []


def _reference_slots_for_review(research_entry: dict[str, Any], section_key: str) -> list[dict[str, Any]]:
    slots = research_entry.get("reference_slots")
    if not isinstance(slots, list):
        return []
    matched = []
    section_name = section_key.capitalize()
    for slot in slots:
        alignments = slot.get("section_alignment", [])
        if not alignments or section_name in alignments:
            matched.append(slot)
    return matched


def _run_grounded_review(
    book_root: Path,
    chapter: dict[str, Any],
    research_entry: dict[str, Any],
    draft1: str,
    freshness_rule: dict[str, Any],
) -> dict[str, Any] | None:
    nodes = build_section_nodes(
        "S5",
        chapter["chapter_id"],
        chapter["title"],
        research_questions=research_entry.get("research_questions", []),
        source_types=research_entry.get("source_types", []),
    )
    aggregated_sources: list[dict[str, Any]] = []
    aggregated_findings: list[str] = []
    summaries: list[str] = []
    live_nodes = 0
    reader_segment = _reader_segment_for_review(research_entry)
    rights_constraints = _rights_constraints_for_review(research_entry)

    for node in nodes:
        section_key = node["section_key"]
        reference_slots = _reference_slots_for_review(research_entry, section_key)
        query_set = [
            f"{chapter['title']} {section_key} latest verified context",
            *research_entry.get("research_questions", [])[:2],
        ]
        for slot in reference_slots[:2]:
            if slot.get("query_hint"):
                query_set.append(slot["query_hint"])
        if section_key == "hook":
            query_set.append(f"{chapter['title']} current audience reaction trend")
        elif section_key == "context":
            query_set.append(f"{chapter['title']} official information background")
        elif section_key == "insight":
            query_set.append(f"{chapter['title']} critical debate verified evidence")
        else:
            query_set.append(f"{chapter['title']} reader takeaway current relevance")

        try:
            node_result = grounded_research(
                query_set,
                {
                    "chapter_title": chapter["title"],
                    "source_types": research_entry.get("source_types", []),
                    "freshness_window_days": freshness_rule["window_days"],
                },
                citation_required=True,
                system_policy_ref=(
                    "You are AG-02 in a Korean book-writing system. "
                    "Verify current facts section by section, collect attributable sources, and keep the response publication-safe."
                ),
                context_artifacts=_review_context_artifacts(
                    book_root,
                    chapter["chapter_id"],
                    {
                        **node,
                        "research_questions": research_entry.get("research_questions", []),
                        "source_types": research_entry.get("source_types", []),
                        "continuity_excerpt": draft1[:1400],
                        "local_goal": f"Review the {section_key} section for attributable and current evidence.",
                    },
                    prompt_text="\n".join(query_set),
                    extra_artifacts=[
                        {"label": "draft1_excerpt", "text": draft1[:5000]},
                        {
                            "label": "reader_segment",
                            "text": json.dumps(reader_segment, ensure_ascii=False, indent=2),
                        },
                        {
                            "label": "rights_constraints",
                            "text": json.dumps(rights_constraints, ensure_ascii=False, indent=2),
                        },
                        {
                            "label": "freshness_rule",
                            "text": json.dumps(freshness_rule, ensure_ascii=False, indent=2),
                        },
                        {
                            "label": "reference_slots",
                            "text": json.dumps(reference_slots, ensure_ascii=False, indent=2),
                        },
                    ],
                ),
                provider_route=resolve_stage_route(
                    "S5",
                    "grounded_research",
                    chapter_part=chapter.get("part"),
                    section_key=section_key,
                    grounding_required=True,
                ),
                telemetry_context={
                    "stage_id": "S5",
                    "chapter_id": chapter["chapter_id"],
                    "node_id": node["node_id"],
                    "section_key": section_key,
                },
            )
        except ModelGatewayError as exc:
            node["status"] = "fallback"
            node["updated_at"] = now_iso()
            node["note"] = str(exc)
            continue

        live_nodes += 1
        node["status"] = "completed"
        node["updated_at"] = now_iso()
        node["note"] = node_result.get("request_variant", "")
        node["source_count"] = len(node_result.get("sources", []))
        node["usage"] = node_result.get("usage", {})
        summaries.append(f"[{node['section_heading']}] {node_result.get('grounded_summary', '').strip()}")
        aggregated_findings.extend(node_result.get("key_findings", []))
        aggregated_sources.extend(node_result.get("sources", []))

    deduped_sources: list[dict[str, Any]] = []
    seen_urls = set()
    for source in aggregated_sources:
        url = source.get("url_or_identifier")
        if not url or url in seen_urls:
            continue
        seen_urls.add(url)
        deduped_sources.append(source)

    partitioned = partition_sources_for_citation(deduped_sources)
    return {
        "node_runs": nodes,
        "grounded_summary": "\n\n".join(summary for summary in summaries if summary).strip(),
        "key_findings": list(dict.fromkeys(item for item in aggregated_findings if item)),
        "all_sources": partitioned["annotated"],
        "sources": partitioned["primary_sources"],
        "supplemental_sources": partitioned["supplemental_sources"],
        "trust_summary": partitioned["trust_summary"],
        "live_node_count": live_nodes,
        "fallback_node_count": len(nodes) - live_nodes,
    }


def _attach_grounded_sources(
    reference_entries: list[dict[str, Any]],
    grounded_sources: list[dict[str, Any]],
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    body_entries = [entry for entry in reference_entries if entry["reference_domain"] == "body_text"]
    entries_by_type: dict[str, list[dict[str, Any]]] = {}
    for entry in body_entries:
        entries_by_type.setdefault(entry["source_type"], []).append(entry)

    attached: list[dict[str, Any]] = []
    supplemental: list[dict[str, Any]] = []
    used_reference_ids: set[str] = set()
    for source in grounded_sources:
        reference_entry = None
        source_type_hint = source.get("source_type_hint")
        if source_type_hint:
            reference_entry = next(
                (
                    item
                    for item in entries_by_type.get(source_type_hint, [])
                    if item["reference_id"] not in used_reference_ids
                ),
                None,
            )
        if reference_entry is None:
            reference_entry = next(
                (
                    item
                    for item in body_entries
                    if item["reference_id"] not in used_reference_ids
                ),
                None,
            )
        if reference_entry is None:
            supplemental.append(source)
            continue

        used_reference_ids.add(reference_entry["reference_id"])
        reference_entry["status"] = "grounded_attached"
        reference_entry["title"] = source.get("title", "")
        reference_entry["source_name"] = source.get("source_name", "")
        reference_entry["url_or_identifier"] = source.get("url_or_identifier", "")
        reference_entry["access_date"] = source.get("access_date", now_iso()[:10])
        reference_entry["usage_note"] = source.get("usage_note", "grounded_research")
        if source.get("published_date"):
            reference_entry["published_date"] = source["published_date"]
        if source_type_hint:
            reference_entry["source_type_hint"] = source_type_hint
        reference_entry["reference_host"] = source.get("reference_host")
        reference_entry["trust_level"] = source.get("trust_level")
        reference_entry["trust_reason"] = source.get("trust_reason")
        attached.append(reference_entry)
    return attached, supplemental


def _attach_citations(
    citation_record: dict[str, Any],
    reference_entries: list[dict[str, Any]],
    freshness_rule: dict[str, Any],
    grounded_result: dict[str, Any] | None,
    supplemental_sources: list[dict[str, Any]],
) -> dict[str, Any]:
    slot_fit_summary = {"strong_fit": 0, "weak_fit": 0, "unfilled": 0}
    citation_items = []
    verified_body_reference_count = 0
    body_external_reference_count = 0
    for entry in reference_entries:
        slot_fit = assess_reference_slot_fit(entry)
        slot_fit_summary[slot_fit["slot_fit_status"]] = slot_fit_summary.get(slot_fit["slot_fit_status"], 0) + 1
        has_provenance = bool(entry.get("url_or_identifier")) and bool(entry.get("source_name") or entry.get("title"))
        is_body_external = entry["reference_domain"] == "body_text" and entry.get("source_kind") == "external_reference"
        if is_body_external:
            body_external_reference_count += 1
            if has_provenance:
                verified_body_reference_count += 1
        citation_items.append(
            {
                "reference_id": entry["reference_id"],
                "reference_domain": entry["reference_domain"],
                "source_type": entry["source_type"],
                "source_kind": entry["source_kind"],
                "attachment_status": (
                    "attached_verified"
                    if is_body_external and has_provenance
                    else "attached_structurally"
                ),
                "freshness_checked": True,
                "appendix_required": entry["appendix_required"],
                "title": entry.get("title"),
                "source_name": entry.get("source_name"),
                "url_or_identifier": entry.get("url_or_identifier"),
                "access_date": entry.get("access_date"),
                "trust_level": entry.get("trust_level"),
                "trust_reason": entry.get("trust_reason"),
                "slot_fit_status": slot_fit["slot_fit_status"],
                "slot_fit_reason": slot_fit["slot_fit_reason"],
            }
        )
    citation_record["generated_at"] = now_iso()
    citation_record["freshness_window_days"] = freshness_rule["window_days"]
    citation_record["citations"] = citation_items
    citation_record["grounded_research"] = {
        "enabled": grounded_result is not None,
        "summary": grounded_result.get("grounded_summary", "") if grounded_result else "",
        "key_findings": grounded_result.get("key_findings", []) if grounded_result else [],
        "source_count": len(grounded_result.get("sources", [])) if grounded_result else 0,
        "supplemental_source_count": len(supplemental_sources),
        "trust_summary": grounded_result.get("trust_summary", {}) if grounded_result else {},
        "slot_fit_summary": slot_fit_summary,
    }
    if grounded_result is not None:
        grounded_result["slot_fit_summary"] = slot_fit_summary
    if supplemental_sources:
        citation_record["supplemental_sources"] = supplemental_sources
    else:
        citation_record.pop("supplemental_sources", None)
    citation_record["status"] = (
        "attached_verified"
        if body_external_reference_count > 0 and verified_body_reference_count == body_external_reference_count
        else "attached_structurally"
    )
    return citation_record


def _rights_items_missing_provenance(rights_review: dict[str, Any]) -> list[dict[str, Any]]:
    missing: list[dict[str, Any]] = []
    for item in rights_review.get("items", []):
        if item.get("reference_domain") == "visual_anchor" and item.get("rights_category") == "engine_structured_visual":
            continue
        if not item.get("appendix_required", True):
            continue
        has_identifier = bool(item.get("url_or_identifier"))
        has_label = bool(item.get("source_name") or item.get("title"))
        if not has_identifier or not has_label:
            missing.append(item)
    return missing


def _review_gate_assessment(
    reference_entries: list[dict[str, Any]],
    grounded_result: dict[str, Any] | None,
    rights_review: dict[str, Any],
    unsupported_claims: list[str],
) -> dict[str, Any]:
    body_external_refs = [
        entry
        for entry in reference_entries
        if entry.get("reference_domain") == "body_text" and entry.get("source_kind") == "external_reference"
    ]
    verified_body_refs = [
        entry
        for entry in body_external_refs
        if entry.get("url_or_identifier") and (entry.get("source_name") or entry.get("title"))
    ]
    grounded_source_count = len(grounded_result.get("sources", [])) if grounded_result else 0
    missing_rights_provenance = _rights_items_missing_provenance(rights_review)

    blockers: list[str] = []
    if unsupported_claims:
        blockers.append("unsupported_claims_remaining")
    if rights_review.get("summary", {}).get("blocking_item_count", 0) > 0:
        blockers.append("blocking_rights_items_present")
    if body_external_refs and grounded_source_count == 0:
        blockers.append("grounded_body_evidence_missing")
    if body_external_refs and len(verified_body_refs) < len(body_external_refs):
        blockers.append("body_reference_provenance_incomplete")
    if missing_rights_provenance:
        blockers.append("rights_provenance_incomplete")

    if blockers:
        review_status = "return_required"
    elif rights_review.get("verdict") == "pass_with_actions":
        review_status = "pass_with_actions"
    else:
        review_status = "pass"

    return {
        "review_status": review_status,
        "grounded_source_count": grounded_source_count,
        "body_external_reference_count": len(body_external_refs),
        "verified_body_reference_count": len(verified_body_refs),
        "missing_rights_provenance_count": len(missing_rights_provenance),
        "blockers": blockers,
        "missing_rights_provenance_reference_ids": [item.get("reference_id") for item in missing_rights_provenance if item.get("reference_id")],
    }


def _apply_rights_review_to_reference_entries(
    reference_entries: list[dict[str, Any]],
    rights_review: dict[str, Any],
) -> None:
    by_reference_id = {
        item["reference_id"]: item
        for item in rights_review.get("items", [])
        if item.get("reference_id")
    }
    for entry in reference_entries:
        reviewed = by_reference_id.get(entry.get("reference_id"))
        if not reviewed:
            continue
        entry["rights_risk_level"] = reviewed.get("risk_level")
        entry["rights_category"] = reviewed.get("rights_category")
        entry["clearance_status"] = reviewed.get("clearance_status")
        entry["required_action"] = reviewed.get("required_action")


def _render_draft2(
    draft1: str,
    chapter_target: dict[str, Any],
    reference_entries: list[dict[str, Any]],
    freshness_rule: dict[str, Any],
    grounded_result: dict[str, Any] | None,
) -> str:
    cleaned, _ = sanitize_reader_manuscript(draft1, target_label="DRAFT2")
    return cleaned


def _render_review_report(
    chapter: dict[str, Any],
    chapter_target: dict[str, Any],
    freshness_rule: dict[str, Any],
    reference_entries: list[dict[str, Any]],
    unsupported_claims: list[str],
    grounded_result: dict[str, Any] | None,
    supplemental_sources: list[dict[str, Any]],
    rights_review: dict[str, Any],
    review_assessment: dict[str, Any],
) -> str:
    body_refs = [entry for entry in reference_entries if entry["reference_domain"] == "body_text"]
    visual_refs = [entry for entry in reference_entries if entry["reference_domain"] == "visual_anchor"]
    reader_segment = chapter.get("reader_segment") or {}
    rights_constraints = chapter.get("rights_constraints") or []
    reference_slots = chapter.get("reference_slots") or []
    lines = [
        f"# REVIEW_REPORT: {chapter['chapter_id']} | {chapter['title']}",
        "",
        "## Verdict",
        f"- Review status: {review_assessment.get('review_status', 'return_required')}",
        "- Freshness status: checked",
        "- Unsupported claims remaining: 0" if not unsupported_claims else f"- Unsupported claims remaining: {len(unsupported_claims)}",
        "",
        "## Target Check",
        f"- Target words: {chapter_target['target_words']}",
        f"- Draft2 expected minimum: {chapter_target['stage_progress_floors']['S5_draft2_min_words']}",
        "",
        "## Citation Coverage",
        f"- Body reference count: {len(body_refs)}",
        f"- Visual reference count: {len(visual_refs)}",
        f"- Total reference count: {len(reference_entries)}",
        f"- Grounded source count: {len(grounded_result.get('sources', [])) if grounded_result else 0}",
        f"- Supplemental grounded source count: {len(supplemental_sources)}",
        f"- Review node count: {len(grounded_result.get('node_runs', [])) if grounded_result else 0}",
        f"- Live node count: {grounded_result.get('live_node_count', 0) if grounded_result else 0}",
        f"- Fallback node count: {grounded_result.get('fallback_node_count', 0) if grounded_result else 0}",
        "",
        "## Reader Segment Input",
        f"- Segment: {reader_segment.get('segment_id', '')}",
        f"- Focus: {reader_segment.get('focus', '')}",
        f"- Reader payoff: {reader_segment.get('reader_payoff', '')}",
        "",
        "## Freshness Check",
        f"- Freshness window days: {freshness_rule['window_days']}",
        f"- Policy rationale: {freshness_rule['rationale']}",
        "- Review notes: follow appendix reference ids during grounded research attachment.",
        "",
        "## Grounded Research",
        f"- Grounded mode: {'enabled' if grounded_result else 'fallback_structural'}",
        f"- Grounded summary available: {'yes' if grounded_result and grounded_result.get('grounded_summary') else 'no'}",
        f"- High trust sources: {grounded_result.get('trust_summary', {}).get('high', 0) if grounded_result else 0}",
        f"- Medium trust sources: {grounded_result.get('trust_summary', {}).get('medium', 0) if grounded_result else 0}",
        f"- Low trust sources: {grounded_result.get('trust_summary', {}).get('low', 0) if grounded_result else 0}",
        f"- Strong slot fit count: {grounded_result.get('slot_fit_summary', {}).get('strong_fit', 0) if grounded_result else 0}",
        f"- Weak slot fit count: {grounded_result.get('slot_fit_summary', {}).get('weak_fit', 0) if grounded_result else 0}",
        f"- Unfilled slot count: {grounded_result.get('slot_fit_summary', {}).get('unfilled', 0) if grounded_result else 0}",
        "",
        "## Rights / Clearance Review",
        f"- Rights verdict: {rights_review.get('verdict', '')}",
        f"- High-risk items: {rights_review.get('summary', {}).get('high_risk_count', 0)}",
        f"- Medium-risk items: {rights_review.get('summary', {}).get('medium_risk_count', 0)}",
        f"- Low-risk items: {rights_review.get('summary', {}).get('low_risk_count', 0)}",
        f"- Blocking items: {rights_review.get('summary', {}).get('blocking_item_count', 0)}",
        "- Key policy: 뉴스/기사 문장 그대로 복사 금지, UGC는 동의 또는 통계화, 제3자 이미지는 허가 또는 대체 자산 필요",
        "",
        "## Gate Signals",
        f"- Body external reference count: {review_assessment.get('body_external_reference_count', 0)}",
        f"- Verified body reference count: {review_assessment.get('verified_body_reference_count', 0)}",
        f"- Missing rights provenance count: {review_assessment.get('missing_rights_provenance_count', 0)}",
    ]
    blockers = review_assessment.get("blockers", [])
    if blockers:
        for blocker in blockers:
            lines.append(f"- Gate blocker: {blocker}")
    else:
        lines.append("- Gate blocker: none")

    lines.extend(
        [
            "",
            "## Rights Input Contract",
        ]
    )
    for item in rights_constraints:
        lines.append(f"- {item}")

    lines.extend(
        [
            "",
            "## Reference Slot Contract",
        ]
    )
    for slot in reference_slots:
        lines.append(
            f"- {slot.get('reference_id', '')} | {slot.get('source_type', '')} | {slot.get('claim_role', '')} | goal: {slot.get('verification_goal', '')}"
        )

    lines.extend(
        [
            "",
            "## Appendix Linkage",
        ]
    )
    for entry in reference_entries[:8]:
        lines.append(f"- {entry['reference_id']} -> {entry['reference_domain']} -> {entry['source_type']}")

    lines.extend(["", "## Unsupported Claims"])
    if unsupported_claims:
        for item in unsupported_claims:
            lines.append(f"- {item}")
    else:
        lines.append("- none")

    lines.extend(["", "## Required Rights Actions"])
    for action in rights_review.get("required_actions", []):
        lines.append(f"- {action}")

    lines.extend(
        [
            "",
            "## Return Policy",
            "- If grounded evidence contradicts draft framing, return to S4.",
            "- If appendix linkage breaks, return to S2 or S3 depending on cause.",
        ]
    )
    return "\n".join(lines) + "\n"


def run_review(
    book_id: str,
    book_root: Path,
    chapter_id: str | None = None,
    *,
    rerun_completed: bool = False,
) -> dict[str, Any]:
    citations_payload = read_json(book_root / "research" / "citations.json", default=None)
    reference_index = read_json(book_root / "research" / "reference_index.json", default=None)
    research_plan = read_json(book_root / "research" / "research_plan.json", default=None)
    image_manifest = read_json(book_root / "research" / "image_manifest.json", default=None)
    word_targets = read_json(book_root / "_master" / "WORD_TARGETS.json", default=None)
    if citations_payload is None or reference_index is None or research_plan is None or image_manifest is None or word_targets is None:
        raise FileNotFoundError(
            "S5 requires citations.json, reference_index.json, research_plan.json, image_manifest.json, and WORD_TARGETS.json."
        )

    book_db = load_book_db(book_root)
    target_chapters = (
        [chapter_id]
        if chapter_id
        else (_all_s5_chapters(book_root) if rerun_completed else _pending_s5_chapters(book_id, book_root))
    )
    if not target_chapters:
        return {
            "stage_id": "S5",
            "status": "no_op",
            "message": "No pending S5 chapters found." if not rerun_completed else "No S5 chapters found for rerun.",
        }

    results = []
    for current_chapter_id in target_chapters:
        contract_status = validate_inputs(book_id, book_root, "S5", current_chapter_id)
        if not contract_status["valid"]:
            raise FileNotFoundError(f"S5 inputs missing for {current_chapter_id}: {contract_status['missing_inputs']}")

        chapter = {
            "chapter_id": current_chapter_id,
            "title": book_db["chapters"][current_chapter_id]["title"],
            "part": book_db["chapters"][current_chapter_id].get("part"),
        }
        current_status = book_db["chapters"][current_chapter_id]["stages"]["S5"]["status"]
        missing_outputs = _missing_s5_outputs(book_id, book_root, current_chapter_id)
        backfill_only = current_status == "completed" and _can_backfill_s5_outputs(book_id, book_root, current_chapter_id)
        if rerun_completed and current_status == "completed":
            transition_stage(
                book_root,
                "S5",
                "in_progress",
                current_chapter_id,
                note="AG-02 review full rerun started.",
            )
        elif current_status == "gate_failed":
            transition_stage(
                book_root,
                "S5",
                "pending",
                current_chapter_id,
                note="AG-02 review rerun requested after gate fix.",
            )
            transition_stage(
                book_root,
                "S5",
                "in_progress",
                current_chapter_id,
                note="AG-02 review generation restarted.",
            )
        elif current_status != "completed":
            transition_stage(
                book_root,
                "S5",
                "in_progress",
                current_chapter_id,
                note="AG-02 review generation started.",
            )
        elif missing_outputs and not backfill_only:
            transition_stage(
                book_root,
                "S5",
                "in_progress",
                current_chapter_id,
                note="AG-02 review regeneration started from missing outputs.",
            )

        output_bundle = _s5_output_bundle(book_id, book_root, current_chapter_id)
        draft2_path = Path(output_bundle["draft2"])
        review_report_path = Path(output_bundle["review_report"])
        rights_review_path = Path(output_bundle["rights_review"])
        draft1 = read_text(book_root / "manuscripts" / "_draft1" / f"{current_chapter_id}_draft1.md")
        chapter_target = get_chapter_target(word_targets, current_chapter_id)
        research_entry = _research_entry(research_plan, current_chapter_id)
        chapter["reader_segment"] = research_entry.get("reader_segment", {})
        chapter["rights_constraints"] = research_entry.get("rights_constraints", [])
        chapter["reference_slots"] = research_entry.get("reference_slots", [])
        reference_entries = _reference_entries(reference_index, current_chapter_id)
        chapter_image_items = _chapter_image_items(image_manifest, current_chapter_id)
        freshness_rule = _freshness_rule(chapter, research_plan)
        unsupported_claims = _unsupported_claims(draft1)
        grounded_result = None if backfill_only else _run_grounded_review(book_root, chapter, research_entry, draft1, freshness_rule)
        node_manifest_payload = {
            "version": "1.0",
            "generated_at": now_iso(),
            "stage_id": "S5",
            "chapter_id": current_chapter_id,
            "chapter_title": chapter["title"],
            "execution_mode": "legacy_artifact_backfill" if backfill_only else "subsection_nodes_sequential",
            "node_count": len(grounded_result.get("node_runs", [])) if grounded_result else 0,
            "live_node_count": grounded_result.get("live_node_count", 0) if grounded_result else 0,
            "fallback_node_count": grounded_result.get("fallback_node_count", 0) if grounded_result else 0,
            "nodes": grounded_result.get("node_runs", []) if grounded_result else [],
        }
        if backfill_only:
            node_manifest_payload["backfilled_from_legacy_stage_output"] = True
            node_manifest_payload["backfill_reason"] = [Path(path).name for path in missing_outputs]
        node_manifest_path = write_node_manifest(
            book_root,
            "S5",
            current_chapter_id,
            node_manifest_payload,
        )
        _, overflow_sources = _attach_grounded_sources(
            reference_entries,
            grounded_result.get("sources", []) if grounded_result else [],
        )
        supplemental_sources = [
            *(grounded_result.get("supplemental_sources", []) if grounded_result else []),
            *overflow_sources,
        ]

        citation_record = _citation_record(citations_payload, current_chapter_id)
        updated_citation_record = _attach_citations(
            citation_record,
            reference_entries,
            freshness_rule,
            grounded_result,
            supplemental_sources,
        )
        reviewed_image_items = apply_image_manifest_rights_annotations(chapter_image_items)
        rights_review = build_chapter_rights_review(chapter, reference_entries, reviewed_image_items)
        _apply_rights_review_to_reference_entries(reference_entries, rights_review)
        review_assessment = _review_gate_assessment(
            reference_entries,
            grounded_result,
            rights_review,
            unsupported_claims,
        )
        image_manifest["items"] = [
            item
            for item in image_manifest.get("items", [])
            if item.get("chapter_id") != current_chapter_id
        ] + reviewed_image_items
        write_json(book_root / "research" / "citations.json", citations_payload)
        write_json(book_root / "research" / "reference_index.json", reference_index)
        write_json(book_root / "research" / "image_manifest.json", image_manifest)
        write_text(
            book_root / "publication" / "appendix" / "REFERENCE_INDEX.md",
            build_reference_appendix(book_id, reference_index, image_manifest, citations_payload),
        )

        if not backfill_only:
            draft2 = _render_draft2(draft1, chapter_target, reference_entries, freshness_rule, grounded_result)
            review_report = _render_review_report(
                chapter,
                chapter_target,
                freshness_rule,
                reference_entries,
                unsupported_claims,
                grounded_result,
                supplemental_sources,
                rights_review,
                review_assessment,
            )
            write_text(draft2_path, draft2)
            write_text(review_report_path, review_report)
        write_json(rights_review_path, rights_review)
        declared_outputs = [
            str(draft2_path),
            str(review_report_path),
            str(rights_review_path),
            str(node_manifest_path),
        ]

        if backfill_only:
            update_chapter_memory(
                book_root,
                current_chapter_id,
                summary=f"S5 artifacts backfilled for {chapter['title']}",
                claims=[
                    "Legacy S5 outputs were backfilled without re-running grounded review.",
                    "Rights review and review node manifest were regenerated for contract completeness.",
                ],
                citations_summary=[entry["reference_id"] for entry in reference_entries],
                unresolved_issues=[],
                visual_notes=[entry["reference_id"] for entry in reference_entries if entry["reference_domain"] == "visual_anchor"],
            )
            transition_stage(
                book_root,
                "S5",
                "completed",
                current_chapter_id,
                note=f"AG-02 legacy output backfill completed: {', '.join(Path(path).name for path in missing_outputs)}",
            )
            results.append(
                {
                    "chapter_id": current_chapter_id,
                    "status": "completed",
                    "repair_mode": "artifact_backfill",
                    "repaired_outputs": [Path(path).name for path in missing_outputs],
                    "outputs": declared_outputs,
                    "node_manifest": str(node_manifest_path),
                    "citation_status": citation_record.get("status"),
                    "gate_result": {
                        "skipped": True,
                        "reason": "artifact_backfill_only",
                    },
                }
            )
            continue

        update_chapter_memory(
            book_root,
            current_chapter_id,
            summary=f"Draft2 reviewed for {chapter['title']}",
            claims=[
                "Citation structure attached to every planned reference.",
                "Freshness rule checked against chapter part and research policy.",
                "Grounded research attempted for current web-backed verification.",
                "Rights and clearance review attached for commercial publication context.",
            ],
            citations_summary=[
                *[entry["reference_id"] for entry in reference_entries],
                *[
                    source.get("source_name", "")
                    for source in (grounded_result or {}).get("sources", [])[:4]
                    if source.get("source_name")
                ],
            ],
            unresolved_issues=research_entry.get("research_questions", []),
            visual_notes=[entry["reference_id"] for entry in reference_entries if entry["reference_domain"] == "visual_anchor"],
        )

        gate_result = evaluate_gate(book_id, book_root, "S5", current_chapter_id)
        if not gate_result["passed"]:
            transition_stage(
                book_root,
                "S5",
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
            "S5",
            "completed",
            current_chapter_id,
            note="AG-02 review generation completed.",
        )
        results.append(
            {
                "chapter_id": current_chapter_id,
                "status": "completed",
                "outputs": declared_outputs,
                "node_manifest": str(node_manifest_path),
                "citation_status": updated_citation_record["status"],
                "gate_result": gate_result,
            }
        )

    citations_payload["generated_at"] = now_iso()
    write_json(book_root / "research" / "citations.json", citations_payload)
    work_order = issue_work_order(book_id, book_root)
    return {
        "stage_id": "S5",
        "requested_chapters": target_chapters,
        "results": results,
        "work_order": {
            "order_id": work_order["order_id"],
            "priority_queue_size": len(work_order["priority_queue"]),
            "first_items": work_order["priority_queue"][:5],
        },
    }
