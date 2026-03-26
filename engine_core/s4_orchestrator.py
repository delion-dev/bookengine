from __future__ import annotations

"""S4Orchestrator — AG-01 Draft-1 Stage Orchestration (SRP separation)

Responsibilities (orchestration-only):
  - Pre-flight: resolve target chapters, validate inputs
  - Chapter loop: status routing (backfill / full-pipeline / gate-revalidation)
  - Post-flight: gate evaluation, stage transitions, memory updates
  - Work-order summary

Content generation is delegated entirely to writer.py (section nodes,
segment plans, expansion, rendering).  This module contains zero model calls.

Public API:
  run_s4(book_id, book_root, chapter_id, *, rerun_completed) -> dict
  S4Orchestrator(book_id, book_root) — class-based entry point
"""

import json
from pathlib import Path
from typing import Any

from .ag01_engine import execute_s4_pipeline
from .book_state import load_book_db
from .common import count_words, now_iso, read_json, read_text, write_json, write_text
from .contracts import validate_inputs
from .gates import evaluate_gate
from .memory import update_chapter_memory
from .stage import transition_stage
from .subsection_nodes import write_node_manifest
from .targets import get_chapter_target
from .work_order import issue_work_order

# Content-generation helpers (stay in writer.py — imported here, not duplicated)
from .writer import (
    MAX_S4_EXPANSIONS,
    _all_s4_chapters,
    _anchor_ids_for_backfill,
    _backfilled_s4_node_manifest,
    _can_backfill_s4_outputs,
    _draft_claims,
    _draft1_section_texts,
    _has_all_s4_outputs,
    _legacy_s4_anchored_path,
    _legacy_s4_narrative_design,
    _legacy_s4_segment_plan,
    _missing_s4_outputs,
    _parse_raw_guide_contract,
    _pending_s4_chapters,
    _research_entry,
    _s4_output_bundle,
    _source_queue_items_for_chapter,
    _source_types_for_chapter,
    _strip_anchor_markup,
)


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _build_density_audit(
    current_chapter_id: str,
    chapter: dict[str, Any],
    chapter_target: dict[str, Any],
    prose_text: str,
    section_texts: dict[str, str],
    segment_plan: dict[str, Any],
    audit_node_manifest: dict[str, Any],
) -> dict[str, Any]:
    return {
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
            and all(
                section_texts.get(k, "").strip()
                for k in ("hook", "context", "insight", "takeaway")
            )
        ),
    }


def _run_backfill_path(
    book_id: str,
    book_root: Path,
    book_db: dict[str, Any],
    current_chapter_id: str,
    output_bundle: dict[str, str],
    missing_outputs: list[str],
    research_plan: dict[str, Any],
    source_queue: dict[str, Any],
    word_targets: dict[str, Any],
) -> dict[str, Any]:
    """Handle the artifact-backfill repair path for a completed chapter."""
    chapter = {
        "chapter_id": current_chapter_id,
        "title": book_db["chapters"][current_chapter_id].get("title", current_chapter_id),
        **book_db["chapters"][current_chapter_id],
    }
    research_entry = _research_entry(research_plan, current_chapter_id)
    source_types = _source_types_for_chapter(source_queue, current_chapter_id)
    chapter_target = get_chapter_target(word_targets, current_chapter_id)
    raw_guide = read_text(book_root / "manuscripts" / "_raw" / f"{current_chapter_id}_raw.md")

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
        chapter, research_entry, source_types, chapter_target, raw_guide_contract, section_texts,
    )
    narrative_design = _legacy_s4_narrative_design(chapter, raw_guide_contract, segment_plan)
    existing_node_manifest = read_json(Path(output_bundle["node_manifest"]), default=None)
    audit_node_manifest = _backfilled_s4_node_manifest(
        chapter, research_entry, source_types, chapter_target, raw_guide, section_texts,
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

    density_audit = _build_density_audit(
        current_chapter_id, chapter, chapter_target, prose_text,
        section_texts, segment_plan, audit_node_manifest,
    )
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
        "artifacts": {
            "draft1_prose": output_bundle["draft1_prose"],
            "segment_plan": output_bundle["segment_plan"],
            "narrative_design": output_bundle["narrative_design"],
            "density_audit": output_bundle["density_audit"],
            "session_report": output_bundle["session_report"],
        },
    }
    if not Path(output_bundle["density_audit"]).exists():
        write_json(Path(output_bundle["density_audit"]), density_audit)
    if not Path(output_bundle["session_report"]).exists():
        write_json(Path(output_bundle["session_report"]), session_report)

    update_chapter_memory(
        book_root, current_chapter_id,
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
        book_root, "S4", "completed", current_chapter_id,
        note=f"AG-01 legacy output backfill completed: {', '.join(Path(p).name for p in missing_outputs)}",
    )
    declared_outputs = list(output_bundle.values())
    return {
        "chapter_id": current_chapter_id,
        "status": "completed",
        "repair_mode": "artifact_backfill",
        "repaired_outputs": [Path(p).name for p in missing_outputs],
        "outputs": declared_outputs,
        "node_manifest": output_bundle["node_manifest"],
        "segment_plan": output_bundle["segment_plan"],
        "narrative_design": output_bundle["narrative_design"],
        "density_audit": output_bundle["density_audit"],
        "session_report": output_bundle["session_report"],
        "gate_result": {"skipped": True, "reason": "artifact_backfill_only"},
    }


