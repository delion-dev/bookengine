from __future__ import annotations

from pathlib import Path
from typing import Any

from .common import now_iso, write_json


SECTION_ORDER = ("hook", "context", "insight", "takeaway")
SECTION_HEADINGS = {
    "hook": "Hook",
    "context": "Context",
    "insight": "Insight",
    "takeaway": "Takeaway",
}
STAGE_NODE_FILENAMES = {
    "S4": "{chapter_id}_node_manifest.json",
    "S5": "{chapter_id}_review_nodes.json",
    "S8A": "{chapter_id}_amplification_nodes.json",
}
STAGE_NODE_DIRS = {
    "S4": ("manuscripts", "_draft1"),
    "S5": ("manuscripts", "_draft2"),
    "S8A": ("manuscripts", "_draft6"),
}


def build_section_nodes(
    stage_id: str,
    chapter_id: str,
    chapter_title: str,
    *,
    section_targets: dict[str, int] | None = None,
    research_questions: list[str] | None = None,
    source_types: list[str] | None = None,
) -> list[dict[str, Any]]:
    nodes: list[dict[str, Any]] = []
    for sequence, section_key in enumerate(SECTION_ORDER, start=1):
        nodes.append(
            {
                "node_id": f"{stage_id}:{chapter_id}:{section_key}",
                "stage_id": stage_id,
                "chapter_id": chapter_id,
                "chapter_title": chapter_title,
                "sequence": sequence,
                "node_type": "subsection",
                "section_key": section_key,
                "section_heading": SECTION_HEADINGS[section_key],
                "target_words": (section_targets or {}).get(section_key),
                "research_questions": list(research_questions or []),
                "source_types": list(source_types or []),
                "status": "pending",
                "updated_at": now_iso(),
                "note": "",
            }
        )
    return nodes


def build_block_nodes(
    stage_id: str,
    chapter_id: str,
    chapter_title: str,
    targets: list[dict[str, str]],
) -> list[dict[str, Any]]:
    nodes: list[dict[str, Any]] = []
    for sequence, target in enumerate(targets, start=1):
        nodes.append(
            {
                "node_id": f"{stage_id}:{chapter_id}:{target['block_id']}",
                "stage_id": stage_id,
                "chapter_id": chapter_id,
                "chapter_title": chapter_title,
                "sequence": sequence,
                "node_type": "rewrite_block",
                "section_key": target["section"].lower(),
                "section_heading": target["section"],
                "block_id": target["block_id"],
                "source_text": target["text"],
                "status": "pending",
                "updated_at": now_iso(),
                "note": "",
            }
        )
    return nodes


def node_manifest_path(book_root: Path, stage_id: str, chapter_id: str) -> Path:
    relative_dir = STAGE_NODE_DIRS[stage_id]
    filename = STAGE_NODE_FILENAMES[stage_id].format(chapter_id=chapter_id)
    return book_root.joinpath(*relative_dir, filename)


def write_node_manifest(
    book_root: Path,
    stage_id: str,
    chapter_id: str,
    payload: dict[str, Any],
) -> Path:
    path = node_manifest_path(book_root, stage_id, chapter_id)
    write_json(path, payload)
    return path
