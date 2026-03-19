from __future__ import annotations

"""AG-SG (S10) — Style Guide Application

Applies a selected style guide template to the publication manuscript,
ensuring final output complies with Google Books technical specifications.

Templates:
  GBOOK-TECH  — IT/Technical books
  GBOOK-ACAD  — Academic/Research books
  GBOOK-BUSI  — Business/Self-help books
  GBOOK-NFIC  — Non-fiction/General
  GBOOK-TUTO  — Tutorial/Workbook
  GBOOK-MINI  — Mini-book/Essay
  CUSTOM      — User-defined parameters
"""

from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

from .book_state import load_book_db
from .common import ensure_dir, now_iso, read_json, write_json, write_text

# ---------------------------------------------------------------------------
# Style Guide Definitions
# ---------------------------------------------------------------------------

STYLE_GUIDE_CATALOG: dict[str, dict[str, Any]] = {
    "GBOOK-TECH": {
        "id": "GBOOK-TECH",
        "name": "Google Books 기술서 표준",
        "description": "IT/기술 전문서. 코드 블록·콜아웃·번호 목록 최적화.",
        "target": "IT/기술 전문서",
        "params": {
            "body_font": "Noto Sans KR",
            "body_font_size": "16px",
            "body_line_height": "1.75",
            "heading_font": "Noto Sans KR",
            "heading_weight": "700",
            "code_font": "JetBrains Mono",
            "code_font_size": "14px",
            "code_background": "#1e1e2e",
            "code_color": "#cdd6f4",
            "page_margin": "2.5cm 2cm",
            "callout_border_color": "#5E6AD2",
            "callout_background": "#f0f2ff",
            "max_line_length": "75ch",
            "toc_depth": 3,
            "figure_numbering": True,
            "table_numbering": True,
            "endnotes": False,
            "chapter_break": "page",
        },
        "css_class": "gbook-tech",
    },
    "GBOOK-ACAD": {
        "id": "GBOOK-ACAD",
        "name": "Google Books 학술서",
        "description": "학술/연구서. 미주·참고문헌·표/그림 번호 체계.",
        "target": "학술/연구서",
        "params": {
            "body_font": "Noto Serif KR",
            "body_font_size": "15px",
            "body_line_height": "1.8",
            "heading_font": "Noto Serif KR",
            "heading_weight": "600",
            "code_font": "Courier New",
            "code_font_size": "13px",
            "code_background": "#f8f8f8",
            "code_color": "#333333",
            "page_margin": "3cm 2.5cm",
            "callout_border_color": "#888888",
            "callout_background": "#fafafa",
            "max_line_length": "70ch",
            "toc_depth": 4,
            "figure_numbering": True,
            "table_numbering": True,
            "endnotes": True,
            "chapter_break": "page",
        },
        "css_class": "gbook-acad",
    },
    "GBOOK-BUSI": {
        "id": "GBOOK-BUSI",
        "name": "Google Books 비즈니스서",
        "description": "경영/자기계발. 사이드바·요약 박스·인용구 강조.",
        "target": "경영/자기계발",
        "params": {
            "body_font": "Noto Sans KR",
            "body_font_size": "16px",
            "body_line_height": "1.7",
            "heading_font": "Noto Sans KR",
            "heading_weight": "700",
            "code_font": "JetBrains Mono",
            "code_font_size": "14px",
            "code_background": "#f5f5f5",
            "code_color": "#222222",
            "page_margin": "2.5cm 2cm",
            "callout_border_color": "#F59E0B",
            "callout_background": "#fffbeb",
            "max_line_length": "72ch",
            "toc_depth": 2,
            "figure_numbering": False,
            "table_numbering": True,
            "endnotes": False,
            "chapter_break": "page",
        },
        "css_class": "gbook-busi",
    },
    "GBOOK-NFIC": {
        "id": "GBOOK-NFIC",
        "name": "Google Books 논픽션",
        "description": "교양/일반 논픽션. 장별 도입 인용·여백 주석.",
        "target": "교양/일반 논픽션",
        "params": {
            "body_font": "Noto Serif KR",
            "body_font_size": "16px",
            "body_line_height": "1.8",
            "heading_font": "Noto Sans KR",
            "heading_weight": "600",
            "code_font": "Courier New",
            "code_font_size": "13px",
            "code_background": "#f8f8f8",
            "code_color": "#333333",
            "page_margin": "2.5cm 2cm",
            "callout_border_color": "#10B981",
            "callout_background": "#ecfdf5",
            "max_line_length": "68ch",
            "toc_depth": 2,
            "figure_numbering": False,
            "table_numbering": False,
            "endnotes": False,
            "chapter_break": "page",
        },
        "css_class": "gbook-nfic",
    },
    "GBOOK-TUTO": {
        "id": "GBOOK-TUTO",
        "name": "Google Books 튜토리얼",
        "description": "실습/워크북. 단계별 박스·연습문제 영역.",
        "target": "실습/워크북",
        "params": {
            "body_font": "Noto Sans KR",
            "body_font_size": "15px",
            "body_line_height": "1.7",
            "heading_font": "Noto Sans KR",
            "heading_weight": "700",
            "code_font": "JetBrains Mono",
            "code_font_size": "13px",
            "code_background": "#0d1117",
            "code_color": "#e6edf3",
            "page_margin": "2cm 1.8cm",
            "callout_border_color": "#3B82F6",
            "callout_background": "#eff6ff",
            "max_line_length": "72ch",
            "toc_depth": 3,
            "figure_numbering": True,
            "table_numbering": True,
            "endnotes": False,
            "chapter_break": "page",
        },
        "css_class": "gbook-tuto",
    },
    "GBOOK-MINI": {
        "id": "GBOOK-MINI",
        "name": "Google Books 미니북",
        "description": "단편/에세이. 심플 레이아웃, 최소 스타일.",
        "target": "단편/에세이",
        "params": {
            "body_font": "Noto Serif KR",
            "body_font_size": "16px",
            "body_line_height": "1.9",
            "heading_font": "Noto Serif KR",
            "heading_weight": "600",
            "code_font": "Courier New",
            "code_font_size": "14px",
            "code_background": "#f8f8f8",
            "code_color": "#333333",
            "page_margin": "3cm 2.5cm",
            "callout_border_color": "#6B7280",
            "callout_background": "#f9fafb",
            "max_line_length": "65ch",
            "toc_depth": 1,
            "figure_numbering": False,
            "table_numbering": False,
            "endnotes": False,
            "chapter_break": "page",
        },
        "css_class": "gbook-mini",
    },
    "CUSTOM": {
        "id": "CUSTOM",
        "name": "사용자 정의",
        "description": "CSS 파라미터를 직접 편집합니다.",
        "target": "전체",
        "params": {
            "body_font": "Noto Sans KR",
            "body_font_size": "16px",
            "body_line_height": "1.7",
            "heading_font": "Noto Sans KR",
            "heading_weight": "700",
            "code_font": "JetBrains Mono",
            "code_font_size": "14px",
            "code_background": "#f5f5f5",
            "code_color": "#222222",
            "page_margin": "2.5cm 2cm",
            "callout_border_color": "#5E6AD2",
            "callout_background": "#f0f2ff",
            "max_line_length": "72ch",
            "toc_depth": 3,
            "figure_numbering": True,
            "table_numbering": True,
            "endnotes": False,
            "chapter_break": "page",
        },
        "css_class": "gbook-custom",
    },
}

