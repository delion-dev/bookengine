from __future__ import annotations

"""engine.stage — Stage runtime endpoints."""

import threading
import uuid
from datetime import datetime
from pathlib import Path
from typing import Any

from fastapi import APIRouter, BackgroundTasks, HTTPException

from engine_core.contracts import get_stage_definition, resolve_stage_contract, validate_inputs
from engine_core.gates import evaluate_gate
from engine_core.stage import transition_stage
from engine_core.stage_api import STAGE_HANDLERS, list_stage_handlers, run_stage
from engine_core.book_state import load_book_db
from engine_api.deps import resolve_book_root
from engine_api.models import GateRefreshRequest, StageRunRequest, StageTransitionRequest

router = APIRouter(prefix="/engine/stage", tags=["stage"])

# ---------------------------------------------------------------------------
# In-memory Job Store (단일 프로세스, 재시작 시 초기화)
# ---------------------------------------------------------------------------
_jobs: dict[str, dict[str, Any]] = {}
_jobs_lock = threading.Lock()


def _make_job(book_id: str, stage_id: str, chapter_id: str | None) -> dict[str, Any]:
    job_id = f"job-{uuid.uuid4().hex[:12]}"
    job: dict[str, Any] = {
        "job_id": job_id,
        "book_id": book_id,
        "stage_id": stage_id,
        "chapter_id": chapter_id,
        "status": "queued",       # queued | running | completed | failed
        "result": None,
        "error": None,
        "started_at": None,
        "completed_at": None,
        "created_at": datetime.now().isoformat(timespec="seconds"),
    }
    with _jobs_lock:
        _jobs[job_id] = job
    return job


def _run_job(job_id: str, book_id: str, book_root: Path, stage_id: str,
             chapter_id: str | None, rerun_completed: bool) -> None:
    with _jobs_lock:
        _jobs[job_id]["status"] = "running"
        _jobs[job_id]["started_at"] = datetime.now().isoformat(timespec="seconds")
    try:
        result = run_stage(book_id, book_root, stage_id, chapter_id,
                           rerun_completed=rerun_completed)
        with _jobs_lock:
            _jobs[job_id]["status"] = "completed"
            _jobs[job_id]["result"] = result
            _jobs[job_id]["completed_at"] = datetime.now().isoformat(timespec="seconds")
    except Exception as exc:
        with _jobs_lock:
            _jobs[job_id]["status"] = "failed"
            _jobs[job_id]["error"] = str(exc)
            _jobs[job_id]["completed_at"] = datetime.now().isoformat(timespec="seconds")


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------

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
    """Execute a stage synchronously. Suitable for fast stages (S0, S1, SQA).
    For long-running stages (S4, S5 etc.) use POST /run-async instead."""
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


@router.post("/run-async")
def run_stage_async(req: StageRunRequest, background_tasks: BackgroundTasks):
    """Submit a stage for background execution. Returns job_id immediately.
    Poll GET /job/{job_id} for status. Recommended for S4, S5, S6, S7, S8, S8A."""
    if req.stage_id not in STAGE_HANDLERS:
        raise HTTPException(status_code=400, detail=f"Unknown stage_id: {req.stage_id}")
    book_root = resolve_book_root(req.book_id)
    job = _make_job(req.book_id, req.stage_id, req.chapter_id)
    background_tasks.add_task(
        _run_job,
        job["job_id"],
        req.book_id,
        book_root,
        req.stage_id,
        req.chapter_id,
        req.rerun_completed,
    )
    return {
        "job_id": job["job_id"],
        "status": "queued",
        "poll_url": f"/engine/stage/job/{job['job_id']}",
    }


@router.get("/job/{job_id}")
def get_job_status(job_id: str):
    """Poll the status of an async stage run."""
    with _jobs_lock:
        job = _jobs.get(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail=f"Job not found: {job_id}")
    return job


@router.get("/jobs")
def list_jobs(book_id: str | None = None):
    """List recent jobs (optionally filtered by book_id). Max 50."""
    with _jobs_lock:
        jobs = list(_jobs.values())
    if book_id:
        jobs = [j for j in jobs if j["book_id"] == book_id]
    return {"jobs": sorted(jobs, key=lambda j: j["created_at"], reverse=True)[:50]}


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
