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
# Constants (fallback values — overridable via BOOK_CONFIG.json knowledge_mesh section)
# ---------------------------------------------------------------------------

MESH_VERSION = "1.1"
_MAX_BRIDGE_CLAIMS = 5       # per upstream chapter
_MAX_BRIDGE_CHAPTERS = 3     # how many upstream chapters to include
_MAX_THREAD_ENTRIES = 20     # per thematic thread

# ---------------------------------------------------------------------------
# Stopword sets — filter noise from thematic thread extraction
# ---------------------------------------------------------------------------

_KO_STOPWORDS: frozenset[str] = frozenset({
    "있는", "있다", "없는", "없다", "하는", "하다", "되는", "되다", "이다",
    "것이다", "때문에", "대해서", "위해서", "통해서", "이라는", "에서의",
    "으로의", "아니다", "이러한", "그러한", "어떤", "모든", "하지만",
    "그러나", "따라서", "그리고", "또한", "뿐만", "아니라", "이에", "따라",
    "위한", "대한", "통한", "관한", "속에서", "함께", "에서", "으로",
})

_EN_STOPWORDS: frozenset[str] = frozenset({
    "that", "this", "with", "have", "from", "they", "been", "were", "will",
    "which", "than", "when", "what", "your", "each", "these", "those",
    "their", "there", "about", "would", "could", "should", "people",
    "through", "before", "after", "again", "more", "also", "some",
    "just", "into", "very", "well", "such", "only", "then", "over",
})

_ALL_STOPWORDS = _KO_STOPWORDS | _EN_STOPWORDS


# ---------------------------------------------------------------------------
# Config loader — reads mesh parameters from book's BOOK_CONFIG.json
# ---------------------------------------------------------------------------

def _get_mesh_config(book_root: Path) -> dict[str, Any]:
    """Return merged mesh configuration (book-local overrides + defaults)."""
    book_config = read_json(book_root / "_master" / "BOOK_CONFIG.json", default={}) or {}
    defaults: dict[str, Any] = {
        "max_bridge_claims": _MAX_BRIDGE_CLAIMS,
        "max_bridge_chapters": _MAX_BRIDGE_CHAPTERS,
        "max_thread_entries": _MAX_THREAD_ENTRIES,
        "enable_cross_chapter_edges": True,
        "cross_chapter_min_match_ratio": 0.4,
        "stopwords_lang": "ko",
    }
    return {**defaults, **book_config.get("knowledge_mesh", {})}


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


def _is_stopword(word: str) -> bool:
    return word in _ALL_STOPWORDS


def _extract_thematic_threads(
    chapter_sequence: list[str],
    nodes: dict[str, dict[str, Any]],
    max_thread_entries: int = _MAX_THREAD_ENTRIES,
) -> dict[str, list[dict[str, Any]]]:
    """Build thematic thread index from claims/issues across all chapters.

    Improvements over v1.0:
      - Stopword filtering (Korean + English) removes noise words
      - Config-based max_thread_entries (no longer hardcoded)
      - Words < 4 chars still excluded; stopwords additionally filtered
    """
    threads: dict[str, list[dict[str, Any]]] = {}
    for chapter_id in chapter_sequence:
        node = nodes.get(chapter_id)
        if not node:
            continue
        for claim in node.get("claims", []):
            words = set(
                w.lower().strip(".,;:\"'()[]『』「」")
                for w in claim.split()
                if len(w) > 3 and not _is_stopword(w.lower().strip(".,;:\"'()[]『』「」"))
            )
            for word in words:
                if not word:
                    continue
                threads.setdefault(word, [])
                entries = threads[word]
                if len(entries) < max_thread_entries:
                    entries.append({
                        "chapter_id": chapter_id,
                        "claim": claim[:120],
                    })

    # Keep only threads that span 2+ distinct chapters
    return {
        word: entries
        for word, entries in threads.items()
        if len({e["chapter_id"] for e in entries}) >= 2
    }