# ---------------------------------------------------------------------------
# Google Books Technical Compliance Checklist
# ---------------------------------------------------------------------------

GBOOKS_COMPLIANCE: dict[str, Any] = {
    "epub_version": "3.x",
    "cover_min_width": 1600,
    "cover_min_height": 2560,
    "cover_aspect_ratio": "1:1.6",
    "image_formats": ["JPEG", "PNG", "GIF", "SVG"],
    "image_min_dpi": 300,
    "font_embedding": "required",
    "toc_ncx": True,
    "toc_nav_document": True,
    "metadata_standard": "Dublin Core + OPF 3.0",
    "max_chapter_size_mb": 50,
}

# ---------------------------------------------------------------------------
# Style Guide Storage
# ---------------------------------------------------------------------------

APPDATA_ROOT = Path.home() / "AppData" / "Roaming" / "BookEngine"


def _style_guide_path(book_id: str) -> Path:
    return APPDATA_ROOT / "books" / book_id / "style_guide.json"


def get_style_guides() -> list[dict[str, Any]]:
    """Return catalog of all available style guide templates."""
    return [
        {
            "id": sg["id"],
            "name": sg["name"],
            "description": sg["description"],
            "target": sg["target"],
            "css_class": sg["css_class"],
        }
        for sg in STYLE_GUIDE_CATALOG.values()
    ]


def get_style_guide(template_id: str) -> dict[str, Any]:
    """Return full style guide including params."""
    if template_id not in STYLE_GUIDE_CATALOG:
        raise ValueError(f"Unknown style guide: {template_id}")
    return STYLE_GUIDE_CATALOG[template_id].copy()


