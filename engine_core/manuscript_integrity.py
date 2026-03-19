from __future__ import annotations

from collections.abc import Iterable

from .meta_blocks import meta_block_summary, strip_meta_blocks


READER_FACING_INTERNAL_HEADINGS = {
    "## Target Window",
    "## Research Carryovers",
    "## Source Priorities",
    "## Raw Guide Contract",
    "## Reader Segment",
    "## Rights Guardrails",
    "## Review Layer",
    "## Citation Attachments",
    "## Grounded Update",
    "## Grounded Trust Filter",
    "## Grounded Findings",
    "## Grounded Sources",
    "## Supplemental / Low-Trust Signals",
    "## Review Resolution",
    "## Visual Planning Handoff",
    "## Visual Planning Status",
    "## Visual Integration Summary",
}

INTERNAL_TONE_LINE_PREFIX = "_이 초고는"
BODY_META_MARKERS = (
    "장의 출발점은",
    "이 장의 맥락은",
    "현재 초고는",
    "이후 AG-02 리뷰 단계",
    "마지막 단락은",
)


def promote_draft_heading(text: str, target_label: str) -> str:
    lines = text.splitlines()
    if lines and lines[0].startswith("# DRAFT"):
        if ":" in lines[0]:
            _, suffix = lines[0].split(":", 1)
            lines[0] = f"# {target_label}:{suffix}"
        else:
            lines[0] = f"# {target_label}"
    return "\n".join(lines)


def sanitize_reader_manuscript(
    text: str,
    *,
    target_label: str | None = None,
    removable_headings: Iterable[str] | None = None,
    strip_tone_line: bool = True,
) -> tuple[str, list[str]]:
    headings = set(removable_headings or READER_FACING_INTERNAL_HEADINGS)
    normalized = promote_draft_heading(text, target_label) if target_label else text
    normalized, removed_meta_ids = strip_meta_blocks(normalized)
    lines = normalized.splitlines()
    removed: list[str] = []
    removed.extend(f"_meta_block:{meta_id}" for meta_id in removed_meta_ids)

    if strip_tone_line and len(lines) > 1:
        first_content_index = next((index for index, line in enumerate(lines[1:], start=1) if line.strip()), None)
        if first_content_index is not None and lines[first_content_index].startswith(INTERNAL_TONE_LINE_PREFIX):
            removed.append("_tone_line")
            lines.pop(first_content_index)
            while first_content_index < len(lines) and not lines[first_content_index].strip():
                lines.pop(first_content_index)

    kept: list[str] = []
    skipping = False
    for line in lines:
        if line.startswith("## "):
            heading = line.strip()
            if heading in headings:
                removed.append(heading)
                skipping = True
                continue
            skipping = False
        if not skipping:
            kept.append(line)

    cleaned_lines: list[str] = []
    for line in kept:
        marker = next((item for item in BODY_META_MARKERS if item in line), None)
        if marker:
            removed.append(f"_body_meta:{marker}")
            continue
        cleaned_lines.append(line)

    cleaned = "\n".join(cleaned_lines).strip() + "\n"
    return cleaned, removed


def find_internal_heading_residue(
    text: str,
    *,
    removable_headings: Iterable[str] | None = None,
) -> list[str]:
    headings = set(removable_headings or READER_FACING_INTERNAL_HEADINGS)
    return [heading for heading in sorted(headings) if heading in text]


def find_body_meta_markers(text: str) -> list[str]:
    return [marker for marker in BODY_META_MARKERS if marker in text]


def find_meta_block_residue(text: str) -> dict[str, object]:
    return meta_block_summary(text)
