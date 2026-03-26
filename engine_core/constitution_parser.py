from __future__ import annotations

"""AG-DCP — Dynamic Constitutional Prompting

Parses the canonical CONSTITUTION.md and AGENT_SOPS.md into structured rule
sets and assembles a context-appropriate constitutional injection block for
each (stage_id, agent_id) combination at runtime.

The injected block is used:
  - In policy_packs (context_packs.py) — replaces hardcoded _GLOBAL_CONSTITUTION_RULES
  - In model prompt assembly — prepended to every structured generation call

Design:
  - Constitution articles are parsed from ## 제N조. headings
  - Agent SOP sections are parsed from ## AG-XX: ... headings
  - Stage-specific rules are layered on top of global rules
  - A lightweight in-process cache prevents redundant disk reads
"""

import re
from functools import lru_cache
from pathlib import Path
from typing import Any

from .common import PLATFORM_CORE_ROOT, now_iso, read_json, read_text


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

CONSTITUTION_PATH = PLATFORM_CORE_ROOT / "CONSTITUTION.md"
AGENT_SOPS_PATH = PLATFORM_CORE_ROOT / "AGENT_SOPS.md"

# Maps stage_id → which constitution article numbers are most relevant
_STAGE_ARTICLE_FOCUS: dict[str, list[int]] = {
    "S-1": [1, 9],
    "S0":  [1, 2, 3, 8],
    "S1":  [1, 3, 6],
    "S2":  [1, 2, 5],
    "S3":  [1, 2, 3, 4],
    "S4":  [1, 2, 3, 5, 7],
    "S4A": [1, 2, 7],
    "S5":  [1, 2, 3, 5, 7],
    "S6":  [1, 2, 3],
    "S6A": [1, 2],
    "S6B": [1, 2, 6],
    "S7":  [1, 2, 3],
    "S8":  [1, 2, 7],
    "S8A": [1, 2, 7],
    "S9":  [1, 2, 4, 6, 7],
}

# ---------------------------------------------------------------------------
# Stage → Agent mapping — loaded dynamically from stage_definitions.json
# Hardcoded fallback used only when the JSON file is unavailable.
# ---------------------------------------------------------------------------

_STAGE_AGENT_MAP_FALLBACK: dict[str, str] = {
    "S-1": "AG-IN",
    "S0":  "AG-AR",
    "S1":  "AG-OM",
    "S2":  "AG-RS",
    "S3":  "AG-00",
    "S4":  "AG-01",
    "S4A": "AG-01B",
    "S5":  "AG-02",
    "S6":  "AG-03",
    "S6A": "AG-AS",
    "S6B": "AG-IM",
    "S7":  "AG-04",
    "S8":  "AG-05",
    "S8A": "AG-05A",
    "S9":  "AG-06",
}


@lru_cache(maxsize=1)
def _load_stage_agent_map() -> dict[str, str]:
    """Build {stage_id: agent_id} from stage_definitions.json. Cached in process."""
    payload = read_json(PLATFORM_CORE_ROOT / "stage_definitions.json", default={}) or {}
    mapping: dict[str, str] = {}
    for stage in payload.get("stages", []):
        sid = stage.get("id")
        agent = stage.get("agent")
        if sid and agent:
            mapping[sid] = agent
    return mapping or dict(_STAGE_AGENT_MAP_FALLBACK)


def get_agent_id_for_stage(stage_id: str) -> str:
    """Return the canonical agent_id for a stage_id.

    Reads from stage_definitions.json (single source of truth).
    Falls back to the embedded map if the file is unavailable.
    """
    return _load_stage_agent_map().get(stage_id, "AG-UNKNOWN")

_ARTICLE_HEADING_PATTERN = re.compile(
    r"^## 제(\d+)조[.。]?\s+(.+)$", re.MULTILINE
)
_AGENT_SOP_HEADING_PATTERN = re.compile(
    r"^##\s+(AG-\w+)[:\s]+(.+)$", re.MULTILINE
)
_FORBIDDEN_PATTERN = re.compile(
    r"(?m)^금지:\s*\n((?:- .+\n?)+)", re.MULTILINE
)
_ALLOWED_PATTERN = re.compile(
    r"(?m)^허용:\s*\n((?:- .+\n?)+)", re.MULTILINE
)
_BULLET_ITEM = re.compile(r"^- (.+)$", re.MULTILINE)


# ---------------------------------------------------------------------------
# Parsing helpers
# ---------------------------------------------------------------------------

def _extract_bullets(block: str) -> list[str]:
    return [m.group(1).strip() for m in _BULLET_ITEM.finditer(block)]


def _section_text(full_text: str, start: int, end: int) -> str:
    return full_text[start:end].strip()


def _parse_constitution_articles(text: str) -> dict[int, dict[str, Any]]:
    """Parse CONSTITUTION.md into {article_number: {title, forbidden, allowed, raw}}."""
    matches = list(_ARTICLE_HEADING_PATTERN.finditer(text))
    articles: dict[int, dict[str, Any]] = {}
    for idx, match in enumerate(matches):
        article_no = int(match.group(1))
        title = match.group(2).strip()
        section_start = match.end()
        section_end = matches[idx + 1].start() if idx + 1 < len(matches) else len(text)
        raw = _section_text(text, section_start, section_end)

        forbidden: list[str] = []
        allowed: list[str] = []
        for fm in _FORBIDDEN_PATTERN.finditer(raw):
            forbidden.extend(_extract_bullets(fm.group(1)))
        for am in _ALLOWED_PATTERN.finditer(raw):
            allowed.extend(_extract_bullets(am.group(1)))

        articles[article_no] = {
            "article_no": article_no,
            "title": title,
            "forbidden": forbidden,
            "allowed": allowed,
            "raw": raw,
        }
    return articles


