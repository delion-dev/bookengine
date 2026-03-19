from __future__ import annotations

"""engine.mesh — Unified Knowledge Mesh endpoints."""

from fastapi import APIRouter, HTTPException

from engine_core.knowledge_mesh import (
    build_mesh,
    get_bridge_context,
    query_mesh,
    update_chapter_node,
)
from engine_api.deps import resolve_book_root
from engine_api.models import MeshBuildRequest, MeshNodeUpdateRequest, MeshQueryRequest

router = APIRouter(prefix="/engine/mesh", tags=["mesh"])


@router.post("/build")
def build(req: MeshBuildRequest):
    """Full rebuild of the knowledge mesh from current shared_memory."""
    book_root = resolve_book_root(req.book_id)
    try:
        mesh = build_mesh(req.book_id, book_root)
        return {
            "ok": True,
            "node_count": mesh["node_count"],
            "edge_count": len(mesh["dependency_edges"]),
            "thread_count": len(mesh["thematic_threads"]),
        }
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))


@router.get("/bridge")
def get_bridge(book_id: str, chapter_id: str):
    """Return cross-chapter bridge context for the given chapter."""
    book_root = resolve_book_root(book_id)
    try:
        return get_bridge_context(book_root, chapter_id)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))


@router.post("/query")
def query(req: MeshQueryRequest):
    """Keyword search across all mesh nodes and thematic threads."""
    book_root = resolve_book_root(req.book_id)
    try:
        hits = query_mesh(book_root, req.query)
        return {"query": req.query, "hit_count": len(hits), "hits": hits}
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))


@router.post("/node/update")
def update_node(req: MeshNodeUpdateRequest):
    """Incrementally update a single chapter node in the mesh."""
    book_root = resolve_book_root(req.book_id)
    try:
        update_chapter_node(
            book_root,
            req.chapter_id,
            summary=req.summary,
            claims=req.claims,
            unresolved_issues=req.unresolved_issues,
        )
        return {"ok": True, "chapter_id": req.chapter_id}
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))
