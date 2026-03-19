from __future__ import annotations

"""AG-PUB (S11) — EPUB 3.x Packager

Assembles the final EPUB 3.x archive from:
  - Publication-ready chapter markdown files (S9 output)
  - Style guide CSS (S10 output)
  - Cover image
  - EPUB metadata (metadata_engine output)

EPUB 3.x structure produced:
  BookTitle.epub
  ├── mimetype                     (uncompressed, first entry)
  ├── META-INF/
  │   └── container.xml
  └── OEBPS/
      ├── content.opf              (Package Document)
      ├── toc.ncx                  (EPUB 2 compatibility)
      ├── nav.xhtml                (EPUB 3 Navigation Document)
      ├── css/
      │   └── style.css
      ├── images/
      │   ├── cover.jpg
      │   └── ...
      └── chapters/
          ├── chapter_001.xhtml
          └── ...

Google Books compliance:
  - Cover: 1600×2560 px minimum
  - Images: JPEG/PNG/GIF/SVG
  - Font embedding via CSS @font-face
  - NCX + Navigation Document both present
  - File size: <50 MB per chapter
"""

from __future__ import annotations

import hashlib
import re
import shutil
import uuid
import zipfile
from pathlib import Path
from typing import Any
from xml.sax.saxutils import escape as xml_escape

from .common import ensure_dir, now_iso, read_json, read_text, write_json, write_text
from .metadata_engine import load_book_metadata

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

MIMETYPE = "application/epub+zip"
EPUB_NS = "http://www.idpf.org/2007/opf"
DC_NS = "http://purl.org/dc/elements/1.1/"
EPUB3_NS = "http://www.idpf.org/2007/ops"
XHTML_NS = "http://www.w3.org/1999/xhtml"

SUPPORTED_IMAGE_EXTS = {".jpg", ".jpeg", ".png", ".gif", ".svg"}

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            digest.update(chunk)
    return digest.hexdigest()[:16]


def _markdown_to_xhtml(md_text: str, chapter_id: str, title: str, css_rel_path: str = "../css/style.css") -> str:
    """Convert markdown to EPUB-compatible XHTML."""
    try:
        from markdown import markdown as md_render
        body_html = md_render(
            md_text,
            extensions=["tables", "fenced_code", "nl2br", "toc"],
        )
    except ImportError:
        # Minimal fallback if markdown library not available
        body_html = f"<p>{xml_escape(md_text[:500])}...</p>"

    return f"""<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE html>
<html xmlns="{XHTML_NS}"
      xmlns:epub="{EPUB3_NS}"
      xml:lang="ko" lang="ko">
<head>
  <meta charset="UTF-8" />
  <title>{xml_escape(title)}</title>
  <link rel="stylesheet" type="text/css" href="{css_rel_path}" />
</head>
<body epub:type="chapter" class="chapter-start" id="{chapter_id}">
  <section epub:type="chapter">
    {body_html}
  </section>
</body>
</html>
"""


def _build_nav_xhtml(toc_entries: list[dict[str, str]], book_title: str) -> str:
    """Build EPUB 3 Navigation Document (nav.xhtml)."""
    items = "\n".join(
        f'      <li><a href="{e["href"]}">{xml_escape(e["title"])}</a></li>'
        for e in toc_entries
    )
    return f"""<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE html>
<html xmlns="{XHTML_NS}"
      xmlns:epub="{EPUB3_NS}"
      xml:lang="ko" lang="ko">
<head>
  <meta charset="UTF-8" />
  <title>{xml_escape(book_title)} — 목차</title>
</head>
<body>
  <nav epub:type="toc" id="toc">
    <h1>목차</h1>
    <ol>
{items}
    </ol>
  </nav>
</body>
</html>
"""


def _build_ncx(toc_entries: list[dict[str, str]], book_title: str, book_uid: str) -> str:
    """Build EPUB 2 NCX (for compatibility with older readers)."""
    nav_points = ""
    for i, e in enumerate(toc_entries, 1):
        nav_points += f"""  <navPoint id="navPoint-{i}" playOrder="{i}">
    <navLabel><text>{xml_escape(e['title'])}</text></navLabel>
    <content src="{e['href']}"/>
  </navPoint>
"""
    return f"""<?xml version="1.0" encoding="UTF-8"?>
<ncx xmlns="http://www.daisy.org/z3986/2005/ncx/" version="2005-1">
<head>
  <meta name="dtb:uid" content="{book_uid}"/>
  <meta name="dtb:depth" content="1"/>
  <meta name="dtb:totalPageCount" content="0"/>
  <meta name="dtb:maxPageNumber" content="0"/>
</head>
<docTitle><text>{xml_escape(book_title)}</text></docTitle>
<navMap>
{nav_points}</navMap>
</ncx>
"""