def _parse_agent_sops(text: str) -> dict[str, dict[str, Any]]:
    """Parse AGENT_SOPS.md into {agent_id: {title, responsibilities, rules, raw}}."""
    matches = list(_AGENT_SOP_HEADING_PATTERN.finditer(text))
    sops: dict[str, dict[str, Any]] = {}
    for idx, match in enumerate(matches):
        agent_id = match.group(1).strip()
        title = match.group(2).strip()
        section_start = match.end()
        section_end = matches[idx + 1].start() if idx + 1 < len(matches) else len(text)
        raw = _section_text(text, section_start, section_end)
        bullets = _extract_bullets(raw)
        sops[agent_id] = {
            "agent_id": agent_id,
            "title": title,
            "rules": bullets[:10],  # cap at 10 bullets for injection size
            "raw": raw,
        }
    return sops


# ---------------------------------------------------------------------------
# Cached loaders
# ---------------------------------------------------------------------------

@lru_cache(maxsize=1)
def _load_constitution() -> dict[int, dict[str, Any]]:
    if not CONSTITUTION_PATH.exists():
        return {}
    return _parse_constitution_articles(read_text(CONSTITUTION_PATH))


@lru_cache(maxsize=1)
def _load_agent_sops() -> dict[str, dict[str, Any]]:
    if not AGENT_SOPS_PATH.exists():
        return {}
    return _parse_agent_sops(read_text(AGENT_SOPS_PATH))


def reload_all() -> None:
    """Clear caches — call when source files are known to have changed."""
    _load_constitution.cache_clear()
    _load_agent_sops.cache_clear()
    _load_stage_agent_map.cache_clear()


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def get_constitution_rules(stage_id: str | None = None) -> list[str]:
    """Return a flat list of constitutional rule strings for the given stage.

    If stage_id is None, all articles are included.
    The list is usable as a drop-in replacement for _GLOBAL_CONSTITUTION_RULES.
    """
    articles = _load_constitution()
    if not articles:
        return [
            "Agents may call models only through engine.model.* APIs.",
            "Context must be staged as policy, book, chapter, and node packs.",
            "No stage may bypass artifact contracts or gate checks.",
        ]

    focus_articles = _STAGE_ARTICLE_FOCUS.get(stage_id or "", list(articles.keys()))
    rules: list[str] = []
    for art_no in focus_articles:
        article = articles.get(art_no)
        if not article:
            continue
        rules.append(f"[제{art_no}조 {article['title']}]")
        for item in article["forbidden"]:
            rules.append(f"  금지: {item}")
        for item in article["allowed"]:
            rules.append(f"  허용: {item}")
    return rules


def get_agent_sop(agent_id: str) -> dict[str, Any] | None:
    """Return parsed SOP entry for a specific agent, or None if not found."""
    sops = _load_agent_sops()
    return sops.get(agent_id)


def build_constitutional_injection(
    stage_id: str,
    agent_id: str | None = None,
    *,
    include_sop: bool = True,
    max_rules: int = 12,
) -> dict[str, Any]:
    """Assemble a constitutional injection block for a (stage_id, agent_id) pair.

    Returns a dict with:
      - constitutional_rules: list[str]   — focused article rules
      - agent_sop_rules: list[str]        — agent-specific SOP bullets
      - prompt_block: str                 — ready-to-prepend text block
      - generated_at: str
      - stage_id: str
      - agent_id: str
    """
    resolved_agent = agent_id or get_agent_id_for_stage(stage_id)
    rules = get_constitution_rules(stage_id)[:max_rules]

    sop_rules: list[str] = []
    if include_sop:
        sop = get_agent_sop(resolved_agent)
        if sop:
            sop_rules = sop["rules"][:6]

    prompt_block = _render_prompt_block(stage_id, resolved_agent, rules, sop_rules)

    return {
        "stage_id": stage_id,
        "agent_id": resolved_agent,
        "constitutional_rules": rules,
        "agent_sop_rules": sop_rules,
        "prompt_block": prompt_block,
        "generated_at": now_iso(),
    }


def build_minimal_injection(stage_id: str) -> str:
    """Return a compact single-string prompt prefix for embedding in model calls."""
    injection = build_constitutional_injection(stage_id, include_sop=False, max_rules=6)
    return injection["prompt_block"]


def list_parsed_articles() -> list[dict[str, Any]]:
    """Return a summary of all parsed constitution articles (for diagnostics)."""
    articles = _load_constitution()
    return [
        {
            "article_no": a["article_no"],
            "title": a["title"],
            "forbidden_count": len(a["forbidden"]),
            "allowed_count": len(a["allowed"]),
        }
        for a in articles.values()
    ]


def list_parsed_sops() -> list[dict[str, Any]]:
    """Return a summary of all parsed agent SOPs (for diagnostics)."""
    sops = _load_agent_sops()
    return [
        {
            "agent_id": s["agent_id"],
            "title": s["title"],
            "rule_count": len(s["rules"]),
        }
        for s in sops.values()
    ]


# ---------------------------------------------------------------------------
# Rendering
# ---------------------------------------------------------------------------

def _render_prompt_block(
    stage_id: str,
    agent_id: str,
    rules: list[str],
    sop_rules: list[str],
) -> str:
    lines = [
        f"[헌법 규칙 | 단계: {stage_id} | 에이전트: {agent_id}]",
        "",
    ]
    for rule in rules:
        lines.append(rule)

    if sop_rules:
        lines.append("")
        lines.append(f"[{agent_id} SOP]")
        for rule in sop_rules:
            lines.append(f"- {rule}")

    lines.append("")
    return "\n".join(lines)
