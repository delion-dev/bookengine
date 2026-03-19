from __future__ import annotations

"""ASHL — Automated Self-Healing Loop (AG-SYS)

Monitors pipeline health, diagnoses gate failures, and generates structured
recovery actions that can be applied automatically or presented to the operator.

Responsibilities:
  1. Scan gate_failures in the work order
  2. Diagnose each failure against known failure patterns
  3. Propose a ranked recovery action (retry, revert, escalate, skip)
  4. Apply safe recoveries automatically (status → pending)
  5. Log every healing event to shared_memory/healing_log.jsonl

Failure patterns and remedies:
  - ingestion_report_missing     → reset S6B → pending
  - model_timeout / fallback     → reset stage → pending
  - word_count_floor_miss        → rerun S4 prose node
  - anchor_slot_residue          → rerun S7 render
  - style_violations             → rerun S8 copyedit
  - amplification_ratio_exceeded → rerun S8A with cap hint
  - epub_pdf_missing             → rerun S9
  - unknown                      → escalate to operator
"""

from pathlib import Path
from typing import Any

from .book_state import load_book_db
from .common import append_jsonl, ensure_dir, now_iso, read_json, write_json
from .stage import transition_stage
from .work_order import issue_work_order


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

HEALING_LOG_VERSION = "1.0"
HEALING_REPORT_VERSION = "1.0"

# Maximum auto-retries per (chapter_id, stage_id) before escalation
MAX_AUTO_RETRIES = 2

# Known failure → diagnosis pattern → remedy
_FAILURE_PATTERNS: list[dict[str, Any]] = [
    {
        "pattern_id": "ingestion_report_missing",
        "stage_ids": ["S6B"],
        "check_names": ["ingestion_report_exists"],
        "remedy": "retry",
        "note": "Image ingestion report missing — reset S6B to pending.",
        "auto_apply": True,
    },
    {
        "pattern_id": "ingestion_error_present",
        "stage_ids": ["S6B"],
        "check_names": ["ingestion_status_synced"],
        "remedy": "retry",
        "note": "Image ingestion recorded errors — reset S6B to pending for re-processing.",
        "auto_apply": True,
    },
    {
        "pattern_id": "model_all_fallback",
        "stage_ids": ["S4", "S5", "S8A"],
        "check_names": ["s8a_live_contribution_present"],
        "remedy": "retry",
        "note": "All model nodes fell back — likely transient API error. Retry.",
        "auto_apply": True,
    },
    {
        "pattern_id": "word_count_floor_miss",
        "stage_ids": ["S4"],
        "check_names": ["min_length_reached"],
        "remedy": "retry",
        "note": "Draft did not meet minimum word count — rerun prose generation.",
        "auto_apply": True,
    },
    {
        "pattern_id": "anchor_slot_residue",
        "stage_ids": ["S7"],
        "check_names": ["draft4_exists"],
        "remedy": "retry",
        "note": "[ANCHOR_SLOT:] tokens remain in draft4 — rerun visual render.",
        "auto_apply": True,
    },
    {
        "pattern_id": "style_violations",
        "stage_ids": ["S8"],
        "check_names": ["style_violations_zero_or_acceptable"],
        "remedy": "retry",
        "note": "Style violations remain — rerun copyedit.",
        "auto_apply": True,
    },
    {
        "pattern_id": "amplification_ratio_exceeded",
        "stage_ids": ["S8A"],
        "check_names": ["s8a_amplification_ratio_within_cap"],
        "remedy": "retry",
        "note": "Amplification ratio exceeded cap — rerun with tighter constraints.",
        "auto_apply": True,
    },
    {
        "pattern_id": "epub_pdf_missing",
        "stage_ids": ["S9"],
        "check_names": ["epub_generated", "pdf_generated"],
        "remedy": "retry",
        "note": "Publication output missing — rerun S9.",
        "auto_apply": True,
    },
    {
        "pattern_id": "unresolved_claims",
        "stage_ids": ["S5"],
        "check_names": ["unsupported_claims_zero"],
        "remedy": "escalate",
        "note": "Unsupported claims remain after review — operator must provide sources.",
        "auto_apply": False,
    },
    {
        "pattern_id": "missing_rights_provenance",
        "stage_ids": ["S5"],
        "check_names": ["rights_provenance_complete"],
        "remedy": "escalate",
        "note": "Rights provenance incomplete — offline clearance required.",
        "auto_apply": False,
    },
]


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _healing_log_path(book_root: Path) -> Path:
    return ensure_dir(book_root / "shared_memory") / "healing_log.jsonl"


