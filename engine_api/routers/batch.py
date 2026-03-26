from __future__ import annotations

"""engine.batch — Batch stage execution endpoints.

Endpoints:
  POST   /engine/batch/run          — Start a batch job
  GET    /engine/batch              — List active batches (up to 20)
  GET    /engine/batch/{batch_id}   — Get batch status
  DELETE /engine/batch/{batch_id}   — Cancel/remove completed or failed batch
"""

import threading
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from engine_api.deps import resolve_book_root

router = APIRouter(prefix="/engine/batch", tags=["batch"])

# ---------------------------------------------------------------------------
# In-memory store (max 50 batches)
# ---------------------------------------------------------------------------

_batches: dict[str, dict[str, Any]] = {}
_batches_lock = threading.Lock()

_MAX_BATCHES = 50
_LIST_LIMIT = 20


# ---------------------------------------------------------------------------
# Pydantic models
# ---------------------------------------------------------------------------

class BatchRunRequest(BaseModel):
    book_ids: list[str]
    stage_id: str
    chapter_id: str | None = None
    rerun_completed: bool = False
    parallel: bool = True
    max_parallel: int = Field(default=3, ge=1, le=10)


class BatchJobDetail(BaseModel):
    status: str
    result: dict[str, Any] | None = None
    error: str | None = None
    started_at: str | None = None
    completed_at: str | None = None


class BatchSummary(BaseModel):
    total: int
    completed: int
    failed: int
    running: int
    queued: int


class BatchResponse(BaseModel):
    batch_id: str
    stage_id: str
    book_ids: list[str]
    parallel: bool
    status: str
    jobs: dict[str, BatchJobDetail]
    summary: BatchSummary
    created_at: str
    completed_at: str | None = None


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _compute_status(jobs: dict[str, dict[str, Any]]) -> str:
    """Derive overall batch status from individual job statuses."""
    statuses = [j["status"] for j in jobs.values()]
    if any(s in ("running", "queued") for s in statuses):
        return "running"
    if all(s == "completed" for s in statuses):
        return "completed"
    if all(s == "failed" for s in statuses):
        return "failed"
    return "partial"


def _compute_summary(jobs: dict[str, dict[str, Any]]) -> dict[str, int]:
    statuses = [j["status"] for j in jobs.values()]
    return {
        "total": len(statuses),
        "completed": statuses.count("completed"),
        "failed": statuses.count("failed"),
        "running": statuses.count("running"),
        "queued": statuses.count("queued"),
    }


def _evict_oldest() -> None:
    """Remove oldest completed/failed batches when store exceeds _MAX_BATCHES."""
    with _batches_lock:
        if len(_batches) < _MAX_BATCHES:
            return
        evictable = [
            (bid, b["created_at"])
            for bid, b in _batches.items()
            if b["status"] in ("completed", "failed", "partial")
        ]
        evictable.sort(key=lambda x: x[1])
        for bid, _ in evictable[: len(_batches) - _MAX_BATCHES + 1]:
            del _batches[bid]


def _run_single_book(
    batch_id: str,
    book_id: str,
    stage_id: str,
    chapter_id: str | None,
    rerun_completed: bool,
    semaphore: threading.Semaphore | None,
) -> None:
    """Execute one book's stage job and update the batch store."""
    if semaphore is not None:
        semaphore.acquire()
    try:
        # Resolve book root — on failure mark job as failed without raising
        try:
            book_root: Path = resolve_book_root(book_id)
        except Exception as exc:
            with _batches_lock:
                batch = _batches.get(batch_id)
                if batch and book_id in batch["jobs"]:
                    job = batch["jobs"][book_id]
                    job["status"] = "failed"
                    job["error"] = str(exc)
                    job["completed_at"] = _now_iso()
                    _update_batch_status(batch)
            return

        # Mark running
        with _batches_lock:
            batch = _batches.get(batch_id)
            if batch and book_id in batch["jobs"]:
                batch["jobs"][book_id]["status"] = "running"
                batch["jobs"][book_id]["started_at"] = _now_iso()
                _update_batch_status(batch)

        # Import here to avoid circular-import issues at module load time
        from engine_core.stage_api import run_stage  # noqa: PLC0415

        result = run_stage(
            book_id,
            book_root,
            stage_id,
            chapter_id,
            rerun_completed=rerun_completed,
        )

        with _batches_lock:
            batch = _batches.get(batch_id)
            if batch and book_id in batch["jobs"]:
                job = batch["jobs"][book_id]
                job["status"] = "completed"
                job["result"] = result if isinstance(result, dict) else {"raw": str(result)}
                job["completed_at"] = _now_iso()
                _update_batch_status(batch)

    except Exception as exc:
        with _batches_lock:
            batch = _batches.get(batch_id)
            if batch and book_id in batch["jobs"]:
                job = batch["jobs"][book_id]
                job["status"] = "failed"
                job["error"] = str(exc)
                job["completed_at"] = _now_iso()
                _update_batch_status(batch)
    finally:
        if semaphore is not None:
            semaphore.release()