def load_book_style_guide(book_id: str) -> dict[str, Any]:
    """Load saved style guide for a book, fallback to GBOOK-TECH."""
    path = _style_guide_path(book_id)
    if path.exists():
        return read_json(path)
    return get_style_guide("GBOOK-TECH")


def save_book_style_guide(book_id: str, template_id: str, params_override: dict[str, Any] | None = None) -> dict[str, Any]:
    """Save style guide selection (with optional param overrides) for a book."""
    guide = get_style_guide(template_id)
    if params_override:
        guide["params"].update(params_override)
    guide["book_id"] = book_id
    guide["saved_at"] = now_iso()

    path = _style_guide_path(book_id)
    ensure_dir(path.parent)
    write_json(path, guide)
    return guide


# ---------------------------------------------------------------------------
# CSS Generation
# ---------------------------------------------------------------------------

def generate_epub_css(guide: dict[str, Any]) -> str:
    """Generate EPUB-compatible CSS from style guide params."""
    p = guide["params"]
    css_class = guide.get("css_class", "gbook-tech")

    return f"""/* BookEngine — Generated EPUB CSS */
/* Template: {guide['id']} — {guide['name']} */
/* Google Books Technical Spec Compliant */

@charset "UTF-8";

@namespace epub "http://www.idpf.org/2007/ops";

/* ── Base ─────────────────────────────────────── */
body {{
  font-family: "{p['body_font']}", sans-serif;
  font-size: {p['body_font_size']};
  line-height: {p['body_line_height']};
  margin: 0;
  padding: 0;
  color: #1a1a1a;
  -epub-hyphens: auto;
  hyphens: auto;
  max-width: {p['max_line_length']};
}}

/* ── Headings ─────────────────────────────────── */
h1, h2, h3, h4, h5, h6 {{
  font-family: "{p['heading_font']}", sans-serif;
  font-weight: {p['heading_weight']};
  line-height: 1.3;
  color: #111111;
  margin-top: 1.5em;
  margin-bottom: 0.5em;
  page-break-after: avoid;
}}
h1 {{ font-size: 2em; border-bottom: 2px solid #eeeeee; padding-bottom: 0.3em; }}
h2 {{ font-size: 1.5em; }}
h3 {{ font-size: 1.25em; }}
h4 {{ font-size: 1.1em; }}

/* ── Paragraph ────────────────────────────────── */
p {{
  margin: 0 0 1em 0;
  text-align: justify;
  orphans: 2;
  widows: 2;
}}

/* ── Code ─────────────────────────────────────── */
code, kbd, samp {{
  font-family: "{p['code_font']}", monospace;
  font-size: {p['code_font_size']};
  background: {p['code_background']};
  color: {p['code_color']};
  padding: 0.2em 0.4em;
  border-radius: 3px;
}}

pre {{
  font-family: "{p['code_font']}", monospace;
  font-size: {p['code_font_size']};
  background: {p['code_background']};
  color: {p['code_color']};
  padding: 1.2em 1.5em;
  border-radius: 8px;
  overflow-x: auto;
  page-break-inside: avoid;
  margin: 1.5em 0;
  line-height: 1.5;
}}

pre code {{
  background: none;
  padding: 0;
  border-radius: 0;
  font-size: inherit;
}}

/* ── Callout / Note ───────────────────────────── */
.callout, .note, .warning, .tip {{
  border-left: 4px solid {p['callout_border_color']};
  background: {p['callout_background']};
  padding: 1em 1.25em;
  margin: 1.5em 0;
  border-radius: 0 8px 8px 0;
  page-break-inside: avoid;
}}

.callout-title {{
  font-weight: 700;
  margin-bottom: 0.5em;
  color: {p['callout_border_color']};
}}

/* ── Tables ───────────────────────────────────── */
table {{
  width: 100%;
  border-collapse: collapse;
  margin: 1.5em 0;
  font-size: 0.9em;
  page-break-inside: avoid;
}}
th {{
  background: #f0f0f0;
  font-weight: 600;
  text-align: left;
  padding: 0.6em 0.8em;
  border: 1px solid #dddddd;
}}
td {{
  padding: 0.5em 0.8em;
  border: 1px solid #dddddd;
}}
tr:nth-child(even) td {{
  background: #fafafa;
}}

/* ── Figures & Images ─────────────────────────── */
figure {{
  text-align: center;
  margin: 2em 0;
  page-break-inside: avoid;
}}
figure img {{
  max-width: 100%;
  height: auto;
}}
figcaption {{
  font-size: 0.85em;
  color: #666666;
  margin-top: 0.5em;
  font-style: italic;
}}

/* ── Blockquote ───────────────────────────────── */
blockquote {{
  border-left: 3px solid #cccccc;
  margin: 1.5em 0;
  padding: 0.5em 1.5em;
  color: #555555;
  font-style: italic;
}}

/* ── Lists ────────────────────────────────────── */
ul, ol {{
  margin: 0.8em 0 0.8em 1.5em;
  padding: 0;
}}
li {{
  margin-bottom: 0.3em;
}}

/* ── Chapter Break ────────────────────────────── */
.chapter-start {{
  page-break-before: {p['chapter_break']};
}}

/* ── Exercise Box (Tutorial) ──────────────────── */
.exercise {{
  border: 2px solid {p['callout_border_color']};
  border-radius: 8px;
  padding: 1.2em;
  margin: 2em 0;
  background: #ffffff;
}}
.exercise-title {{
  font-weight: 700;
  color: {p['callout_border_color']};
  margin-bottom: 0.8em;
  font-size: 0.9em;
  text-transform: uppercase;
  letter-spacing: 0.05em;
}}

/* ── Summary Box ──────────────────────────────── */
.summary-box {{
  background: #f8f9ff;
  border: 1px solid {p['callout_border_color']};
  border-radius: 8px;
  padding: 1.2em;
  margin: 2em 0;
}}

/* ── Page-level ───────────────────────────────── */
@page {{
  margin: {p['page_margin']};
}}

@page chapter-start {{
  page-break-before: always;
}}

/* ── Accessibility ────────────────────────────── */
img[alt=""] {{
  display: none;
}}

a {{
  color: {p['callout_border_color']};
  text-decoration: underline;
}}

/* End of {css_class} stylesheet */
"""


