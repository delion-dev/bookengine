from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass
from difflib import unified_diff


ANCHOR_BLOCK_PATTERN = re.compile(
    r'<!-- ANCHOR_START\b[^>]*?id="(?P<anchor_id>[^"]+)"[^>]*?-->.*?<!-- ANCHOR_END\b[^>]*?id="(?P=anchor_id)"[^>]*?-->',
    re.DOTALL,
)


@dataclass(frozen=True)
class AnchorScopeIntegrity:
    passed: bool
    before_anchor_count: int
    after_anchor_count: int
    non_anchor_sha1_before: str
    non_anchor_sha1_after: str
    diff_preview: str


def _normalize_heading(text: str) -> str:
    lines = text.splitlines()
    if lines and lines[0].startswith("# DRAFT"):
        lines[0] = "# DRAFT"
    return "\n".join(lines)


def extract_anchor_blocks(text: str) -> list[str]:
    return [match.group(0) for match in ANCHOR_BLOCK_PATTERN.finditer(text)]


def non_anchor_text(text: str) -> str:
    normalized = _normalize_heading(text)
    stripped = ANCHOR_BLOCK_PATTERN.sub("[ANCHOR_BLOCK]", normalized)
    lines = [line.rstrip() for line in stripped.splitlines()]
    return "\n".join(lines).strip() + "\n"


def strip_anchor_blocks(text: str) -> str:
    normalized = _normalize_heading(text)
    stripped = ANCHOR_BLOCK_PATTERN.sub("", normalized)
    stripped = re.sub(r"\[ANCHOR_SLOT:[^\]]+\]\s*", "", stripped)
    stripped = re.sub(r"\n{3,}", "\n\n", stripped)
    lines = [line.rstrip() for line in stripped.splitlines()]
    return "\n".join(lines).strip() + "\n"


def anchor_scope_integrity(before_text: str, after_text: str, *, diff_limit: int = 40) -> AnchorScopeIntegrity:
    before_non_anchor = non_anchor_text(before_text)
    after_non_anchor = non_anchor_text(after_text)
    before_blocks = extract_anchor_blocks(before_text)
    after_blocks = extract_anchor_blocks(after_text)
    diff_lines = list(
        unified_diff(
            before_non_anchor.splitlines(),
            after_non_anchor.splitlines(),
            fromfile="before_non_anchor",
            tofile="after_non_anchor",
            lineterm="",
        )
    )
    preview = "\n".join(diff_lines[:diff_limit])
    return AnchorScopeIntegrity(
        passed=before_non_anchor == after_non_anchor and len(before_blocks) == len(after_blocks),
        before_anchor_count=len(before_blocks),
        after_anchor_count=len(after_blocks),
        non_anchor_sha1_before=hashlib.sha1(before_non_anchor.encode("utf-8")).hexdigest(),
        non_anchor_sha1_after=hashlib.sha1(after_non_anchor.encode("utf-8")).hexdigest(),
        diff_preview=preview,
    )
