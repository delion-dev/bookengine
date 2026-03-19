from __future__ import annotations

from pathlib import Path
from typing import Any, Callable

from .asset_collection import run_asset_collection
from .image_ingestion import run_image_ingestion
from .qa_checker import run_publication_qa
from .anchor_injector import run_anchor_injection
from .amplifier import run_amplification
from .architecture import run_architecture
from .copyeditor import run_copyedit
from .contracts import get_stage_definition, register_stage_outputs
from .orchestration import run_orchestration
from .publication import run_publication
from .planner import run_raw_guides
from .research import run_research_plan
from .reviewer import run_review
from .session import close_session, open_session
from .telemetry import build_runtime_telemetry_dashboard
from .visual_renderer import run_visual_render
from .visual_planner import run_visual_plan
from .writer import run_draft1


StageHandler = Callable[..., dict[str, Any]]


def _book_only(handler: Callable[[str, Path], dict[str, Any]]) -> StageHandler:
    def runner(book_id: str, book_root: Path, chapter_id: str | None = None) -> dict[str, Any]:
        return handler(book_id, book_root)

    return runner


STAGE_HANDLERS: dict[str, StageHandler] = {
    "S0": _book_only(run_architecture),
    "S1": _book_only(run_orchestration),
    "S2": _book_only(run_research_plan),
    "S3": run_raw_guides,
    "S4": run_draft1,
    "S4A": run_anchor_injection,
    "S5": run_review,
    "S6": run_visual_plan,
    "S6A": run_asset_collection,
    "S6B": run_image_ingestion,
    "S7": run_visual_render,
    "S8": run_copyedit,
    "S8A": run_amplification,
    "SQA": _book_only(run_publication_qa),
    "S9": _book_only(run_publication),
}


def _stage_requires_chapter(stage_id: str) -> bool:
    stage = get_stage_definition(stage_id)
    templates = [*stage.get("input", []), *stage.get("output", [])]
    return any("{chapter_id}" in template for template in templates)


def _chapters_for_output_registration(
    stage_id: str,
    requested_chapter_id: str | None,
    result: dict[str, Any],
) -> list[str | None]:
    if not _stage_requires_chapter(stage_id):
        return [None]
    if requested_chapter_id is not None:
        return [requested_chapter_id]
    return [
        item["chapter_id"]
        for item in result.get("results", [])
        if isinstance(item, dict) and item.get("chapter_id")
    ]


def _register_outputs_for_result(
    book_id: str,
    book_root: Path,
    stage_id: str,
    requested_chapter_id: str | None,
    result: dict[str, Any],
) -> dict[str, Any]:
    if result.get("status") == "no_op":
        return {
            "stage_id": stage_id,
            "registered_output_count": 0,
            "registrations": [],
        }

    registrations = [
        register_stage_outputs(book_id, book_root, stage_id, chapter_id)
        for chapter_id in _chapters_for_output_registration(stage_id, requested_chapter_id, result)
    ]
    registered_output_count = sum(len(item["registered_outputs"]) for item in registrations)
    return {
        "stage_id": stage_id,
        "registered_output_count": registered_output_count,
        "registrations": registrations,
    }


def list_stage_handlers() -> list[dict[str, str]]:
    return [
        {
            "stage_id": stage_id,
            "handler": f"engine.stage.run::{stage_id}",
            "agent": get_stage_definition(stage_id)["agent"],
        }
        for stage_id in sorted(STAGE_HANDLERS.keys())
    ]


def run_stage(
    book_id: str,
    book_root: Path,
    stage_id: str,
    chapter_id: str | None = None,
    *,
    rerun_completed: bool = False,
) -> dict[str, Any]:
    if stage_id not in STAGE_HANDLERS:
        raise KeyError(f"No implemented stage handler for {stage_id}")
    stage_def = get_stage_definition(stage_id)
    session_bundle = open_session(book_id, stage_def["agent"], book_root, stage_id=stage_id)
    try:
        if stage_id in {"S4", "S4A", "S5", "S6", "S7", "S8"}:
            result = STAGE_HANDLERS[stage_id](
                book_id,
                book_root,
                chapter_id,
                rerun_completed=rerun_completed,
            )
        else:
            result = STAGE_HANDLERS[stage_id](book_id, book_root, chapter_id)
        output_registration = _register_outputs_for_result(book_id, book_root, stage_id, chapter_id, result)
        close_report = close_session(
            book_root,
            session_bundle["session_id"],
            f"{stage_id} completed with status={result.get('status', 'ok')}.",
        )
    except Exception as exc:
        close_session(
            book_root,
            session_bundle["session_id"],
            f"{stage_id} failed: {exc}",
        )
        raise

    result["session"] = {
        "session_id": session_bundle["session_id"],
        "agent_id": session_bundle["agent_id"],
        "stage_id": stage_id,
        "opened_at": session_bundle["opened_at"],
        "closed_at": close_report["closed_at"],
    }
    result["output_registration"] = output_registration
    if stage_id in {"S4", "S5", "S8A", "S9"}:
        telemetry_payload = build_runtime_telemetry_dashboard(book_id, book_root)
        result["runtime_telemetry_dashboard"] = str(book_root / "verification" / "runtime_telemetry_dashboard.json")
        result["runtime_telemetry_generated_at"] = telemetry_payload["generated_at"]
    return result
