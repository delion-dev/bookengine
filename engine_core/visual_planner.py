from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

from .book_state import load_book_db
from .common import now_iso, read_json, read_text, write_json, write_text
from .contracts import resolve_stage_contract, validate_inputs
from .gates import evaluate_gate
from .manuscript_integrity import sanitize_reader_manuscript
from .memory import update_chapter_memory
from .section_labels import normalize_section_headings, required_section_markers
from .stage import transition_stage
from .work_order import issue_work_order

RETAINED_READING_HEADINGS = required_section_markers()


def _missing_s6_outputs(book_id: str, book_root: Path, chapter_id: str) -> list[str]:
    outputs = resolve_stage_contract(book_id, book_root, "S6", chapter_id)["outputs"]
    return [path for path in outputs if not Path(path).exists()]


def _pending_s6_chapters(book_id: str, book_root: Path) -> list[str]:
    payload = load_book_db(book_root)
    return [
        chapter_id
        for chapter_id in payload["chapter_sequence"]
        if payload["chapters"][chapter_id]["stages"]["S6"]["status"] in {"pending", "in_progress", "gate_failed"}
        or (
            payload["chapters"][chapter_id]["stages"]["S6"]["status"] == "completed"
            and bool(_missing_s6_outputs(book_id, book_root, chapter_id))
        )
    ]


def _all_s6_chapters(book_root: Path) -> list[str]:
    payload = load_book_db(book_root)
    return [
        chapter_id
        for chapter_id in payload["chapter_sequence"]
        if payload["chapters"][chapter_id]["stages"]["S6"]["status"] in {"completed", "gate_failed"}
    ]


def _anchor_plan(book_root: Path, chapter_id: str) -> dict[str, Any]:
    payload = read_json(book_root / "manuscripts" / "_raw" / f"{chapter_id}_anchor_plan.json", default=None)
    if payload is None:
        raise FileNotFoundError(f"Missing anchor plan for {chapter_id}")
    return payload


def _image_items(image_manifest: dict[str, Any], chapter_id: str) -> list[dict[str, Any]]:
    return [
        item
        for item in image_manifest.get("items", [])
        if item["chapter_id"] == chapter_id
    ]


def _reference_entries(reference_index: dict[str, Any], chapter_id: str) -> list[dict[str, Any]]:
    for chapter in reference_index.get("chapters", []):
        if chapter["chapter_id"] == chapter_id:
            return chapter.get("entries", [])
    raise KeyError(f"Missing reference index entry for {chapter_id}")


def _chapter_citations(citations_payload: dict[str, Any], chapter_id: str) -> dict[str, Any]:
    for chapter in citations_payload.get("chapters", []):
        if chapter["chapter_id"] == chapter_id:
            return chapter
    raise KeyError(f"Missing citations payload entry for {chapter_id}")


def _lookup_image(image_items: list[dict[str, Any]], appendix_reference_id: str) -> dict[str, Any]:
    for item in image_items:
        if item["appendix_reference_id"] == appendix_reference_id:
            return item
    raise KeyError(f"Missing image manifest entry for {appendix_reference_id}")


def _chapter_render_strategy(part: str | None) -> str:
    label = part or ""
    if "CINEMA" in label:
        return "editorial_comparison"
    if "HISTORY" in label:
        return "fact_alignment"
    if "TRAVEL" in label:
        return "location_experience"
    if "TASTE" in label:
        return "sensory_local_guide"
    return "orientation"


