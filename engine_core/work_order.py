from __future__ import annotations

from pathlib import Path
from typing import Any

from .book_state import BOOK_STAGE_SEQUENCE, CHAPTER_STAGE_SEQUENCE, load_book_db, save_book_db
from .common import now_iso, read_json, write_json
from .contracts import get_stage_definition


BOOK_STAGE_PREREQS = {
    "S0": ["S-1"],
    "S1": ["S0"],
    "S2": ["S1"],
    "SQA": ["BOOK:S2", "ALL_CHAPTERS:S8"],
    "S9": ["BOOK:SQA"],
}
NODE_EXECUTION_STAGES = {
    "S4": {"node_strategy": "subsection_sequential", "default_node_count": 4},
    "S5": {"node_strategy": "subsection_sequential", "default_node_count": 4},
    "S8A": {"node_strategy": "subsection_sequential", "default_node_count": 4},
}


def _chapter_prereqs(stage_id: str) -> list[str]:
    if stage_id == "S3":
        return ["BOOK:S2"]
    idx = CHAPTER_STAGE_SEQUENCE.index(stage_id)
    return [CHAPTER_STAGE_SEQUENCE[idx - 1]]


def _prereqs_met(payload: dict[str, Any], stage_id: str, chapter_id: str | None = None) -> bool:
    prereqs = BOOK_STAGE_PREREQS.get(stage_id, []) if chapter_id is None else _chapter_prereqs(stage_id)
    if not prereqs:
        return True
    for prereq in prereqs:
        if prereq.startswith("BOOK:"):
            book_stage_id = prereq.split(":", 1)[1]
            if payload["book_level_stages"][book_stage_id]["status"] != "completed":
                return False
        elif prereq.startswith("ALL_CHAPTERS:"):
            chapter_stage_id = prereq.split(":", 1)[1]
            for chapter in payload["chapters"].values():
                if chapter["stages"][chapter_stage_id]["status"] != "completed":
                    return False
        else:
            if chapter_id is None:
                if payload["book_level_stages"][prereq]["status"] != "completed":
                    return False
            else:
                if payload["chapters"][chapter_id]["stages"][prereq]["status"] != "completed":
                    return False
    return True


def _update_unblocked_states(payload: dict[str, Any]) -> None:
    for stage_id in BOOK_STAGE_SEQUENCE[1:]:
        stage = payload["book_level_stages"][stage_id]
        if stage["status"] == "blocked" and _prereqs_met(payload, stage_id):
            stage["status"] = "pending"
            stage["updated_at"] = now_iso()
            stage["note"] = "Automatically unblocked by upstream completion."

    for chapter_id, chapter in payload["chapters"].items():
        for stage_id in CHAPTER_STAGE_SEQUENCE:
            stage = chapter["stages"][stage_id]
            if stage["status"] == "blocked" and _prereqs_met(payload, stage_id, chapter_id):
                stage["status"] = "pending"
                stage["updated_at"] = now_iso()
                stage["note"] = "Automatically unblocked by upstream completion."


