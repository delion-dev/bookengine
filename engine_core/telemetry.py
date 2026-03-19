from __future__ import annotations

import json
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

from .book_state import load_book_db
from .common import REPO_ROOT, ensure_dir, now_iso, read_json, write_json, write_text


MODEL_CALL_LOG_PATH = REPO_ROOT / "platform" / "core_engine" / "runtime" / "model_call_log.jsonl"


def _read_jsonl(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    items: list[dict[str, Any]] = []
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line:
            continue
        try:
            items.append(json.loads(line))
        except json.JSONDecodeError:
            continue
    return items


def _runtime_budget_files(book_root: Path) -> list[Path]:
    runtime_root = book_root / "shared_memory" / "context_packs" / "runtime"
    if not runtime_root.exists():
        return []
    return sorted(runtime_root.glob("*_context_budget.json"))


def _node_manifest_files(book_root: Path) -> list[Path]:
    targets = [
        book_root / "manuscripts" / "_draft1",
        book_root / "manuscripts" / "_draft2",
        book_root / "manuscripts" / "_draft6",
    ]
    paths: list[Path] = []
    for root in targets:
        if root.exists():
            paths.extend(sorted(root.glob("*_node_manifest.json")))
            paths.extend(sorted(root.glob("*_review_nodes.json")))
            paths.extend(sorted(root.glob("*_amplification_nodes.json")))
    return paths


def _latest_budget_by_key(book_root: Path) -> dict[str, dict[str, Any]]:
    latest: dict[str, dict[str, Any]] = {}
    for path in _runtime_budget_files(book_root):
        payload = read_json(path, default=None)
        if not isinstance(payload, dict):
            continue
        if not payload.get("stage_id"):
            stem = path.stem
            parts = stem.split("_")
            if len(parts) >= 3:
                payload["chapter_id"] = payload.get("chapter_id") or parts[0]
                payload["stage_id"] = parts[1]
        key = f"{payload.get('stage_id')}:{payload.get('chapter_id') or 'book'}"
        current = latest.get(key)
        if current is None or current.get("generated_at", "") <= payload.get("generated_at", ""):
            latest[key] = payload
    return latest


def _node_manifest_summary(book_root: Path) -> list[dict[str, Any]]:
    summaries: list[dict[str, Any]] = []
    for path in _node_manifest_files(book_root):
        payload = read_json(path, default=None)
        if not isinstance(payload, dict):
            continue
        summaries.append(
            {
                "path": str(path),
                "stage_id": payload.get("stage_id"),
                "chapter_id": payload.get("chapter_id"),
                "node_count": payload.get("node_count", 0),
                "live_node_count": payload.get("live_node_count", 0),
                "fallback_node_count": payload.get("fallback_node_count", 0),
                "generated_at": payload.get("generated_at"),
            }
        )
    return summaries


def _filter_book_events(book_root: Path, events: list[dict[str, Any]]) -> list[dict[str, Any]]:
    book_db = load_book_db(book_root)
    chapter_ids = set(book_db.get("chapter_sequence", []))
    filtered = []
    for event in events:
        chapter_id = event.get("chapter_id")
        if chapter_id in chapter_ids:
            filtered.append(event)
            continue
        if event.get("stage_id") in {"S4", "S5", "S8A"} and chapter_id is None:
            filtered.append(event)
    return filtered


def _aggregate_model_events(events: list[dict[str, Any]]) -> dict[str, Any]:
    status_counter = Counter(event.get("status", "unknown") for event in events)
    stage_counter = Counter(event.get("stage_id", "unknown") for event in events)
    request_counter = Counter(event.get("request_variant", "unknown") for event in events)
    stage_breakdown: dict[str, dict[str, Any]] = defaultdict(lambda: {"events": 0, "avg_wait_seconds": 0.0, "avg_attempt": 0.0})
    waits_by_stage: dict[str, list[float]] = defaultdict(list)
    attempts_by_stage: dict[str, list[int]] = defaultdict(list)

    for event in events:
        stage_id = event.get("stage_id", "unknown")
        waits_by_stage[stage_id].append(float(event.get("wait_seconds", 0.0) or 0.0))
        attempts_by_stage[stage_id].append(int(event.get("attempt", 1) or 1))
        stage_breakdown[stage_id]["events"] += 1

    for stage_id, summary in stage_breakdown.items():
        waits = waits_by_stage.get(stage_id, [])
        attempts = attempts_by_stage.get(stage_id, [])
        summary["avg_wait_seconds"] = round(sum(waits) / len(waits), 3) if waits else 0.0
        summary["avg_attempt"] = round(sum(attempts) / len(attempts), 3) if attempts else 0.0

    return {
        "event_count": len(events),
        "status_counts": dict(status_counter),
        "stage_counts": dict(stage_counter),
        "request_variant_counts": dict(request_counter),
        "stage_breakdown": dict(stage_breakdown),
    }


def _build_warnings(
    context_budgets: list[dict[str, Any]],
    node_manifests: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    warnings: list[dict[str, Any]] = []

    for item in context_budgets:
        if item.get("within_budget") is False:
            warnings.append(
                {
                    "severity": "high",
                    "code": "context_budget_exceeded",
                    "stage_id": item.get("stage_id"),
                    "chapter_id": item.get("chapter_id"),
                    "detail": {
                        "approx_tokens": item.get("context_total_approx_tokens"),
                        "soft_max_input_tokens": item.get("soft_max_input_tokens"),
                        "distill_level": item.get("distill_level"),
                    },
                }
            )
        elif item.get("budget_enforced"):
            warnings.append(
                {
                    "severity": "low" if item.get("stage_id") == "S8A" else "medium",
                    "code": "context_budget_distilled",
                    "stage_id": item.get("stage_id"),
                    "chapter_id": item.get("chapter_id"),
                    "detail": {
                        "approx_tokens": item.get("context_total_approx_tokens"),
                        "soft_max_input_tokens": item.get("soft_max_input_tokens"),
                        "distill_level": item.get("distill_level"),
                    },
                }
            )

    for item in node_manifests:
        node_count = int(item.get("node_count", 0) or 0)
        live_count = int(item.get("live_node_count", 0) or 0)
        fallback_count = int(item.get("fallback_node_count", 0) or 0)
        if node_count > 0 and live_count == 0 and fallback_count == node_count:
            warnings.append(
                {
                    "severity": "low" if item.get("stage_id") == "S8A" else "medium",
                    "code": "all_nodes_fallback",
                    "stage_id": item.get("stage_id"),
                    "chapter_id": item.get("chapter_id"),
                    "detail": {
                        "node_count": node_count,
                        "live_node_count": live_count,
                        "fallback_node_count": fallback_count,
                    },
                }
            )
        elif fallback_count > 0:
            warnings.append(
                {
                    "severity": "low",
                    "code": "partial_node_fallback",
                    "stage_id": item.get("stage_id"),
                    "chapter_id": item.get("chapter_id"),
                    "detail": {
                        "node_count": node_count,
                        "live_node_count": live_count,
                        "fallback_node_count": fallback_count,
                    },
                }
            )

    return warnings


def _render_dashboard_markdown(payload: dict[str, Any]) -> str:
    lines = [
        f"# Runtime Telemetry Dashboard: {payload['book_id']}",
        "",
        f"- Generated at: {payload['generated_at']}",
        f"- Model event count: {payload['model_events']['event_count']}",
        "",
        "## Stage Breakdown",
    ]
    for stage_id, summary in sorted(payload["model_events"]["stage_breakdown"].items()):
        lines.append(
            f"- {stage_id}: events={summary['events']}, avg_wait_seconds={summary['avg_wait_seconds']}, avg_attempt={summary['avg_attempt']}"
        )
    lines.extend(["", "## Context Budgets"])
    for item in payload["context_budgets"]:
        lines.append(
            f"- {item.get('stage_id', 'unknown')}:{item.get('chapter_id') or 'book'} -> "
            f"approx_tokens={item.get('context_total_approx_tokens', 'n/a')}, "
            f"soft_max={item.get('soft_max_input_tokens', 'n/a')}, "
            f"within_budget={item.get('within_budget', 'n/a')}, "
            f"distill_level={item.get('distill_level', 'n/a')}"
        )
    lines.extend(["", "## Node Manifests"])
    for item in payload["node_manifests"]:
        lines.append(
            f"- {item['stage_id']}:{item['chapter_id']} -> nodes={item['node_count']}, live={item['live_node_count']}, fallback={item['fallback_node_count']}"
        )
    lines.extend(["", "## Warnings"])
    if payload["warnings"]:
        for warning in payload["warnings"]:
            lines.append(
                f"- [{warning['severity']}] {warning['code']} -> "
                f"{warning.get('stage_id', 'unknown')}:{warning.get('chapter_id') or 'book'}"
            )
    else:
        lines.append("- none")
    return "\n".join(lines) + "\n"


def build_runtime_telemetry_dashboard(book_id: str, book_root: Path) -> dict[str, Any]:
    verification_root = ensure_dir(book_root / "verification")
    events = _filter_book_events(book_root, _read_jsonl(MODEL_CALL_LOG_PATH))
    latest_budgets = list(_latest_budget_by_key(book_root).values())
    latest_budgets.sort(key=lambda item: (item.get("stage_id") or "", item.get("chapter_id") or ""))
    node_manifests = _node_manifest_summary(book_root)
    node_manifests.sort(key=lambda item: (item.get("stage_id") or "", item.get("chapter_id") or ""))

    payload = {
        "version": "1.0",
        "generated_at": now_iso(),
        "book_id": book_id,
        "book_root": str(book_root),
        "model_events": _aggregate_model_events(events),
        "context_budgets": latest_budgets,
        "node_manifests": node_manifests,
        "warnings": _build_warnings(latest_budgets, node_manifests),
    }
    write_json(verification_root / "runtime_telemetry_dashboard.json", payload)
    write_text(verification_root / "runtime_telemetry_dashboard.md", _render_dashboard_markdown(payload))
    return payload
