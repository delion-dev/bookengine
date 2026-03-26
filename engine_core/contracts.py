from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Any

from .common import (
    PLATFORM_CORE_ROOT,
    STAGE_DEFINITIONS_PATH,
    append_jsonl,
    new_id,
    now_iso,
    read_json,
    render_template_path,
)

_OUTPUT_NAMES_FILE = PLATFORM_CORE_ROOT / "stage_output_names.json"


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


@lru_cache(maxsize=1)
def _load_output_names() -> dict[str, list[str]]:
    """Load {stage_id: [name, ...]} from stage_output_names.json. Cached in process."""
    payload = read_json(_OUTPUT_NAMES_FILE, default={}) or {}
    return payload.get("stages", {})


def _build_output_map(stage_id: str, output_paths: list[str]) -> dict[str, str]:
    """Build {name: resolved_path} for a stage's outputs.

    Falls back to positional keys ("output_0", "output_1", ...) when
    stage_output_names.json has no entry for this stage.
    """
    names = _load_output_names().get(stage_id, [])
    if not names:
        return {f"output_{i}": path for i, path in enumerate(output_paths)}
    # Zip — if counts differ, the shorter side wins (extra outputs get fallback keys)
    result: dict[str, str] = {}
    for i, path in enumerate(output_paths):
        key = names[i] if i < len(names) else f"output_{i}"
        result[key] = path
    return result


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
    output_map = _build_output_map(stage_id, outputs)
    return {
        "stage_id": stage["id"],
        "name": stage["name"],
        "agent": stage["agent"],
        "inputs": inputs,
        "outputs": outputs,
        "output_map": output_map,   # ← named-key access (replaces fragile index lookups)
        "gate": stage["gate"],
    }


def get_stage_output(
    book_id: str,
    book_root: Path,
    stage_id: str,
    key: str,
    chapter_id: str | None = None,
) -> str:
    """Return the resolved file path for a named output slot.

    Example:
        path = get_stage_output(book_id, book_root, "S4", "draft1_prose", chapter_id)

    Raises KeyError if the key is not defined for this stage.
    """
    contract = resolve_stage_contract(book_id, book_root, stage_id, chapter_id)
    output_map = contract["output_map"]
    if key not in output_map:
        available = list(output_map.keys())
        raise KeyError(
            f"Output key '{key}' not found for stage '{stage_id}'. "
            f"Available: {available}"
        )
    return output_map[key]


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
