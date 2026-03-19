from __future__ import annotations

from pathlib import Path
from typing import Any

from .common import now_iso, read_json, write_json


BOOK_STAGE_SEQUENCE = ["S-1", "S0", "S1", "S2", "SQA", "S9"]
CHAPTER_STAGE_SEQUENCE = ["S3", "S4", "S4A", "S5", "S6", "S6A", "S6B", "S7", "S8", "S8A"]
VALID_STATUSES = {
    "not_started",
    "pending",
    "in_progress",
    "completed",
    "gate_failed",
    "blocked",
}


def build_initial_book_db(
    book_id: str,
    display_name: str,
    book_root: Path,
    toc_info: dict[str, Any],
) -> dict[str, Any]:
    book_level_stages: dict[str, Any] = {}
    for stage_id in BOOK_STAGE_SEQUENCE:
        status = "not_started"
        note = ""
        if stage_id == "S-1":
            status = "completed"
            note = "Input normalization completed during bootstrap."
        elif stage_id == "S0":
            status = "pending"
            note = "Ready for AG-AR architecture."
        else:
            status = "blocked"
            note = "Waiting for upstream stage."
        book_level_stages[stage_id] = {
            "status": status,
            "updated_at": now_iso(),
            "note": note,
        }

    chapters: dict[str, Any] = {}
    for chapter in toc_info.get("chapters", []):
        chapters[chapter["chapter_id"]] = {
            "title": chapter["title"],
            "part": chapter.get("part"),
            "notes": chapter.get("notes", []),
            "stages": {
                stage_id: {
                    "status": "blocked",
                    "updated_at": now_iso(),
                    "note": "Waiting for upstream stage.",
                }
                for stage_id in CHAPTER_STAGE_SEQUENCE
            },
        }

    return {
        "engine_version": "1.0",
        "book": {
            "book_id": book_id,
            "display_name": display_name,
            "book_root": str(book_root),
            "status": "bootstrapped",
            "created_at": now_iso(),
        },
        "book_level_stages": book_level_stages,
        "chapters": chapters,
        "chapter_sequence": [chapter["chapter_id"] for chapter in toc_info.get("chapters", [])],
    }


def _default_inserted_stage(previous_completed: bool) -> dict[str, Any]:
    status = "pending" if previous_completed else "blocked"
    note = (
        "Inserted by engine migration and ready for execution."
        if previous_completed
        else "Waiting for upstream stage."
    )
    return {
        "status": status,
        "updated_at": now_iso(),
        "note": note,
    }


def _reconcile_stage_structure(payload: dict[str, Any]) -> bool:
    changed = False

    for stage_id in BOOK_STAGE_SEQUENCE:
        if stage_id in payload.get("book_level_stages", {}):
            continue
        previous_completed = False
        idx = BOOK_STAGE_SEQUENCE.index(stage_id)
        if idx > 0:
            previous_stage = BOOK_STAGE_SEQUENCE[idx - 1]
            previous_completed = payload["book_level_stages"].get(previous_stage, {}).get("status") == "completed"
        payload.setdefault("book_level_stages", {})[stage_id] = _default_inserted_stage(previous_completed)
        changed = True

    for chapter in payload.get("chapters", {}).values():
        stages = chapter.setdefault("stages", {})
        for stage_id in CHAPTER_STAGE_SEQUENCE:
            if stage_id in stages:
                continue
            previous_completed = False
            idx = CHAPTER_STAGE_SEQUENCE.index(stage_id)
            if idx > 0:
                previous_stage = CHAPTER_STAGE_SEQUENCE[idx - 1]
                previous_completed = stages.get(previous_stage, {}).get("status") == "completed"
            stages[stage_id] = _default_inserted_stage(previous_completed)
            changed = True

    return changed


def book_db_path(book_root: Path) -> Path:
    return book_root / "db" / "book_db.json"


def load_book_db(book_root: Path) -> dict[str, Any]:
    data = read_json(book_db_path(book_root), default=None)
    if data is None:
        raise FileNotFoundError(f"book_db.json not found: {book_db_path(book_root)}")
    if _reconcile_stage_structure(data):
        save_book_db(book_root, data)
    return data


def save_book_db(book_root: Path, payload: dict[str, Any]) -> None:
    write_json(book_db_path(book_root), payload)


def set_stage_status(
    book_root: Path,
    stage_id: str,
    status: str,
    chapter_id: str | None = None,
    note: str = "",
) -> dict[str, Any]:
    if status not in VALID_STATUSES:
        raise ValueError(f"Unsupported status: {status}")

    payload = load_book_db(book_root)
    target = (
        payload["book_level_stages"][stage_id]
        if chapter_id is None
        else payload["chapters"][chapter_id]["stages"][stage_id]
    )
    target["status"] = status
    target["updated_at"] = now_iso()
    if note:
        target["note"] = note
    save_book_db(book_root, payload)
    return payload