def _retry_count(book_root: Path, chapter_id: str, stage_id: str) -> int:
    log_path = _healing_log_path(book_root)
    if not log_path.exists():
        return 0
    count = 0
    for line in log_path.read_text(encoding="utf-8").splitlines():
        try:
            import json
            entry = json.loads(line)
            if (
                entry.get("chapter_id") == chapter_id
                and entry.get("stage_id") == stage_id
                and entry.get("action") == "retry"
            ):
                count += 1
        except Exception:
            pass
    return count


def _log_healing_event(
    book_root: Path,
    chapter_id: str,
    stage_id: str,
    pattern_id: str,
    action: str,
    note: str,
    auto_applied: bool,
) -> None:
    append_jsonl(
        _healing_log_path(book_root),
        {
            "version": HEALING_LOG_VERSION,
            "timestamp": now_iso(),
            "chapter_id": chapter_id,
            "stage_id": stage_id,
            "pattern_id": pattern_id,
            "action": action,
            "note": note,
            "auto_applied": auto_applied,
        },
    )


def _diagnose_failure(
    gate_failure: dict[str, Any],
) -> dict[str, Any] | None:
    """Match a gate_failure record to a known failure pattern."""
    stage_id = gate_failure.get("stage_id", "")
    reason = gate_failure.get("reason", "")

    for pattern in _FAILURE_PATTERNS:
        if stage_id not in pattern["stage_ids"]:
            continue
        # Match by check name mentioned in reason string
        for check_name in pattern["check_names"]:
            if check_name in reason or pattern["pattern_id"] in reason:
                return pattern
        # If reason is generic, use first pattern for this stage_id
    # Fallback: first pattern for this stage
    for pattern in _FAILURE_PATTERNS:
        if stage_id in pattern["stage_ids"]:
            return pattern

    return None  # unknown pattern