def _run_full_pipeline_path(
    book_id: str,
    book_root: Path,
    book_db: dict[str, Any],
    current_chapter_id: str,
    output_bundle: dict[str, str],
    research_plan: dict[str, Any],
    source_queue: dict[str, Any],
    word_targets: dict[str, Any],
) -> dict[str, Any]:
    """Handle the full-generation pipeline path for a chapter."""
    chapter = {
        "chapter_id": current_chapter_id,
        "title": book_db["chapters"][current_chapter_id].get("title", current_chapter_id),
        **book_db["chapters"][current_chapter_id],
    }
    research_entry = _research_entry(research_plan, current_chapter_id)
    source_queue_items = _source_queue_items_for_chapter(source_queue, current_chapter_id)
    source_types = _source_types_for_chapter(source_queue, current_chapter_id)
    chapter_target = get_chapter_target(word_targets, current_chapter_id)
    raw_guide = read_text(book_root / "manuscripts" / "_raw" / f"{current_chapter_id}_raw.md")

    pipeline_result = execute_s4_pipeline(
        book_root, chapter, research_entry, source_queue_items,
        source_types, chapter_target, raw_guide,
    )
    grounded = pipeline_result["grounded"]
    node_manifest_path = pipeline_result["node_manifest_path"]
    generation_mode = pipeline_result["generation_mode"]
    output_path = pipeline_result["prose_path"]
    session_report = pipeline_result["session_report"]

    update_chapter_memory(
        book_root, current_chapter_id,
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
            book_root, "S4", "gate_failed", current_chapter_id,
            note=json.dumps(gate_result, ensure_ascii=False),
        )
        return {
            "chapter_id": current_chapter_id,
            "status": "gate_failed",
            "outputs": declared_outputs,
            "node_manifest": str(node_manifest_path),
            "gate_result": gate_result,
        }

    transition_stage(
        book_root, "S4", "completed", current_chapter_id,
        note=f"AG-01 draft1 generation completed ({session_report.get('verdict', 'completed')}).",
    )
    return {
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


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

class S4Orchestrator:
    """Orchestrates the S4 (Draft-1) stage lifecycle.

    Responsibilities:
      - Resolve target chapters and validate inputs
      - Route each chapter to the correct execution path (backfill, full, revalidate)
      - Coordinate gate evaluation and stage transitions
      - Delegate all content generation to writer.py helpers / ag01_engine
    """

    def __init__(self, book_id: str, book_root: Path) -> None:
        self.book_id = book_id
        self.book_root = book_root

    # -----------------------------------------------------------------------
    # Introspection helpers (useful for API / monitoring)
    # -----------------------------------------------------------------------

    def pending_chapters(self) -> list[str]:
        return _pending_s4_chapters(self.book_id, self.book_root)

    def output_status(self, chapter_id: str) -> dict[str, Any]:
        bundle = _s4_output_bundle(self.book_id, self.book_root, chapter_id)
        missing = _missing_s4_outputs(self.book_id, self.book_root, chapter_id)
        return {
            "chapter_id": chapter_id,
            "outputs": bundle,
            "missing": missing,
            "all_present": not missing,
            "can_backfill": _can_backfill_s4_outputs(self.book_id, self.book_root, chapter_id),
        }

    # -----------------------------------------------------------------------
    # Main entry point
    # -----------------------------------------------------------------------

    def run(
        self,
        chapter_id: str | None = None,
        *,
        rerun_completed: bool = False,
    ) -> dict[str, Any]:
        """Run the S4 draft-generation stage.

        Args:
            chapter_id:      Target a specific chapter; None = auto-select pending.
            rerun_completed: If True, rerun chapters whose S4 is already completed.

        Returns:
            Stage result dict compatible with run_stage() in stage_api.py.
        """
        book_db = load_book_db(self.book_root)
        research_plan = read_json(
            self.book_root / "research" / "research_plan.json", default=None
        )
        source_queue = read_json(
            self.book_root / "research" / "source_queue.json", default=None
        )
        word_targets = read_json(
            self.book_root / "_master" / "WORD_TARGETS.json", default=None
        )
        if research_plan is None or source_queue is None or word_targets is None:
            raise FileNotFoundError(
                "S4 requires research_plan.json, source_queue.json, and WORD_TARGETS.json."
            )

        target_chapters: list[str]
        if chapter_id:
            target_chapters = [chapter_id]
        elif rerun_completed:
            target_chapters = _all_s4_chapters(self.book_root)
        else:
            target_chapters = _pending_s4_chapters(self.book_id, self.book_root)

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

        results: list[dict[str, Any]] = []

        for current_chapter_id in target_chapters:
            contract_status = validate_inputs(
                self.book_id, self.book_root, "S4", current_chapter_id
            )
            if not contract_status["valid"]:
                raise FileNotFoundError(
                    f"S4 inputs missing for {current_chapter_id}: "
                    f"{contract_status['missing_inputs']}"
                )

            current_status = (
                book_db["chapters"][current_chapter_id]["stages"]["S4"]["status"]
            )
            output_bundle = _s4_output_bundle(self.book_id, self.book_root, current_chapter_id)
            missing_outputs = _missing_s4_outputs(self.book_id, self.book_root, current_chapter_id)
            backfill_only = (
                current_status == "completed"
                and _can_backfill_s4_outputs(self.book_id, self.book_root, current_chapter_id)
            )

            # ── Status transitions before content generation ──────────────
            if rerun_completed and current_status == "completed":
                transition_stage(
                    self.book_root, "S4", "in_progress", current_chapter_id,
                    note="AG-01 draft1 full rerun started from stabilized pipeline.",
                )
            elif current_status == "gate_failed":
                transition_stage(
                    self.book_root, "S4", "pending", current_chapter_id,
                    note="AG-01 draft1 rerun requested after gate fix.",
                )
                transition_stage(
                    self.book_root, "S4", "in_progress", current_chapter_id,
                    note="AG-01 draft1 generation restarted.",
                )
            elif current_status != "completed":
                transition_stage(
                    self.book_root, "S4", "in_progress", current_chapter_id,
                    note="AG-01 draft1 generation started.",
                )
            elif missing_outputs and not backfill_only:
                transition_stage(
                    self.book_root, "S4", "in_progress", current_chapter_id,
                    note="AG-01 draft1 regeneration started from missing outputs.",
                )

            # ── Execution path routing ────────────────────────────────────
            common_kwargs = dict(
                book_id=self.book_id,
                book_root=self.book_root,
                book_db=book_db,
                current_chapter_id=current_chapter_id,
                output_bundle=output_bundle,
                research_plan=research_plan,
                source_queue=source_queue,
                word_targets=word_targets,
            )
            if backfill_only:
                result = _run_backfill_path(
                    **common_kwargs, missing_outputs=missing_outputs,
                )
            else:
                result = _run_full_pipeline_path(**common_kwargs)

            results.append(result)

        work_order = issue_work_order(self.book_id, self.book_root)
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


# ---------------------------------------------------------------------------
# Module-level shim — preserves the run_stage() call signature expected by
# stage_api.py when S4Orchestrator is registered as the handler.
# ---------------------------------------------------------------------------

def run_s4(
    book_id: str,
    book_root: Path,
    chapter_id: str | None = None,
    *,
    rerun_completed: bool = False,
) -> dict[str, Any]:
    """Canonical S4 entry point.  Delegates to S4Orchestrator.run()."""
    return S4Orchestrator(book_id, book_root).run(chapter_id, rerun_completed=rerun_completed)
