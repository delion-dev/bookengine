from __future__ import annotations

"""engine.registry — Book registry endpoints."""

from pathlib import Path

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from engine_core.registry import get_registry
from engine_core.book_state import load_book_db
from engine_core.bootstrap import scaffold_book
from engine_api.deps import resolve_book_root

router = APIRouter(prefix="/engine/registry", tags=["registry"])


class BootstrapRequest(BaseModel):
    book_id: str
    display_name: str
    book_root: str
    source_file: str


@router.post("/books")
def bootstrap_book(req: BootstrapRequest):
    """Bootstrap a new book and register it."""
    book_root = Path(req.book_root)
    source_file = Path(req.source_file)
    if not source_file.exists():
        raise HTTPException(status_code=400, detail=f"source_file not found: {source_file}")
    result = scaffold_book(
        book_id=req.book_id,
        display_name=req.display_name,
        book_root=book_root,
        source_file=source_file,
    )
    return {"ok": True, "book_id": req.book_id, "result": result}


@router.get("/books")
def list_books():
    """List all registered books."""
    return get_registry()


@router.get("/books/{book_id}")
def get_book(book_id: str):
    """Get book identity and pipeline status summary."""
    book_root = resolve_book_root(book_id)
    book_db = load_book_db(book_root)
    registry = get_registry()
    entry = registry.get("books", {}).get(book_id, {})
    return {
        "registry_entry": entry,
        "book": book_db["book"],
        "chapter_count": len(book_db.get("chapter_sequence", [])),
        "book_level_stages": book_db.get("book_level_stages", {}),
    }
