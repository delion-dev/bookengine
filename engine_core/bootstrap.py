from __future__ import annotations

import re
import shutil
from pathlib import Path
from typing import Any

from .book_state import build_initial_book_db, save_book_db
from .common import ensure_dir, now_iso, read_text, write_json, write_text
from .registry import register_book


STANDARD_DIRS = [
    "_inputs",
    "_master",
    "db",
    "research",
    "research/assets",
    "shared_memory",
    "manuscripts/_raw",
    "manuscripts/_draft1",
    "manuscripts/_draft2",
    "manuscripts/_draft3",
    "manuscripts/_draft4",
    "manuscripts/_draft5",
    "manuscripts/_draft6",
    "publication/metadata",
    "publication/assets",
    "publication/assets/cleared",
    "publication/output",
    "verification",
    "skills/local",
]


def extract_toc_seed(source_text: str) -> str:
    lines = source_text.splitlines()
    start = next((idx for idx, line in enumerate(lines) if line.startswith("## 📂 도서명(가제):")), 0)
    end = next(
        (
            idx
            for idx, line in enumerate(lines[start:], start=start)
            if line.startswith("### 💡 **집필 시 팁")
        ),
        len(lines),
    )
    toc_lines = [line.rstrip() for line in lines[start:end]]
    return "\n".join(toc_lines).strip() + "\n"


def _clean_heading(line: str) -> str:
    cleaned = re.sub(r"\*+", "", line.strip())
    cleaned = re.sub(r"\s+", " ", cleaned).strip()
    return cleaned


def parse_toc_structure(toc_seed: str) -> dict[str, Any]:
    parts: list[dict[str, Any]] = []
    chapters: list[dict[str, Any]] = []
    current_part: str | None = None
    last_chapter: dict[str, Any] | None = None

    for raw_line in toc_seed.splitlines():
        line = raw_line.strip()
        if not line:
            continue
        if line.startswith("### **INTRO:"):
            title = _clean_heading(line.replace("### ", "", 1))
            chapter = {
                "chapter_id": "intro",
                "title": title,
                "part": "INTRO",
                "notes": [],
            }
            chapters.append(chapter)
            last_chapter = chapter
            current_part = "INTRO"
            continue
        if line.startswith("### **PART "):
            current_part = _clean_heading(line.replace("### ", "", 1))
            parts.append({"part_id": current_part, "title": current_part})
            last_chapter = None
            continue
        if line.startswith("### **OUTRO:"):
            title = _clean_heading(line.replace("### ", "", 1))
            chapter = {
                "chapter_id": "outro",
                "title": title,
                "part": "OUTRO",
                "notes": [],
            }
            chapters.append(chapter)
            last_chapter = chapter
            current_part = "OUTRO"
            continue
        if line.startswith("* **") and "." in line:
            text = _clean_heading(line[2:])
            number_end = text.find(".")
            chapter_number = text[:number_end].strip()
            title = text
            chapter = {
                "chapter_id": f"ch{int(chapter_number):02d}",
                "title": title,
                "part": current_part,
                "notes": [],
            }
            chapters.append(chapter)
            last_chapter = chapter
            continue
        if line.startswith("* ") and last_chapter is not None:
            last_chapter["notes"].append(_clean_heading(line[2:]))

    return {"parts": parts, "chapters": chapters}


def initialize_shared_memory(book_id: str, toc_info: dict[str, Any]) -> dict[str, Any]:
    return {
        "global_memory": {
            "engine_version": "1.0",
            "constitution_version": "1.0",
            "registry_snapshot": {},
        },
        "book_memory": {
            "book_id": book_id,
            "core_message": "",
            "reader_persona": "",
            "chapter_dependencies": [],
            "open_questions": [],
        },
        "chapter_memory": [
            {
                "chapter_id": chapter["chapter_id"],
                "summary": "",
                "claims": [],
                "citations_summary": [],
                "unresolved_issues": [],
                "visual_notes": [],
            }
            for chapter in toc_info.get("chapters", [])
        ],
        "run_memory": [],
    }


def scaffold_book(
    book_id: str,
    display_name: str,
    book_root: Path,
    source_file: Path,
) -> dict[str, Any]:
    for directory in STANDARD_DIRS:
        ensure_dir(book_root / directory)

    source_text = read_text(source_file)
    toc_seed = extract_toc_seed(source_text)
    toc_info = parse_toc_structure(toc_seed)

    source_copy = book_root / "_inputs" / "source_original.md"
    proposal_path = book_root / "_inputs" / "proposal.md"
    toc_seed_path = book_root / "_inputs" / "toc_seed.md"
    intake_manifest_path = book_root / "_inputs" / "intake_manifest.json"
    shared_memory_path = book_root / "shared_memory" / "shared_memory.json"
    session_history_path = book_root / "db" / "session_history.jsonl"

    shutil.copyfile(source_file, source_copy)
    write_text(proposal_path, source_text if source_text.endswith("\n") else source_text + "\n")
    write_text(toc_seed_path, toc_seed)

    intake_manifest = {
        "version": "1.0",
        "book_id": book_id,
        "display_name": display_name,
        "book_root": str(book_root),
        "source_file": str(source_file),
        "normalized_at": now_iso(),
        "chapters_detected": toc_info["chapters"],
        "parts_detected": toc_info["parts"],
    }
    write_json(intake_manifest_path, intake_manifest)

    book_db = build_initial_book_db(book_id, display_name, book_root, toc_info)
    save_book_db(book_root, book_db)
    if not session_history_path.exists():
        write_text(session_history_path, "")

    registry = register_book(book_id, display_name, book_root)
    shared_memory = initialize_shared_memory(book_id, toc_info)
    shared_memory["global_memory"]["registry_snapshot"] = registry
    write_json(shared_memory_path, shared_memory)

    return {
        "book_id": book_id,
        "display_name": display_name,
        "book_root": str(book_root),
        "proposal_path": str(proposal_path),
        "toc_seed_path": str(toc_seed_path),
        "intake_manifest_path": str(intake_manifest_path),
        "chapters_detected": len(toc_info["chapters"]),
        "parts_detected": len(toc_info["parts"]),
    }
