from __future__ import annotations

import hashlib
import os
import re
import shutil
import tempfile
import textwrap
import uuid
import zipfile
from dataclasses import dataclass
from html import escape
from pathlib import Path
from typing import Any

from PIL import Image, ImageDraw, ImageFont

REPO_ROOT = Path(__file__).resolve().parent.parent
CACHE_ROOT = REPO_ROOT / ".cache"
CACHE_ROOT.mkdir(parents=True, exist_ok=True)
TEMP_ROOT = CACHE_ROOT / "tmp"
TEMP_ROOT.mkdir(parents=True, exist_ok=True)
os.environ.setdefault("XDG_CACHE_HOME", str(CACHE_ROOT))
os.environ.setdefault("TMP", str(TEMP_ROOT))
os.environ.setdefault("TEMP", str(TEMP_ROOT))
os.environ.setdefault("TMPDIR", str(TEMP_ROOT))
tempfile.tempdir = str(TEMP_ROOT)

from markdown import markdown as render_markdown
from weasyprint import HTML

from .book_state import load_book_db
from .common import ensure_dir, now_iso, read_json, read_text, write_json, write_text
from .contracts import validate_inputs
from .gates import evaluate_gate
from .manuscript_integrity import sanitize_reader_manuscript
from .stage import transition_stage
from .work_order import issue_work_order


PDF_FONT_FAMILY = "NanumGothic"   # PIL cover rendering (TTF required)
EPUB_BODY_FONT  = "Pretendard"    # EPUB text — modern geometric sans-serif
COVER_SIZE = (1400, 2000)
SUPPORTED_EPUB_IMAGE_SUFFIXES = {".gif", ".jpeg", ".jpg", ".png", ".svg"}
MD_LINK_PATTERN = re.compile(r"(!?\[[^\]]*\]\()([^)]+)(\))")


@dataclass
class PublicationChapter:
    chapter_id: str
    title: str
    source_path: Path
    source_stage: str
    markdown: str


@dataclass
class EpubMeta:
    identifier: str
    title: str
    language: str
    creator: str
    publisher: str
    description: str
    subjects: list[str]
    modified_timestamp: str


@dataclass(frozen=True)
class EpubManifestEntry:
    item_id: str
    href: str
    media_type: str
    properties: str = ""

    def to_opf_line(self) -> str:
        props = f' properties="{self.properties}"' if self.properties else ""
        return f'    <item id="{self.item_id}" href="{self.href}" media-type="{self.media_type}"{props}/>'


@dataclass
class EpubStagingDirs:
    root: Path
    meta_inf: Path
    epub_root: Path
    text_dir: Path
    styles_dir: Path
    fonts_dir: Path
    images_dir: Path
    assets_dir: Path


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(65536), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _chapter_payloads(book_root: Path, book_db: dict[str, Any]) -> list[PublicationChapter]:
    chapters: list[PublicationChapter] = []
    for chapter_id in book_db["chapter_sequence"]:
        title = book_db["chapters"][chapter_id]["title"]
        s8a_status = book_db["chapters"][chapter_id]["stages"]["S8A"]["status"]
        preferred_draft6 = book_root / "manuscripts" / "_draft6" / f"{chapter_id}_draft6.md"
        fallback_draft5 = book_root / "manuscripts" / "_draft5" / f"{chapter_id}_draft5.md"
        if s8a_status == "completed" and preferred_draft6.exists():
            source_path = preferred_draft6
            source_stage = "S8A"
        else:
            source_path = fallback_draft5
            source_stage = "S8"
        if not source_path.exists():
            raise FileNotFoundError(f"Missing publication manuscript for {chapter_id}: {source_path}")
        chapters.append(
            PublicationChapter(
                chapter_id=chapter_id,
                title=title,
                source_path=source_path,
                source_stage=source_stage,
                markdown=read_text(source_path),
            )
        )
    return chapters


def _strip_anchor_comments(text: str) -> str:
    return re.sub(r"<!--.*?-->", "", text, flags=re.DOTALL)


def _normalize_callouts(text: str) -> str:
    return re.sub(
        r"^> \[!(\w+)\]\s*$",
        lambda match: f"> **{match.group(1).title()}**",
        text,
        flags=re.MULTILINE,
    )


def _publication_ready_markdown(text: str, chapter_title: str) -> str:
    sanitized, _ = sanitize_reader_manuscript(text)
    cleaned = _strip_anchor_comments(sanitized)
    lines = cleaned.splitlines()
    if lines and lines[0].startswith("# DRAFT"):
        lines[0] = f"# {chapter_title}"
    cleaned = "\n".join(lines).strip() + "\n"
    return _normalize_callouts(cleaned)


def _rewrite_markdown_paths(
    markdown_text: str,
    source_path: Path,
    target_dir: Path,
    book_root: Path,
    mapped_publication_assets_root: Path,
) -> str:
    publication_assets_root = (book_root / "publication" / "assets").resolve()

    def replace(match: re.Match[str]) -> str:
        prefix, raw_path, suffix = match.groups()
        path_value = raw_path.strip()
        if path_value.startswith(("http://", "https://", "mailto:", "#", "data:")):
            return match.group(0)

        resolved = (source_path.parent / path_value).resolve()
        if resolved.is_relative_to(publication_assets_root):
            mapped = mapped_publication_assets_root / resolved.relative_to(publication_assets_root)
        else:
            mapped = resolved
        relative = os.path.relpath(mapped, target_dir).replace("\\", "/")
        return f"{prefix}{relative}{suffix}"

    return MD_LINK_PATTERN.sub(replace, markdown_text)


def _markdown_extensions() -> list[str]:
    return ["extra", "tables", "fenced_code", "footnotes", "sane_lists"]


def _markdown_to_html(markdown_text: str) -> str:
    return render_markdown(markdown_text, extensions=_markdown_extensions())


