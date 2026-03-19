from __future__ import annotations

from pathlib import Path
from typing import Any

from .book_state import VALID_STATUSES, load_book_db, save_book_db
from .common import now_iso


ALLOWED_TRANSITIONS = {
    ("not_started", "pending"),
    ("pending", "in_progress"),
    ("in_progress", "completed"),
    ("in_progress", "gate_failed"),
    ("gate_failed", "pending"),
    ("pending", "blocked"),
    ("blocked", "pending"),
    ("completed", "in_progress"),
    ("completed", "gate_failed"),
}


def _target_stage(payload: dict[str, Any], stage_id: str, chapter_id: str | None = None) -> dict[str, Any]:
    if chapter_id is None:
        return payload["book_level_stages"][stage_id]
    return payload["chapters"][chapter_id]["stages"][stage_id]


def transition_stage(
    book_root: Path,
    stage_id: str,
    to_status: str,
    chapter_id: str | None = None,
    note: str = "",
) -> dict[str, Any]:
    if to_status not in VALID_STATUSES:
        raise ValueError(f"Unsupported status: {to_status}")

    payload = load_book_db(book_root)
    target = _target_stage(payload, stage_id, chapter_id)
    from_status = target["status"]

    if from_status == to_status:
        target["updated_at"] = now_iso()
        if note:
            target["note"] = note
        save_book_db(book_root, payload)
        return {
            "stage_id": stage_id,
            "chapter_id": chapter_id,
            "from_status": from_status,
            "to_status": to_status,
            "updated_at": target["updated_at"],
            "note": target.get("note", ""),
        }

    if (from_status, to_status) not in ALLOWED_TRANSITIONS:
        raise ValueError(f"Invalid transition: {from_status} -> {to_status}")

    target["status"] = to_status
    target["updated_at"] = now_iso()
    if note:
        target["note"] = note
    save_book_db(book_root, payload)
    return {
        "stage_id": stage_id,
        "chapter_id": chapter_id,
        "from_status": from_status,
        "to_status": to_status,
        "updated_at": target["updated_at"],
        "note": target.get("note", ""),
    }