def _build_priority_queue(payload: dict[str, Any]) -> tuple[list[dict[str, Any]], list[dict[str, Any]], list[dict[str, Any]]]:
    priority_queue: list[dict[str, Any]] = []
    blocked_items: list[dict[str, Any]] = []
    gate_failures: list[dict[str, Any]] = []
    rank = 1

    for stage_id in BOOK_STAGE_SEQUENCE[1:]:
        state = payload["book_level_stages"][stage_id]
        if state["status"] == "pending":
            stage_def = get_stage_definition(stage_id)
            priority_queue.append(
                {
                    "rank": rank,
                    "stage_id": stage_id,
                    "chapter_id": "BOOK",
                    "agent_id": stage_def["agent"],
                    "action": stage_def["name"],
                    "input_artifacts": stage_def.get("input", []),
                    "reason": state.get("note", ""),
                    "parallel_group": "book-level",
                }
            )
            rank += 1
        elif state["status"] == "blocked":
            blocked_items.append(
                {
                    "chapter_id": "BOOK",
                    "stage_id": stage_id,
                    "reason": state.get("note", "Blocked"),
                    "unblock_condition": "Upstream stage completion",
                }
            )
        elif state["status"] == "gate_failed":
            gate_failures.append(
                {
                    "stage_id": stage_id,
                    "chapter_id": "BOOK",
                    "return_to_stage": stage_id,
                    "reason": state.get("note", "Gate failed"),
                }
            )

    for chapter_id in payload["chapter_sequence"]:
        chapter = payload["chapters"][chapter_id]
        for stage_id in CHAPTER_STAGE_SEQUENCE:
            state = chapter["stages"][stage_id]
            if state["status"] == "pending":
                stage_def = get_stage_definition(stage_id)
                priority_queue.append(
                    {
                        "rank": rank,
                        "stage_id": stage_id,
                        "chapter_id": chapter_id,
                        "agent_id": stage_def["agent"],
                        "action": stage_def["name"],
                        "input_artifacts": stage_def.get("input", []),
                        "reason": state.get("note", ""),
                        "parallel_group": stage_id,
                        "node_strategy": NODE_EXECUTION_STAGES.get(stage_id, {}).get("node_strategy"),
                        "node_count": NODE_EXECUTION_STAGES.get(stage_id, {}).get("default_node_count"),
                    }
                )
                rank += 1
            elif state["status"] == "blocked":
                blocked_items.append(
                    {
                        "chapter_id": chapter_id,
                        "stage_id": stage_id,
                        "reason": state.get("note", "Blocked"),
                        "unblock_condition": "Upstream stage completion",
                    }
                )
            elif state["status"] == "gate_failed":
                if stage_id == "S8A":
                    continue
                gate_failures.append(
                    {
                        "stage_id": stage_id,
                        "chapter_id": chapter_id,
                        "return_to_stage": stage_id,
                        "reason": state.get("note", "Gate failed"),
                    }
                )
    return priority_queue, blocked_items, gate_failures


def _pipeline_snapshot(payload: dict[str, Any]) -> dict[str, Any]:
    return {
        "book": payload["book"],
        "book_level_stages": payload["book_level_stages"],
        "chapters": {
            chapter_id: {
                "title": chapter["title"],
                "states": chapter["stages"],
            }
            for chapter_id, chapter in payload["chapters"].items()
        },
        "updated_at": now_iso(),
    }


def _runtime_alerts(book_root: Path) -> list[dict[str, Any]]:
    dashboard_path = book_root / "verification" / "runtime_telemetry_dashboard.json"
    payload = read_json(dashboard_path, default=None)
    if not isinstance(payload, dict):
        return []
    alerts: list[dict[str, Any]] = []
    for warning in payload.get("warnings", []):
        if warning.get("severity") not in {"medium", "high"}:
            continue
        if warning.get("stage_id") == "S8A":
            continue
        alerts.append(
            {
                "severity": warning.get("severity", "medium"),
                "code": warning.get("code", "runtime_warning"),
                "stage_id": warning.get("stage_id", "unknown"),
                "chapter_id": warning.get("chapter_id") or "BOOK",
                "detail": warning.get("detail", {}),
                "resolution_hint": (
                    "Retry the affected stage after network/model recovery."
                    if warning.get("code") == "all_nodes_fallback"
                    else "Inspect runtime telemetry and retry if needed."
                ),
            }
        )
    return alerts


def issue_work_order(book_id: str, book_root: Path) -> dict[str, Any]:
    payload = load_book_db(book_root)
    _update_unblocked_states(payload)
    save_book_db(book_root, payload)

    priority_queue, blocked_items, gate_failures = _build_priority_queue(payload)
    work_order = {
        "version": "1.0",
        "order_id": f"WO-{book_id}-{now_iso()}",
        "book_id": book_id,
        "issued_at": now_iso(),
        "priority_queue": priority_queue,
        "blocked_items": blocked_items,
        "gate_failures": gate_failures,
        "runtime_alerts": _runtime_alerts(book_root),
    }

    write_json(book_root / "db" / "WORK_ORDER.local.json", work_order)
    write_json(book_root / "db" / "PIPELINE_STATUS.local.json", _pipeline_snapshot(payload))
    return work_order
