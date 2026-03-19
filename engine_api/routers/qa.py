from __future__ import annotations

"""engine.qa — Publication QA endpoints (AG-QA / SQA)."""

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from engine_core.qa_checker import run_publication_qa
from engine_api.deps import resolve_book_root

router = APIRouter(prefix="/engine/qa", tags=["qa"])


class QARunRequest(BaseModel):
    book_id: str


@router.post("/run")
def run_qa(req: QARunRequest):
    """Run the full publication QA check (SQA stage). Returns go/no-go verdict."""
    book_root = resolve_book_root(req.book_id)
    try:
        return run_publication_qa(req.book_id, book_root)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))


@router.get("/report")
def get_report(book_id: str):
    """Return the latest clearance report JSON without re-running QA."""
    from engine_core.common import read_json
    book_root = resolve_book_root(book_id)
    report_path = book_root / "publication" / "qa" / "publication_clearance_report.json"
    payload = read_json(report_path, default=None)
    if payload is None:
        raise HTTPException(status_code=404, detail="No QA report found. Run /engine/qa/run first.")
    return payload


@router.get("/report/md")
def get_report_md(book_id: str):
    """Return the latest QA report as Markdown text."""
    book_root = resolve_book_root(book_id)
    md_path = book_root / "publication" / "qa" / "qa_report.md"
    if not md_path.exists():
        raise HTTPException(status_code=404, detail="No QA report found. Run /engine/qa/run first.")
    return {"book_id": book_id, "content": md_path.read_text(encoding="utf-8")}
