from __future__ import annotations

"""engine.publish — Google Books Publication Pipeline Endpoints

Endpoints:
  GET  /engine/publish/style-guides                  — style guide catalog
  GET  /engine/publish/style-guide/{book_id}         — current book style guide
  POST /engine/publish/style-guide/{book_id}         — save style guide selection
  GET  /engine/publish/metadata/{book_id}            — EPUB metadata (with preview)
  PUT  /engine/publish/metadata/{book_id}            — save metadata
  POST /engine/publish/keywords/generate/{book_id}   — AI keyword generation
  GET  /engine/publish/keywords/{book_id}            — current keywords
  PUT  /engine/publish/keywords/{book_id}            — save keywords manually
  POST /engine/publish/export/{book_id}              — build final EPUB (async)
  GET  /engine/publish/export/{book_id}/status       — export job status
  GET  /engine/publish/export/{book_id}/download     — download EPUB
"""

import threading
import uuid
from datetime import datetime
from pathlib import Path
from typing import Any

from fastapi import APIRouter, BackgroundTasks, HTTPException
from fastapi.responses import FileResponse
from pydantic import BaseModel

from engine_api.deps import resolve_book_root

router = APIRouter(prefix="/engine/publish", tags=["publish"])

# ---------------------------------------------------------------------------
# Export Job Store (in-memory)
# ---------------------------------------------------------------------------
_export_jobs: dict[str, dict[str, Any]] = {}
_export_lock = threading.Lock()


def _run_export(job_id: str, book_id: str, book_root: Path) -> None:
    with _export_lock:
        _export_jobs[job_id]["status"] = "running"
        _export_jobs[job_id]["started_at"] = datetime.now().isoformat(timespec="seconds")
    try:
        from engine_core.epub_packager import pack_epub
        from engine_core.style_guide import run_style_guide_stage

        css_path = book_root / "publication" / "epub" / "OEBPS" / "css" / "style.css"
        if not css_path.exists():
            run_style_guide_stage(book_id, book_root)

        result = pack_epub(book_id, book_root)
        with _export_lock:
            _export_jobs[job_id].update({
                "status": "completed",
                "result": result,
                "completed_at": datetime.now().isoformat(timespec="seconds"),
            })
    except Exception as exc:
        with _export_lock:
            _export_jobs[job_id].update({
                "status": "failed",
                "error": str(exc),
                "completed_at": datetime.now().isoformat(timespec="seconds"),
            })


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
def export_epub(book_id: str, background_tasks: BackgroundTasks):
    """Submit EPUB build job (async). Returns job_id immediately.
    Poll GET /export/{book_id}/status for progress."""
    book_root = resolve_book_root(book_id)

    job_id = f"epub-{uuid.uuid4().hex[:12]}"
    job: dict[str, Any] = {
        "job_id": job_id,
        "book_id": book_id,
        "status": "queued",
        "result": None,
        "error": None,
        "started_at": None,
        "completed_at": None,
        "created_at": datetime.now().isoformat(timespec="seconds"),
    }
    with _export_lock:
        _export_jobs[job_id] = job

    background_tasks.add_task(_run_export, job_id, book_id, book_root)
    return {"job_id": job_id, "status": "queued",
            "poll_url": f"/engine/publish/export/{book_id}/status"}


@router.get("/export/{book_id}/status")
def export_status(book_id: str):
    """Return latest EPUB export job status."""
    resolve_book_root(book_id)

    # Find most recent job for this book
    with _export_lock:
        jobs = [j for j in _export_jobs.values() if j["book_id"] == book_id]

    if not jobs:
        # Fallback: check persisted result file
        book_root = resolve_book_root(book_id)
        result_path = book_root / "publication" / "epub_export" / "result.json"
        if result_path.exists():
            from engine_core.common import read_json
            return {"status": "completed", **read_json(result_path)}
        return {"status": "not_exported", "epub_path": None}

    latest = sorted(jobs, key=lambda j: j["created_at"], reverse=True)[0]
    return latest


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
