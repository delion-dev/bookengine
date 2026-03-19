from __future__ import annotations

"""FastAPI dependency providers for book context resolution."""

import sys
from pathlib import Path
from typing import Annotated

from fastapi import Header, HTTPException, Query

# Ensure repo root is on sys.path when imported from platform/api/
_REPO_ROOT = Path(__file__).resolve().parent.parent.parent
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from engine_core.registry import get_registry


def resolve_book_root(book_id: str) -> Path:
    """Resolve book_root from registry given book_id. Raises 404 if unknown."""
    registry = get_registry()
    books = registry.get("books", {})
    entry = books.get(book_id) if isinstance(books, dict) else None
    if not entry:
        raise HTTPException(status_code=404, detail=f"Unknown book_id: {book_id}")
    root = Path(entry["book_root"])
    if not root.exists():
        raise HTTPException(status_code=503, detail=f"book_root not accessible: {root}")
    return root


def book_context(
    book_id: str = Query(..., description="Registered book identifier"),
) -> tuple[str, Path]:
    """FastAPI dependency: returns (book_id, book_root) for any book-scoped request."""
    book_root = resolve_book_root(book_id)
    return book_id, book_root


BookContext = Annotated[tuple[str, Path], book_context]
