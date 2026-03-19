from __future__ import annotations

"""Metadata Engine — EPUB / Google Books Metadata Management

Handles:
  - Dublin Core metadata storage (OPF 3.0 compliant)
  - ISBN-13 validation (check digit)
  - Google Books Partner ID storage
  - BISAC / THEMA subject code lookup
  - Metadata serialization to OPF XML fragment
  - AppData persistence per book
"""

import re
import uuid
from pathlib import Path
from typing import Any

from .common import ensure_dir, now_iso, read_json, write_json

# ---------------------------------------------------------------------------
# Storage
# ---------------------------------------------------------------------------

APPDATA_ROOT = Path.home() / "AppData" / "Roaming" / "BookEngine"


def _metadata_path(book_id: str) -> Path:
    return APPDATA_ROOT / "books" / book_id / "metadata.json"


# ---------------------------------------------------------------------------
# ISBN-13 Validation
# ---------------------------------------------------------------------------

def validate_isbn13(isbn: str) -> bool:
    """Validate ISBN-13 check digit per ISO 2108."""
    digits = re.sub(r"[-\s]", "", isbn)
    if not re.fullmatch(r"\d{13}", digits):
        return False
    total = sum(
        int(d) * (1 if i % 2 == 0 else 3)
        for i, d in enumerate(digits)
    )
    return total % 10 == 0


def format_isbn13(isbn: str) -> str:
    """Format raw ISBN-13 digits as 978-X-XXX-XXXXX-X."""
    digits = re.sub(r"[-\s]", "", isbn)
    if len(digits) == 13:
        return f"{digits[:3]}-{digits[3]}-{digits[4:7]}-{digits[7:12]}-{digits[12]}"
    return isbn


# ---------------------------------------------------------------------------
# BISAC / THEMA Code Tables
# ---------------------------------------------------------------------------

BISAC_CODES: dict[str, str] = {
    "COM004000": "COMPUTERS / Artificial Intelligence / General",
    "COM014000": "COMPUTERS / Databases / General",
    "COM051230": "COMPUTERS / Programming Languages / Python",
    "COM060000": "COMPUTERS / Web / General",
    "COM051000": "COMPUTERS / Programming / General",
    "COM018000": "COMPUTERS / Desktop Applications / General",
    "BUS000000": "BUSINESS & ECONOMICS / General",
    "BUS041000": "BUSINESS & ECONOMICS / Management",
    "EDU000000": "EDUCATION / General",
    "LIT000000": "LITERARY COLLECTIONS / General",
    "SCI000000": "SCIENCE / General",
    "TEC000000": "TECHNOLOGY & ENGINEERING / General",
}

THEMA_CODES: dict[str, str] = {
    "UYQ": "Artificial intelligence",
    "UYM": "Machine learning",
    "UNF": "Natural language processing (NLP)",
    "UM":  "Computer programming / software engineering",
    "UMW": "Web programming",
    "UND": "Databases",
    "KJ":  "Business and management",
    "JN":  "Education",
    "PDX": "History and philosophy of science",
}

BISAC_CATEGORIES: list[dict[str, Any]] = [
    {"code": "COM004000", "label": "컴퓨터 / 인공지능", "bisac": "COM004000"},
    {"code": "COM051230", "label": "컴퓨터 / Python 프로그래밍", "bisac": "COM051230"},
    {"code": "COM060000", "label": "컴퓨터 / 웹 개발", "bisac": "COM060000"},
    {"code": "COM051000", "label": "컴퓨터 / 프로그래밍 일반", "bisac": "COM051000"},
    {"code": "BUS041000", "label": "경영 / 경영관리", "bisac": "BUS041000"},
    {"code": "BUS000000", "label": "경영 / 일반", "bisac": "BUS000000"},
    {"code": "EDU000000", "label": "교육 / 일반", "bisac": "EDU000000"},
    {"code": "LIT000000", "label": "문학 / 에세이·기타", "bisac": "LIT000000"},
    {"code": "TEC000000", "label": "기술 / 공학 일반", "bisac": "TEC000000"},
]

THEMA_CATEGORIES: list[dict[str, Any]] = [
    {"code": "UYQ", "label": "인공지능"},
    {"code": "UYM", "label": "머신러닝"},
    {"code": "UNF", "label": "자연어처리 (NLP)"},
    {"code": "UM",  "label": "소프트웨어 엔지니어링"},
    {"code": "UMW", "label": "웹 프로그래밍"},
    {"code": "KJ",  "label": "경영/관리"},
    {"code": "JN",  "label": "교육"},
]

AGE_RATINGS = ["전체", "어린이(12세 이하)", "청소년(12-17세)", "성인(18세 이상)"]

LANGUAGES = [
    {"code": "ko", "label": "한국어"},
    {"code": "en", "label": "English"},
    {"code": "ja", "label": "日本語"},
    {"code": "zh", "label": "中文"},
]

# ---------------------------------------------------------------------------
# Default Metadata Template
# ---------------------------------------------------------------------------

