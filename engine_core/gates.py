from __future__ import annotations

from pathlib import Path
from typing import Any

from .anchor_scope import anchor_scope_integrity, strip_anchor_blocks
from .contracts import get_stage_definition, resolve_stage_contract
from .common import GATE_DEFINITIONS_PATH, PLATFORM_CORE_ROOT, count_words, read_json
from .manuscript_integrity import READER_FACING_INTERNAL_HEADINGS, find_body_meta_markers, find_meta_block_residue
from .section_labels import SECTION_ORDER, find_section_marker, required_section_markers
from .subsection_nodes import STAGE_NODE_DIRS


def _gate_execution_limits() -> dict:
    payload = read_json(PLATFORM_CORE_ROOT / "stage_execution_policies.json", default={}) or {}
    stages = payload.get("stages", {})
    s4_lim = stages.get("S4", {}).get("execution_limits", {})
    s8a_lim = stages.get("S8A", {}).get("execution_limits", {})
    return {
        "max_s4_expansions": int(s4_lim.get("max_expansions", 3)),
        "max_s8a_rewrite_targets": int(s8a_lim.get("max_rewrite_targets", 10)),
        "max_amplification_ratio": float(s8a_lim.get("max_amplification_ratio", 2.0)),
    }

_GATE_LIMITS = _gate_execution_limits()
MAX_GATE_S4_EXPANSIONS: int = _GATE_LIMITS["max_s4_expansions"]
MAX_GATE_S8A_REWRITE_TARGETS: int = _GATE_LIMITS["max_s8a_rewrite_targets"]
MAX_GATE_AMPLIFICATION_RATIO: float = _GATE_LIMITS["max_amplification_ratio"]
S6_FORBIDDEN_DRAFT3_HEADINGS = set(READER_FACING_INTERNAL_HEADINGS)
REQUIRED_SECTIONS = required_section_markers()


def load_gate_definitions() -> dict[str, Any]:
    data = read_json(GATE_DEFINITIONS_PATH, default=None)
    if data is None:
        raise FileNotFoundError(f"Missing gate definitions: {GATE_DEFINITIONS_PATH}")
    return data


def get_gate_definition(gate_id: str) -> dict[str, Any]:
    for gate in load_gate_definitions()["gates"]:
        if gate["gate_id"] == gate_id:
            return gate
    raise KeyError(f"Unknown gate_id: {gate_id}")


def _exists(path_str: str) -> bool:
    return Path(path_str).exists()


def _read_artifact(path_str: str) -> Any | None:
    path = Path(path_str)
    if not path.exists() or path.is_dir():
        return None
    if path.suffix == ".json":
        return read_json(path, default=None)
    return path.read_text(encoding="utf-8")


def _s6a_asset_request_lookup(
    book_id: str,
    book_root: Path,
    chapter_id: str | None,
) -> dict[str, dict[str, Any]]:
    if not chapter_id:
        return {}
    try:
        contract = resolve_stage_contract(book_id, book_root, "S6A", chapter_id)
    except Exception:
        return {}
    payload = _read_artifact(contract["outputs"][0])
    if not isinstance(payload, dict):
        return {}
    requests = payload.get("asset_requests", [])
    if not isinstance(requests, list):
        return {}
    return {
        item.get("appendix_ref_id"): item
        for item in requests
        if isinstance(item, dict) and item.get("appendix_ref_id")
    }


def _runtime_budget_path(book_root: Path, stage_id: str, chapter_id: str | None) -> Path:
    if not chapter_id:
        raise ValueError("chapter_id is required to resolve runtime budget path")
    return book_root / "shared_memory" / "context_packs" / "runtime" / f"{chapter_id}_{stage_id}_context_budget.json"


def _draft_path(book_root: Path, draft_folder: str, chapter_id: str | None) -> Path:
    if not chapter_id:
        raise ValueError("chapter_id is required to resolve draft paths")
    return book_root / "manuscripts" / draft_folder / f"{chapter_id}_{draft_folder[1:]}.md"


_NODE_MANIFEST_FILENAMES: dict[str, str] = {
    "S4":  "{chapter_id}_node_manifest.json",
    "S5":  "{chapter_id}_review_nodes.json",
    "S8A": "{chapter_id}_amplification_nodes.json",
}


def _node_manifest_path(book_root: Path, stage_id: str, chapter_id: str | None) -> Path:
    if not chapter_id:
        raise ValueError("chapter_id is required to resolve node manifest paths")
    if stage_id not in STAGE_NODE_DIRS or stage_id not in _NODE_MANIFEST_FILENAMES:
        raise KeyError(f"No node manifest path rule for stage_id={stage_id}")
    folder_parts = STAGE_NODE_DIRS[stage_id]
    filename = _NODE_MANIFEST_FILENAMES[stage_id].format(chapter_id=chapter_id)
    return book_root.joinpath(*folder_parts) / filename


