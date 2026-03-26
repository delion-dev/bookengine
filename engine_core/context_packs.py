from __future__ import annotations

import json
import math
import re
from functools import lru_cache
from pathlib import Path
from typing import Any

from .book_state import load_book_db
from .common import PLATFORM_CORE_ROOT, ensure_dir, now_iso, read_json, read_text, slugify, write_json
from .constitution_parser import get_constitution_rules
from .memory import load_shared_memory
from .targets import get_chapter_target


CONTEXT_PACK_VERSION = "1.0"
_MARKDOWN_H2_PATTERN = re.compile(r"(?m)^## ([^\n]+)\s*$")

# ---------------------------------------------------------------------------
# Stage Execution Policies — loaded from stage_execution_policies.json
# Fallback values are used only when the JSON file is unavailable.
# ---------------------------------------------------------------------------

_POLICY_FILE = PLATFORM_CORE_ROOT / "stage_execution_policies.json"

_FALLBACK_TOKEN_BUDGET = {"soft_max_input_tokens": 5500, "soft_max_output_tokens": 2800}
_FALLBACK_POLICY = {
    "task_family": "generic_stage_execution",
    "preferred_model_route": "engine.stage.run",
    "node_strategy": "stage_default",
    "global_characteristics": [
        "Follow artifact contracts and gate checks.",
        "Use distilled context instead of full source documents when possible.",
    ],
    "local_characteristics": [
        "Book-local rules may refine content, not engine policy.",
    ],
}


@lru_cache(maxsize=1)
def _load_stage_execution_policies() -> dict[str, Any]:
    """Load stage_execution_policies.json once, cache in process."""
    return read_json(_POLICY_FILE, default={}) or {}


def _get_stage_policy(stage_id: str) -> dict[str, Any]:
    """Return execution policy for a stage, falling back to generic defaults."""
    stages = _load_stage_execution_policies().get("stages", {})
    entry = stages.get(stage_id, {})
    if not entry:
        return dict(_FALLBACK_POLICY)
    # Return only policy keys (exclude token_budget and execution_limits)
    policy = {k: v for k, v in entry.items() if k not in ("token_budget", "execution_limits")}
    # Ensure required keys exist
    for key in ("task_family", "preferred_model_route", "node_strategy",
                "global_characteristics", "local_characteristics"):
        if key not in policy:
            policy[key] = _FALLBACK_POLICY.get(key, "")
    return policy


def _get_token_budget(stage_id: str) -> dict[str, Any]:
    """Return token budget for a stage, falling back to conservative defaults."""
    stages = _load_stage_execution_policies().get("stages", {})
    entry = stages.get(stage_id, {})
    return entry.get("token_budget") or dict(
        _load_stage_execution_policies().get("default_token_budget") or _FALLBACK_TOKEN_BUDGET
    )


def reload_stage_policies() -> None:
    """Clear policy cache — call when stage_execution_policies.json changes."""
    _load_stage_execution_policies.cache_clear()


def _context_pack_root(book_root: Path) -> Path:
    return ensure_dir(book_root / "shared_memory" / "context_packs")


def _save_pack(book_root: Path, scope: str, name: str, payload: dict[str, Any]) -> Path:
    path = _context_pack_root(book_root) / scope / name
    write_json(path, payload)
    return path


def _load_stage_definition(stage_id: str) -> dict[str, Any]:
    payload = read_json(PLATFORM_CORE_ROOT / "stage_definitions.json", default={}) or {}
    for stage in payload.get("stages", []):
        if stage.get("id") == stage_id:
            return stage
    raise KeyError(f"Unknown stage definition: {stage_id}")


def _load_gate_definition(gate_id: str) -> dict[str, Any]:
    payload = read_json(PLATFORM_CORE_ROOT / "gate_definitions.json", default={}) or {}
    for gate in payload.get("gates", []):
        if gate.get("gate_id") == gate_id or gate.get("id") == gate_id:
            return gate
    raise KeyError(f"Unknown gate definition: {gate_id}")


def _markdown_sections(text: str) -> dict[str, str]:
    matches = list(_MARKDOWN_H2_PATTERN.finditer(text))
    if not matches:
        return {}
    sections: dict[str, str] = {}
    for index, match in enumerate(matches):
        heading = match.group(1).strip()
        start = match.end()
        end = matches[index + 1].start() if index + 1 < len(matches) else len(text)
        sections[heading] = text[start:end].strip()
    return sections


