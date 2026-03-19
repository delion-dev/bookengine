from __future__ import annotations

"""engine.healing — ASHL self-healing endpoints."""

from fastapi import APIRouter, HTTPException

from engine_core.self_healing import get_healing_log, healing_status, scan_and_heal
from ..deps import resolve_book_root
from ..models import HealRequest

router = APIRouter(prefix="/engine/healing", tags=["healing"])


@router.get("/status")
def get_status(book_id: str):
    """Return pipeline health summary (completion rate, gate failures)."""
    book_root = resolve_book_root(book_id)
    try:
        return healing_status(book_root)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))


@router.post("/scan")
def scan(req: HealRequest):
    """Scan gate failures and apply/propose remedies. Use dry_run=true for preview."""
    book_root = resolve_book_root(req.book_id)
    try:
        return scan_and_heal(req.book_id, book_root, dry_run=req.dry_run)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))


@router.get("/log")
def get_log(book_id: str, limit: int = 50):
    """Return the last N healing log entries."""
    book_root = resolve_book_root(book_id)
    return {"entries": get_healing_log(book_root, limit=limit)}
