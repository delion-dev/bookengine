from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from .book_state import load_book_db
from .common import new_id, now_iso, read_json, write_json
from .registry import get_registry, save_registry


def _shared_memory_path(book_root: Path) -> Path:
    return book_root / "shared_memory" / "shared_memory.json"


def _session_history_path(book_root: Path) -> Path:
    return book_root / "db" / "session_history.jsonl"


def open_session(
    book_id: str,
    agent_id: str,
    book_root: Path,
    stage_id: str = "",
) -> dict[str, Any]:
    session_id = new_id("session")
    shared_memory = read_json(_shared_memory_path(book_root), default=None)
    if shared_memory is None:
        raise FileNotFoundError(f"shared memory missing: {_shared_memory_path(book_root)}")

    entry = {
        "session_id": session_id,
        "agent_id": agent_id,
        "stage_id": stage_id,
        "notes": [f"Session opened for {book_id}."],
        "updated_at": now_iso(),
    }
    shared_memory["run_memory"].append(entry)
    write_json(_shared_memory_path(book_root), shared_memory)

    with _session_history_path(book_root).open("a", encoding="utf-8") as handle:
        handle.write(json.dumps({"event": "open", **entry}, ensure_ascii=False) + "\n")

    registry = get_registry()
    if book_id in registry["books"]:
        registry["books"][book_id]["last_session"] = now_iso()
        save_registry(registry)

    return {
        "session_id": session_id,
        "book_id": book_id,
        "agent_id": agent_id,
        "stage_id": stage_id,
        "opened_at": entry["updated_at"],
        "book_status": load_book_db(book_root)["book"]["status"],
    }


def close_session(book_root: Path, session_id: str, memo: str) -> dict[str, Any]:
    shared_memory = read_json(_shared_memory_path(book_root), default=None)
    if shared_memory is None:
        raise FileNotFoundError(f"shared memory missing: {_shared_memory_path(book_root)}")

    updated = False
    for entry in shared_memory["run_memory"]:
        if entry["session_id"] == session_id:
            entry["notes"].append(memo)
            entry["updated_at"] = now_iso()
            updated = True
            close_entry = entry
            break
    if not updated:
        raise KeyError(f"Unknown session_id: {session_id}")

    write_json(_shared_memory_path(book_root), shared_memory)
    with _session_history_path(book_root).open("a", encoding="utf-8") as handle:
        handle.write(json.dumps({"event": "close", **close_entry}, ensure_ascii=False) + "\n")

    return {
        "session_id": session_id,
        "closed_at": close_entry["updated_at"],
        "memo": memo,
    }
