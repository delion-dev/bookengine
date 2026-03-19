from __future__ import annotations

"""AG-UKM — Unified Knowledge Mesh

Builds and maintains a cross-chapter knowledge graph that captures:
  - Key claims and conclusions per chapter
  - Forward/backward narrative dependencies
  - Unresolved questions that bridge chapters
  - Thematic threads (characters, events, concepts) that span the book

The mesh is persisted in shared_memory/knowledge_mesh.json and is consulted
by S4/S5/S8A context pack builders to inject relevant bridge context into each
chapter's model prompt, preventing narrative inconsistencies.

Public API:
  - build_mesh(book_id, book_root) → dict          # full rebuild from shared_memory
  - update_chapter_node(book_root, chapter_id, ...) # incremental update
  - get_bridge_context(book_root, chapter_id)       # context pack slice for a chapter
  - query_mesh(book_root, query)                     # keyword search across nodes
"""

from pathlib import Path
from typing import Any

from .common import ensure_dir, now_iso, read_json, write_json
from .book_state import load_book_db
from .memory import load_shared_memory


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

MESH_VERSION = "1.0"
_MAX_BRIDGE_CLAIMS = 5       # per upstream chapter
_MAX_BRIDGE_CHAPTERS = 3     # how many upstream chapters to include
_MAX_THREAD_ENTRIES = 20     # per thematic thread


# ---------------------------------------------------------------------------
# Mesh file helpers
# ---------------------------------------------------------------------------

def mesh_path(book_root: Path) -> Path:
    return book_root / "shared_memory" / "knowledge_mesh.json"


def _load_mesh(book_root: Path) -> dict[str, Any]:
    return read_json(mesh_path(book_root), default=None) or _empty_mesh()


def _save_mesh(book_root: Path, mesh: dict[str, Any]) -> None:
    write_json(mesh_path(book_root), mesh)


def _empty_mesh() -> dict[str, Any]:
    return {
        "version": MESH_VERSION,
        "generated_at": now_iso(),
        "updated_at": now_iso(),
        "nodes": {},
        "dependency_edges": [],
        "thematic_threads": {},
        "open_questions": [],
    }


# ---------------------------------------------------------------------------
# Node builders
# ---------------------------------------------------------------------------

def _node_from_chapter_memory(chapter_memory: dict[str, Any]) -> dict[str, Any]:
    """Convert a chapter_memory entry into a knowledge mesh node."""
    return {
        "chapter_id": chapter_memory.get("chapter_id", ""),
        "summary": chapter_memory.get("summary", ""),
        "claims": chapter_memory.get("claims", []),
        "unresolved_issues": chapter_memory.get("unresolved_issues", []),
        "citations_summary": chapter_memory.get("citations_summary", []),
        "visual_notes": chapter_memory.get("visual_notes", []),
        "updated_at": now_iso(),
    }


def _extract_thematic_threads(
    chapter_sequence: list[str],
    nodes: dict[str, dict[str, Any]],
) -> dict[str, list[dict[str, Any]]]:
    """Build thematic thread index from claims/issues across all chapters.

    A thread is a named concept that appears in multiple chapter nodes.
    Simple heuristic: shared significant words across claims.
    """
    threads: dict[str, list[dict[str, Any]]] = {}
    for chapter_id in chapter_sequence:
        node = nodes.get(chapter_id)
        if not node:
            continue
        for claim in node.get("claims", []):
            words = set(
                w.lower().strip(".,;:\"'()")
                for w in claim.split()
                if len(w) > 3
            )
            for word in words:
                threads.setdefault(word, [])
                entries = threads[word]
                if len(entries) < _MAX_THREAD_ENTRIES:
                    entries.append({
                        "chapter_id": chapter_id,
                        "claim": claim[:120],
                    })

    # Keep only threads that span 2+ chapters
    multi_chapter_threads = {
        word: entries
        for word, entries in threads.items()
        if len({e["chapter_id"] for e in entries}) >= 2
    }
    return multi_chapter_threads


def _build_dependency_edges(
    chapter_sequence: list[str],
    nodes: dict[str, dict[str, Any]],
) -> list[dict[str, Any]]:
    """Create sequential dependency edges based on chapter order and open questions."""
    edges: list[dict[str, Any]] = []
    for idx, chapter_id in enumerate(chapter_sequence):
        if idx == 0:
            continue
        prev_id = chapter_sequence[idx - 1]
        prev_node = nodes.get(prev_id, {})
        unresolved = prev_node.get("unresolved_issues", [])
        if unresolved or prev_node.get("summary"):
            edges.append({
                "from_chapter": prev_id,
                "to_chapter": chapter_id,
                "dependency_type": "sequential_narrative",
                "bridged_issues": unresolved[:3],
                "carry_forward_summary": prev_node.get("summary", "")[:200],
            })
    return edges


# ---------------------------------------------------------------------------
# Public: full mesh build
# ---------------------------------------------------------------------------

