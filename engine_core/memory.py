from __future__ import annotations

from pathlib import Path
from typing import Any

from .common import read_json, write_json


def shared_memory_path(book_root: Path) -> Path:
    return book_root / "shared_memory" / "shared_memory.json"


def load_shared_memory(book_root: Path) -> dict[str, Any]:
    payload = read_json(shared_memory_path(book_root), default=None)
    if payload is None:
        raise FileNotFoundError(f"shared_memory.json not found: {shared_memory_path(book_root)}")
    return payload


def save_shared_memory(book_root: Path, payload: dict[str, Any]) -> None:
    write_json(shared_memory_path(book_root), payload)


def update_book_memory(
    book_root: Path,
    *,
    core_message: str | None = None,
    reader_persona: str | None = None,
    chapter_dependencies: list[dict[str, Any]] | None = None,
    open_questions: list[str] | None = None,
) -> dict[str, Any]:
    payload = load_shared_memory(book_root)
    book_memory = payload["book_memory"]
    if core_message is not None:
        book_memory["core_message"] = core_message
    if reader_persona is not None:
        book_memory["reader_persona"] = reader_persona
    if chapter_dependencies is not None:
        book_memory["chapter_dependencies"] = chapter_dependencies
    if open_questions is not None:
        book_memory["open_questions"] = open_questions
    save_shared_memory(book_root, payload)
    return payload


def update_chapter_memory(
    book_root: Path,
    chapter_id: str,
    *,
    summary: str | None = None,
    claims: list[str] | None = None,
    citations_summary: list[str] | None = None,
    unresolved_issues: list[str] | None = None,
    visual_notes: list[str] | None = None,
) -> dict[str, Any]:
    payload = load_shared_memory(book_root)
    chapter_memory = next(
        (item for item in payload["chapter_memory"] if item["chapter_id"] == chapter_id),
        None,
    )
    if chapter_memory is None:
        raise KeyError(f"Unknown chapter_id in shared memory: {chapter_id}")
    if summary is not None:
        chapter_memory["summary"] = summary
    if claims is not None:
        chapter_memory["claims"] = claims
    if citations_summary is not None:
        chapter_memory["citations_summary"] = citations_summary
    if unresolved_issues is not None:
        chapter_memory["unresolved_issues"] = unresolved_issues
    if visual_notes is not None:
        chapter_memory["visual_notes"] = visual_notes
    save_shared_memory(book_root, payload)
    return payload
