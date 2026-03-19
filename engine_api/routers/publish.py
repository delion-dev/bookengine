from __future__ import annotations

"""engine.publish — Google Books Publication Pipeline Endpoints

Endpoints:
  GET  /engine/publish/style-guides              — style guide catalog
  GET  /engine/publish/style-guide/{book_id}     — current book style guide
  POST /engine/publish/style-guide/{book_id}     — save style guide selection
  GET  /engine/publish/metadata/{book_id}        — EPUB metadata (with preview)
  PUT  /engine/publish/metadata/{book_id}        — save metadata
  POST /engine/publish/keywords/generate/{book_id} — AI keyword generation
  GET  /engine/publish/keywords/{book_id}        — current keywords
  PUT  /engine/publish/keywords/{book_id}        — save keywords manually
  POST /engine/publish/export/{book_id}          — build final EPUB
  GET  /engine/publish/export/{book_id}/status   — last export result
"""

from pathlib import Path
from typing import Any

from fastapi import APIRouter, BackgroundTasks, HTTPException
from fastapi.responses import FileResponse
from pydantic import BaseModel

from engine_api.deps import resolve_book_root

router = APIRouter(prefix="/engine/publish", tags=["publish"])


# ---------------------------------------------------------------------------
# Pydantic Models
# ---------------------------------------------------------------------------

class StyleGuideRequest(BaseModel):
    template_id: str
    params_override: dict[str, Any] | None = None


class MetadataRequest(BaseModel):
    title: str = ""
    subtitle: str = ""
    author: str = ""
    publisher: str = "Self-Published"
    publication_date: str = ""
    language: str = "ko"
    isbn13: str = ""
    google_books_id: str = ""
    description: str = ""
    keywords: list[str] = []
    bisac_code: str = "COM004000"
    thema_code: str = "UYQ"
    age_rating: str = "전체"
    adult_content: bool = False


class KeywordsRequest(BaseModel):
    keywords: list[str]
    longtail_keywords: list[str] = []


# ---------------------------------------------------------------------------
# Style Guide Endpoints
# ---------------------------------------------------------------------------

@router.get("/style-guides")
def list_style_guides():
    """Return all available style guide templates."""
    from engine_core.style_guide import get_style_guides
    return {"style_guides": get_style_guides()}


@router.get("/style-guide/{book_id}")
def get_book_style_guide(book_id: str):
    """Return the current style guide for a book."""
    from engine_core.style_guide import load_book_style_guide
    resolve_book_root(book_id)  # 404 if unknown
    guide = load_book_style_guide(book_id)
    return guide


@router.post("/style-guide/{book_id}")
def save_style_guide(book_id: str, req: StyleGuideRequest):
    """Save style guide selection and generate CSS."""
    from engine_core.style_guide import get_style_guide, save_book_style_guide
    resolve_book_root(book_id)

    if req.template_id not in ("GBOOK-TECH", "GBOOK-ACAD", "GBOOK-BUSI",
                                "GBOOK-NFIC", "GBOOK-TUTO", "GBOOK-MINI", "CUSTOM"):
        raise HTTPException(status_code=400, detail=f"Unknown template_id: {req.template_id}")

    guide = save_book_style_guide(book_id, req.template_id, req.params_override)
    return {"ok": True, "guide": guide}


# ---------------------------------------------------------------------------
# Metadata Endpoints
# ---------------------------------------------------------------------------

@router.get("/metadata/{book_id}")
def get_metadata(book_id: str):
    """Return EPUB metadata with OPF XML preview and category lists."""
    from engine_core.metadata_engine import get_metadata_preview
    resolve_book_root(book_id)
    return get_metadata_preview(book_id)


@router.put("/metadata/{book_id}")
def update_metadata(book_id: str, req: MetadataRequest):
    """Save EPUB metadata. Returns validation result."""
    from engine_core.metadata_engine import save_book_metadata
    resolve_book_root(book_id)

    result = save_book_metadata(book_id, req.model_dump())
    if not result["valid"]:
        # Return 200 with errors so UI can display them inline
        return {
            "ok": False,
            "errors": result["errors"],
            "metadata": result["metadata"],
        }
    return {"ok": True, "errors": [], "metadata": result["metadata"]}


# ---------------------------------------------------------------------------
# Keyword Endpoints
# ---------------------------------------------------------------------------

@router.post("/keywords/generate/{book_id}")
def generate_keywords(book_id: str):
    """Trigger AI keyword generation (synchronous, may take a few seconds)."""
    from engine_core.keyword_generator import generate_keywords_sync
    book_root = resolve_book_root(book_id)
    result = generate_keywords_sync(book_id, book_root)
    return result


@router.get("/keywords/{book_id}")
def get_keywords(book_id: str):
    """Return current saved keywords for a book."""
    from engine_core.keyword_generator import load_keywords
    resolve_book_root(book_id)
    kw = load_keywords(book_id)
    if kw is None:
        return {"keywords": [], "longtail_keywords": [], "source": "none"}
    return kw


@router.put("/keywords/{book_id}")
def update_keywords(book_id: str, req: KeywordsRequest):
    """Save manually edited keywords and sync to metadata."""
    from engine_core.keyword_generator import merge_keywords_to_metadata, save_keywords_manual
    resolve_book_root(book_id)

    if len(req.keywords) > 7:
        raise HTTPException(status_code=400, detail="키워드는 최대 7개입니다.")

    saved = save_keywords_manual(book_id, req.keywords, req.longtail_keywords)
    meta = merge_keywords_to_metadata(book_id)
    return {"ok": True, "keywords": saved, "metadata_updated": True}


# ---------------------------------------------------------------------------
# EPUB Export Endpoints
# ---------------------------------------------------------------------------

@router.post("/export/{book_id}")
def export_epub(book_id: str):
    """Build final EPUB 3.x from publication artifacts."""
    from engine_core.epub_packager import pack_epub
    from engine_core.style_guide import run_style_guide_stage

    book_root = resolve_book_root(book_id)

    # Ensure style guide CSS exists (run S10 if needed)
    css_path = book_root / "publication" / "epub" / "OEBPS" / "css" / "style.css"
    if not css_path.exists():
        run_style_guide_stage(book_id, book_root)

    try:
        result = pack_epub(book_id, book_root)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"EPUB 생성 실패: {e}")

    return result


@router.get("/export/{book_id}/status")
def export_status(book_id: str):
    """Return last EPUB export result."""
    book_root = resolve_book_root(book_id)
    result_path = book_root / "publication" / "epub_export" / "result.json"

    if not result_path.exists():
        return {"status": "not_exported", "epub_path": None}

    from engine_core.common import read_json
    return read_json(result_path)


@router.get("/export/{book_id}/download")
def download_epub(book_id: str):
    """Download the generated EPUB file."""
    book_root = resolve_book_root(book_id)
    result_path = book_root / "publication" / "epub_export" / "result.json"

    if not result_path.exists():
        raise HTTPException(status_code=404, detail="EPUB이 아직 생성되지 않았습니다.")

    from engine_core.common import read_json
    result = read_json(result_path)
    epub_path = Path(result.get("epub_path", ""))

    if not epub_path.exists():
        raise HTTPException(status_code=404, detail="EPUB 파일을 찾을 수 없습니다.")

    return FileResponse(
        path=str(epub_path),
        media_type="application/epub+zip",
        filename=epub_path.name,
    )