DEFAULT_METADATA: dict[str, Any] = {
    "title": "",
    "subtitle": "",
    "author": "",
    "publisher": "Self-Published",
    "publication_date": "",
    "language": "ko",
    "isbn13": "",
    "google_books_id": "",
    "description": "",
    "keywords": [],
    "bisac_code": "COM004000",
    "thema_code": "UYQ",
    "age_rating": "전체",
    "adult_content": False,
    "identifier": "",
    "updated_at": "",
}


# ---------------------------------------------------------------------------
# CRUD
# ---------------------------------------------------------------------------

def load_book_metadata(book_id: str) -> dict[str, Any]:
    """Load metadata for a book. Returns defaults if not yet saved."""
    path = _metadata_path(book_id)
    if path.exists():
        return {**DEFAULT_METADATA, **read_json(path)}
    return {**DEFAULT_METADATA, "book_id": book_id}


def save_book_metadata(book_id: str, data: dict[str, Any]) -> dict[str, Any]:
    """Validate and persist metadata. Returns saved metadata with errors."""
    meta = {**DEFAULT_METADATA, **data}
    meta["book_id"] = book_id
    meta["updated_at"] = now_iso()

    errors: list[str] = []

    # ISBN-13 validation
    if meta["isbn13"]:
        if not validate_isbn13(meta["isbn13"]):
            errors.append(f"ISBN-13 체크섬 오류: {meta['isbn13']}")
        else:
            meta["isbn13"] = format_isbn13(meta["isbn13"])

    # Set identifier (prefer ISBN, fallback to Google ID, else UUID)
    if meta["isbn13"] and not errors:
        meta["identifier"] = f"isbn:{re.sub(r'[-]', '', meta['isbn13'])}"
    elif meta["google_books_id"]:
        meta["identifier"] = f"google:{meta['google_books_id']}"
    elif not meta["identifier"]:
        meta["identifier"] = f"urn:uuid:{uuid.uuid4()}"

    # Required field check
    for req in ("title", "author", "language"):
        if not meta.get(req):
            errors.append(f"필수 항목 누락: {req}")

    path = _metadata_path(book_id)
    ensure_dir(path.parent)
    write_json(path, meta)

    return {"metadata": meta, "errors": errors, "valid": len(errors) == 0}


# ---------------------------------------------------------------------------
# OPF XML Fragment
# ---------------------------------------------------------------------------

def build_opf_metadata_xml(metadata: dict[str, Any]) -> str:
    """Serialize metadata to Dublin Core / OPF 3.0 XML fragment."""
    from xml.sax.saxutils import escape as xe

    uid = metadata.get("identifier") or f"urn:uuid:{uuid.uuid4()}"
    title = xe(metadata.get("title", ""))
    subtitle = xe(metadata.get("subtitle", ""))
    author = xe(metadata.get("author", ""))
    publisher = xe(metadata.get("publisher", ""))
    lang = metadata.get("language", "ko")
    date = metadata.get("publication_date", now_iso()[:10])
    desc = xe(metadata.get("description", ""))
    keywords = metadata.get("keywords", [])

    subject_tags = "\n    ".join(
        f"<dc:subject>{xe(kw)}</dc:subject>" for kw in keywords
    )

    bisac = metadata.get("bisac_code", "")
    thema = metadata.get("thema_code", "")
    bisac_label = BISAC_CODES.get(bisac, bisac)
    thema_label = THEMA_CODES.get(thema, thema)

    full_title = f"{title}: {subtitle}" if subtitle else title

    return f"""<metadata xmlns:dc="http://purl.org/dc/elements/1.1/"
            xmlns:opf="http://www.idpf.org/2007/opf">
    <dc:identifier id="BookID">{xe(uid)}</dc:identifier>
    <dc:title>{full_title}</dc:title>
    <dc:creator opf:role="aut">{author}</dc:creator>
    <dc:language>{lang}</dc:language>
    <dc:publisher>{publisher}</dc:publisher>
    <dc:date>{date}</dc:date>
    <dc:description>{desc}</dc:description>
    {subject_tags}
    <dc:subject>{xe(bisac_label)}</dc:subject>
    <dc:subject>{xe(thema_label)}</dc:subject>
    <meta property="dcterms:modified">{date}T00:00:00Z</meta>
  </metadata>"""


# ---------------------------------------------------------------------------
# JSON Preview (for UI display)
# ---------------------------------------------------------------------------

def get_metadata_preview(book_id: str) -> dict[str, Any]:
    """Return metadata + OPF XML preview + validation status."""
    meta = load_book_metadata(book_id)
    validation = save_book_metadata(book_id, meta)

    opf_xml = build_opf_metadata_xml(meta)

    return {
        "metadata": meta,
        "opf_xml": opf_xml,
        "bisac_categories": BISAC_CATEGORIES,
        "thema_categories": THEMA_CATEGORIES,
        "languages": LANGUAGES,
        "age_ratings": AGE_RATINGS,
        "errors": validation["errors"],
        "valid": validation["valid"],
    }