def _build_opf(
    book_id: str,
    metadata: dict[str, Any],
    manifest_items: list[dict[str, str]],
    spine_items: list[str],
    cover_id: str | None,
) -> str:
    """Build OPF Package Document (content.opf)."""
    uid = metadata.get("identifier") or f"urn:uuid:{uuid.uuid4()}"
    title = xml_escape(metadata.get("title", book_id))
    author = xml_escape(metadata.get("author", "Unknown"))
    language = metadata.get("language", "ko")
    publisher = xml_escape(metadata.get("publisher", "Self-Published"))
    date = metadata.get("publication_date", now_iso()[:10])
    description = xml_escape(metadata.get("description", ""))
    subjects = metadata.get("keywords", [])

    subject_tags = "\n    ".join(
        f"<dc:subject>{xml_escape(s)}</dc:subject>" for s in subjects
    )

    cover_meta = f'\n    <meta name="cover" content="{cover_id}"/>' if cover_id else ""

    manifest_xml = "\n    ".join(
        f'<item id="{item["id"]}" href="{item["href"]}" media-type="{item["media_type"]}"{" properties=\"" + item["properties"] + "\"" if item.get("properties") else ""}/>'
        for item in manifest_items
    )

    spine_xml = "\n    ".join(
        f'<itemref idref="{sid}"/>' for sid in spine_items
    )

    return f"""<?xml version="1.0" encoding="UTF-8"?>
<package xmlns="{EPUB_NS}"
         xmlns:dc="{DC_NS}"
         version="3.0"
         unique-identifier="BookID">

  <metadata xmlns:dc="{DC_NS}"
            xmlns:opf="http://www.idpf.org/2007/opf">
    <dc:identifier id="BookID">{xml_escape(uid)}</dc:identifier>
    <dc:title>{title}</dc:title>
    <dc:creator>{author}</dc:creator>
    <dc:language>{language}</dc:language>
    <dc:publisher>{publisher}</dc:publisher>
    <dc:date>{date}</dc:date>
    <dc:description>{description}</dc:description>
    {subject_tags}
    <meta property="dcterms:modified">{now_iso().replace('+', 'T').split('T')[0]}T00:00:00Z</meta>{cover_meta}
  </metadata>

  <manifest>
    {manifest_xml}
  </manifest>

  <spine toc="ncx">
    {spine_xml}
  </spine>

</package>
"""


def _build_container_xml() -> str:
    return """<?xml version="1.0" encoding="UTF-8"?>
<container xmlns="urn:oasis:names:tc:opendocument:xmlns:container" version="1.0">
  <rootfiles>
    <rootfile full-path="OEBPS/content.opf" media-type="application/oebps-package+xml"/>
  </rootfiles>
</container>
"""


# ---------------------------------------------------------------------------
# Main Packager
# ---------------------------------------------------------------------------