def _run_check(
    check_name: str,
    book_id: str,
    book_root: Path,
    stage_id: str,
    chapter_id: str | None,
    contract: dict[str, Any],
) -> dict[str, Any]:
    passed = False
    detail: Any = ""

    def _section_presence_detail(payload_text: str) -> dict[str, Any]:
        return {
            "required_sections": REQUIRED_SECTIONS,
            "detected_sections": {
                section_key: find_section_marker(payload_text, section_key)
                for section_key in SECTION_ORDER
            },
        }

    if check_name == "proposal_exists":
        path = book_root / "_inputs" / "proposal.md"
        passed = path.exists()
        detail = str(path)
    elif check_name == "toc_seed_exists":
        path = book_root / "_inputs" / "toc_seed.md"
        passed = path.exists()
        detail = str(path)
    elif check_name == "intake_manifest_schema_valid":
        payload = _read_artifact(str(book_root / "_inputs" / "intake_manifest.json"))
        passed = isinstance(payload, dict) and all(
            key in payload for key in ["book_id", "display_name", "chapters_detected", "parts_detected"]
        )
        detail = "intake manifest keys"
    elif check_name in {"book_config_exists", "book_blueprint_exists", "style_guide_exists", "quality_criteria_exists"}:
        passed = all(item["exists"] for item in [{"exists": _exists(path)} for path in contract["outputs"]])
        detail = contract["outputs"]
    elif check_name == "word_targets_defined":
        payload = _read_artifact(str(book_root / "_master" / "WORD_TARGETS.json"))
        passed = isinstance(payload, dict) and bool(payload.get("chapters"))
        detail = "WORD_TARGETS.json"
    elif check_name == "anchor_policy_defined":
        payload = _read_artifact(str(book_root / "_master" / "ANCHOR_POLICY.json"))
        passed = isinstance(payload, dict) and bool(payload.get("chapters")) and "grammar" in payload
        detail = "ANCHOR_POLICY.json"
    elif check_name == "pipeline_snapshot_valid":
        payload = _read_artifact(str(book_root / "db" / "PIPELINE_STATUS.local.json"))
        passed = isinstance(payload, dict) and "book_level_stages" in payload and "chapters" in payload
        detail = "pipeline snapshot structure"
    elif check_name == "work_order_valid":
        payload = _read_artifact(str(book_root / "db" / "WORK_ORDER.local.json"))
        passed = isinstance(payload, dict) and all(
            key in payload for key in ["priority_queue", "blocked_items", "gate_failures"]
        )
        detail = "work order structure"
    elif check_name == "research_questions_present":
        payload = _read_artifact(str(book_root / "research" / "research_plan.json"))
        chapters = payload.get("chapters", []) if isinstance(payload, dict) else []
        passed = bool(chapters) and all(chapter.get("research_questions") for chapter in chapters)
        detail = "research questions per chapter"
    elif check_name == "source_queue_present":
        payload = _read_artifact(str(book_root / "research" / "source_queue.json"))
        items = payload.get("items", []) if isinstance(payload, dict) else []
        passed = bool(items)
        detail = "source queue items"
    elif check_name == "freshness_policy_defined":
        payload = _read_artifact(str(book_root / "research" / "research_plan.json"))
        passed = isinstance(payload, dict) and "freshness_policy" in payload
        detail = "freshness policy"
    elif check_name == "reference_index_present":
        payload = _read_artifact(str(book_root / "research" / "reference_index.json"))
        passed = isinstance(payload, dict) and bool(payload.get("chapters"))
        detail = "reference_index.json"
    elif check_name == "image_manifest_present":
        payload = _read_artifact(str(book_root / "research" / "image_manifest.json"))
        passed = isinstance(payload, dict) and bool(payload.get("items"))
        detail = "image_manifest.json"
    elif check_name == "appendix_reference_scaffold_present":
        payload = _read_artifact(str(book_root / "publication" / "appendix" / "REFERENCE_INDEX.md"))
        passed = isinstance(payload, str) and "## Text References" in payload and "## Visual / Image References" in payload
        detail = "publication/appendix/REFERENCE_INDEX.md"
    elif check_name == "chapter_goal_defined":
        payload = _read_artifact(contract["outputs"][0])
        passed = isinstance(payload, str) and "## Chapter Goal" in payload and "- " in payload.split("## Chapter Goal", 1)[1]
        detail = contract["outputs"][0]
    elif check_name == "section_guides_present":
        payload = _read_artifact(contract["outputs"][0])
        passed = False
        if isinstance(payload, str) and "## Section Guides" in payload:
            block = payload.split("## Section Guides", 1)[1]
            passed = block.count("- ") >= 4
        detail = contract["outputs"][0]
    elif check_name == "exclusion_rules_present":
        payload = _read_artifact(contract["outputs"][0])
        passed = isinstance(payload, str) and "## Exclude" in payload and "- " in payload.split("## Exclude", 1)[1]
        detail = contract["outputs"][0]
    elif check_name == "word_budget_present":
        payload = _read_artifact(contract["outputs"][0])
        passed = isinstance(payload, str) and "## Target Length" in payload and "Target words" in payload
        detail = contract["outputs"][0]
    elif check_name == "anchor_plan_present":
        payload = _read_artifact(contract["outputs"][1])
        passed = isinstance(payload, dict) and bool(payload.get("anchors"))
        detail = contract["outputs"][1]
    elif check_name == "chapter_structure_complete":
        payload = _read_artifact(contract["outputs"][0])
        passed = isinstance(payload, str) and all(find_section_marker(payload, section_key) for section_key in SECTION_ORDER)
        detail = _section_presence_detail(payload) if isinstance(payload, str) else REQUIRED_SECTIONS
    elif check_name == "min_length_reached":
        payload = _read_artifact(contract["outputs"][0])
        target_payload = _read_artifact(str(book_root / "_master" / "WORD_TARGETS.json"))
        floor = 180
        if isinstance(target_payload, dict) and chapter_id:
            for chapter in target_payload.get("chapters", []):
                if chapter["chapter_id"] == chapter_id:
                    floor = chapter["stage_progress_floors"]["S4_draft1_min_words"]
                    break
        measured = count_words(payload) if isinstance(payload, str) else 0
        passed = isinstance(payload, str) and measured >= floor
        detail = {"measured_words": measured, "required_floor_words": floor}
    elif check_name == "required_sections_present":
        payload = _read_artifact(contract["outputs"][0])
        passed = isinstance(payload, str) and all(find_section_marker(payload, section_key) for section_key in SECTION_ORDER)
        detail = _section_presence_detail(payload) if isinstance(payload, str) else REQUIRED_SECTIONS
    elif check_name == "anchor_blocks_inserted":
        payload = _read_artifact(contract["outputs"][0])
        passed = isinstance(payload, str) and "<!-- ANCHOR_START" in payload and "[ANCHOR_SLOT:" in payload
        detail = contract["outputs"][0]
    elif check_name == "anchor_injection_report_exists":
        payload = _read_artifact(contract["outputs"][1])
        passed = (
            isinstance(payload, dict)
            and isinstance(payload.get("anchor_count"), int)
            and bool(payload.get("anchor_ids"))
        )
        detail = contract["outputs"][1]
    elif check_name == "anchor_scope_integrity_pass":
        before_payload = _read_artifact(contract["inputs"][0])
        after_payload = _read_artifact(contract["outputs"][0])
        integrity = (
            anchor_scope_integrity(before_payload, after_payload)
            if isinstance(before_payload, str) and isinstance(after_payload, str)
            else None
        )
        passed = bool(
            integrity
            and isinstance(before_payload, str)
            and isinstance(after_payload, str)
            and strip_anchor_blocks(before_payload) == strip_anchor_blocks(after_payload)
            and integrity.after_anchor_count > 0
        )
        detail = {
            "before_anchor_count": integrity.before_anchor_count if integrity else None,
            "after_anchor_count": integrity.after_anchor_count if integrity else None,
            "non_anchor_sha1_before": integrity.non_anchor_sha1_before if integrity else None,
            "non_anchor_sha1_after": integrity.non_anchor_sha1_after if integrity else None,
            "diff_preview": integrity.diff_preview if integrity else "",
        }
    elif check_name == "segment_plan_exists":
        payload = _read_artifact(contract["outputs"][2])
        passed = isinstance(payload, dict) and bool(payload.get("segments"))
        detail = contract["outputs"][2]
    elif check_name == "narrative_design_exists":
        payload = _read_artifact(contract["outputs"][3])
        passed = isinstance(payload, dict) and bool(payload.get("segments"))
        detail = contract["outputs"][3]
    elif check_name == "density_audit_exists":
        payload = _read_artifact(contract["outputs"][4])
        passed = isinstance(payload, dict) and "draft_coverage_ratio" in payload and "density_pass" in payload
        detail = contract["outputs"][4]
    elif check_name == "session_report_exists":
        payload = _read_artifact(contract["outputs"][5])
        passed = isinstance(payload, dict) and "verdict" in payload and "recommended_status" in payload
        detail = contract["outputs"][5]
    elif check_name == "context_budget_within_policy":
        payload = _read_artifact(str(_runtime_budget_path(book_root, stage_id, chapter_id)))
        approx_tokens = payload.get("context_total_approx_tokens") if isinstance(payload, dict) else None
        soft_max = payload.get("soft_max_input_tokens") if isinstance(payload, dict) else None
        distill_level = payload.get("distill_level") if isinstance(payload, dict) else None
        budget_enforced = payload.get("budget_enforced") if isinstance(payload, dict) else None
        within_budget = payload.get("within_budget") if isinstance(payload, dict) else False
        passed = isinstance(payload, dict) and bool(within_budget)
        detail = {
            "budget_path": str(_runtime_budget_path(book_root, stage_id, chapter_id)),
            "approx_tokens": approx_tokens,
            "soft_max_input_tokens": soft_max,
            "within_budget": within_budget,
            "distill_level": distill_level,
            "budget_enforced": budget_enforced,
        }
    elif check_name == "s4_expansion_cap_respected":
        payload = _read_artifact(str(_node_manifest_path(book_root, "S4", chapter_id)))
        expansion_count = payload.get("expansion_count") if isinstance(payload, dict) else None
        expansion_cap = payload.get("expansion_cap") if isinstance(payload, dict) else None
        passed = (
            isinstance(payload, dict)
            and isinstance(expansion_count, int)
            and isinstance(expansion_cap, int)
            and expansion_cap <= MAX_GATE_S4_EXPANSIONS
            and expansion_count <= expansion_cap
        )
        detail = {
            "node_manifest_path": str(_node_manifest_path(book_root, "S4", chapter_id)),
            "expansion_count": expansion_count,
            "expansion_cap": expansion_cap,
            "global_cap_limit": MAX_GATE_S4_EXPANSIONS,
        }
    elif check_name == "review_report_exists":
        payload = _read_artifact(contract["outputs"][1])
        passed = isinstance(payload, str) and "## Verdict" in payload and "## Citation Coverage" in payload
        detail = contract["outputs"][1]
    elif check_name == "rights_review_exists":
        payload = _read_artifact(contract["outputs"][2])
        passed = (
            isinstance(payload, dict)
            and "summary" in payload
            and "items" in payload
            and "verdict" in payload
        )
        detail = contract["outputs"][2]
    elif check_name == "citations_attached":
        payload = _read_artifact(str(book_root / "research" / "citations.json"))
        chapter_payload = None
        if isinstance(payload, dict) and chapter_id:
            chapter_payload = next((item for item in payload.get("chapters", []) if item["chapter_id"] == chapter_id), None)
        passed = isinstance(chapter_payload, dict) and bool(chapter_payload.get("citations")) and chapter_payload.get("status") in {
            "attached_structurally",
            "attached_verified",
        }
        detail = chapter_payload.get("status") if isinstance(chapter_payload, dict) else None
    elif check_name == "grounded_body_evidence_attached":
        payload = _read_artifact(str(book_root / "research" / "citations.json"))
        chapter_payload = None
        if isinstance(payload, dict) and chapter_id:
            chapter_payload = next((item for item in payload.get("chapters", []) if item["chapter_id"] == chapter_id), None)
        citations = chapter_payload.get("citations", []) if isinstance(chapter_payload, dict) else []
        grounded_payload = chapter_payload.get("grounded_research", {}) if isinstance(chapter_payload, dict) else {}
        body_external_refs = [
            item
            for item in citations
            if item.get("reference_domain") == "body_text" and item.get("source_kind") == "external_reference"
        ]
        verified_body_refs = [
            item
            for item in body_external_refs
            if item.get("url_or_identifier") and (item.get("source_name") or item.get("title"))
        ]
        source_count = grounded_payload.get("source_count", 0) if isinstance(grounded_payload, dict) else 0
        passed = not body_external_refs or (
            source_count > 0 and len(verified_body_refs) == len(body_external_refs)
        )
        detail = {
            "body_external_reference_count": len(body_external_refs),
            "verified_body_reference_count": len(verified_body_refs),
            "grounded_source_count": source_count,
        }
    elif check_name == "rights_provenance_complete":
        payload = _read_artifact(contract["outputs"][2])
        items = payload.get("items", []) if isinstance(payload, dict) else []
        s6a_requests = _s6a_asset_request_lookup(book_id, book_root, chapter_id)
        missing = []
        handed_off = []
        for item in items:
            if item.get("reference_domain") == "visual_anchor" and item.get("rights_category") == "engine_structured_visual":
                continue
            if not item.get("appendix_required", True):
                continue
            has_identifier = bool(item.get("url_or_identifier"))
            has_label = bool(item.get("source_name") or item.get("title"))
            if item.get("reference_domain") == "visual_anchor" and not has_identifier and not has_label:
                asset_request = s6a_requests.get(item.get("reference_id"))
                if asset_request:
                    handed_off.append(item.get("reference_id"))
                    continue
            if not has_identifier or not has_label:
                missing.append(item.get("reference_id"))
        passed = isinstance(payload, dict) and not missing
        detail = {
            "missing_reference_ids": missing,
            "handoff_reference_ids": handed_off,
            "total_items": len(items),
        }
    elif check_name == "freshness_checked":
        payload = _read_artifact(contract["outputs"][1])
        passed = isinstance(payload, str) and "## Freshness Check" in payload and "Freshness status: checked" in payload
        detail = contract["outputs"][1]
    elif check_name == "unsupported_claims_zero":
        payload = _read_artifact(contract["outputs"][1])
        passed = isinstance(payload, str) and "Unsupported claims remaining: 0" in payload
        detail = contract["outputs"][1]
    elif check_name == "unsupported_claims_conditional":
        import os
        web_search_enabled = os.environ.get("ENABLE_WEB_SEARCH", "1").strip().lower() not in {"0", "false", "no"}
        if not web_search_enabled:
            passed = True
            detail = {"skipped": True, "reason": "ENABLE_WEB_SEARCH=0: citation verification deferred to online pipeline run"}
        else:
            payload = _read_artifact(contract["outputs"][1])
            passed = isinstance(payload, str) and "Unsupported claims remaining: 0" in payload
            detail = contract["outputs"][1]
    elif check_name == "visual_plan_exists":
        payload = _read_artifact(contract["outputs"][1])
        passed = isinstance(payload, dict) and bool(payload.get("anchors"))
        detail = contract["outputs"][1]
    elif check_name == "anchor_ids_unique":
        payload = _read_artifact(contract["outputs"][1])
        anchor_ids = [anchor["anchor_id"] for anchor in payload.get("anchors", [])] if isinstance(payload, dict) else []
        passed = len(anchor_ids) == len(set(anchor_ids)) and bool(anchor_ids)
        detail = anchor_ids
    elif check_name == "priority_items_present":
        payload = _read_artifact(contract["outputs"][1])
        passed = isinstance(payload, dict) and bool(payload.get("priority_items"))
        detail = payload.get("priority_items", []) if isinstance(payload, dict) else []
    elif check_name == "draft3_reading_view_clean":
        payload = _read_artifact(contract["outputs"][0])
        meta_markers = find_body_meta_markers(payload) if isinstance(payload, str) else []
        meta_blocks = find_meta_block_residue(payload) if isinstance(payload, str) else {"meta_block_count": 0, "meta_block_ids": []}
        present_forbidden = [
            heading for heading in S6_FORBIDDEN_DRAFT3_HEADINGS
            if isinstance(payload, str) and heading in payload
        ]
        passed = (
            isinstance(payload, str)
            and all(find_section_marker(payload, section_key) for section_key in SECTION_ORDER)
            and "_이 초고는" not in payload
            and not present_forbidden
            and not meta_markers
            and meta_blocks["meta_block_count"] == 0
        )
        detail = {
            **_section_presence_detail(payload),
            "forbidden_headings_found": present_forbidden,
            "tone_line_found": isinstance(payload, str) and "_이 초고는" in payload,
            "body_meta_markers_found": meta_markers,
            "meta_block_count": meta_blocks["meta_block_count"],
            "meta_block_ids": meta_blocks["meta_block_ids"],
        }
    elif check_name == "visual_support_exists":
        payload = _read_artifact(contract["outputs"][2])
        passed = (
            isinstance(payload, dict)
            and "draft3_contract" in payload
            and "anchor_support" in payload
            and bool(payload.get("anchor_support"))
        )
        detail = contract["outputs"][2]
    elif check_name == "numeric_support_packets_present":
        visual_plan = _read_artifact(contract["outputs"][1])
        support = _read_artifact(contract["outputs"][2])
        anchors = visual_plan.get("anchors", []) if isinstance(visual_plan, dict) else []
        support_items = support.get("anchor_support", []) if isinstance(support, dict) else []
        ds_anchor_ids = [
            anchor.get("anchor_id")
            for anchor in anchors
            if anchor.get("anchor_type") == "DS"
        ]
        numeric_packets = [
            item.get("anchor_id")
            for item in support_items
            if item.get("packet_type") == "numeric_source_packet"
        ]
        passed = set(ds_anchor_ids).issubset(set(numeric_packets))
        detail = {
            "ds_anchor_ids": ds_anchor_ids,
            "numeric_packet_anchor_ids": numeric_packets,
        }
    elif check_name == "asset_collection_manifest_exists":
        payload = _read_artifact(contract["outputs"][0])
        asset_requests = payload.get("asset_requests", []) if isinstance(payload, dict) else []
        passed = (
            isinstance(payload, dict)
            and payload.get("stage_id") == "S6A"
            and isinstance(asset_requests, list)
        )
        detail = {
            "path": contract["outputs"][0],
            "asset_request_count": len(asset_requests),
            "offline_asset_round_required": payload.get("offline_asset_round_required") if isinstance(payload, dict) else None,
        }
    elif check_name == "asset_collection_handoff_exists":
        payload = _read_artifact(contract["outputs"][1])
        passed = (
            isinstance(payload, str)
            and "ASSET COLLECTION HANDOFF" in payload
            and "Naming rule" in payload
            and "## Requests" in payload
        )
        detail = contract["outputs"][1]
    elif check_name == "asset_filename_contract_defined":
        payload = _read_artifact(contract["outputs"][0])
        asset_requests = payload.get("asset_requests", []) if isinstance(payload, dict) else []
        invalid_requests = [
            item.get("anchor_id")
            for item in asset_requests
            if item.get("collection_required")
            and (
                not item.get("appendix_ref_id")
                or not item.get("target_dir")
                or not item.get("target_filename")
                or not item.get("target_filename_stub")
            )
        ]
        passed = isinstance(payload, dict) and not invalid_requests
        detail = {
            "invalid_anchor_ids": invalid_requests,
            "request_count": len(asset_requests),
        }
    elif check_name == "ingestion_report_exists":
        payload = _read_artifact(contract["outputs"][2])
        passed = (
            isinstance(payload, dict)
            and payload.get("stage_id") == "S6B"
            and "chapter_id" in payload
            and isinstance(payload.get("processed_count"), int)
            and isinstance(payload.get("pending_count"), int)
        )
        detail = {
            "path": contract["outputs"][2],
            "processed_count": payload.get("processed_count") if isinstance(payload, dict) else None,
            "pending_count": payload.get("pending_count") if isinstance(payload, dict) else None,
        }
    elif check_name == "ingestion_status_synced":
        report = _read_artifact(contract["outputs"][2])
        # Gate passes when all collection-required anchors are either cleared or
        # documented as pending (no silent unknowns). Errors block the gate.
        passed = (
            isinstance(report, dict)
            and report.get("error_count", 0) == 0
        )
        detail = {
            "error_count": report.get("error_count") if isinstance(report, dict) else None,
            "pending_anchor_ids": report.get("pending_anchor_ids") if isinstance(report, dict) else [],
        }
    elif check_name == "visual_bundle_exists":
        payload = _read_artifact(contract["outputs"][1])
        passed = isinstance(payload, dict) and bool(payload.get("anchors")) and "resolution" in payload
        detail = contract["outputs"][1]
    elif check_name == "anchor_resolve_rate_threshold":
        payload = _read_artifact(contract["outputs"][1])
        resolution = payload.get("resolution", {}) if isinstance(payload, dict) else {}
        rate = resolution.get("anchor_resolve_rate", 0.0)
        unresolved = resolution.get("unresolved_anchor_ids", [])
        passed = isinstance(payload, dict) and rate >= 1.0 and not unresolved
        detail = {"anchor_resolve_rate": rate, "unresolved_anchor_ids": unresolved}
    elif check_name == "draft4_exists":
        payload = _read_artifact(contract["outputs"][0])
        meta_blocks = find_meta_block_residue(payload) if isinstance(payload, str) else {"meta_block_count": 0}
        passed = (
            isinstance(payload, str)
            and "[ANCHOR_SLOT:" not in payload
            and meta_blocks["meta_block_count"] == 0
        )
        detail = {
            "path": contract["outputs"][0],
            "meta_block_count": meta_blocks["meta_block_count"],
        }
    elif check_name == "style_violations_zero_or_acceptable":
        payload = _read_artifact(contract["outputs"][1])
        passed = isinstance(payload, str) and "Style issues remaining: 0" in payload and "Copyedit gate: pass" in payload
        detail = contract["outputs"][1]
    elif check_name == "structure_integrity_pass":
        payload = _read_artifact(contract["outputs"][0])
        start_count = payload.count("<!-- ANCHOR_START") if isinstance(payload, str) else 0
        end_count = payload.count("<!-- ANCHOR_END") if isinstance(payload, str) else 0
        slot_count = payload.count("[ANCHOR_SLOT:") if isinstance(payload, str) else 0
        meta_blocks = find_meta_block_residue(payload) if isinstance(payload, str) else {"meta_block_count": 0}
        passed = (
            isinstance(payload, str)
            and all(find_section_marker(payload, section_key) for section_key in SECTION_ORDER)
            and start_count == end_count
            and slot_count == 0
            and meta_blocks["meta_block_count"] == 0
        )
        detail = {
            **_section_presence_detail(payload),
            "anchor_start_count": start_count,
            "anchor_end_count": end_count,
            "anchor_slot_count": slot_count,
            "meta_block_count": meta_blocks["meta_block_count"],
        }
    elif check_name == "proofreading_report_exists":
        payload = _read_artifact(contract["outputs"][1])
        passed = isinstance(payload, str) and "## Verdict" in payload and "## Structure Integrity" in payload
        detail = contract["outputs"][1]
    elif check_name == "word_floor_met_at_s8":
        payload = _read_artifact(contract["outputs"][0])
        target_payload = _read_artifact(str(book_root / "_master" / "WORD_TARGETS.json"))
        floor = 180
        if isinstance(target_payload, dict) and chapter_id:
            for chapter in target_payload.get("chapters", []):
                if chapter["chapter_id"] == chapter_id:
                    floors_cfg = chapter.get("stage_progress_floors", {})
                    floor = floors_cfg.get("S8_final_draft_min_words",
                                          floors_cfg.get("S4_draft1_min_words", floor))
                    break
        measured = count_words(payload) if isinstance(payload, str) else 0
        passed = isinstance(payload, str) and measured >= floor
        detail = {"measured_words": measured, "required_floor_words": floor, "floor_source": "S8_final_draft_min_words"}
    elif check_name == "draft6_exists":
        payload = _read_artifact(contract["outputs"][0])
        start_count = payload.count("<!-- ANCHOR_START") if isinstance(payload, str) else 0
        end_count = payload.count("<!-- ANCHOR_END") if isinstance(payload, str) else 0
        slot_count = payload.count("[ANCHOR_SLOT:") if isinstance(payload, str) else 0
        meta_blocks = find_meta_block_residue(payload) if isinstance(payload, str) else {"meta_block_count": 0}
        passed = (
            isinstance(payload, str)
            and all(find_section_marker(payload, section_key) for section_key in SECTION_ORDER)
            and start_count == end_count
            and slot_count == 0
            and meta_blocks["meta_block_count"] == 0
        )
        detail = {
            **_section_presence_detail(payload),
            "anchor_start_count": start_count,
            "anchor_end_count": end_count,
            "anchor_slot_count": slot_count,
            "meta_block_count": meta_blocks["meta_block_count"],
        }
    elif check_name == "amplification_report_exists":
        payload = _read_artifact(contract["outputs"][1])
        passed = isinstance(payload, str) and "## Verdict" in payload and "## Value Amplification" in payload
        detail = contract["outputs"][1]
    elif check_name == "amplification_integrity_pass":
        payload = _read_artifact(contract["outputs"][1])
        passed = isinstance(payload, str) and "Amplification gate: pass" in payload
        detail = contract["outputs"][1]
    elif check_name == "s8a_rewrite_target_cap_respected":
        payload = _read_artifact(str(_node_manifest_path(book_root, "S8A", chapter_id)))
        node_count = payload.get("node_count") if isinstance(payload, dict) else None
        passed = isinstance(payload, dict) and isinstance(node_count, int) and node_count <= MAX_GATE_S8A_REWRITE_TARGETS
        detail = {
            "node_manifest_path": str(_node_manifest_path(book_root, "S8A", chapter_id)),
            "node_count": node_count,
            "live_node_count": payload.get("live_node_count") if isinstance(payload, dict) else None,
            "fallback_node_count": payload.get("fallback_node_count") if isinstance(payload, dict) else None,
            "rewrite_target_cap": MAX_GATE_S8A_REWRITE_TARGETS,
        }
    elif check_name == "s8a_live_contribution_present":
        payload = _read_artifact(str(_node_manifest_path(book_root, "S8A", chapter_id)))
        node_count = payload.get("node_count") if isinstance(payload, dict) else 0
        live_node_count = payload.get("live_node_count") if isinstance(payload, dict) else 0
        all_nodes_fallback = payload.get("all_nodes_fallback") if isinstance(payload, dict) else False
        passed = isinstance(payload, dict) and (
            node_count == 0 or (isinstance(live_node_count, int) and live_node_count > 0 and not all_nodes_fallback)
        )
        detail = {
            "node_manifest_path": str(_node_manifest_path(book_root, "S8A", chapter_id)),
            "node_count": node_count,
            "live_node_count": live_node_count,
            "all_nodes_fallback": all_nodes_fallback,
        }
    elif check_name == "s8a_section_coverage_balanced":
        payload = _read_artifact(str(_node_manifest_path(book_root, "S8A", chapter_id)))
        node_count = payload.get("node_count") if isinstance(payload, dict) else 0
        selected_sections = payload.get("selected_sections") if isinstance(payload, dict) else []
        available_sections = payload.get("available_sections") if isinstance(payload, dict) else []
        required_section_count = payload.get("required_section_count") if isinstance(payload, dict) else 0
        section_coverage_balanced = payload.get("section_coverage_balanced") if isinstance(payload, dict) else False
        passed = isinstance(payload, dict) and (
            node_count == 0 or bool(section_coverage_balanced)
        )
        detail = {
            "node_manifest_path": str(_node_manifest_path(book_root, "S8A", chapter_id)),
            "available_sections": available_sections,
            "selected_sections": selected_sections,
            "required_section_count": required_section_count,
            "section_coverage_balanced": section_coverage_balanced,
        }
    elif check_name == "s8a_amplification_ratio_within_cap":
        draft5_payload = _read_artifact(str(_draft_path(book_root, "_draft5", chapter_id)))
        draft6_payload = _read_artifact(str(_draft_path(book_root, "_draft6", chapter_id)))
        input_words = count_words(draft5_payload) if isinstance(draft5_payload, str) else 0
        output_words = count_words(draft6_payload) if isinstance(draft6_payload, str) else 0
        max_allowed_words = round(input_words * MAX_GATE_AMPLIFICATION_RATIO) if input_words else 0
        passed = (
            isinstance(draft5_payload, str)
            and isinstance(draft6_payload, str)
            and input_words > 0
            and output_words <= max_allowed_words
        )
        detail = {
            "draft5_path": str(_draft_path(book_root, "_draft5", chapter_id)),
            "draft6_path": str(_draft_path(book_root, "_draft6", chapter_id)),
            "input_words": input_words,
            "output_words": output_words,
            "max_allowed_words": max_allowed_words,
            "max_amplification_ratio": MAX_GATE_AMPLIFICATION_RATIO,
        }
    elif check_name == "qa_clearance_report_exists":
        # SQA output[0] = publication/qa/publication_clearance_report.json
        report_path = book_root / "publication" / "qa" / "publication_clearance_report.json"
        payload = _read_artifact(str(report_path))
        passed = (
            isinstance(payload, dict)
            and payload.get("stage_id") == "SQA"
            and isinstance(payload.get("checks"), list)
            and "verdict" in payload
        )
        detail = {
            "path": str(report_path),
            "verdict": payload.get("verdict") if isinstance(payload, dict) else None,
            "checks_passed": payload.get("checks_passed") if isinstance(payload, dict) else None,
            "checks_total": payload.get("checks_total") if isinstance(payload, dict) else None,
        }
    elif check_name == "qa_verdict_pass":
        report_path = book_root / "publication" / "qa" / "publication_clearance_report.json"
        payload = _read_artifact(str(report_path))
        passed = isinstance(payload, dict) and payload.get("overall_pass") is True
        detail = {
            "verdict": payload.get("verdict") if isinstance(payload, dict) else None,
            "failed_checks": payload.get("failed_checks") if isinstance(payload, dict) else [],
        }
    elif check_name == "epub_generated":
        path = Path(contract["outputs"][0])
        passed = path.exists() and path.stat().st_size > 0
        detail = str(path)
    elif check_name == "pdf_generated":
        path = Path(contract["outputs"][1])
        passed = path.exists() and path.stat().st_size > 0
        detail = str(path)
    elif check_name == "metadata_validation_pass":
        payload = _read_artifact(contract["outputs"][3])
        validation = payload.get("validation", {}).get("metadata_validation", {}) if isinstance(payload, dict) else {}
        passed = bool(validation.get("passed"))
        detail = validation
    elif check_name == "seo_pack_exists":
        seo_payload = _read_artifact(contract["outputs"][4])
        store_payload = _read_artifact(contract["outputs"][5])
        passed = (
            isinstance(seo_payload, dict)
            and all(key in seo_payload for key in ["full_title", "short_description", "keywords", "subjects", "html_meta", "epub_meta"])
            and isinstance(store_payload, str)
            and "## Headline" in store_payload
            and "## Long Description" in store_payload
        )
        detail = {
            "seo_path": contract["outputs"][4],
            "store_listing_path": contract["outputs"][5],
        }
    elif check_name == "platform_validation_pass":
        payload = _read_artifact(contract["outputs"][3])
        validation = payload.get("validation", {}).get("platform_validation", {}) if isinstance(payload, dict) else {}
        passed = bool(validation.get("passed"))
        detail = validation
    elif check_name == "publication_manifest_exists":
        payload = _read_artifact(contract["outputs"][3])
        passed = isinstance(payload, dict) and "artifacts" in payload and "validation" in payload
        detail = contract["outputs"][3]
    else:
        passed = all(item["exists"] for item in [{"exists": _exists(path)} for path in contract["outputs"]])
        detail = "default output existence check"

    return {
        "check": check_name,
        "passed": passed,
        "detail": detail,
    }


def evaluate_gate(
    book_id: str,
    book_root: Path,
    stage_id: str,
    chapter_id: str | None = None,
) -> dict[str, Any]:
    stage = get_stage_definition(stage_id)
    gate = get_gate_definition(stage["gate"])
    contract = resolve_stage_contract(book_id, book_root, stage_id, chapter_id)

    output_checks = []
    for output in contract["outputs"]:
        output_checks.append(
            {
                "artifact": output,
                "exists": _exists(output),
            }
        )

    check_results = [
        _run_check(check, book_id, book_root, stage_id, chapter_id, contract)
        for check in gate["checks"]
    ]
    passed = all(item["passed"] for item in check_results) and all(item["exists"] for item in output_checks)
    return {
        "stage_id": stage_id,
        "chapter_id": chapter_id,
        "gate_id": gate["gate_id"],
        "checks": check_results,
        "output_checks": output_checks,
        "passed": passed,
        "on_fail": gate["on_fail"],
    }
