from __future__ import annotations

"""engine.stage — Stage runtime endpoints."""

from pathlib import Path

from fastapi import APIRouter, BackgroundTasks, HTTPException

from engine_core.contracts import get_stage_definition, resolve_stage_contract, validate_inputs
from engine_core.gates import evaluate_gate
from engine_core.stage import transition_stage
from engine_core.stage_api import STAGE_HANDLERS, list_stage_handlers, run_stage
from engine_core.book_state import load_book_db
from engine_api.deps import resolve_book_root
from engine_api.models import GateRefreshRequest, StageRunRequest, StageTransitionRequest

router = APIRouter(prefix="/engine/stage", tags=["stage"])


@router.get("/handlers")
def list_handlers():
    """List all registered stage handlers."""
    return {"handlers": list_stage_handlers()}


@router.get("/definition/{stage_id}")
def get_definition(stage_id: str):
    """Get stage definition (inputs, outputs, gate, agent)."""
    try:
        return get_stage_definition(stage_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc))


@router.post("/contract/resolve")
def resolve_contract(book_id: str, stage_id: str, chapter_id: str | None = None):
    """Resolve the artifact contract for a specific (stage, chapter)."""
    book_root = resolve_book_root(book_id)
    try:
        return resolve_stage_contract(book_id, book_root, stage_id, chapter_id)
    except (KeyError, ValueError) as exc:
        raise HTTPException(status_code=400, detail=str(exc))


@router.post("/contract/validate")
def validate_contract(book_id: str, stage_id: str, chapter_id: str | None = None):
    """Validate that required inputs exist for a stage."""
    book_root = resolve_book_root(book_id)
    try:
        return validate_inputs(book_id, book_root, stage_id, chapter_id)
    except (KeyError, ValueError) as exc:
        raise HTTPException(status_code=400, detail=str(exc))


@router.post("/run")
def run_stage_endpoint(req: StageRunRequest):
    """Execute a stage synchronously. Long-running stages may time out — use /run-async."""
    if req.stage_id not in STAGE_HANDLERS:
        raise HTTPException(status_code=400, detail=f"Unknown stage_id: {req.stage_id}")
    book_root = resolve_book_root(req.book_id)
    try:
        result = run_stage(
            req.book_id,
            book_root,
            req.stage_id,
            req.chapter_id,
            rerun_completed=req.rerun_completed,
        )
        return {"stage_id": req.stage_id, "status": result.get("status", "ok"), "result": result}
    except FileNotFoundError as exc:
        raise HTTPException(status_code=422, detail=str(exc))
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))


@router.post("/transition")
def transition(req: StageTransitionRequest):
    """Manually transition a stage status."""
    book_root = resolve_book_root(req.book_id)
    try:
        result = transition_stage(
            book_root, req.stage_id, req.to_status, req.chapter_id, req.note
        )
        return {"ok": True, "transition": result}
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc))


@router.get("/pipeline/{book_id}")
def get_pipeline(book_id: str):
    """Get current chapter-level pipeline status for all stages."""
    book_root = resolve_book_root(book_id)
    book_db = load_book_db(book_root)
    return {
        "book_id": book_id,
        "chapter_sequence": book_db.get("chapter_sequence", []),
        "chapters": {
            cid: {"title": ch["title"], "stages": ch["stages"]}
            for cid, ch in book_db.get("chapters", {}).items()
        },
    }
