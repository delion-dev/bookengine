from __future__ import annotations

from pathlib import Path
from typing import Any

from .common import RUNTIME_REGISTRY_PATH, now_iso, read_json, write_json


def get_registry() -> dict[str, Any]:
    registry = read_json(RUNTIME_REGISTRY_PATH, default=None)
    if registry is None:
        registry = {
            "version": "1.0",
            "updated_at": now_iso(),
            "books": {},
        }
    return registry


def save_registry(registry: dict[str, Any]) -> None:
    registry["updated_at"] = now_iso()
    write_json(RUNTIME_REGISTRY_PATH, registry)


def register_book(book_id: str, display_name: str, book_root: Path) -> dict[str, Any]:
    registry = get_registry()
    registry["books"][book_id] = {
        "book_id": book_id,
        "display_name": display_name,
        "book_root": str(book_root),
        "status": "bootstrapped",
        "last_session": None,
    }
    save_registry(registry)
    return registry
