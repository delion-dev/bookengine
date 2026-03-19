#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from engine_core.book_state import load_book_db
from engine_core.bootstrap import scaffold_book
from engine_core.anchors import load_anchor_catalog
from engine_core.contracts import get_stage_definition, resolve_stage_contract, validate_inputs
from engine_core.gates import evaluate_gate
from engine_core.model_gateway import (
    build_generate_content_preview,
    describe_model_gateway,
    diagnose_vertex_live_probe,
)
from engine_core.model_policy import load_model_routing_policy
from engine_core.registry import get_registry
from engine_core.review_pack import build_stage_review_index
from engine_core.runtime_diagnostics import diagnose_runtime
from engine_core.session import close_session, open_session
from engine_core.stage import transition_stage
from engine_core.stage_api import list_stage_handlers, run_stage
from engine_core.telemetry import build_runtime_telemetry_dashboard
from engine_core.work_order import issue_work_order


def _print(payload: dict) -> None:
    print(json.dumps(payload, ensure_ascii=False, indent=2))


def _stage_requires_chapter(stage_id: str) -> bool:
    stage = get_stage_definition(stage_id)
    templates = [*stage.get("input", []), *stage.get("output", [])]
    return any("{chapter_id}" in template for template in templates)


def _target_stage_chapters(book_root: Path, stage_id: str, chapter_id: str | None) -> list[str | None]:
    if chapter_id:
        return [chapter_id]
    if not _stage_requires_chapter(stage_id):
        return [None]
    book_db = load_book_db(book_root)
    return list(book_db.get("chapter_sequence", []))


def _refresh_transition(
    book_root: Path,
    stage_id: str,
    chapter_id: str | None,
    next_status: str,
    note: str,
) -> None:
    book_db = load_book_db(book_root)
    current = (
        book_db["chapters"][chapter_id]["stages"][stage_id]["status"]
        if chapter_id
        else book_db["book_level_stages"][stage_id]["status"]
    )
    if current == next_status:
        transition_stage(book_root, stage_id, next_status, chapter_id, note)
        return
    if current == "gate_failed" and next_status == "completed":
        transition_stage(book_root, stage_id, "pending", chapter_id, "Gate refresh reset from gate_failed.")
        transition_stage(book_root, stage_id, "in_progress", chapter_id, "Gate refresh validation started.")
        transition_stage(book_root, stage_id, "completed", chapter_id, note)
        return
    transition_stage(book_root, stage_id, next_status, chapter_id, note)


