from __future__ import annotations

from pathlib import Path
from typing import Any

from .common import (
    STAGE_DEFINITIONS_PATH,
    append_jsonl,
    new_id,
    now_iso,
    read_json,
    render_template_path,
)


def load_stage_definitions() -> dict[str, Any]:
    data = read_json(STAGE_DEFINITIONS_PATH, default=None)
    if data is None:
        raise FileNotFoundError(f"Missing stage definitions: {STAGE_DEFINITIONS_PATH}")
    return data


def get_stage_definition(stage_id: str) -> dict[str, Any]:
    for stage in load_stage_definitions()["stages"]:
        if stage["id"] == stage_id:
            return stage
    raise KeyError(f"Unknown stage_id: {stage_id}")


def resolve_stage_contract(
    book_id: str,
    book_root: Path,
    stage_id: str,
    chapter_id: str | None = None,
) -> dict[str, Any]:
    stage = get_stage_definition(stage_id)
    templates = [*stage.get("input", []), *stage.get("output", [])]
    if chapter_id is None and any("{chapter_id}" in template for template in templates):
        raise ValueError(f"stage_id {stage_id} requires chapter_id")
    inputs = [
        str(render_template_path(template, book_root, book_id, chapter_id))
        for template in stage.get("input", [])
    ]
    outputs = [
        str(render_template_path(template, book_root, book_id, chapter_id))
        for template in stage.get("output", [])
    ]
    return {
        "stage_id": stage["id"],
        "name": stage["name"],
        "agent": stage["agent"],
        "inputs": inputs,
        "outputs": outputs,
        "gate": stage["gate"],
    }


def validate_inputs(
    book_id: str,
    book_root: Path,
    stage_id: str,
    chapter_id: str | None = None,
) -> dict[str, Any]:
    contract = resolve_stage_contract(book_id, book_root, stage_id, chapter_id)
    existing = []
    missing = []
    for path_str in contract["inputs"]:
        path = Path(path_str)
        if path.exists():
            existing.append(path_str)
        else:
            missing.append(path_str)
    return {
        "stage_id": stage_id,
        "chapter_id": chapter_id,
        "existing_inputs": existing,
        "missing_inputs": missing,
        "valid": not missing,
    }


def artifact_registry_path(book_root: Path) -> Path:
    return book_root / "db" / "artifact_registry.jsonl"


def register_output(
    book_id: str,
    book_root: Path,
    stage_id: str,
    artifact_path: str | Path,
    chapter_id: str | None = None,
) -> dict[str, Any]:
    artifact = Path(artifact_path)
    exists = artifact.exists()
    ack = {
        "ack_id": new_id("artifact"),
        "book_id": book_id,
        "stage_id": stage_id,
        "chapter_id": chapter_id,
        "artifact_path": str(artifact),
        "exists": exists,
        "registered_at": now_iso(),
    }
    if exists:
        ack["size_bytes"] = artifact.stat().st_size
    append_jsonl(artifact_registry_path(book_root), ack)
    return ack


def register_stage_outputs(
    book_id: str,
    book_root: Path,
    stage_id: str,
    chapter_id: str | None = None,
) -> dict[str, Any]:
    contract = resolve_stage_contract(book_id, book_root, stage_id, chapter_id)
    registered_outputs = [
        register_output(book_id, book_root, stage_id, output_path, chapter_id)
        for output_path in contract["outputs"]
    ]
    return {
        "stage_id": stage_id,
        "chapter_id": chapter_id,
        "registered_outputs": registered_outputs,
    }