def _bullet_lines(section_text: str, max_items: int = 6) -> list[str]:
    lines = []
    for raw_line in section_text.splitlines():
        line = raw_line.strip()
        if line.startswith("- "):
            lines.append(line[2:].strip())
        if len(lines) >= max_items:
            break
    return lines


def _first_paragraph(section_text: str, max_chars: int = 400) -> str:
    for paragraph in re.split(r"\n{2,}", section_text.strip()):
        stripped = paragraph.strip()
        if stripped:
            return stripped[:max_chars]
    return ""


def _compact_text(value: Any, max_chars: int = 600) -> str:
    if value is None:
        return ""
    text = value if isinstance(value, str) else json.dumps(value, ensure_ascii=False, indent=2)
    compact = re.sub(r"\s+", " ", text).strip()
    return compact[:max_chars]


def _approx_token_count(text: str, lang: str = "auto") -> int:
    """Estimate token count with language-aware character ratios.

    Ratios (chars per token):
      Korean (ko): ~2.0  — CJK characters encode densely but count as ~1 token each
      English (en): ~4.0 — English words average ~1.3 tokens but characters are wider
      auto: detect dominant script and apply weighted average
    """
    if not text:
        return 0
    if lang == "ko":
        ratio = 2.0
    elif lang == "en":
        ratio = 4.0
    else:
        # Auto: count CJK codepoints and apply weighted blend
        cjk_chars = sum(1 for ch in text if "\uAC00" <= ch <= "\uD7A3" or "\u4E00" <= ch <= "\u9FFF")
        cjk_ratio = cjk_chars / max(len(text), 1)
        # Blend: cjk_ratio × 2.0 + (1 - cjk_ratio) × 4.0
        ratio = cjk_ratio * 2.0 + (1.0 - cjk_ratio) * 4.0
    return max(1, math.ceil(len(text) / ratio))


def build_policy_pack(book_root: Path, stage_id: str) -> dict[str, Any]:
    stage_definition = _load_stage_definition(stage_id)
    gate_definition = _load_gate_definition(stage_definition["gate"])
    stage_policy = _get_stage_policy(stage_id)
    token_budget = _get_token_budget(stage_id)
    payload = {
        "version": CONTEXT_PACK_VERSION,
        "pack_type": "policy_pack",
        "scope": "global",
        "owner": "core_engine",
        "mutable": False,
        "generated_at": now_iso(),
        "stage_id": stage_id,
        "immutable_sources": [
            "platform/core_engine/CONSTITUTION.md",
            "platform/core_engine/PROJECT_SOP.md",
            "platform/core_engine/stage_definitions.json",
            "platform/core_engine/stage_execution_policies.json",
            "platform/core_engine/gate_definitions.json",
        ],
        "constitution_rules": get_constitution_rules(stage_id),
        "execution_contract": {
            "stage_name": stage_definition["name"],
            "agent": stage_definition["agent"],
            "gate": stage_definition["gate"],
            "declared_inputs": stage_definition.get("input", []),
            "declared_outputs": stage_definition.get("output", []),
        },
        "gate_summary": {
            "gate_id": gate_definition.get("gate_id") or gate_definition.get("id"),
            "required_checks": [
                check["check"] if isinstance(check, dict) else check
                for check in gate_definition.get("checks", [])
            ],
            "on_fail": gate_definition.get("on_fail", {}),
        },
        "stage_policy": {
            **stage_policy,
            "token_budget": token_budget,
        },
    }
    _save_pack(book_root, "global", f"policy_{stage_id}.json", payload)
    return payload


def build_book_context_digest(book_root: Path) -> dict[str, Any]:
    book_config = read_json(book_root / "_master" / "BOOK_CONFIG.json", default={}) or {}
    word_targets = read_json(book_root / "_master" / "WORD_TARGETS.json", default={}) or {}
    blueprint_text = read_text(book_root / "_master" / "BOOK_BLUEPRINT.md")
    shared_memory = load_shared_memory(book_root)
    blueprint_sections = _markdown_sections(blueprint_text)

    payload = {
        "version": CONTEXT_PACK_VERSION,
        "pack_type": "book_context_digest",
        "scope": "local",
        "owner": "book_local",
        "mutable": True,
        "generated_at": now_iso(),
        "book_id": book_config.get("book_id"),
        "display_name": book_config.get("display_name"),
        "working_title": book_config.get("working_title"),
        "audience": book_config.get("audience"),
        "language": book_config.get("language"),
        "tone_profile": list(book_config.get("tone_profile", [])),
        "global_characteristics": {
            "core_message": shared_memory.get("book_memory", {}).get("core_message", ""),
            "reader_persona": shared_memory.get("book_memory", {}).get("reader_persona", ""),
            "structural_strategy": _bullet_lines(blueprint_sections.get("Structural Strategy", ""), max_items=4),
            "writing_rules": _bullet_lines(blueprint_sections.get("Writing Rules", ""), max_items=6),
        },
        "local_characteristics": {
            "part_labels": list(dict.fromkeys(chapter.get("part", "") for chapter in word_targets.get("chapters", []))),
            "chapter_count": book_config.get("chapter_count"),
            "part_count": book_config.get("part_count"),
            "total_target_words": word_targets.get("total_target_words"),
            "anchor_budget_total": book_config.get("anchor_system", {}).get("total_anchor_budget"),
            "reference_policy": book_config.get("reference_policy", {}),
        },
    }
    _save_pack(book_root, "local", "book_context_digest.json", payload)
    return payload