def _build_sequential_edges(
    chapter_sequence: list[str],
    nodes: dict[str, dict[str, Any]],
) -> list[dict[str, Any]]:
    """Create forward-sequential dependency edges (ch[n-1] → ch[n])."""
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


def _build_cross_chapter_edges(
    chapter_sequence: list[str],
    nodes: dict[str, dict[str, Any]],
    min_match_ratio: float = 0.4,
) -> list[dict[str, Any]]:
    """Detect non-linear (cross-chapter) dependencies.

    If chapter B's claims contain keywords that resolve chapter A's unresolved
    issue — and A, B are non-adjacent — we record a cross_chapter_resolution edge.
    This captures cases like ch05 answering a question raised in ch02.
    """
    edges: list[dict[str, Any]] = []
    seen_pairs: set[tuple[str, str]] = set()

    for i, chapter_b in enumerate(chapter_sequence):
        node_b = nodes.get(chapter_b, {})
        claims_text = " ".join(node_b.get("claims", [])).lower()
        if not claims_text:
            continue

        for j, chapter_a in enumerate(chapter_sequence):
            if i == j or abs(i - j) <= 1:
                continue  # Skip self and adjacent chapters (handled by sequential edges)
            if (chapter_a, chapter_b) in seen_pairs:
                continue

            node_a = nodes.get(chapter_a, {})
            for issue in node_a.get("unresolved_issues", []):
                issue_words = [
                    w.lower().strip(".,;:\"'()")
                    for w in issue.split()
                    if len(w) > 3 and not _is_stopword(w.lower())
                ]
                if not issue_words:
                    continue
                matches = sum(1 for w in issue_words if w in claims_text)
                ratio = matches / len(issue_words)
                if ratio >= min_match_ratio:
                    edges.append({
                        "from_chapter": chapter_a,
                        "to_chapter": chapter_b,
                        "dependency_type": "cross_chapter_resolution",
                        "resolved_issue": issue[:100],
                        "match_ratio": round(ratio, 2),
                    })
                    seen_pairs.add((chapter_a, chapter_b))
                    break  # One edge per chapter pair is sufficient

    return edges


def _build_dependency_edges(
    chapter_sequence: list[str],
    nodes: dict[str, dict[str, Any]],
    enable_cross_chapter: bool = True,
    cross_chapter_min_match_ratio: float = 0.4,
) -> list[dict[str, Any]]:
    """Build all dependency edges: sequential + optional cross-chapter."""
    edges = _build_sequential_edges(chapter_sequence, nodes)
    if enable_cross_chapter:
        edges.extend(_build_cross_chapter_edges(
            chapter_sequence, nodes, min_match_ratio=cross_chapter_min_match_ratio
        ))
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

    cfg = _get_mesh_config(book_root)
    thematic_threads = _extract_thematic_threads(
        chapter_sequence, nodes,
        max_thread_entries=int(cfg["max_thread_entries"]),
    )
    dependency_edges = _build_dependency_edges(
        chapter_sequence, nodes,
        enable_cross_chapter=bool(cfg["enable_cross_chapter_edges"]),
        cross_chapter_min_match_ratio=float(cfg["cross_chapter_min_match_ratio"]),
    )

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

    cfg = _get_mesh_config(book_root)
    max_bridge_chapters = int(cfg["max_bridge_chapters"])
    max_bridge_claims = int(cfg["max_bridge_claims"])

    upstream_ids = chapter_sequence[max(0, idx - max_bridge_chapters):idx]
    upstream_summaries: list[dict[str, Any]] = []
    bridged_issues: list[str] = []

    for uid in reversed(upstream_ids):
        node = mesh["nodes"].get(uid)
        if not node:
            continue
        upstream_summaries.append({
            "chapter_id": uid,
            "summary": node.get("summary", "")[:300],
            "key_claims": node.get("claims", [])[:max_bridge_claims],
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