def _update_batch_status(batch: dict[str, Any]) -> None:
    """Recompute and write batch-level status and summary (must be called under _batches_lock)."""
    batch["status"] = _compute_status(batch["jobs"])
    batch["summary"] = _compute_summary(batch["jobs"])
    if batch["status"] in ("completed", "failed", "partial"):
        if batch["completed_at"] is None:
            batch["completed_at"] = _now_iso()


def _run_batch_worker(
    batch_id: str,
    book_ids: list[str],
    stage_id: str,
    chapter_id: str | None,
    rerun_completed: bool,
    parallel: bool,
    max_parallel: int,
) -> None:
    """Top-level batch runner — parallel or sequential."""
    if parallel:
        semaphore = threading.Semaphore(max_parallel)
        threads: list[threading.Thread] = []
        for book_id in book_ids:
            t = threading.Thread(
                target=_run_single_book,
                args=(batch_id, book_id, stage_id, chapter_id, rerun_completed, semaphore),
                daemon=True,
            )
            threads.append(t)
            t.start()
        for t in threads:
            t.join()
    else:
        for book_id in book_ids:
            _run_single_book(
                batch_id, book_id, stage_id, chapter_id, rerun_completed, None
            )


def _batch_to_response(batch: dict[str, Any]) -> dict[str, Any]:
    """Convert internal dict to API response shape."""
    return {
        "batch_id": batch["batch_id"],
        "stage_id": batch["stage_id"],
        "book_ids": batch["book_ids"],
        "parallel": batch["parallel"],
        "status": batch["status"],
        "jobs": batch["jobs"],
        "summary": batch["summary"],
        "created_at": batch["created_at"],
        "completed_at": batch["completed_at"],
    }


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------

@router.post("/run", status_code=202)
def batch_run(req: BatchRunRequest) -> dict[str, Any]:
    """Start a batch stage execution job.

    Launches all book/stage pairs in background threads (parallel) or
    sequentially.  Returns immediately with batch_id and initial status.
    """
    if not req.book_ids:
        raise HTTPException(status_code=400, detail="book_ids must not be empty")

    # Deduplicate while preserving order
    seen: set[str] = set()
    unique_ids: list[str] = []
    for bid in req.book_ids:
        if bid not in seen:
            seen.add(bid)
            unique_ids.append(bid)

    batch_id = f"batch-{uuid.uuid4().hex[:12]}"
    now = _now_iso()

    jobs: dict[str, dict[str, Any]] = {
        book_id: {
            "status": "queued",
            "result": None,
            "error": None,
            "started_at": None,
            "completed_at": None,
        }
        for book_id in unique_ids
    }

    batch: dict[str, Any] = {
        "batch_id": batch_id,
        "stage_id": req.stage_id,
        "book_ids": unique_ids,
        "parallel": req.parallel,
        "status": "queued",
        "jobs": jobs,
        "summary": _compute_summary(jobs),
        "created_at": now,
        "completed_at": None,
    }

    _evict_oldest()
    with _batches_lock:
        _batches[batch_id] = batch

    # Launch background runner
    worker = threading.Thread(
        target=_run_batch_worker,
        args=(
            batch_id,
            unique_ids,
            req.stage_id,
            req.chapter_id,
            req.rerun_completed,
            req.parallel,
            req.max_parallel,
        ),
        daemon=True,
    )
    worker.start()

    with _batches_lock:
        return _batch_to_response(_batches[batch_id])


@router.get("")
def list_batches() -> list[dict[str, Any]]:
    """Return the most recent up-to-20 batches, newest first."""
    with _batches_lock:
        sorted_batches = sorted(
            _batches.values(),
            key=lambda b: b["created_at"],
            reverse=True,
        )
    return [_batch_to_response(b) for b in sorted_batches[:_LIST_LIMIT]]


@router.get("/{batch_id}")
def get_batch(batch_id: str) -> dict[str, Any]:
    """Return current status of a specific batch."""
    with _batches_lock:
        batch = _batches.get(batch_id)
    if batch is None:
        raise HTTPException(status_code=404, detail=f"Batch not found: {batch_id}")
    with _batches_lock:
        return _batch_to_response(batch)


@router.delete("/{batch_id}", status_code=200)
def delete_batch(batch_id: str) -> dict[str, Any]:
    """Remove a completed or failed batch from the store.

    Raises 400 if the batch is still running or queued.
    Raises 404 if the batch does not exist.
    """
    with _batches_lock:
        batch = _batches.get(batch_id)
        if batch is None:
            raise HTTPException(status_code=404, detail=f"Batch not found: {batch_id}")
        if batch["status"] in ("queued", "running"):
            raise HTTPException(
                status_code=400,
                detail=f"Cannot delete batch in status '{batch['status']}'. "
                       "Wait until completed or failed.",
            )
        del _batches[batch_id]

    return {"ok": True, "batch_id": batch_id, "detail": "Batch removed."}