def build_chapter_context_pack(book_root: Path, chapter_id: str, stage_id: str) -> dict[str, Any]:
    book_db = load_book_db(book_root)
    shared_memory = load_shared_memory(book_root)
    word_targets = read_json(book_root / "_master" / "WORD_TARGETS.json", default={}) or {}
    research_plan = read_json(book_root / "research" / "research_plan.json", default={}) or {}
    reference_index = read_json(book_root / "research" / "reference_index.json", default={}) or {}
    anchor_plan = read_json(book_root / "manuscripts" / "_raw" / f"{chapter_id}_anchor_plan.json", default={}) or {}

    chapter_state = book_db["chapters"][chapter_id]
    chapter_target = get_chapter_target(word_targets, chapter_id)
    chapter_memory = next(
        (item for item in shared_memory.get("chapter_memory", []) if item.get("chapter_id") == chapter_id),
        {},
    )
    research_entry = next(
        (item for item in research_plan.get("chapters", []) if item.get("chapter_id") == chapter_id),
        {},
    )
    reference_entries = next(
        (item.get("entries", []) for item in reference_index.get("chapters", []) if item.get("chapter_id") == chapter_id),
        [],
    )

    payload = {
        "version": CONTEXT_PACK_VERSION,
        "pack_type": "chapter_context_pack",
        "scope": "local",
        "owner": "book_local",
        "mutable": True,
        "generated_at": now_iso(),
        "stage_id": stage_id,
        "chapter_id": chapter_id,
        "chapter_profile": {
            "title": chapter_state["title"],
            "part": chapter_state.get("part"),
            "target_words": chapter_target["target_words"],
            "stage_floor_words": chapter_target["stage_progress_floors"].get("S4_draft1_min_words"),
            "anchor_budget": chapter_target.get("anchor_budget"),
            "notes": list(chapter_state.get("notes", [])),
        },
        "global_characteristics": {
            "summary": chapter_memory.get("summary", ""),
            "claims": list(chapter_memory.get("claims", []))[:5],
            "chapter_dependencies": [
                item
                for item in shared_memory.get("book_memory", {}).get("chapter_dependencies", [])
                if item.get("chapter_id") == chapter_id or item.get("depends_on") == chapter_id
            ],
        },
        "local_characteristics": {
            "research_questions": list(research_entry.get("research_questions", []))[:4],
            "source_types": list(research_entry.get("source_types", []))[:6],
            "unresolved_issues": list(chapter_memory.get("unresolved_issues", []))[:6],
            "citation_shortlist": list(chapter_memory.get("citations_summary", []))[:8],
            "visual_notes": list(chapter_memory.get("visual_notes", []))[:8],
            "planned_anchor_ids": [item.get("anchor_id") for item in anchor_plan.get("anchors", []) if item.get("anchor_id")],
            "reference_shortlist": [
                {
                    "reference_id": item.get("reference_id"),
                    "source_type": item.get("source_type"),
                    "reference_domain": item.get("reference_domain"),
                }
                for item in reference_entries[:8]
            ],
        },
        "stage_state": chapter_state.get("stages", {}),
    }
    _save_pack(book_root, "local", f"{chapter_id}_{stage_id}_chapter_context_pack.json", payload)
    return payload


