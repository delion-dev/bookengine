from __future__ import annotations

import json
from pathlib import Path

from .contracts import validate_inputs
from .gates import evaluate_gate
from .stage import transition_stage
from .work_order import issue_work_order


def run_orchestration(book_id: str, book_root: Path) -> dict:
    contract_status = validate_inputs(book_id, book_root, "S1")
    if not contract_status["valid"]:
        raise FileNotFoundError(f"S1 inputs missing: {contract_status['missing_inputs']}")

    transition_stage(book_root, "S1", "in_progress", note="AG-OM orchestration run started.")
    issue_work_order(book_id, book_root)
    gate_result = evaluate_gate(book_id, book_root, "S1")
    if not gate_result["passed"]:
        transition_stage(book_root, "S1", "gate_failed", note=json.dumps(gate_result, ensure_ascii=False))
        return {
            "stage_id": "S1",
            "status": "gate_failed",
            "gate_result": gate_result,
        }

    transition_stage(book_root, "S1", "completed", note="AG-OM orchestration completed.")
    work_order = issue_work_order(book_id, book_root)
    return {
        "stage_id": "S1",
        "status": "completed",
        "gate_result": gate_result,
        "work_order": work_order,
    }