def _build_visual_tasks(
    chapter: dict[str, Any],
    anchor_plan: dict[str, Any],
    image_items: list[dict[str, Any]],
    reference_entries: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    reference_map = {
        entry["reference_id"]: entry
        for entry in reference_entries
    }
    tasks: list[dict[str, Any]] = []
    for anchor in anchor_plan.get("anchors", []):
        image = _lookup_image(image_items, anchor["appendix_ref_id"])
        reference_entry = reference_map[anchor["appendix_ref_id"]]
        task = {
            "anchor_id": anchor["anchor_id"],
            "anchor_type": anchor["anchor_type"],
            "anchor_name": anchor["anchor_name"],
            "category": anchor["category"],
            "placement": anchor["placement"],
            "asset_mode": anchor["asset_mode"],
            "source_mode": image["source_mode"],
            "fallback_mode": image["fallback_mode"],
            "renderer_hint": anchor["renderer_hint"],
            "major_engine": anchor["major_engine"],
            "grammar": anchor["grammar"],
            "quality_gate": anchor["quality_gate"],
            "priority": anchor["priority"],
            "appendix_ref_id": anchor["appendix_ref_id"],
            "image_id": image["image_id"],
            "render_strategy": _chapter_render_strategy(chapter.get("part")),
            "reference_requirements": anchor["reference_requirements"],
            "rights_status": image["rights_status"],
            "caption": anchor["caption"],
            "brief": {
                "goal": anchor["justification"],
                "reader_value": f"Support the chapter '{chapter['title']}' with a clearer visual cue.",
                "provenance_requirement": reference_entry["required_fields"],
            },
        }
        if image["source_mode"] == "ai_generated_image":
            task["generation_brief"] = {
                "gateway": "engine.model.generate_structured",
                "prompt_summary": f"{chapter['title']}의 감정과 정보를 {anchor['anchor_type']} 시각물로 압축한다.",
                "record_required": True,
            }
        elif image["source_mode"] == "external_image":
            task["acquisition_brief"] = {
                "search_focus": anchor["caption"],
                "rights_review_required": True,
                "must_match_appendix_ref": anchor["appendix_ref_id"],
            }
        else:
            task["design_brief"] = {
                "data_backed": True,
                "manual_layout_required": True,
            }
        tasks.append(task)
    return tasks


def _render_draft3(draft2: str) -> tuple[str, list[str]]:
    cleaned, removed = sanitize_reader_manuscript(draft2, target_label="DRAFT3")
    return normalize_section_headings(cleaned), removed


def _extract_report_value(report_text: str, label: str) -> str | None:
    pattern = re.compile(rf"^- {re.escape(label)}:\s*(.+)$", re.MULTILINE)
    match = pattern.search(report_text)
    if not match:
        return None
    return match.group(1).strip()


def _numeric_like_findings(findings: list[str]) -> list[str]:
    numeric_findings: list[str] = []
    for item in findings:
        if re.search(r"\d", item):
            numeric_findings.append(item)
    return numeric_findings


def _anchor_support_packet(
    task: dict[str, Any],
    body_citations: list[dict[str, Any]],
    grounded_key_findings: list[str],
) -> dict[str, Any]:
    candidate_refs = [
        {
            "reference_id": item.get("reference_id"),
            "source_type": item.get("source_type"),
            "source_name": item.get("source_name"),
            "title": item.get("title"),
            "url_or_identifier": item.get("url_or_identifier"),
            "attachment_status": item.get("attachment_status"),
            "trust_level": item.get("trust_level"),
            "slot_fit_status": item.get("slot_fit_status"),
        }
        for item in body_citations
        if item.get("attachment_status") in {"attached_verified", "attached_structurally"}
    ]

    if task["anchor_type"] == "DS" or task["asset_mode"] == "chart":
        numeric_findings = _numeric_like_findings(grounded_key_findings)
        official_candidates = [
            item for item in candidate_refs
            if item.get("source_type") in {"official_source", "official_film_info", "official_box_office"}
        ]
        gaps: list[str] = []
        if not numeric_findings:
            gaps.append("numeric_finding_missing")
        if not official_candidates:
            gaps.append("official_reference_missing")
        elif not any(item.get("slot_fit_status") == "strong_fit" for item in official_candidates):
            gaps.append("official_reference_weak_fit")
        packet_status = "ready" if not gaps else "partial_ready"
        return {
            "anchor_id": task["anchor_id"],
            "anchor_type": task["anchor_type"],
            "packet_type": "numeric_source_packet",
            "packet_status": packet_status,
            "required_evidence": task.get("reference_requirements", []),
            "candidate_reference_ids": [item["reference_id"] for item in candidate_refs],
            "candidate_references": candidate_refs,
            "numeric_findings": numeric_findings[:8],
            "gaps": gaps,
        }

    if task["anchor_type"] == "SB" or task["asset_mode"] == "summary_box":
        summary_points = grounded_key_findings[:4]
        packet_status = "ready" if summary_points else "partial_ready"
        return {
            "anchor_id": task["anchor_id"],
            "anchor_type": task["anchor_type"],
            "packet_type": "summary_box_packet",
            "packet_status": packet_status,
            "required_evidence": task.get("reference_requirements", []),
            "candidate_reference_ids": [item["reference_id"] for item in candidate_refs],
            "candidate_references": candidate_refs[:4],
            "summary_points": summary_points,
            "gaps": [] if summary_points else ["summary_points_missing"],
        }

    return {
        "anchor_id": task["anchor_id"],
        "anchor_type": task["anchor_type"],
        "packet_type": "general_visual_support",
        "packet_status": "ready",
        "required_evidence": task.get("reference_requirements", []),
        "candidate_reference_ids": [item["reference_id"] for item in candidate_refs],
        "candidate_references": candidate_refs[:4],
        "support_notes": [
            f"Use appendix ref `{task['appendix_ref_id']}` as the provenance anchor.",
            f"Prefer renderer `{task['renderer_hint']}` with source mode `{task['source_mode']}`.",
        ],
        "gaps": [],
    }


def _render_visual_support(
    book_id: str,
    chapter: dict[str, Any],
    draft3: str,
    removed_sections: list[str],
    report_text: str,
    rights_review: dict[str, Any],
    citations_payload: dict[str, Any],
    reference_entries: list[dict[str, Any]],
    visual_tasks: list[dict[str, Any]],
) -> dict[str, Any]:
    chapter_citations = _chapter_citations(citations_payload, chapter["chapter_id"])
    body_citations = [
        item for item in chapter_citations.get("citations", [])
        if item.get("reference_domain") == "body_text"
    ]
    visual_refs = [
        entry for entry in reference_entries
        if entry.get("reference_domain") == "visual_anchor"
    ]
    grounded = chapter_citations.get("grounded_research", {})
    grounded_key_findings = grounded.get("key_findings", []) if isinstance(grounded, dict) else []
    trust_summary = grounded.get("trust_summary", {}) if isinstance(grounded, dict) else {}
    slot_fit_summary = grounded.get("slot_fit_summary", {}) if isinstance(grounded, dict) else {}
    rights_summary = rights_review.get("summary", {}) if isinstance(rights_review, dict) else {}

    anchor_support = [
        _anchor_support_packet(task, body_citations, grounded_key_findings)
        for task in visual_tasks
    ]

    return {
        "version": "1.0",
        "generated_at": now_iso(),
        "book_id": book_id,
        "chapter_id": chapter["chapter_id"],
        "chapter_title": chapter["title"],
        "draft3_contract": {
            "reading_view_only": True,
            "retained_sections": [heading for heading in RETAINED_READING_HEADINGS if heading in draft3],
            "stripped_sections": removed_sections,
            "anchor_ids": [task["anchor_id"] for task in visual_tasks],
        },
        "s5_review_handoff": {
            "review_status": _extract_report_value(report_text, "Review status"),
            "freshness_status": _extract_report_value(report_text, "Freshness status"),
            "unsupported_claims_remaining": _extract_report_value(report_text, "Unsupported claims remaining"),
            "grounded_source_count": grounded.get("source_count", 0) if isinstance(grounded, dict) else 0,
            "trust_summary": trust_summary,
            "slot_fit_summary": slot_fit_summary,
            "rights_verdict": rights_review.get("verdict") if isinstance(rights_review, dict) else None,
            "rights_summary": rights_summary,
        },
        "visual_reference_entries": [
            {
                "reference_id": entry.get("reference_id"),
                "source_type": entry.get("source_type"),
                "status": entry.get("status"),
                "required_fields": entry.get("required_fields", []),
                "clearance_status": entry.get("clearance_status"),
                "required_action": entry.get("required_action"),
            }
            for entry in visual_refs
        ],
        "grounded_support": {
            "summary": grounded.get("summary", "") if isinstance(grounded, dict) else "",
            "key_findings": grounded_key_findings,
        },
        "anchor_support": anchor_support,
    }


def _render_visual_plan(
    book_id: str,
    chapter: dict[str, Any],
    visual_tasks: list[dict[str, Any]],
) -> dict[str, Any]:
    return {
        "version": "1.0",
        "generated_at": now_iso(),
        "book_id": book_id,
        "chapter_id": chapter["chapter_id"],
        "chapter_title": chapter["title"],
        "render_strategy": _chapter_render_strategy(chapter.get("part")),
        "priority_items": [task["anchor_id"] for task in visual_tasks if task["priority"] == "high"],
        "anchors": visual_tasks,
        "status": "planned",
    }


def run_visual_plan(
    book_id: str,
    book_root: Path,
    chapter_id: str | None = None,
    *,
    rerun_completed: bool = False,
) -> dict[str, Any]:
    image_manifest = read_json(book_root / "research" / "image_manifest.json", default=None)
    reference_index = read_json(book_root / "research" / "reference_index.json", default=None)
    citations_payload = read_json(book_root / "research" / "citations.json", default=None)
    if image_manifest is None or reference_index is None or citations_payload is None:
        raise FileNotFoundError("S6 requires image_manifest.json, reference_index.json, and citations.json.")

    book_db = load_book_db(book_root)
    target_chapters = [chapter_id] if chapter_id else (
        _all_s6_chapters(book_root) if rerun_completed else _pending_s6_chapters(book_id, book_root)
    )
    if not target_chapters:
        return {
            "stage_id": "S6",
            "status": "no_op",
            "message": "No pending S6 chapters found.",
        }

    results = []
    for current_chapter_id in target_chapters:
        contract_status = validate_inputs(book_id, book_root, "S6", current_chapter_id)
        if not contract_status["valid"]:
            raise FileNotFoundError(f"S6 inputs missing for {current_chapter_id}: {contract_status['missing_inputs']}")

        chapter = {
            "chapter_id": current_chapter_id,
            "title": book_db["chapters"][current_chapter_id]["title"],
            "part": book_db["chapters"][current_chapter_id].get("part"),
        }
        current_status = book_db["chapters"][current_chapter_id]["stages"]["S6"]["status"]
        missing_outputs = _missing_s6_outputs(book_id, book_root, current_chapter_id)
        if current_status == "gate_failed":
            transition_stage(
                book_root,
                "S6",
                "pending",
                current_chapter_id,
                note="AG-03 visual planning rerun requested.",
            )
            transition_stage(
                book_root,
                "S6",
                "in_progress",
                current_chapter_id,
                note="AG-03 visual planning restarted.",
            )
        elif current_status == "completed" and rerun_completed:
            transition_stage(
                book_root,
                "S6",
                "in_progress",
                current_chapter_id,
                note="AG-03 visual planning rerun requested for refreshed draft2.",
            )
        elif current_status != "completed":
            transition_stage(
                book_root,
                "S6",
                "in_progress",
                current_chapter_id,
                note="AG-03 visual planning started.",
            )
        elif missing_outputs:
            transition_stage(
                book_root,
                "S6",
                "in_progress",
                current_chapter_id,
                note="AG-03 visual planning regeneration started from missing outputs.",
            )

        draft2 = read_text(book_root / "manuscripts" / "_draft2" / f"{current_chapter_id}_draft2.md")
        review_report = read_text(book_root / "manuscripts" / "_draft2" / f"{current_chapter_id}_review_report.md")
        rights_review = read_json(book_root / "manuscripts" / "_draft2" / f"{current_chapter_id}_rights_review.json", default={})
        anchor_plan = _anchor_plan(book_root, current_chapter_id)
        chapter_image_items = _image_items(image_manifest, current_chapter_id)
        reference_entries = _reference_entries(reference_index, current_chapter_id)
        visual_tasks = _build_visual_tasks(chapter, anchor_plan, chapter_image_items, reference_entries)

        draft3, removed_sections = _render_draft3(draft2)
        visual_plan = _render_visual_plan(book_id, chapter, visual_tasks)
        visual_support = _render_visual_support(
            book_id,
            chapter,
            draft3,
            removed_sections,
            review_report,
            rights_review,
            citations_payload,
            reference_entries,
            visual_tasks,
        )

        draft3_path = book_root / "manuscripts" / "_draft3" / f"{current_chapter_id}_draft3.md"
        visual_plan_path = book_root / "manuscripts" / "_draft3" / f"{current_chapter_id}_visual_plan.json"
        visual_support_path = book_root / "manuscripts" / "_draft3" / f"{current_chapter_id}_visual_support.json"
        write_text(draft3_path, draft3)
        write_json(visual_plan_path, visual_plan)
        write_json(visual_support_path, visual_support)

        update_chapter_memory(
            book_root,
            current_chapter_id,
            summary=f"Draft3 visual planning ready for {chapter['title']}",
            claims=[
                "Visual tasks mapped one-to-one to anchor ids.",
                "Image manifest and appendix references linked in visual plan.",
            ],
            citations_summary=[task["appendix_ref_id"] for task in visual_tasks],
            unresolved_issues=[],
            visual_notes=[task["anchor_id"] for task in visual_tasks],
        )

        gate_result = evaluate_gate(book_id, book_root, "S6", current_chapter_id)
        if not gate_result["passed"]:
            transition_stage(
                book_root,
                "S6",
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
            "S6",
            "completed",
            current_chapter_id,
            note="AG-03 visual planning completed.",
        )
        results.append(
            {
                "chapter_id": current_chapter_id,
                "status": "completed",
                "outputs": [
                    str(draft3_path),
                    str(visual_plan_path),
                    str(visual_support_path),
                ],
                "gate_result": gate_result,
            }
        )

    work_order = issue_work_order(book_id, book_root)
    return {
        "stage_id": "S6",
        "requested_chapters": target_chapters,
        "results": results,
        "work_order": {
            "order_id": work_order["order_id"],
            "priority_queue_size": len(work_order["priority_queue"]),
            "first_items": work_order["priority_queue"][:5],
        },
    }
