from __future__ import annotations

"""engine.gate — Gate evaluation and refresh endpoints."""

from fastapi import APIRouter, HTTPException

from engine_core.gates import evaluate_gate, get_gate_definition, load_gate_definitions
from engine_core.stage import transition_stage
from engine_core.book_state import load_book_db
from engine_core.contracts import get_stage_definition
from ..deps import resolve_book_root

router = APIRouter(prefix="/engine/gate", tags=["gate"])


@router.get("/definitions")
def list_gate_definitions():
    """List all gate definitions."""
    return load_gate_definitions()


@router.get("/definitions/{gate_id}")
def get_gate(gate_id: str):
    """Get a specific gate definition."""
    try:
        return get_gate_definition(gate_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc))


@router.post("/evaluate")
def evaluate(book_id: str, stage_id: str, chapter_id: str | None = None):
    """Evaluate the gate for a completed stage."""
    book_root = resolve_book_root(book_id)
    try:
        return evaluate_gate(book_id, book_root, stage_id, chapter_id)
    except (KeyError, ValueError) as exc:
        raise HTTPException(status_code=400, detail=str(exc))


@router.post("/refresh")
def refresh_gates(book_id: str, stage_id: str, chapter_id: str | None = None):
    """Re-evaluate gate from existing outputs and update stage status accordingly."""
    book_root = resolve_book_root(book_id)
    book_db = load_book_db(book_root)

    # Determine chapters to refresh
    stage_def = get_stage_definition(stage_id)
    uses_chapter = any(
        "{chapter_id}" in t
        for t in [*stage_def.get("input", []), *stage_def.get("output", [])]
    )
    if uses_chapter:
        chapters = [chapter_id] if chapter_id else list(book_db.get("chapter_sequence", []))
    else:
        chapters = [None]

    results = []
    for cid in chapters:
        gate_result = evaluate_gate(book_id, book_root, stage_id, cid)
        new_status = "completed" if gate_result["passed"] else "gate_failed"
        try:
            transition_stage(book_root, stage_id, new_status, cid, "Gate refreshed via API.")
        except Exception:
            pass
        results.append({"chapter_id": cid, "passed": gate_result["passed"], "status": new_status})

    return {"stage_id": stage_id, "refreshed": len(results), "results": results}