def build_node_context_pack(
    book_root: Path,
    stage_id: str,
    chapter_id: str,
    node_payload: dict[str, Any],
) -> dict[str, Any]:
    node_id = str(node_payload.get("node_id") or node_payload.get("block_id") or node_payload.get("section_key") or "node")
    payload = {
        "version": CONTEXT_PACK_VERSION,
        "pack_type": "node_context_pack",
        "scope": "local",
        "owner": "runtime",
        "mutable": True,
        "generated_at": now_iso(),
        "stage_id": stage_id,
        "chapter_id": chapter_id,
        "node_id": node_id,
        "global_characteristics": {
            "node_type": node_payload.get("node_type", "runtime_node"),
            "section_key": node_payload.get("section_key"),
            "section_heading": node_payload.get("section_heading"),
            "target_words": node_payload.get("target_words"),
        },
        "local_characteristics": {
            "research_questions": list(node_payload.get("research_questions", []))[:3],
            "source_types": list(node_payload.get("source_types", []))[:4],
            "block_id": node_payload.get("block_id"),
            "source_text_excerpt": _compact_text(node_payload.get("source_text"), max_chars=900),
            "continuity_excerpt": _compact_text(node_payload.get("continuity_excerpt"), max_chars=900),
            "local_goal": _compact_text(node_payload.get("local_goal"), max_chars=320),
        },
    }
    safe_node_id = slugify(node_id) or "node"
    _save_pack(book_root, "runtime", f"{chapter_id}_{stage_id}_{safe_node_id}.json", payload)
    return payload


def pack_to_artifact(payload: dict[str, Any]) -> dict[str, str]:
    return {
        "label": payload["pack_type"],
        "text": json.dumps(payload, ensure_ascii=False, indent=2),
    }


def estimate_context_budget(context_artifacts: list[dict[str, str]], prompt_text: str = "") -> dict[str, Any]:
    artifact_stats = []
    total_chars = len(prompt_text)
    total_tokens = _approx_token_count(prompt_text)
    for artifact in context_artifacts:
        text = artifact.get("text", "")
        chars = len(text)
        tokens = _approx_token_count(text)
        total_chars += chars
        total_tokens += tokens
        artifact_stats.append(
            {
                "label": artifact.get("label", "context"),
                "char_count": chars,
                "approx_tokens": tokens,
            }
        )
    return {
        "version": CONTEXT_PACK_VERSION,
        "generated_at": now_iso(),
        "prompt_char_count": len(prompt_text),
        "prompt_approx_tokens": _approx_token_count(prompt_text),
        "context_artifact_count": len(context_artifacts),
        "context_total_char_count": total_chars,
        "context_total_approx_tokens": total_tokens,
        "artifacts": artifact_stats,
        "note": "approx_tokens is a heuristic estimate used for routing and guardrails, not model-billed usage.",
    }


def _copy_payload(payload: dict[str, Any]) -> dict[str, Any]:
    return json.loads(json.dumps(payload, ensure_ascii=False))


def _distill_book_context_digest(payload: dict[str, Any], level: int) -> dict[str, Any]:
    distilled = _copy_payload(payload)
    if level >= 1:
        global_characteristics = distilled.get("global_characteristics", {})
        global_characteristics["structural_strategy"] = global_characteristics.get("structural_strategy", [])[:2]
        global_characteristics["writing_rules"] = global_characteristics.get("writing_rules", [])[:3]
        local_characteristics = distilled.get("local_characteristics", {})
        local_characteristics["part_labels"] = local_characteristics.get("part_labels", [])[:4]
    if level >= 2:
        global_characteristics = distilled.get("global_characteristics", {})
        global_characteristics["core_message"] = _compact_text(global_characteristics.get("core_message"), max_chars=240)
        local_characteristics = distilled.get("local_characteristics", {})
        for key in ("reference_policy",):
            local_characteristics[key] = _compact_text(local_characteristics.get(key), max_chars=220)
    return distilled


def _distill_chapter_context_pack(payload: dict[str, Any], level: int) -> dict[str, Any]:
    distilled = _copy_payload(payload)
    local_characteristics = distilled.get("local_characteristics", {})
    global_characteristics = distilled.get("global_characteristics", {})
    if level >= 1:
        local_characteristics["research_questions"] = local_characteristics.get("research_questions", [])[:2]
        local_characteristics["source_types"] = local_characteristics.get("source_types", [])[:4]
        local_characteristics["citation_shortlist"] = local_characteristics.get("citation_shortlist", [])[:5]
        local_characteristics["visual_notes"] = local_characteristics.get("visual_notes", [])[:5]
        local_characteristics["reference_shortlist"] = local_characteristics.get("reference_shortlist", [])[:5]
        distilled["stage_state"] = {
            stage_id: stage_state
            for stage_id, stage_state in distilled.get("stage_state", {}).items()
            if stage_id == distilled.get("stage_id") or stage_id in {"S4", "S5", "S8A"}
        }
    if level >= 2:
        global_characteristics["summary"] = _compact_text(global_characteristics.get("summary"), max_chars=220)
        global_characteristics["claims"] = global_characteristics.get("claims", [])[:3]
        local_characteristics["unresolved_issues"] = local_characteristics.get("unresolved_issues", [])[:3]
        local_characteristics["planned_anchor_ids"] = local_characteristics.get("planned_anchor_ids", [])[:4]
    return distilled