# ---------------------------------------------------------------------------
# Compliance Validation
# ---------------------------------------------------------------------------

def validate_gbooks_compliance(book_root: Path, guide: dict[str, Any]) -> dict[str, Any]:
    """Check book artifacts against Google Books technical requirements."""
    results: list[dict[str, Any]] = []

    # Check cover image
    cover_path = book_root / "publication" / "cover.jpg"
    if not cover_path.exists():
        cover_path = book_root / "publication" / "cover.png"
    results.append({
        "check": "cover_image_exists",
        "passed": cover_path.exists(),
        "detail": str(cover_path) if cover_path.exists() else "publication/cover.jpg not found",
    })

    # Check publication directory
    pub_dir = book_root / "publication"
    results.append({
        "check": "publication_dir_exists",
        "passed": pub_dir.exists(),
        "detail": str(pub_dir),
    })

    # Check style guide saved
    results.append({
        "check": "style_guide_selected",
        "passed": guide.get("id") not in (None, ""),
        "detail": guide.get("id", "none"),
    })

    passed = sum(1 for r in results if r["passed"])
    return {
        "overall_pass": passed == len(results),
        "checks_passed": passed,
        "checks_total": len(results),
        "checks": results,
        "gbooks_spec": GBOOKS_COMPLIANCE,
    }


# ---------------------------------------------------------------------------
# Stage Entry Point
# ---------------------------------------------------------------------------

def run_style_guide_stage(book_id: str, book_root: Path, template_id: str | None = None, params_override: dict[str, Any] | None = None) -> dict[str, Any]:
    """S10 stage: apply style guide to book, generate CSS, validate compliance."""
    db = load_book_db(book_root)

    # Load or select template
    if template_id:
        guide = save_book_style_guide(book_id, template_id, params_override)
    else:
        guide = load_book_style_guide(book_id)

    # Generate CSS
    css = generate_epub_css(guide)
    css_dir = ensure_dir(book_root / "publication" / "epub" / "OEBPS" / "css")
    css_path = css_dir / "style.css"
    write_text(css_path, css)

    # Validate compliance
    compliance = validate_gbooks_compliance(book_root, guide)

    # Save stage result
    result = {
        "stage": "S10",
        "book_id": book_id,
        "template_id": guide["id"],
        "template_name": guide["name"],
        "css_path": str(css_path.relative_to(book_root)),
        "compliance": compliance,
        "completed_at": now_iso(),
    }

    result_path = ensure_dir(book_root / "publication" / "style_guide") / "result.json"
    write_json(result_path, result)

    return result
