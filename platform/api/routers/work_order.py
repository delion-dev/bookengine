from __future__ import annotations

"""engine.work_order — Pipeline orchestration and work order endpoints."""

from fastapi import APIRouter, HTTPException

from engine_core.work_order import issue_work_order
from engine_core.telemetry import build_runtime_telemetry_dashboard
from ..deps import resolve_book_root

router = APIRouter(prefix="/engine/work-order", tags=["work_order"])


@router.post("/issue")
def issue(book_id: str):
    """Issue (or refresh) the work order for the current pipeline state."""
    book_root = resolve_book_root(book_id)
    try:
        return issue_work_order(book_id, book_root)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))


@router.get("/telemetry")
def get_telemetry(book_id: str):
    """Build and return the runtime telemetry dashboard."""
    book_root = resolve_book_root(book_id)
    try:
        return build_runtime_telemetry_dashboard(book_id, book_root)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))
