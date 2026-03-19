from __future__ import annotations

"""engine.registry — Book registry endpoints."""

from fastapi import APIRouter

from engine_core.registry import get_registry
from engine_core.book_state import load_book_db
from ..deps import resolve_book_root

router = APIRouter(prefix="/engine/registry", tags=["registry"])


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
    entry = next((b for b in registry.get("books", []) if b["book_id"] == book_id), {})
    return {
        "registry_entry": entry,
        "book": book_db["book"],
        "chapter_count": len(book_db.get("chapter_sequence", [])),
        "book_level_stages": book_db.get("book_level_stages", {}),
    }