def pack_epub(
    book_id: str,
    book_root: Path,
    output_dir: Path | None = None,
) -> dict[str, Any]:
    """
    Assemble EPUB 3.x from book publication artifacts.

    Returns dict with epub_path, file_size_mb, chapter_count, compliance.
    """
    pub_dir = book_root / "publication"
    epub_dir = pub_dir / "epub" / "OEBPS"
    chapters_dir = epub_dir / "chapters"
    images_dir = epub_dir / "images"
    css_dir = epub_dir / "css"

    ensure_dir(chapters_dir)
    ensure_dir(images_dir)
    ensure_dir(css_dir)

    metadata = load_book_metadata(book_id)
    book_title = metadata.get("title", book_id)
    book_uid = metadata.get("identifier") or f"urn:uuid:{uuid.uuid4()}"

    # ── Gather chapter markdown files ──────────────────────────────────────
    chapter_files = sorted(
        pub_dir.glob("chapters/*.md"),
        key=lambda p: p.stem,
    )
    if not chapter_files:
        # Fallback: look for draft5/draft6 files
        for ch_dir in sorted((book_root / "chapters").iterdir()):
            if not ch_dir.is_dir():
                continue
            for suffix in ("draft6.md", "draft5.md", "draft4.md"):
                candidate = ch_dir / suffix
                if candidate.exists():
                    chapter_files.append(candidate)
                    break

    # ── Convert markdown → XHTML ───────────────────────────────────────────
    manifest_items: list[dict[str, str]] = []
    spine_items: list[str] = []
    toc_entries: list[dict[str, str]] = []

    # Nav document (always first in manifest, not in spine-order)
    manifest_items.append({
        "id": "nav",
        "href": "nav.xhtml",
        "media_type": "application/xhtml+xml",
        "properties": "nav",
    })

    # NCX
    manifest_items.append({
        "id": "ncx",
        "href": "toc.ncx",
        "media_type": "application/x-dtbncx+xml",
        "properties": "",
    })

    # CSS
    css_path = css_dir / "style.css"
    if not css_path.exists():
        # Generate default CSS if style guide stage hasn't run
        from .style_guide import generate_epub_css, get_style_guide
        default_css = generate_epub_css(get_style_guide("GBOOK-TECH"))
        write_text(css_path, default_css)

    manifest_items.append({
        "id": "css-main",
        "href": "css/style.css",
        "media_type": "text/css",
        "properties": "",
    })

    # Chapters
    for idx, ch_file in enumerate(chapter_files, 1):
        ch_stem = ch_file.stem.replace(" ", "_").lower()
        ch_id = f"chapter_{idx:03d}"
        href = f"chapters/{ch_id}.xhtml"

        md_text = read_text(ch_file)

        # Extract title from first H1
        title_match = re.search(r"^#\s+(.+)$", md_text, re.MULTILINE)
        ch_title = title_match.group(1).strip() if title_match else f"Chapter {idx}"

        xhtml = _markdown_to_xhtml(md_text, ch_id, ch_title)
        write_text(chapters_dir / f"{ch_id}.xhtml", xhtml)

        manifest_items.append({
            "id": ch_id,
            "href": href,
            "media_type": "application/xhtml+xml",
            "properties": "",
        })
        spine_items.append(ch_id)
        toc_entries.append({"href": href, "title": ch_title})

    # ── Cover image ────────────────────────────────────────────────────────
    cover_id = None
    for ext in (".jpg", ".jpeg", ".png"):
        cover_src = pub_dir / f"cover{ext}"
        if cover_src.exists():
            cover_dst = images_dir / f"cover{ext}"
            shutil.copy2(cover_src, cover_dst)
            media_type = "image/jpeg" if ext in (".jpg", ".jpeg") else "image/png"
            manifest_items.append({
                "id": "cover-image",
                "href": f"images/cover{ext}",
                "media_type": media_type,
                "properties": "cover-image",
            })
            cover_id = "cover-image"
            break

    # ── Additional images ──────────────────────────────────────────────────
    for img_path in sorted((pub_dir / "images").glob("*") if (pub_dir / "images").exists() else []):
        if img_path.suffix.lower() in SUPPORTED_IMAGE_EXTS:
            dst = images_dir / img_path.name
            shutil.copy2(img_path, dst)
            ext = img_path.suffix.lower()
            mt_map = {".jpg": "image/jpeg", ".jpeg": "image/jpeg", ".png": "image/png",
                      ".gif": "image/gif", ".svg": "image/svg+xml"}
            img_id = f"img-{img_path.stem}"
            manifest_items.append({
                "id": img_id,
                "href": f"images/{img_path.name}",
                "media_type": mt_map.get(ext, "image/jpeg"),
                "properties": "",
            })

    # ── Write EPUB structure files ─────────────────────────────────────────
    opf = _build_opf(book_id, metadata, manifest_items, spine_items, cover_id)
    nav = _build_nav_xhtml(toc_entries, book_title)
    ncx = _build_ncx(toc_entries, book_title, book_uid)

    write_text(epub_dir / "content.opf", opf)
    write_text(epub_dir / "nav.xhtml", nav)
    write_text(epub_dir / "toc.ncx", ncx)

    meta_inf = ensure_dir(epub_dir.parent / "META-INF")
    write_text(meta_inf / "container.xml", _build_container_xml())

    # ── Zip into .epub ─────────────────────────────────────────────────────
    safe_title = re.sub(r"[^\w\-]", "_", book_title)[:40]
    epub_name = f"{safe_title}_{book_id}.epub"

    if output_dir is None:
        output_dir = pub_dir
    ensure_dir(output_dir)
    epub_path = output_dir / epub_name

    epub_root = epub_dir.parent  # .../publication/epub/

    with zipfile.ZipFile(epub_path, "w", zipfile.ZIP_DEFLATED) as zf:
        # mimetype MUST be first and uncompressed
        zf.writestr(zipfile.ZipInfo("mimetype"), MIMETYPE,
                    compress_type=zipfile.ZIP_STORED)

        for file_path in epub_root.rglob("*"):
            if file_path.is_file() and file_path.name != "mimetype":
                arcname = file_path.relative_to(epub_root)
                zf.write(file_path, arcname)

    file_size_mb = epub_path.stat().st_size / (1024 * 1024)

    # ── Compliance summary ─────────────────────────────────────────────────
    compliance = {
        "epub_version": "3.x",
        "has_nav_document": True,
        "has_ncx": True,
        "has_cover": cover_id is not None,
        "chapter_count": len(chapter_files),
        "file_size_mb": round(file_size_mb, 2),
        "size_ok": file_size_mb < 50,
    }

    result = {
        "stage": "S11",
        "book_id": book_id,
        "epub_path": str(epub_path),
        "epub_name": epub_name,
        "file_size_mb": round(file_size_mb, 2),
        "chapter_count": len(chapter_files),
        "toc_entries": len(toc_entries),
        "compliance": compliance,
        "completed_at": now_iso(),
    }

    result_path = ensure_dir(pub_dir / "epub_export") / "result.json"
    write_json(result_path, result)

    return result