def main() -> None:
    parser = argparse.ArgumentParser(description="Core Engine utility CLI")
    subparsers = parser.add_subparsers(dest="command", required=True)

    bootstrap_parser = subparsers.add_parser("bootstrap-book")
    bootstrap_parser.add_argument("--book-id", required=True)
    bootstrap_parser.add_argument("--display-name", required=True)
    bootstrap_parser.add_argument("--book-root", required=True)
    bootstrap_parser.add_argument("--source-file", required=True)

    session_open_parser = subparsers.add_parser("open-session")
    session_open_parser.add_argument("--book-id", required=True)
    session_open_parser.add_argument("--agent-id", required=True)
    session_open_parser.add_argument("--book-root", required=True)

    session_close_parser = subparsers.add_parser("close-session")
    session_close_parser.add_argument("--book-root", required=True)
    session_close_parser.add_argument("--session-id", required=True)
    session_close_parser.add_argument("--memo", required=True)

    work_order_parser = subparsers.add_parser("issue-work-order")
    work_order_parser.add_argument("--book-id", required=True)
    work_order_parser.add_argument("--book-root", required=True)

    contract_parser = subparsers.add_parser("resolve-contract")
    contract_parser.add_argument("--book-id", required=True)
    contract_parser.add_argument("--book-root", required=True)
    contract_parser.add_argument("--stage-id", required=True)
    contract_parser.add_argument("--chapter-id")

    validate_parser = subparsers.add_parser("validate-contract")
    validate_parser.add_argument("--book-id", required=True)
    validate_parser.add_argument("--book-root", required=True)
    validate_parser.add_argument("--stage-id", required=True)
    validate_parser.add_argument("--chapter-id")

    gate_parser = subparsers.add_parser("evaluate-gate")
    gate_parser.add_argument("--book-id", required=True)
    gate_parser.add_argument("--book-root", required=True)
    gate_parser.add_argument("--stage-id", required=True)
    gate_parser.add_argument("--chapter-id")

    refresh_gate_parser = subparsers.add_parser("refresh-stage-gates")
    refresh_gate_parser.add_argument("--book-id", required=True)
    refresh_gate_parser.add_argument("--book-root", required=True)
    refresh_gate_parser.add_argument("--stage-id", required=True)
    refresh_gate_parser.add_argument("--chapter-id")

    architecture_parser = subparsers.add_parser("run-architecture")
    architecture_parser.add_argument("--book-id", required=True)
    architecture_parser.add_argument("--book-root", required=True)

    orchestration_parser = subparsers.add_parser("run-orchestration")
    orchestration_parser.add_argument("--book-id", required=True)
    orchestration_parser.add_argument("--book-root", required=True)

    research_parser = subparsers.add_parser("run-research-plan")
    research_parser.add_argument("--book-id", required=True)
    research_parser.add_argument("--book-root", required=True)

    raw_guides_parser = subparsers.add_parser("run-raw-guides")
    raw_guides_parser.add_argument("--book-id", required=True)
    raw_guides_parser.add_argument("--book-root", required=True)
    raw_guides_parser.add_argument("--chapter-id")

    draft1_parser = subparsers.add_parser("run-draft1")
    draft1_parser.add_argument("--book-id", required=True)
    draft1_parser.add_argument("--book-root", required=True)
    draft1_parser.add_argument("--chapter-id")

    anchor_injection_parser = subparsers.add_parser("run-anchor-injection")
    anchor_injection_parser.add_argument("--book-id", required=True)
    anchor_injection_parser.add_argument("--book-root", required=True)
    anchor_injection_parser.add_argument("--chapter-id")

    review_parser = subparsers.add_parser("run-review")
    review_parser.add_argument("--book-id", required=True)
    review_parser.add_argument("--book-root", required=True)
    review_parser.add_argument("--chapter-id")

    asset_collection_parser = subparsers.add_parser("run-asset-collection")
    asset_collection_parser.add_argument("--book-id", required=True)
    asset_collection_parser.add_argument("--book-root", required=True)
    asset_collection_parser.add_argument("--chapter-id")

    amplification_parser = subparsers.add_parser("run-amplification")
    amplification_parser.add_argument("--book-id", required=True)
    amplification_parser.add_argument("--book-root", required=True)
    amplification_parser.add_argument("--chapter-id")

    stage_runner_parser = subparsers.add_parser("run-stage")
    stage_runner_parser.add_argument("--book-id", required=True)
    stage_runner_parser.add_argument("--book-root", required=True)
    stage_runner_parser.add_argument("--stage-id", required=True)
    stage_runner_parser.add_argument("--chapter-id")
    stage_runner_parser.add_argument("--rerun-completed", action="store_true")

    model_config_parser = subparsers.add_parser("show-model-config")
    model_config_parser.add_argument("--as-json", action="store_true")

    model_preview_parser = subparsers.add_parser("preview-model-request")
    model_preview_parser.add_argument("--task-type", required=True)
    model_preview_parser.add_argument("--prompt", required=True)
    model_preview_parser.add_argument("--grounded", action="store_true")

    subparsers.add_parser("diagnose-vertex-auth")
    runtime_diag_parser = subparsers.add_parser("diagnose-runtime")
    runtime_diag_parser.add_argument("--with-live-probes", action="store_true")
    runtime_diag_parser.add_argument("--with-grounded-probe", action="store_true")
    model_policy_parser = subparsers.add_parser("show-model-routing-policy")
    model_policy_parser.add_argument("--as-json", action="store_true")

    telemetry_parser = subparsers.add_parser("build-telemetry-dashboard")
    telemetry_parser.add_argument("--book-id", required=True)
    telemetry_parser.add_argument("--book-root", required=True)

    review_index_parser = subparsers.add_parser("build-stage-review-index")
    review_index_parser.add_argument("--book-id", required=True)
    review_index_parser.add_argument("--book-root", required=True)

    transition_parser = subparsers.add_parser("transition-stage")
    transition_parser.add_argument("--book-root", required=True)
    transition_parser.add_argument("--stage-id", required=True)
    transition_parser.add_argument("--to-status", required=True)
    transition_parser.add_argument("--chapter-id")
    transition_parser.add_argument("--note", default="")

    server_parser = subparsers.add_parser("run-server")
    server_parser.add_argument("--host", default="127.0.0.1")
    server_parser.add_argument("--port", type=int, default=8000)
    server_parser.add_argument("--reload", action="store_true")

    subparsers.add_parser("show-registry")
    subparsers.add_parser("show-anchor-catalog")
    subparsers.add_parser("show-stage-handlers")

    args = parser.parse_args()

    if args.command == "bootstrap-book":
        result = scaffold_book(
            book_id=args.book_id,
            display_name=args.display_name,
            book_root=Path(args.book_root),
            source_file=Path(args.source_file),
        )
        _print(result)
        return

    if args.command == "open-session":
        _print(open_session(args.book_id, args.agent_id, Path(args.book_root)))
        return

    if args.command == "close-session":
        _print(close_session(Path(args.book_root), args.session_id, args.memo))
        return

    if args.command == "issue-work-order":
        _print(issue_work_order(args.book_id, Path(args.book_root)))
        return

    if args.command == "resolve-contract":
        _print(
            resolve_stage_contract(
                args.book_id,
                Path(args.book_root),
                args.stage_id,
                args.chapter_id,
            )
        )
        return

    if args.command == "validate-contract":
        _print(
            validate_inputs(
                args.book_id,
                Path(args.book_root),
                args.stage_id,
                args.chapter_id,
            )
        )
        return

    if args.command == "evaluate-gate":
        _print(
            evaluate_gate(
                args.book_id,
                Path(args.book_root),
                args.stage_id,
                args.chapter_id,
            )
        )
        return

    if args.command == "refresh-stage-gates":
        book_root = Path(args.book_root)
        results = []
        for target_chapter_id in _target_stage_chapters(book_root, args.stage_id, args.chapter_id):
            gate_result = evaluate_gate(
                args.book_id,
                book_root,
                args.stage_id,
                target_chapter_id,
            )
            next_status = "completed" if gate_result.get("passed") else "gate_failed"
            note = (
                "Gate refreshed from existing outputs."
                if gate_result.get("passed")
                else json.dumps(gate_result, ensure_ascii=False)
            )
            _refresh_transition(
                book_root,
                args.stage_id,
                target_chapter_id,
                next_status,
                note,
            )
            results.append(
                {
                    "stage_id": args.stage_id,
                    "chapter_id": target_chapter_id,
                    "status": next_status,
                    "passed": gate_result.get("passed", False),
                }
            )
        _print(
            {
                "stage_id": args.stage_id,
                "refreshed_count": len(results),
                "results": results,
            }
        )
        return

    if args.command == "run-architecture":
        _print(run_stage(args.book_id, Path(args.book_root), "S0"))
        return

    if args.command == "run-orchestration":
        _print(run_stage(args.book_id, Path(args.book_root), "S1"))
        return

    if args.command == "run-research-plan":
        _print(run_stage(args.book_id, Path(args.book_root), "S2"))
        return

    if args.command == "run-raw-guides":
        _print(run_stage(args.book_id, Path(args.book_root), "S3", args.chapter_id))
        return

    if args.command == "run-draft1":
        _print(
            run_stage(
                args.book_id,
                Path(args.book_root),
                "S4",
                args.chapter_id,
                rerun_completed=args.rerun_completed,
            )
        )
        return

    if args.command == "run-anchor-injection":
        _print(run_stage(args.book_id, Path(args.book_root), "S4A", args.chapter_id))
        return

    if args.command == "run-review":
        _print(run_stage(args.book_id, Path(args.book_root), "S5", args.chapter_id))
        return

    if args.command == "run-asset-collection":
        _print(run_stage(args.book_id, Path(args.book_root), "S6A", args.chapter_id))
        return

    if args.command == "run-amplification":
        _print(run_stage(args.book_id, Path(args.book_root), "S8A", args.chapter_id))
        return

    if args.command == "run-stage":
        _print(
            run_stage(
                args.book_id,
                Path(args.book_root),
                args.stage_id,
                args.chapter_id,
                rerun_completed=args.rerun_completed,
            )
        )
        return

    if args.command == "show-model-config":
        _print(describe_model_gateway())
        return

    if args.command == "preview-model-request":
        _print(
            build_generate_content_preview(
                args.task_type,
                prompt=args.prompt,
                grounded=args.grounded,
            )
        )
        return

    if args.command == "diagnose-vertex-auth":
        _print(diagnose_vertex_live_probe())
        return

    if args.command == "diagnose-runtime":
        _print(
            diagnose_runtime(
                include_live_probes=args.with_live_probes,
                include_grounded_probe=args.with_grounded_probe,
            )
        )
        return

    if args.command == "show-model-routing-policy":
        _print(load_model_routing_policy())
        return

    if args.command == "build-telemetry-dashboard":
        _print(build_runtime_telemetry_dashboard(args.book_id, Path(args.book_root)))
        return

    if args.command == "build-stage-review-index":
        _print(build_stage_review_index(args.book_id, Path(args.book_root)))
        return

    if args.command == "transition-stage":
        _print(
            transition_stage(
                Path(args.book_root),
                args.stage_id,
                args.to_status,
                args.chapter_id,
                args.note,
            )
        )
        return

    if args.command == "run-server":
        import uvicorn
        uvicorn.run(
            "engine_api.main:app",
            host=args.host,
            port=args.port,
            reload=args.reload,
            app_dir=str(REPO_ROOT),
        )
        return

    if args.command == "show-registry":
        _print(get_registry())
        return

    if args.command == "show-anchor-catalog":
        _print(load_anchor_catalog())
        return

    if args.command == "show-stage-handlers":
        _print({"handlers": list_stage_handlers()})
        return


if __name__ == "__main__":
    main()