def _distill_node_context_pack(payload: dict[str, Any], level: int) -> dict[str, Any]:
    distilled = _copy_payload(payload)
    local_characteristics = distilled.get("local_characteristics", {})
    if level >= 1:
        local_characteristics["research_questions"] = local_characteristics.get("research_questions", [])[:2]
        local_characteristics["source_types"] = local_characteristics.get("source_types", [])[:3]
        local_characteristics["source_text_excerpt"] = _compact_text(
            local_characteristics.get("source_text_excerpt"),
            max_chars=500,
        )
        local_characteristics["continuity_excerpt"] = _compact_text(
            local_characteristics.get("continuity_excerpt"),
            max_chars=420,
        )
    if level >= 2:
        local_characteristics["source_text_excerpt"] = _compact_text(
            local_characteristics.get("source_text_excerpt"),
            max_chars=280,
        )
        local_characteristics["continuity_excerpt"] = _compact_text(
            local_characteristics.get("continuity_excerpt"),
            max_chars=220,
        )
        local_characteristics["local_goal"] = _compact_text(local_characteristics.get("local_goal"), max_chars=180)
    return distilled


def _effective_artifact_payloads(
    *,
    policy_pack: dict[str, Any],
    book_context_digest: dict[str, Any],
    chapter_context_pack: dict[str, Any] | None,
    node_context_pack: dict[str, Any] | None,
    level: int,
) -> list[dict[str, Any]]:
    artifacts = [policy_pack, _distill_book_context_digest(book_context_digest, level)]
    if chapter_context_pack is not None:
        artifacts.append(_distill_chapter_context_pack(chapter_context_pack, level))
    if node_context_pack is not None:
        artifacts.append(_distill_node_context_pack(node_context_pack, level))
    return artifacts


def build_context_bundle(
    book_root: Path,
    stage_id: str,
    chapter_id: str | None = None,
    node_payload: dict[str, Any] | None = None,
    prompt_text: str = "",
) -> dict[str, Any]:
    policy_pack = build_policy_pack(book_root, stage_id)
    book_context_digest = build_book_context_digest(book_root)
    chapter_context_pack = None
    node_context_pack = None

    if chapter_id is not None:
        chapter_context_pack = build_chapter_context_pack(book_root, chapter_id, stage_id)
    if chapter_id is not None and node_payload is not None:
        node_context_pack = build_node_context_pack(book_root, stage_id, chapter_id, node_payload)

    soft_budget = policy_pack.get("stage_policy", {}).get("token_budget", {}).get("soft_max_input_tokens", 5500)
    effective_level = 0
    effective_payloads = _effective_artifact_payloads(
        policy_pack=policy_pack,
        book_context_digest=book_context_digest,
        chapter_context_pack=chapter_context_pack,
        node_context_pack=node_context_pack,
        level=effective_level,
    )
    context_artifacts = [pack_to_artifact(pack) for pack in effective_payloads]
    budget = estimate_context_budget(context_artifacts, prompt_text=prompt_text)
    while budget["context_total_approx_tokens"] > soft_budget and effective_level < 2:
        effective_level += 1
        effective_payloads = _effective_artifact_payloads(
            policy_pack=policy_pack,
            book_context_digest=book_context_digest,
            chapter_context_pack=chapter_context_pack,
            node_context_pack=node_context_pack,
            level=effective_level,
        )
        context_artifacts = [pack_to_artifact(pack) for pack in effective_payloads]
        budget = estimate_context_budget(context_artifacts, prompt_text=prompt_text)
    budget["soft_max_input_tokens"] = soft_budget
    budget["within_budget"] = budget["context_total_approx_tokens"] <= soft_budget
    budget["distill_level"] = effective_level
    budget["budget_enforced"] = effective_level > 0
    budget["stage_id"] = stage_id
    budget["chapter_id"] = chapter_id
    _save_pack(
        book_root,
        "runtime",
        f"{chapter_id or 'book'}_{stage_id}_context_budget.json",
        budget,
    )
    return {
        "policy_pack": policy_pack,
        "book_context_digest": book_context_digest,
        "chapter_context_pack": chapter_context_pack,
        "node_context_pack": node_context_pack,
        "context_artifacts": context_artifacts,
        "budget": budget,
    }