def build_mesh(book_id: str, book_root: Path) -> dict[str, Any]:
    """Full rebuild of the knowledge mesh from current shared_memory state.

    Safe to call repeatedly — overwrites the previous mesh.
    """
    book_db = load_book_db(book_root)
    chapter_sequence: list[str] = book_db.get("chapter_sequence", [])
    shared = load_shared_memory(book_root)

    nodes: dict[str, dict[str, Any]] = {}
    for cm in shared.get("chapter_memory", []):
        chapter_id = cm.get("chapter_id", "")
        if chapter_id in chapter_sequence:
            nodes[chapter_id] = _node_from_chapter_memory(cm)

    thematic_threads = _extract_thematic_threads(chapter_sequence, nodes)
    dependency_edges = _build_dependency_edges(chapter_sequence, nodes)

    # Gather book-level open questions
    book_memory = shared.get("book_memory", {})
    open_questions: list[str] = book_memory.get("open_questions", [])
    # Merge chapter-level unresolved issues
    for node in nodes.values():
        for issue in node.get("unresolved_issues", []):
            if issue not in open_questions:
                open_questions.append(issue)

    mesh: dict[str, Any] = {
        "version": MESH_VERSION,
        "book_id": book_id,
        "generated_at": now_iso(),
        "updated_at": now_iso(),
        "chapter_count": len(chapter_sequence),
        "node_count": len(nodes),
        "nodes": nodes,
        "dependency_edges": dependency_edges,
        "thematic_threads": thematic_threads,
        "open_questions": open_questions[:50],
    }
    _save_mesh(book_root, mesh)
    return mesh


# ---------------------------------------------------------------------------
# Public: incremental update
# ---------------------------------------------------------------------------

def update_chapter_node(
    book_root: Path,
    chapter_id: str,
    *,
    summary: str | None = None,
    claims: list[str] | None = None,
    unresolved_issues: list[str] | None = None,
    citations_summary: list[str] | None = None,
    visual_notes: list[str] | None = None,
) -> dict[str, Any]:
    """Incrementally update a single chapter node in the mesh."""
    mesh = _load_mesh(book_root)
    node = mesh["nodes"].setdefault(chapter_id, {
        "chapter_id": chapter_id,
        "summary": "",
        "claims": [],
        "unresolved_issues": [],
        "citations_summary": [],
        "visual_notes": [],
        "updated_at": now_iso(),
    })
    if summary is not None:
        node["summary"] = summary
    if claims is not None:
        node["claims"] = claims
    if unresolved_issues is not None:
        node["unresolved_issues"] = unresolved_issues
    if citations_summary is not None:
        node["citations_summary"] = citations_summary
    if visual_notes is not None:
        node["visual_notes"] = visual_notes
    node["updated_at"] = now_iso()
    mesh["updated_at"] = now_iso()
    mesh["node_count"] = len(mesh["nodes"])
    _save_mesh(book_root, mesh)
    return mesh


# ---------------------------------------------------------------------------
# Public: bridge context retrieval (used by context_packs)
# ---------------------------------------------------------------------------

def get_bridge_context(book_root: Path, chapter_id: str) -> dict[str, Any]:
    """Return a compact bridge context slice for a chapter.

    The slice contains:
      - upstream_summaries: last N completed chapters' summaries
      - bridged_issues:     open issues from upstream that may affect this chapter
      - thematic_threads:   cross-chapter concepts relevant to this chapter
    """
    mesh = _load_mesh(book_root)
    book_db = load_book_db(book_root)
    chapter_sequence: list[str] = book_db.get("chapter_sequence", [])

    try:
        idx = chapter_sequence.index(chapter_id)
    except ValueError:
        return {"upstream_summaries": [], "bridged_issues": [], "thematic_threads": []}

    upstream_ids = chapter_sequence[max(0, idx - _MAX_BRIDGE_CHAPTERS):idx]
    upstream_summaries: list[dict[str, Any]] = []
    bridged_issues: list[str] = []

    for uid in reversed(upstream_ids):
        node = mesh["nodes"].get(uid)
        if not node:
            continue
        upstream_summaries.append({
            "chapter_id": uid,
            "summary": node.get("summary", "")[:300],
            "key_claims": node.get("claims", [])[:_MAX_BRIDGE_CLAIMS],
        })
        for issue in node.get("unresolved_issues", []):
            if issue not in bridged_issues:
                bridged_issues.append(issue)

    # Thematic threads: include only those that touch upstream chapters
    upstream_set = set(upstream_ids)
    relevant_threads: list[dict[str, Any]] = []
    for thread_name, entries in mesh.get("thematic_threads", {}).items():
        if any(e["chapter_id"] in upstream_set for e in entries):
            relevant_threads.append({
                "thread": thread_name,
                "appearances": [
                    {"chapter_id": e["chapter_id"], "claim": e["claim"]}
                    for e in entries
                    if e["chapter_id"] in upstream_set
                ][:3],
            })
        if len(relevant_threads) >= 8:
            break

    return {
        "chapter_id": chapter_id,
        "upstream_summaries": upstream_summaries,
        "bridged_issues": bridged_issues[:10],
        "thematic_threads": relevant_threads,
        "retrieved_at": now_iso(),
    }


# ---------------------------------------------------------------------------
# Public: keyword search
# ---------------------------------------------------------------------------

def query_mesh(book_root: Path, query: str) -> list[dict[str, Any]]:
    """Search all mesh nodes and threads for the given keyword.

    Returns a list of hits with chapter_id and matching text.
    """
    mesh = _load_mesh(book_root)
    query_lower = query.lower()
    hits: list[dict[str, Any]] = []

    for chapter_id, node in mesh.get("nodes", {}).items():
        matched_fields: list[str] = []
        if query_lower in (node.get("summary") or "").lower():
            matched_fields.append("summary")
        for claim in node.get("claims", []):
            if query_lower in claim.lower():
                matched_fields.append(f"claim: {claim[:80]}")
        for issue in node.get("unresolved_issues", []):
            if query_lower in issue.lower():
                matched_fields.append(f"issue: {issue[:80]}")
        if matched_fields:
            hits.append({
                "chapter_id": chapter_id,
                "matched_fields": matched_fields,
            })

    # Also search thematic threads
    for thread_name, entries in mesh.get("thematic_threads", {}).items():
        if query_lower in thread_name.lower():
            hits.append({
                "type": "thematic_thread",
                "thread": thread_name,
                "entry_count": len(entries),
            })

    return hits
