from __future__ import annotations

import json
import re
import uuid
from datetime import datetime
from pathlib import Path
from typing import Any


REPO_ROOT = Path(__file__).resolve().parent.parent
PLATFORM_CORE_ROOT = REPO_ROOT / "platform" / "core_engine"
STAGE_DEFINITIONS_PATH = PLATFORM_CORE_ROOT / "stage_definitions.json"
GATE_DEFINITIONS_PATH = PLATFORM_CORE_ROOT / "gate_definitions.json"
RUNTIME_REGISTRY_PATH = PLATFORM_CORE_ROOT / "runtime_registry.json"
POSTPROCESS_RULE_CANDIDATES_PATH = PLATFORM_CORE_ROOT / "postprocess_rule_candidates.json"


def now_iso() -> str:
    return datetime.now().astimezone().isoformat(timespec="seconds")


def new_id(prefix: str) -> str:
    return f"{prefix}-{uuid.uuid4().hex[:12]}"


def ensure_dir(path: Path) -> Path:
    path.mkdir(parents=True, exist_ok=True)
    return path


def read_text(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def write_text(path: Path, content: str) -> None:
    ensure_dir(path.parent)
    path.write_text(content, encoding="utf-8")


def read_json(path: Path, default: Any | None = None) -> Any:
    if not path.exists():
        return default
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path: Path, payload: Any) -> None:
    ensure_dir(path.parent)
    path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


def append_jsonl(path: Path, payload: Any) -> None:
    ensure_dir(path.parent)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(payload, ensure_ascii=False) + "\n")


def count_words(text: str) -> int:
    normalized = re.sub(r"<!--.*?-->", " ", text, flags=re.DOTALL)
    normalized = re.sub(r"\[ANCHOR_SLOT:[^\]]+\]", " ", normalized)
    normalized = re.sub(r"[#*_`>|-]+", " ", normalized)
    return len(re.findall(r"\S+", normalized))


def slugify(value: str) -> str:
    value = value.strip().lower()
    value = re.sub(r"[^a-z0-9]+", "_", value)
    value = re.sub(r"_+", "_", value).strip("_")
    return value


def render_template_path(
    template: str,
    book_root: Path,
    book_id: str,
    chapter_id: str | None = None,
) -> Path:
    rendered = template.format(book_id=book_id, chapter_id=chapter_id or "")
    return book_root / rendered.replace("/", str(Path("/")))