def _safe_slug(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", value.lower()).strip("-")


def _font_sources() -> dict[str, Path]:
    """Return font paths for cover image rendering (PIL — TTF required)."""
    nanum_root = REPO_ROOT / "platform" / "fonts" / "NanumGothic-main"
    candidates = {
        "regular": [
            nanum_root / "NanumGothic.ttf",
            Path(r"C:\Windows\Fonts\NanumGothic.ttf"),
        ],
        "bold": [
            nanum_root / "NanumGothicBold.ttf",
            Path(r"C:\Windows\Fonts\NanumGothicBold.ttf"),
        ],
    }
    selected: dict[str, Path] = {}
    for weight, paths in candidates.items():
        source = next((path for path in paths if path.exists()), None)
        if source is None:
            raise FileNotFoundError(f"Required publication font not found for {weight}: {paths}")
        selected[weight] = source
    return selected


def _epub_font_sources() -> dict[str, Path]:
    """Return Pretendard OTF paths for EPUB embedding.

    Weight map:
      light    → 300  (captions, footnotes)
      regular  → 400  (body text)
      semibold → 600  (sub-headings, emphasis)
      bold     → 700  (h1, chapter titles)
    """
    pretendard_root = REPO_ROOT / "platform" / "fonts" / "Pretendard-main"
    candidates = {
        "light":    pretendard_root / "Pretendard-Light.otf",
        "regular":  pretendard_root / "Pretendard-Regular.otf",
        "semibold": pretendard_root / "Pretendard-SemiBold.otf",
        "bold":     pretendard_root / "Pretendard-Bold.otf",
    }
    selected: dict[str, Path] = {}
    for weight, path in candidates.items():
        if not path.exists():
            raise FileNotFoundError(f"Pretendard font not found: {path}")
        selected[weight] = path
    return selected


def _ensure_google_books_fonts(book_root: Path) -> dict[str, Path]:
    font_dir = ensure_dir(book_root / "publication" / "assets" / "fonts" / "google_books")
    copied: dict[str, Path] = {}
    selected_names = {path.name for path in _font_sources().values()}
    for stale in font_dir.glob("*"):
        if stale.is_file() and stale.name not in selected_names:
            stale.unlink()
    for weight, source in _font_sources().items():
        if not source.exists():
            raise FileNotFoundError(f"Required Google Books font not found: {source}")
        target = font_dir / source.name
        if not target.exists() or source.stat().st_mtime > target.stat().st_mtime:
            shutil.copy2(source, target)
        copied[weight] = target
    return copied


def _load_font(path: Path, size: int) -> ImageFont.FreeTypeFont:
    return ImageFont.truetype(str(path), size=size)


def _wrapped_lines(text: str, width: int) -> list[str]:
    wrapped = textwrap.wrap(text, width=width, break_long_words=False, break_on_hyphens=False)
    return wrapped or [text]


def _draw_centered_lines(
    draw: ImageDraw.ImageDraw,
    lines: list[str],
    font: ImageFont.FreeTypeFont,
    *,
    x_center: int,
    top: int,
    fill: tuple[int, int, int],
    line_gap: int,
) -> int:
    current_top = top
    for line in lines:
        bbox = draw.textbbox((0, 0), line, font=font)
        width = bbox[2] - bbox[0]
        height = bbox[3] - bbox[1]
        draw.text((x_center - width / 2, current_top), line, font=font, fill=fill)
        current_top += height + line_gap
    return current_top


def _cover_title_parts(working_title: str) -> tuple[str, str]:
    if ":" in working_title:
        title, subtitle = working_title.split(":", 1)
        return title.strip(), subtitle.strip()
    return working_title.strip(), ""


# epub_style_guide → BISAC/Google Books subject category mapping
_EPUB_STYLE_SUBJECTS: dict[str, list[str]] = {
    "GBOOK-TECH": [
        "Computers / Artificial Intelligence",
        "Software Development & Engineering",
        "Business & Economics / Information Management",
    ],
    "GBOOK-ACAD": ["Education / General", "Academic Reference"],
    "GBOOK-BUSI": ["Business & Economics / Management", "Business & Economics / General"],
    "GBOOK-NFIC": ["Fiction / Literary", "Fiction / Cultural Heritage"],
    "GBOOK-TUTO": ["Computers / General", "Self-Help / General"],
    "GBOOK-MINI": ["Computers / General"],
    "GBOOK-CUSTOM": [],
    "GBOOK-TRAVEL": ["Travel / Korea", "Essays / Travel", "Cultural Heritage"],
    "GBOOK-KIDS": ["Juvenile Fiction / General", "Children's Literature / Korean"],
    "GBOOK-LANG": ["Language Arts & Disciplines / Language Learning", "Foreign Language Study / Korean"],
}


def _seo_keywords(book_config: dict[str, Any], book_db: dict[str, Any]) -> list[str]:
    """Build SEO keyword list from BOOK_CONFIG fields and chapter titles.

    No book-specific hardcoded terms — derives entirely from the config so
    every book gets correct keywords without code changes.
    Priority: explicit seo.keywords override → display_name + working_title
    + chapter titles (first 6).
    """
    # Explicit override wins
    override = book_config.get("seo", {}).get("keywords", [])
    if override:
        return list(override)[:12]

    candidates: list[str] = []
    working_title = book_config.get("working_title", "")
    display_name = book_config.get("display_name", "")

    # Title splits (before / after colon) yield useful sub-keywords
    for raw in [working_title, display_name]:
        if raw:
            candidates.append(raw.strip())
            if ":" in raw:
                for part in raw.split(":", 1):
                    p = part.strip()
                    if p:
                        candidates.append(p)

    for chapter_id in book_db["chapter_sequence"][:6]:
        candidates.append(book_db["chapters"][chapter_id]["title"])

    seen: set[str] = set()
    keywords: list[str] = []
    for item in candidates:
        normalized = item.strip()
        if not normalized or normalized in seen:
            continue
        seen.add(normalized)
        keywords.append(normalized)
        if len(keywords) >= 12:
            break
    return keywords


def _chapter_teasers(chapters: list[PublicationChapter], limit: int = 4) -> list[str]:
    teasers: list[str] = []
    for chapter in chapters[:limit]:
        teasers.append(chapter.title)
    return teasers


def _derive_subjects(book_config: dict[str, Any]) -> list[str]:
    """Derive BISAC subjects from epub_style_guide; falls back to seo.subjects override."""
    override = book_config.get("seo", {}).get("subjects", [])
    if override:
        return list(override)
    style_guide = book_config.get("epub_style_guide", "")
    return list(_EPUB_STYLE_SUBJECTS.get(style_guide, []))


def _derive_descriptions(book_config: dict[str, Any]) -> tuple[str, str]:
    """Build short + long descriptions from BOOK_CONFIG.

    Priority for each field:
      1. Explicit seo.short_description / seo.long_description override
      2. Derived from audience_segments (focus + reader_payoff)
      3. Plain working_title fallback
    """
    seo_override = book_config.get("seo", {})
    display_name = book_config.get("display_name") or book_config.get("working_title", "")
    segments: list[dict[str, Any]] = book_config.get("audience_segments", [])

    # Short description
    short = seo_override.get("short_description", "")
    if not short:
        if segments:
            focus = segments[0].get("focus", "")
            short = f"{display_name}. {focus}를 위한 실전 가이드."
        else:
            short = display_name

    # Long description
    long = seo_override.get("long_description", "")
    if not long:
        if segments:
            payoffs = [seg.get("reader_payoff", "") for seg in segments if seg.get("reader_payoff")]
            long = "\n\n".join(payoffs) if payoffs else display_name
        else:
            long = display_name

    return short, long


def _build_seo_pack(
    book_config: dict[str, Any],
    book_db: dict[str, Any],
    chapters: list[PublicationChapter],
) -> tuple[dict[str, Any], str]:
    title, subtitle = _cover_title_parts(book_config["working_title"])
    keywords = _seo_keywords(book_config, book_db)
    subjects = _derive_subjects(book_config)
    short_description, long_description = _derive_descriptions(book_config)
    teaser_text = "; ".join(_chapter_teasers(chapters))
    seo_payload = {
        "version": "1.0",
        "book_id": book_config["book_id"],
        "slug": book_config["book_id"],
        "title": title,
        "subtitle": subtitle,
        "full_title": book_config["working_title"],
        "language": book_config.get("language", "ko-KR"),
        "audience": book_config.get("audience", "general"),
        "creator": book_config.get("creator", "Codex Book Engine"),
        "publisher": book_config.get("publisher", "Codex Book Engine"),
        "short_description": short_description,
        "long_description": long_description,
        "keywords": keywords,
        "subjects": subjects,
        "chapter_teasers": _chapter_teasers(chapters),
        "html_meta": {
            "description": short_description,
            "keywords": ", ".join(keywords),
            "og_title": book_config["working_title"],
            "og_description": short_description,
            "og_type": "book",
        },
        "epub_meta": {
            "description": long_description.replace("\n", " ").strip(),
            "subjects": subjects,
        },
        "store_copy": {
            "headline": title,
            "one_line_pitch": short_description,
            "body": long_description,
            "highlights": teaser_text,
        },
    }
    store_listing = "\n".join(
        [
            f"# STORE_LISTING: {book_config['working_title']}",
            "",
            "## Headline",
            seo_payload["store_copy"]["headline"],
            "",
            "## One-line Pitch",
            seo_payload["store_copy"]["one_line_pitch"],
            "",
            "## Long Description",
            seo_payload["store_copy"]["body"],
            "",
            "## Chapter Highlights",
            *[f"- {item}" for item in seo_payload["chapter_teasers"]],
        ]
    ) + "\n"
    return seo_payload, store_listing


def _html_meta_tags(seo_payload: dict[str, Any]) -> str:
    meta = seo_payload.get("html_meta", {})
    return "\n".join(
        [
            f'    <meta name="description" content="{escape(meta.get("description", ""))}" />',
            f'    <meta name="keywords" content="{escape(meta.get("keywords", ""))}" />',
            f'    <meta property="og:title" content="{escape(meta.get("og_title", seo_payload.get("full_title", "")))}" />',
            f'    <meta property="og:description" content="{escape(meta.get("og_description", ""))}" />',
            f'    <meta property="og:type" content="{escape(meta.get("og_type", "book"))}" />',
        ]
    )


def _generate_front_cover(
    book_root: Path,
    book_config: dict[str, Any],
    font_paths: dict[str, Path],
) -> dict[str, Any]:
    output_dir = ensure_dir(book_root / "publication" / "output")
    cover_path = output_dir / f"{book_config['book_id']}_frontcover.png"
    width, height = COVER_SIZE

    image = Image.new("RGB", (width, height), "#f7f1e8")
    draw = ImageDraw.Draw(image)

    draw.rectangle((0, 0, width, 260), fill="#bf6b36")
    draw.rectangle((0, height - 220, width, height), fill="#1f4a53")
    draw.ellipse((width - 500, 180, width - 90, 590), fill="#e0a06c")
    draw.ellipse((90, height - 700, 610, height - 180), fill="#d7e0d6")
    draw.rectangle((110, 340, width - 110, height - 300), outline="#8d6c4a", width=4)

    title, subtitle = _cover_title_parts(book_config["working_title"])
    display_name = book_config.get("display_name", book_config["book_id"])

    label_font = _load_font(font_paths["bold"], 44)
    title_font = _load_font(font_paths["bold"], 94)
    subtitle_font = _load_font(font_paths["regular"], 42)
    meta_font = _load_font(font_paths["regular"], 30)

    draw.text((120, 96), display_name, font=label_font, fill="#fff9f2")
    top = _draw_centered_lines(
        draw,
        _wrapped_lines(title, 13),
        title_font,
        x_center=width // 2,
        top=520,
        fill=(52, 39, 27),
        line_gap=20,
    )
    if subtitle:
        top += 34
        _draw_centered_lines(
            draw,
            _wrapped_lines(subtitle, 21),
            subtitle_font,
            x_center=width // 2,
            top=top,
            fill=(83, 67, 51),
            line_gap=14,
        )

    footer_lines = [
        "Google Play Books profile",
        "EPUB reflow + PDF original pages",
    ]
    footer_top = height - 180
    for index, line in enumerate(footer_lines):
        draw.text((120, footer_top + index * 42), line, font=meta_font, fill="#eef4f5")

    image.save(cover_path, format="PNG", optimize=True)
    return {
        "path": cover_path,
        "width": width,
        "height": height,
        "megapixels": round((width * height) / 1_000_000, 3),
    }


def _write_html_css(output_dir: Path, font_paths: dict[str, Path]) -> Path:
    css_path = output_dir / "google_books_book.css"
    _ = font_paths
    css = f"""@page {{
  size: A5 portrait;
  margin: 18mm 16mm 20mm 16mm;
}}

@page cover {{
  size: A5 portrait;
  margin: 0;
}}

html {{
  color: #2b241f;
  font-family: "{PDF_FONT_FAMILY}", sans-serif;
  line-height: 1.72;
}}

body {{
  margin: 0;
  background: #f7f2ea;
  color: #2b241f;
  font-size: 11pt;
}}

.cover-page {{
  page: cover;
  min-height: 100vh;
  display: flex;
  align-items: center;
  justify-content: center;
  background: #efe5d8;
}}

.cover-page img {{
  display: block;
  width: 100%;
  height: auto;
}}

.title-page,
.chapter,
.appendix {{
  background: #fffdfa;
  padding: 0;
}}

.title-page {{
  page-break-after: always;
}}

.toc {{
  page-break-after: always;
  background: #fffdfa;
}}

.toc ol {{
  padding-left: 1.2rem;
}}

.chapter,
.appendix {{
  page-break-before: always;
}}

h1, h2, h3 {{
  color: #1c3940;
  line-height: 1.3;
}}

h1 {{
  font-size: 22pt;
  margin: 0 0 14pt;
  bookmark-level: 1;
}}

h2 {{
  font-size: 14pt;
  margin-top: 18pt;
  margin-bottom: 8pt;
  bookmark-level: 2;
}}

p, li {{
  widows: 2;
  orphans: 2;
}}

a {{
  color: #0d5a66;
  text-decoration: none;
}}

img, svg {{
  max-width: 100%;
  height: auto;
  break-inside: avoid;
}}

pre {{
  padding: 12px 14px;
  overflow-wrap: anywhere;
  white-space: pre-wrap;
  background: #f4efe8;
  border: 1px solid #d6c5ae;
}}

code {{
  font-size: 0.95em;
}}

blockquote {{
  margin: 16px 0;
  padding: 0 14px;
  border-left: 4px solid #bf6b36;
  color: #4d3d2f;
  background: #fcf7f1;
}}

table {{
  width: 100%;
  border-collapse: collapse;
  margin: 14px 0 18px;
  font-size: 0.95em;
}}

th, td {{
  border: 1px solid #d8cab8;
  padding: 8px 10px;
  vertical-align: top;
}}

th {{
  background: #f1e7d9;
}}

.meta-list {{
  list-style: none;
  padding: 0;
}}

.meta-list li {{
  margin: 4px 0;
}}
"""
    write_text(css_path, css)
    return css_path


def _epub_css() -> str:
    """Generate EPUB CSS for AI/SW tech books.

    Font stack  : Pretendard (embedded OTF) — modern geometric Korean sans-serif
    Color palette: cool blue-gray tech tone (replaces warm travel-book palette)
    Extras       : code blocks, callout boxes, layer-label sections, figure captions
    """
    f = EPUB_BODY_FONT
    return f"""/* BookEngine EPUB — GBOOK-TECH (Pretendard) */

/* ── @font-face ──────────────────────────────── */
@font-face {{
  font-family: "{f}";
  src: url("../fonts/Pretendard-Light.otf") format("opentype");
  font-weight: 300;
  font-style: normal;
}}

@font-face {{
  font-family: "{f}";
  src: url("../fonts/Pretendard-Regular.otf") format("opentype");
  font-weight: 400;
  font-style: normal;
}}

@font-face {{
  font-family: "{f}";
  src: url("../fonts/Pretendard-SemiBold.otf") format("opentype");
  font-weight: 600;
  font-style: normal;
}}

@font-face {{
  font-family: "{f}";
  src: url("../fonts/Pretendard-Bold.otf") format("opentype");
  font-weight: 700;
  font-style: normal;
}}

/* ── Base ────────────────────────────────────── */
body {{
  margin: 0;
  padding: 0 4%;
  color: #1e2233;
  font-family: "{f}", "NanumGothic", sans-serif;
  font-weight: 400;
  font-size: 1em;
  line-height: 1.78;
  -epub-hyphens: auto;
  hyphens: auto;
}}

section {{
  margin: 0 0 1.5em;
}}

/* ── Headings ────────────────────────────────── */
h1, h2, h3, h4 {{
  font-family: "{f}", "NanumGothic", sans-serif;
  line-height: 1.3;
  color: #0f1f4b;
  margin-top: 1.6em;
  margin-bottom: 0.5em;
  page-break-after: avoid;
}}

h1 {{
  font-size: 1.65em;
  font-weight: 700;
  border-bottom: 2px solid #dde3f0;
  padding-bottom: 0.3em;
}}

h2 {{
  font-size: 1.2em;
  font-weight: 600;
  color: #1a3272;
}}

h3 {{
  font-size: 1.05em;
  font-weight: 600;
  color: #2c4fa3;
}}

h4 {{
  font-size: 0.95em;
  font-weight: 600;
  color: #3d5cb8;
  text-transform: uppercase;
  letter-spacing: 0.04em;
}}

/* ── Paragraph ───────────────────────────────── */
p {{
  margin: 0 0 0.9em;
  text-align: justify;
  orphans: 2;
  widows: 2;
}}

/* ── Code ────────────────────────────────────── */
code, kbd, samp {{
  font-family: "JetBrains Mono", "Courier New", monospace;
  font-size: 0.88em;
  background: #eef1f8;
  color: #2c3a6e;
  padding: 0.15em 0.4em;
  border-radius: 3px;
}}

pre {{
  font-family: "JetBrains Mono", "Courier New", monospace;
  font-size: 0.85em;
  background: #1b2033;
  color: #cdd6f4;
  padding: 1em 1.2em;
  border-radius: 6px;
  overflow-x: auto;
  white-space: pre-wrap;
  overflow-wrap: anywhere;
  page-break-inside: avoid;
  margin: 1.4em 0;
  line-height: 1.55;
}}

pre code {{
  background: none;
  color: inherit;
  padding: 0;
  font-size: inherit;
}}

/* ── Callout / Note / Warning (CO anchor) ────── */
.callout, .note, .tip, .warning {{
  border-left: 4px solid #3b5bdb;
  background: #eef2ff;
  padding: 0.9em 1.1em;
  margin: 1.4em 0;
  border-radius: 0 6px 6px 0;
  page-break-inside: avoid;
}}

.warning {{
  border-left-color: #e03131;
  background: #fff5f5;
}}

.tip {{
  border-left-color: #2f9e44;
  background: #ebfbee;
}}

.callout-title, .note-title, .tip-title, .warning-title {{
  font-weight: 700;
  font-size: 0.88em;
  text-transform: uppercase;
  letter-spacing: 0.05em;
  margin-bottom: 0.4em;
  color: #3b5bdb;
}}

.warning .callout-title {{ color: #e03131; }}
.tip .callout-title     {{ color: #2f9e44; }}

/* ── Summary Box (SB anchor) ─────────────────── */
.summary-box {{
  background: #f0f4ff;
  border: 1px solid #bac8ff;
  border-top: 3px solid #4263eb;
  border-radius: 6px;
  padding: 1em 1.2em;
  margin: 1.6em 0;
  page-break-inside: avoid;
}}

.summary-box-title {{
  font-weight: 700;
  font-size: 0.9em;
  color: #364fc7;
  margin-bottom: 0.5em;
}}

/* ── 4-Layer Section Labels ──────────────────── */
.layer-label {{
  display: inline-block;
  font-size: 0.75em;
  font-weight: 700;
  text-transform: uppercase;
  letter-spacing: 0.08em;
  padding: 0.2em 0.6em;
  border-radius: 4px;
  margin-bottom: 0.6em;
}}

.layer-sdlc     {{ background: #e7f5ff; color: #1971c2; border: 1px solid #74c0fc; }}
.layer-metagpt  {{ background: #f3f0ff; color: #7048e8; border: 1px solid #b197fc; }}
.layer-claude   {{ background: #ebfbee; color: #2f9e44; border: 1px solid #8ce99a; }}
.layer-case     {{ background: #fff9db; color: #e67700; border: 1px solid #ffd43b; }}

/* ── Tables ──────────────────────────────────── */
table {{
  width: 100%;
  border-collapse: collapse;
  margin: 1.4em 0;
  font-size: 0.92em;
  page-break-inside: avoid;
}}

th {{
  background: #e8ecf8;
  font-weight: 600;
  color: #1a3272;
  text-align: left;
  padding: 0.55em 0.75em;
  border: 1px solid #c5cee8;
}}

td {{
  padding: 0.45em 0.75em;
  border: 1px solid #d0d8ee;
  vertical-align: top;
}}

tr:nth-child(even) td {{
  background: #f7f9ff;
}}

/* ── Figures & Images ────────────────────────── */
figure {{
  text-align: center;
  margin: 1.8em 0;
  page-break-inside: avoid;
}}

img, svg {{
  display: block;
  max-width: 100%;
  height: auto;
  margin: 1em auto;
}}

figcaption {{
  font-size: 0.82em;
  font-weight: 300;
  color: #5c6b9a;
  margin-top: 0.4em;
  font-style: italic;
}}

/* ── Blockquote ──────────────────────────────── */
blockquote {{
  margin: 1.4em 0;
  padding: 0.6em 1.2em;
  border-left: 4px solid #748ffc;
  background: #f0f4ff;
  color: #364fc7;
  font-style: italic;
}}

/* ── Lists ───────────────────────────────────── */
ul, ol {{
  margin: 0.7em 0 0.7em 1.4em;
  padding: 0;
}}

li {{
  margin-bottom: 0.3em;
  line-height: 1.65;
}}

/* ── Links ───────────────────────────────────── */
a {{
  color: #3b5bdb;
  text-decoration: none;
}}

/* ── Cover ───────────────────────────────────── */
.cover-image {{
  width: 100%;
  margin: 0;
  padding: 0;
}}

/* ── Chapter break ───────────────────────────── */
.chapter-start {{
  page-break-before: always;
}}

/* ── Accessibility ───────────────────────────── */
img[alt=""] {{
  display: none;
}}
"""


def _html_shell(
    *,
    title: str,
    css_href: str,
    cover_href: str,
    book_config: dict[str, Any],
    seo_payload: dict[str, Any],
    chapters: list[tuple[str, str, str]],
    appendix_html: str,
) -> str:
    toc_items = "\n".join(
        f'<li><a href="#chapter-{escape(chapter_id)}">{escape(chapter_title)}</a></li>'
        for chapter_id, chapter_title, _ in chapters
    )
    chapter_blocks = "\n".join(
        f'<section id="chapter-{escape(chapter_id)}" class="chapter">{chapter_html}</section>'
        for chapter_id, _, chapter_html in chapters
    )
    return f"""<!DOCTYPE html>
<html lang="{escape(book_config.get('language', 'ko-KR'))}">
  <head>
    <meta charset="utf-8" />
    <meta name="viewport" content="width=device-width, initial-scale=1" />
    <title>{escape(title)}</title>
{_html_meta_tags(seo_payload)}
    <link rel="stylesheet" href="{escape(css_href)}" />
  </head>
  <body>
    <section class="cover-page">
      <img src="{escape(cover_href)}" alt="{escape(title)} cover" />
    </section>
    <section class="title-page">
      <h1>{escape(title)}</h1>
      <ul class="meta-list">
        <li>Book ID: <code>{escape(book_config['book_id'])}</code></li>
        <li>Language: {escape(book_config.get('language', 'ko-KR'))}</li>
        <li>Audience: {escape(book_config.get('audience', 'general'))}</li>
        <li>Profile: Google Play Books reflow EPUB + original-pages PDF</li>
      </ul>
    </section>
    <nav class="toc" aria-label="Table of contents">
      <h1>Table of Contents</h1>
      <ol>
        {toc_items}
        <li><a href="#appendix-reference-index">Reference Index</a></li>
      </ol>
    </nav>
    {chapter_blocks}
    <section id="appendix-reference-index" class="appendix">
      {appendix_html}
    </section>
  </body>
</html>
"""


def _write_html_book(
    book_root: Path,
    book_config: dict[str, Any],
    seo_payload: dict[str, Any],
    chapters: list[PublicationChapter],
    cover_path: Path,
    css_path: Path,
) -> Path:
    output_dir = ensure_dir(book_root / "publication" / "output")
    html_path = output_dir / f"{book_config['book_id']}.html"
    appendix_markdown = read_text(book_root / "publication" / "appendix" / "REFERENCE_INDEX.md")
    appendix_html = _markdown_to_html(appendix_markdown)

    chapter_payloads: list[tuple[str, str, str]] = []
    for chapter in chapters:
        normalized = _publication_ready_markdown(chapter.markdown, chapter.title)
        rewritten = _rewrite_markdown_paths(
            normalized,
            chapter.source_path,
            output_dir,
            book_root,
            mapped_publication_assets_root=(book_root / "publication" / "assets").resolve(),
        )
        chapter_payloads.append((chapter.chapter_id, chapter.title, _markdown_to_html(rewritten)))

    html = _html_shell(
        title=book_config["working_title"],
        css_href=css_path.name,
        cover_href=cover_path.name,
        book_config=book_config,
        seo_payload=seo_payload,
        chapters=chapter_payloads,
        appendix_html=appendix_html,
    )
    write_text(html_path, html)
    return html_path


def _write_pdf(html_path: Path, output_path: Path) -> Path:
    renderer = HTML(filename=str(html_path), base_url=str(html_path.parent))
    try:
        renderer.write_pdf(str(output_path))
        return output_path
    except PermissionError:
        timestamp = now_iso().replace(":", "").replace("+", "_")
        fallback_path = output_path.with_name(f"{output_path.stem}_{timestamp}{output_path.suffix}")
        renderer.write_pdf(str(fallback_path))
        return fallback_path


def _media_type(path: Path) -> str:
    mapping = {
        ".xhtml": "application/xhtml+xml",
        ".css": "text/css",
        ".svg": "image/svg+xml",
        ".png": "image/png",
        ".jpg": "image/jpeg",
        ".jpeg": "image/jpeg",
        ".gif": "image/gif",
        ".ttf": "font/ttf",
        ".otf": "font/otf",
    }
    return mapping[path.suffix.lower()]


def _copy_tree_files(source_dir: Path, target_dir: Path) -> list[Path]:
    copied: list[Path] = []
    if not source_dir.exists():
        return copied
    for source in source_dir.rglob("*"):
        if source.is_dir():
            continue
        target = target_dir / source.relative_to(source_dir)
        ensure_dir(target.parent)
        shutil.copy2(source, target)
        copied.append(target)
    return copied


def _epub_text_xhtml(title: str, css_href: str, body_html: str) -> str:
    return f"""<?xml version="1.0" encoding="utf-8"?>
<html xmlns="http://www.w3.org/1999/xhtml" xml:lang="ko" lang="ko">
  <head>
    <title>{escape(title)}</title>
    <link rel="stylesheet" type="text/css" href="{escape(css_href)}" />
  </head>
  <body>
    <section>
      {body_html}
    </section>
  </body>
</html>
"""


def _epub_cover_xhtml(title: str) -> str:
    return f"""<?xml version="1.0" encoding="utf-8"?>
<html xmlns="http://www.w3.org/1999/xhtml" xml:lang="ko" lang="ko">
  <head>
    <title>{escape(title)}</title>
    <link rel="stylesheet" type="text/css" href="styles/book.css" />
  </head>
  <body>
    <section class="cover-image">
      <img src="images/cover.png" alt="{escape(title)} cover" />
    </section>
  </body>
</html>
"""


def _epub_nav_xhtml(book_config: dict[str, Any], chapters: list[PublicationChapter]) -> str:
    items = "\n".join(
        f'        <li><a href="text/{chapter.chapter_id}.xhtml">{escape(chapter.title)}</a></li>'
        for chapter in chapters
    )
    return f"""<?xml version="1.0" encoding="utf-8"?>
<html xmlns="http://www.w3.org/1999/xhtml" xmlns:epub="http://www.idpf.org/2007/ops" xml:lang="ko" lang="ko">
  <head>
    <title>{escape(book_config["working_title"])}</title>
  </head>
  <body>
    <nav epub:type="toc" id="toc">
      <h1>Table of Contents</h1>
      <ol>
{items}
        <li><a href="text/appendix.xhtml">Reference Index</a></li>
      </ol>
    </nav>
  </body>
</html>
"""


def _epub_package_opf(
    *,
    meta: EpubMeta,
    chapter_files: list[Path],
    font_entries: list[EpubManifestEntry],
    asset_files: list[Path],
) -> str:
    """Generate EPUB 3.0 package.opf.

    Font manifest entries are derived from the injected ``font_entries`` list
    (OCP: adding/removing weights requires only changing the font source dict
    upstream, not this function).
    """
    subject_lines = "\n".join(
        f"    <dc:subject>{escape(s)}</dc:subject>"
        for s in meta.subjects
    )
    manifest_lines = [
        EpubManifestEntry("nav", "nav.xhtml", "application/xhtml+xml", "nav").to_opf_line(),
        EpubManifestEntry("cover-image", "images/cover.png", "image/png", "cover-image").to_opf_line(),
        EpubManifestEntry("cover-page", "cover.xhtml", "application/xhtml+xml").to_opf_line(),
        EpubManifestEntry("css", "styles/book.css", "text/css").to_opf_line(),
    ]
    for entry in font_entries:
        manifest_lines.append(entry.to_opf_line())

    spine_lines = ['    <itemref idref="cover-page"/>']

    for chapter_file in chapter_files:
        chapter_id = chapter_file.stem
        entry = EpubManifestEntry(chapter_id, f"text/{chapter_file.name}", "application/xhtml+xml")
        manifest_lines.append(entry.to_opf_line())
        spine_lines.append(f'    <itemref idref="{chapter_id}"/>')

    manifest_lines.append(
        EpubManifestEntry("appendix", "text/appendix.xhtml", "application/xhtml+xml").to_opf_line()
    )
    spine_lines.append('    <itemref idref="appendix"/>')

    for asset_file in asset_files:
        rel = asset_file.as_posix().split("EPUB/", 1)[1]
        asset_id = _safe_slug(rel.replace("/", "-"))
        manifest_lines.append(EpubManifestEntry(asset_id, rel, _media_type(asset_file)).to_opf_line())

    return f"""<?xml version="1.0" encoding="utf-8"?>
<package xmlns="http://www.idpf.org/2007/opf" version="3.0" unique-identifier="pub-id">
  <metadata xmlns:dc="http://purl.org/dc/elements/1.1/">
    <dc:identifier id="pub-id">{escape(meta.identifier)}</dc:identifier>
    <dc:title>{escape(meta.title)}</dc:title>
    <dc:language>{escape(meta.language)}</dc:language>
    <dc:creator>{escape(meta.creator)}</dc:creator>
    <dc:publisher>{escape(meta.publisher)}</dc:publisher>
    <dc:description>{escape(meta.description)}</dc:description>
{subject_lines}
    <meta property="dcterms:modified">{meta.modified_timestamp}</meta>
    <meta name="cover" content="cover-image"/>
  </metadata>
  <manifest>
{chr(10).join(manifest_lines)}
  </manifest>
  <spine>
{chr(10).join(spine_lines)}
  </spine>
</package>
"""


# ── EPUB Build: Single-Responsibility Steps ──────────────────────────────


def _setup_epub_staging(book_id: str) -> EpubStagingDirs:
    """Create and return staging directory tree. Cleans any prior run."""
    root = CACHE_ROOT / "epub_staging" / book_id
    if root.exists():
        shutil.rmtree(root, ignore_errors=True)
    return EpubStagingDirs(
        root=root,
        meta_inf=ensure_dir(root / "META-INF"),
        epub_root=ensure_dir(root / "EPUB"),
        text_dir=ensure_dir(root / "EPUB" / "text"),
        styles_dir=ensure_dir(root / "EPUB" / "styles"),
        fonts_dir=ensure_dir(root / "EPUB" / "fonts"),
        images_dir=ensure_dir(root / "EPUB" / "images"),
        assets_dir=ensure_dir(root / "EPUB" / "assets"),
    )


def _write_epub_skeleton(dirs: EpubStagingDirs) -> None:
    """Write mimetype and META-INF/container.xml."""
    write_text(dirs.root / "mimetype", "application/epub+zip")
    write_text(
        dirs.meta_inf / "container.xml",
        """<?xml version="1.0" encoding="UTF-8"?>
<container version="1.0" xmlns="urn:oasis:names:tc:opendocument:xmlns:container">
  <rootfiles>
    <rootfile full-path="EPUB/package.opf" media-type="application/oebps-package+xml"/>
  </rootfiles>
</container>
""",
    )


def _embed_epub_fonts(
    dirs: EpubStagingDirs,
    epub_font_sources: dict[str, Path],
) -> list[EpubManifestEntry]:
    """Copy EPUB fonts into staging; return OPF manifest entries.

    The source dict drives both file copying and manifest generation (OCP):
    adding or removing a weight only requires changing the source dict upstream.
    """
    entries: list[EpubManifestEntry] = []
    for weight, src in epub_font_sources.items():
        shutil.copy2(src, dirs.fonts_dir / src.name)
        entries.append(EpubManifestEntry(f"font-{weight}", f"fonts/{src.name}", _media_type(src)))
    return entries


def _embed_cover_image(dirs: EpubStagingDirs, cover_path: Path) -> None:
    """Copy cover image into EPUB images dir."""
    shutil.copy2(cover_path, dirs.images_dir / "cover.png")


def _embed_epub_assets(
    dirs: EpubStagingDirs,
    publication_assets_root: Path,
) -> list[Path]:
    """Copy generated publication assets; return list of copied paths."""
    return _copy_tree_files(
        publication_assets_root / "generated",
        dirs.assets_dir / "generated",
    )


def _assemble_epub_text(
    dirs: EpubStagingDirs,
    chapters: list[PublicationChapter],
    book_root: Path,
    appendix_md: str,
) -> list[Path]:
    """Convert chapters + appendix to XHTML; write into text_dir; return chapter file list."""
    write_text(dirs.styles_dir / "book.css", _epub_css())

    chapter_files: list[Path] = []
    for chapter in chapters:
        normalized = _publication_ready_markdown(chapter.markdown, chapter.title)
        rewritten = _rewrite_markdown_paths(
            normalized,
            chapter.source_path,
            dirs.text_dir,
            book_root,
            mapped_publication_assets_root=dirs.assets_dir.resolve(),
        )
        chapter_html = _markdown_to_html(rewritten)
        chapter_path = dirs.text_dir / f"{chapter.chapter_id}.xhtml"
        write_text(chapter_path, _epub_text_xhtml(chapter.title, "../styles/book.css", chapter_html))
        chapter_files.append(chapter_path)

    appendix_html = _markdown_to_html(appendix_md)
    write_text(
        dirs.text_dir / "appendix.xhtml",
        _epub_text_xhtml("Reference Index", "../styles/book.css", appendix_html),
    )
    return chapter_files


def _write_epub_nav_and_opf(
    dirs: EpubStagingDirs,
    meta: EpubMeta,
    book_config: dict[str, Any],
    chapters: list[PublicationChapter],
    chapter_files: list[Path],
    font_entries: list[EpubManifestEntry],
    asset_files: list[Path],
) -> None:
    """Write cover.xhtml, nav.xhtml, and package.opf into staging."""
    write_text(dirs.epub_root / "cover.xhtml", _epub_cover_xhtml(meta.title))
    write_text(dirs.epub_root / "nav.xhtml", _epub_nav_xhtml(book_config, chapters))
    write_text(
        dirs.epub_root / "package.opf",
        _epub_package_opf(
            meta=meta,
            chapter_files=chapter_files,
            font_entries=font_entries,
            asset_files=asset_files,
        ),
    )


def _zip_epub_archive(dirs: EpubStagingDirs, epub_path: Path) -> None:
    """Package staging directory into a valid EPUB ZIP archive, then clean up staging."""
    with zipfile.ZipFile(epub_path, "w") as archive:
        archive.write(dirs.root / "mimetype", "mimetype", compress_type=zipfile.ZIP_STORED)
        for path in sorted(dirs.root.rglob("*")):
            if path.is_dir() or path.name == "mimetype":
                continue
            archive.write(
                path,
                path.relative_to(dirs.root).as_posix(),
                compress_type=zipfile.ZIP_DEFLATED,
            )
    shutil.rmtree(dirs.root, ignore_errors=True)


def _build_epub(
    *,
    book_root: Path,
    book_config: dict[str, Any],
    seo_payload: dict[str, Any],
    chapters: list[PublicationChapter],
    font_paths: dict[str, Path],
    epub_font_sources: dict[str, Path],
    cover_path: Path,
    output_dir: Path,
) -> dict[str, Any]:
    """Orchestrate EPUB assembly via single-responsibility steps.

    font_paths        — NanumGothic TTF paths (cover image / PDF rendering only, not EPUB-embedded)
    epub_font_sources — injected font map for EPUB embedding (DIP: resolved by caller, not here)
    """
    epub_path = output_dir / f"{book_config['book_id']}.epub"
    identifier = f"urn:uuid:{uuid.uuid5(uuid.NAMESPACE_URL, book_config['book_id'])}"

    meta = EpubMeta(
        identifier=identifier,
        title=book_config["working_title"],
        language=book_config.get("language", "ko-KR"),
        creator=book_config.get("creator", "BookEngine"),
        publisher=book_config.get("publisher", "BookEngine"),
        description=seo_payload.get("epub_meta", {}).get("description", ""),
        subjects=seo_payload.get("epub_meta", {}).get("subjects", []),
        modified_timestamp=now_iso().replace("+09:00", "Z"),
    )

    appendix_md = read_text(book_root / "publication" / "appendix" / "REFERENCE_INDEX.md")

    dirs = _setup_epub_staging(book_config["book_id"])
    _write_epub_skeleton(dirs)
    font_entries = _embed_epub_fonts(dirs, epub_font_sources)
    _embed_cover_image(dirs, cover_path)
    asset_files = _embed_epub_assets(dirs, (book_root / "publication" / "assets").resolve())
    chapter_files = _assemble_epub_text(dirs, chapters, book_root, appendix_md)
    _write_epub_nav_and_opf(dirs, meta, book_config, chapters, chapter_files, font_entries, asset_files)
    _zip_epub_archive(dirs, epub_path)

    return {
        "path": epub_path,
        "identifier": identifier,
    }


def _extract_pending_note(markup: str) -> str:
    match = re.search(r"\*Pending:\*\s*(.+?)(?:\n|$)", markup or "")
    if not match:
        return ""
    return match.group(1).strip().rstrip(".")


def _visual_asset_status(book_root: Path, book_db: dict[str, Any]) -> dict[str, Any]:
    structured = 0
    placeholder = 0
    placeholder_with_asset = 0
    placeholder_missing_asset = 0
    placeholder_by_mode: dict[str, int] = {}
    placeholder_chapters: dict[str, int] = {}
    placeholder_details: list[dict[str, Any]] = []
    for chapter_id in book_db["chapter_sequence"]:
        bundle_path = book_root / "manuscripts" / "_draft4" / f"{chapter_id}_visual_bundle.json"
        bundle = read_json(bundle_path, default={})
        chapter_title = book_db["chapters"].get(chapter_id, {}).get("title", chapter_id)
        for anchor in bundle.get("anchors", []):
            if anchor.get("render_status") == "placeholder_rendered":
                placeholder += 1
                asset_mode = anchor.get("asset_mode", "unknown")
                placeholder_by_mode[asset_mode] = placeholder_by_mode.get(asset_mode, 0) + 1
                placeholder_chapters[chapter_id] = placeholder_chapters.get(chapter_id, 0) + 1
                asset_path_value = anchor.get("asset_path", "")
                asset_exists = bool(asset_path_value) and Path(asset_path_value).exists()
                if asset_exists:
                    placeholder_with_asset += 1
                else:
                    placeholder_missing_asset += 1
                placeholder_details.append(
                    {
                        "chapter_id": chapter_id,
                        "chapter_title": chapter_title,
                        "anchor_id": anchor.get("anchor_id", ""),
                        "asset_mode": asset_mode,
                        "appendix_ref_id": anchor.get("appendix_ref_id", ""),
                        "provenance_status": anchor.get("provenance_status", ""),
                        "asset_path": asset_path_value,
                        "asset_exists": asset_exists,
                        "pending_note": _extract_pending_note(anchor.get("markup", "")),
                    }
                )
            else:
                structured += 1
    return {
        "structured_rendered": structured,
        "placeholder_rendered": placeholder,
        "placeholder_with_asset": placeholder_with_asset,
        "placeholder_missing_asset": placeholder_missing_asset,
        "placeholder_by_mode": placeholder_by_mode,
        "placeholder_chapters": placeholder_chapters,
        "placeholder_details": placeholder_details,
    }


def _metadata_validation(book_config: dict[str, Any], chapter_count: int) -> dict[str, Any]:
    required_keys = ["book_id", "display_name", "working_title", "language", "chapter_count", "creator", "publisher"]
    missing = [key for key in required_keys if key not in book_config]
    return {
        "passed": not missing and book_config.get("chapter_count") == chapter_count,
        "required_keys": required_keys,
        "missing_keys": missing,
        "chapter_count_matches": book_config.get("chapter_count") == chapter_count,
    }


def _seo_validation(seo_payload: dict[str, Any], store_listing_path: Path) -> dict[str, Any]:
    required_keys = ["full_title", "short_description", "long_description", "keywords", "subjects", "html_meta", "epub_meta"]
    missing = [key for key in required_keys if key not in seo_payload or not seo_payload.get(key)]
    return {
        "passed": not missing and store_listing_path.exists(),
        "required_keys": required_keys,
        "missing_keys": missing,
        "store_listing_exists": store_listing_path.exists(),
    }


def _inspect_epub(epub_path: Path) -> dict[str, Any]:
    checks = {
        "mimetype": False,
        "container": False,
        "package": False,
        "nav": False,
        "cover_xhtml": False,
        "cover_image": False,
        "front_cover_reference": False,
        "fonts_embedded": False,
        "supported_image_types_only": True,
    }
    font_files: list[str] = []
    with zipfile.ZipFile(epub_path) as archive:
        members = archive.namelist()
        checks["mimetype"] = members[:1] == ["mimetype"]
        checks["container"] = "META-INF/container.xml" in members
        checks["package"] = "EPUB/package.opf" in members
        checks["nav"] = "EPUB/nav.xhtml" in members
        checks["cover_xhtml"] = "EPUB/cover.xhtml" in members
        checks["cover_image"] = "EPUB/images/cover.png" in members
        font_files = [member for member in members if member.startswith("EPUB/fonts/")]
        checks["fonts_embedded"] = bool(font_files)
        if "EPUB/package.opf" in members:
            opf = archive.read("EPUB/package.opf").decode("utf-8")
            checks["front_cover_reference"] = 'properties="cover-image"' in opf and 'href="images/cover.png"' in opf
        image_members = [
            Path(member)
            for member in members
            if member.startswith("EPUB/assets/") or member.startswith("EPUB/images/")
        ]
        for member in image_members:
            if member.suffix.lower() not in SUPPORTED_EPUB_IMAGE_SUFFIXES:
                checks["supported_image_types_only"] = False
                break
    return {
        "checks": checks,
        "font_count": len(font_files),
    }


def _inspect_pdf(pdf_path: Path) -> dict[str, Any]:
    content = pdf_path.read_bytes()
    return {
        "signature_valid": content.startswith(b"%PDF-"),
        "nanum_regular_detected": b"NanumGothic" in content,
        "nanum_bold_detected": b"NanumGothicBold" in content or b"NanumGothic" in content,
    }


def _inspect_html_render(html_path: Path) -> dict[str, Any]:
    content = read_text(html_path)
    return {
        "mermaid_code_block_count": content.count('class="language-mermaid"'),
        "anchor_slot_residue_count": content.count("[ANCHOR_SLOT:"),
        "meta_block_residue_count": content.count("<!-- META_START"),
    }


def _platform_validation(
    *,
    book_root: Path,
    book_db: dict[str, Any],
    html_path: Path,
    epub_path: Path,
    pdf_path: Path,
    cover_info: dict[str, Any],
    visual_asset_status: dict[str, int],
) -> dict[str, Any]:
    html_info = _inspect_html_render(html_path)
    epub_info = _inspect_epub(epub_path)
    pdf_info = _inspect_pdf(pdf_path)
    appendix_exists = (book_root / "publication" / "appendix" / "REFERENCE_INDEX.md").exists()
    completed_s8a_chapters = [
        chapter_id
        for chapter_id, chapter in book_db["chapters"].items()
        if chapter["stages"]["S8A"]["status"] == "completed"
    ]
    all_s8a_complete = len(completed_s8a_chapters) == len(book_db["chapters"])
    warnings: list[str] = []
    if completed_s8a_chapters:
        warnings.append(f"s8a_optional_applied:{','.join(completed_s8a_chapters)}")
    if visual_asset_status["placeholder_rendered"] > 0:
        warnings.append(f"placeholder_assets_remaining:{visual_asset_status['placeholder_rendered']}")
    if cover_info["megapixels"] > 3.2:
        warnings.append("cover_above_google_recommended_3.2_megapixels")
    if html_info["mermaid_code_block_count"] > 0:
        warnings.append(f"raw_mermaid_code_blocks:{html_info['mermaid_code_block_count']}")
    if html_info["anchor_slot_residue_count"] > 0:
        warnings.append(f"anchor_slot_residue:{html_info['anchor_slot_residue_count']}")
    if html_info["meta_block_residue_count"] > 0:
        warnings.append(f"meta_block_residue:{html_info['meta_block_residue_count']}")

    passed = (
        appendix_exists
        and all(epub_info["checks"].values())
        and pdf_info["signature_valid"]
        and html_info["mermaid_code_block_count"] == 0
        and html_info["anchor_slot_residue_count"] == 0
        and html_info["meta_block_residue_count"] == 0
    )
    return {
        "passed": passed,
        "mode": "google_play_books_profile",
        "all_s8a_complete": all_s8a_complete,
        "completed_s8a_chapters": completed_s8a_chapters,
        "appendix_exists": appendix_exists,
        "html_checks": html_info,
        "epub_checks": epub_info["checks"],
        "pdf_checks": pdf_info,
        "cover_checks": {
            "width_px": cover_info["width"],
            "height_px": cover_info["height"],
            "under_3200px_limit": cover_info["width"] <= 3200 and cover_info["height"] <= 3200,
            "under_3_2_megapixels": cover_info["megapixels"] <= 3.2,
        },
        "warnings": warnings,
        "placeholder_summary": {
            "remaining": visual_asset_status["placeholder_rendered"],
            "with_asset": visual_asset_status.get("placeholder_with_asset", 0),
            "missing_asset": visual_asset_status.get("placeholder_missing_asset", 0),
            "by_mode": visual_asset_status.get("placeholder_by_mode", {}),
        },
    }


def run_publication(
    book_id: str,
    book_root: Path,
) -> dict[str, Any]:
    contract_status = validate_inputs(book_id, book_root, "S9")
    if not contract_status["valid"]:
        raise FileNotFoundError(f"S9 inputs missing: {contract_status['missing_inputs']}")

    book_db = load_book_db(book_root)
    current_status = book_db["book_level_stages"]["S9"]["status"]
    if current_status == "gate_failed":
        transition_stage(book_root, "S9", "pending", note="AG-06 publication rerun requested.")
        transition_stage(book_root, "S9", "in_progress", note="AG-06 publication restarted.")
    elif current_status == "completed":
        transition_stage(book_root, "S9", "in_progress", note="AG-06 publication rerun for hardened output.")
    elif current_status != "in_progress":
        transition_stage(book_root, "S9", "in_progress", note="AG-06 publication started.")

    book_config = read_json(book_root / "_master" / "BOOK_CONFIG.json", default=None)
    if book_config is None:
        raise FileNotFoundError("BOOK_CONFIG.json not found for S9 publication.")
    book_config.setdefault("creator", "Codex Book Engine")
    book_config.setdefault("publisher", "Codex Book Engine")

    output_dir = ensure_dir(book_root / "publication" / "output")
    font_paths = _ensure_google_books_fonts(book_root)
    cover_info = _generate_front_cover(book_root, book_config, font_paths)
    css_path = _write_html_css(output_dir, font_paths)
    chapters = _chapter_payloads(book_root, book_db)
    seo_payload, store_listing = _build_seo_pack(book_config, book_db, chapters)
    seo_path = output_dir / "seo_metadata.json"
    store_listing_path = output_dir / "store_listing.md"
    write_json(seo_path, seo_payload)
    write_text(store_listing_path, store_listing)
    html_path = _write_html_book(book_root, book_config, seo_payload, chapters, cover_info["path"], css_path)
    pdf_path = _write_pdf(html_path, output_dir / f"{book_config['book_id']}.pdf")
    epub_info = _build_epub(
        book_root=book_root,
        book_config=book_config,
        seo_payload=seo_payload,
        chapters=chapters,
        font_paths=font_paths,
        epub_font_sources=_epub_font_sources(),
        cover_path=cover_info["path"],
        output_dir=output_dir,
    )

    visual_asset_status = _visual_asset_status(book_root, book_db)
    metadata_validation = _metadata_validation(book_config, len(chapters))
    seo_validation = _seo_validation(seo_payload, store_listing_path)
    platform_validation = _platform_validation(
        book_root=book_root,
        book_db=book_db,
        html_path=html_path,
        epub_path=epub_info["path"],
        pdf_path=pdf_path,
        cover_info=cover_info,
        visual_asset_status=visual_asset_status,
    )

    manifest_path = output_dir / "publication_manifest.json"
    manifest = {
        "version": "1.3",
        "generated_at": now_iso(),
        "book_id": book_id,
        "working_title": book_config["working_title"],
        "language": book_config.get("language", "ko-KR"),
        "chapter_count": len(chapters),
        "artifacts": {
            "html": {"path": str(html_path), "sha256": _sha256(html_path)},
            "css": {"path": str(css_path), "sha256": _sha256(css_path)},
            "cover": {
                "path": str(cover_info["path"]),
                "sha256": _sha256(cover_info["path"]),
                "width_px": cover_info["width"],
                "height_px": cover_info["height"],
            },
            "epub": {"path": str(epub_info["path"]), "sha256": _sha256(epub_info["path"])},
            "pdf": {"path": str(pdf_path), "sha256": _sha256(pdf_path)},
            "seo": {"path": str(seo_path), "sha256": _sha256(seo_path)},
            "store_listing": {"path": str(store_listing_path), "sha256": _sha256(store_listing_path)},
        },
        "publication_source_layers": {
            "default_stage": "S8",
            "optional_polish_stage": "S8A",
            "chapters": [
                {
                    "chapter_id": chapter.chapter_id,
                    "title": chapter.title,
                    "source_stage": chapter.source_stage,
                    "source_path": str(chapter.source_path),
                }
                for chapter in chapters
            ],
        },
        "validation": {
            "metadata_validation": metadata_validation,
            "seo_validation": seo_validation,
            "platform_validation": platform_validation,
        },
        "visual_asset_status": visual_asset_status,
        "google_play_books_profile": {
            "epub_target": "reflowable_epub",
            "pdf_target": "original_pages_pdf",
            "epub_embedded_fonts": [src.name for src in _epub_font_sources().values()],
            "pdf_cover_font": PDF_FONT_FAMILY,
            "front_cover_embedded_in_epub": True,
            "separate_cover_file_generated": True,
        },
        "epub_info": {
            "path": str(epub_info["path"]),
            "identifier": epub_info["identifier"],
            "asset_count": len(list((book_root / "publication" / "assets" / "generated").glob("*"))),
        },
        "seo_info": {
            "keywords": seo_payload["keywords"],
            "subjects": seo_payload["subjects"],
        },
        "pdf_info": {
            "path": str(pdf_path),
            "font_family": PDF_FONT_FAMILY,
            "page_orientation": "portrait",
        },
    }
    write_json(manifest_path, manifest)
    declared_outputs = [
        str(epub_info["path"]),
        str(pdf_path),
        str(cover_info["path"]),
        str(manifest_path),
        str(seo_path),
        str(store_listing_path),
    ]

    gate_result = evaluate_gate(book_id, book_root, "S9")
    if not gate_result["passed"]:
        transition_stage(book_root, "S9", "gate_failed", note=str(gate_result))
        return {
            "stage_id": "S9",
            "status": "gate_failed",
            "gate_result": gate_result,
            "outputs": declared_outputs,
        }

    transition_stage(book_root, "S9", "completed", note="AG-06 publication completed.")
    work_order = issue_work_order(book_id, book_root)
    return {
        "stage_id": "S9",
        "status": "completed",
        "profile": "google_play_books",
        "outputs": declared_outputs,
        "gate_result": gate_result,
        "work_order": {
            "order_id": work_order["order_id"],
            "priority_queue_size": len(work_order["priority_queue"]),
            "blocked_items": len(work_order["blocked_items"]),
            "gate_failures": len(work_order["gate_failures"]),
        },
    }
