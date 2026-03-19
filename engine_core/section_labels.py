from __future__ import annotations

import re


SECTION_ORDER = ("hook", "context", "insight", "takeaway")
SECTION_CANONICAL_LABELS = {
    "hook": "Hook",
    "context": "Context",
    "insight": "Insight",
    "takeaway": "Takeaway",
}
SECTION_DISPLAY_LABELS = {
    "hook": "도입 (Hook)",
    "context": "맥락 (Context)",
    "insight": "통찰 (Insight)",
    "takeaway": "실전 포인트 (Takeaway)",
}
SECTION_MARKERS = {
    section_key: f"## {label}"
    for section_key, label in SECTION_DISPLAY_LABELS.items()
}
LEGACY_SECTION_MARKERS = {
    section_key: f"## {label}"
    for section_key, label in SECTION_CANONICAL_LABELS.items()
}


def canonical_section_label(section_key: str) -> str:
    return SECTION_CANONICAL_LABELS[section_key]


def display_section_label(section_key: str) -> str:
    return SECTION_DISPLAY_LABELS[section_key]


def section_marker(section_key: str) -> str:
    return SECTION_MARKERS[section_key]


def section_marker_variants(section_key: str) -> list[str]:
    return [SECTION_MARKERS[section_key], LEGACY_SECTION_MARKERS[section_key]]


def required_section_markers() -> list[str]:
    return [SECTION_MARKERS[section_key] for section_key in SECTION_ORDER]


def find_section_marker(text: str, section_key: str) -> str | None:
    for marker in section_marker_variants(section_key):
        if marker in text:
            return marker
    return None


def has_required_sections(text: str) -> bool:
    return all(find_section_marker(text, section_key) for section_key in SECTION_ORDER)


def canonical_section_label_from_heading(heading: str) -> str | None:
    normalized = heading.replace("## ", "", 1).strip()
    for section_key in SECTION_ORDER:
        if normalized in {
            SECTION_CANONICAL_LABELS[section_key],
            SECTION_DISPLAY_LABELS[section_key],
        }:
            return SECTION_CANONICAL_LABELS[section_key]
    return None


def strip_leading_section_heading(text: str) -> str:
    cleaned = text.strip()
    for section_key in SECTION_ORDER:
        for marker in section_marker_variants(section_key):
            if cleaned.startswith(marker):
                return cleaned[len(marker) :].strip()
    return cleaned


def normalize_section_headings(text: str) -> str:
    normalized = text
    for section_key in SECTION_ORDER:
        legacy_marker = LEGACY_SECTION_MARKERS[section_key]
        marker = SECTION_MARKERS[section_key]
        normalized = re.sub(
            rf"(?m)^{re.escape(legacy_marker)}\s*$",
            marker,
            normalized,
        )
    return normalized