def _apply_remedy(
    book_root: Path,
    chapter_id: str,
    stage_id: str,
    pattern: dict[str, Any],
    *,
    dry_run: bool = False,
) -> dict[str, Any]:
    action = pattern["remedy"]
    note = pattern["note"]
    auto_applied = False

    if action == "retry" and pattern.get("auto_apply"):
        retry_count = _retry_count(book_root, chapter_id, stage_id)
        if retry_count >= MAX_AUTO_RETRIES:
            action = "escalate"
            note = f"Auto-retry cap ({MAX_AUTO_RETRIES}) reached. Escalating."
        else:
            if not dry_run:
                transition_stage(book_root, stage_id, "pending", chapter_id if chapter_id != "BOOK" else None, note=note)
            auto_applied = not dry_run
    elif action == "escalate":
        auto_applied = False

    if not dry_run:
        _log_healing_event(
            book_root, chapter_id, stage_id, pattern["pattern_id"], action, note, auto_applied
        )

    return {
        "chapter_id": chapter_id,
        "stage_id": stage_id,
        "pattern_id": pattern["pattern_id"],
        "action": action,
        "note": note,
        "auto_applied": auto_applied,
        "retry_count": _retry_count(book_root, chapter_id, stage_id) if action == "retry" else None,
    }


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def scan_and_heal(
    book_id: str,
    book_root: Path,
    *,
    dry_run: bool = False,
) -> dict[str, Any]:
    """Scan all gate failures in the current work order and apply safe remedies.

    Args:
        book_id:  Book identifier
        book_root: Path to book root directory
        dry_run:  If True, diagnose and propose but do not modify any state

    Returns:
        Healing report dict with actions taken / proposed.
    """
    work_order = issue_work_order(book_id, book_root)
    gate_failures: list[dict[str, Any]] = work_order.get("gate_failures", [])
    runtime_alerts: list[dict[str, Any]] = work_order.get("runtime_alerts", [])

    healing_actions: list[dict[str, Any]] = []
    escalations: list[dict[str, Any]] = []
    skipped: list[dict[str, Any]] = []

    for failure in gate_failures:
        stage_id = failure.get("stage_id", "")
        chapter_id = failure.get("chapter_id", "BOOK")

        pattern = _diagnose_failure(failure)
        if pattern is None:
            skipped.append({
                "chapter_id": chapter_id,
                "stage_id": stage_id,
                "reason": "No matching failure pattern — manual investigation required.",
            })
            continue

        result = _apply_remedy(book_root, chapter_id, stage_id, pattern, dry_run=dry_run)
        if result["action"] == "escalate":
            escalations.append(result)
        else:
            healing_actions.append(result)

    # Also surface runtime alerts as informational
    alert_summaries = [
        {
            "stage_id": a.get("stage_id"),
            "chapter_id": a.get("chapter_id"),
            "code": a.get("code"),
            "resolution_hint": a.get("resolution_hint"),
        }
        for a in runtime_alerts
    ]

    report = {
        "version": HEALING_REPORT_VERSION,
        "generated_at": now_iso(),
        "book_id": book_id,
        "dry_run": dry_run,
        "gate_failure_count": len(gate_failures),
        "healing_actions": healing_actions,
        "escalations": escalations,
        "skipped": skipped,
        "runtime_alerts": alert_summaries,
        "summary": {
            "auto_remedied": sum(1 for a in healing_actions if a.get("auto_applied")),
            "proposed_only": sum(1 for a in healing_actions if not a.get("auto_applied")),
            "escalated": len(escalations),
            "unknown": len(skipped),
        },
    }

    if not dry_run:
        report_path = book_root / "shared_memory" / "healing_report.json"
        write_json(report_path, report)

    return report


def get_healing_log(book_root: Path, limit: int = 50) -> list[dict[str, Any]]:
    """Return the last N entries from the healing log."""
    log_path = _healing_log_path(book_root)
    if not log_path.exists():
        return []
    import json
    lines = log_path.read_text(encoding="utf-8").strip().splitlines()
    entries = []
    for line in lines[-limit:]:
        try:
            entries.append(json.loads(line))
        except Exception:
            pass
    return list(reversed(entries))


def healing_status(book_root: Path) -> dict[str, Any]:
    """Return a summary of pipeline health from the latest book_db snapshot."""
    book_db = load_book_db(book_root)
    gate_failed_chapters: list[dict[str, Any]] = []
    pending_count = 0
    completed_count = 0
    total_stages = 0

    from .book_state import CHAPTER_STAGE_SEQUENCE
    for chapter_id in book_db.get("chapter_sequence", []):
        chapter = book_db["chapters"][chapter_id]
        for stage_id in CHAPTER_STAGE_SEQUENCE:
            status = chapter["stages"].get(stage_id, {}).get("status", "blocked")
            total_stages += 1
            if status == "completed":
                completed_count += 1
            elif status == "pending":
                pending_count += 1
            elif status == "gate_failed":
                gate_failed_chapters.append({
                    "chapter_id": chapter_id,
                    "stage_id": stage_id,
                    "note": chapter["stages"][stage_id].get("note", ""),
                })

    return {
        "total_chapter_stages": total_stages,
        "completed": completed_count,
        "pending": pending_count,
        "gate_failed_count": len(gate_failed_chapters),
        "gate_failed": gate_failed_chapters,
        "completion_rate": round(completed_count / total_stages, 3) if total_stages else 0.0,
        "generated_at": now_iso(),
    }
