from __future__ import annotations

from pathlib import Path
from typing import Any

from .book_state import BOOK_STAGE_SEQUENCE, CHAPTER_STAGE_SEQUENCE, load_book_db
from .common import count_words, ensure_dir, now_iso, read_json, read_text, write_json, write_text
from .contracts import resolve_stage_contract


STAGE_REVIEW_GUIDANCE: dict[str, dict[str, str]] = {
    "S-1": {
        "label": "입력 정규화",
        "review_focus": "기획안과 목차 초안이 책 범위와 일치하는지 확인",
    },
    "S0": {
        "label": "아키텍처",
        "review_focus": "BOOK_CONFIG, BLUEPRINT, STYLE, QUALITY, WORD_TARGETS가 책 의도와 일치하는지 확인",
    },
    "S1": {
        "label": "오케스트레이션",
        "review_focus": "WORK_ORDER와 PIPELINE_STATUS가 현재 진행 상태를 정확히 반영하는지 확인",
    },
    "S2": {
        "label": "리서치 설계",
        "review_focus": "research_plan, source_queue, reference_index, image_manifest의 조사 범위와 누락 여부 확인",
    },
    "S3": {
        "label": "Raw Guide",
        "review_focus": "장 목표 분량, 핵심 논지, anchor plan이 적절한지 확인",
    },
    "S4": {
        "label": "Draft1 Prose",
        "review_focus": "독자용 초고 서사, 분량 진척, 메타 오염 여부 확인",
    },
    "S4A": {
        "label": "Anchor Injection",
        "review_focus": "canonical anchor block 주입과 anchor 바깥 본문 보존 여부 확인",
    },
    "S5": {
        "label": "Draft2 Review",
        "review_focus": "사실 검증, 출처 연결, review report 지적 사항 확인",
    },
    "S6": {
        "label": "Visual Plan",
        "review_focus": "anchor별 시각화 유형, appendix ref, renderer 계획 확인",
    },
    "S6A": {
        "label": "Asset Collection Handoff",
        "review_focus": "오프라인 자산 수집용 파일명, appendix ref, 저장 경로, 바인딩 상태 확인",
    },
    "S7": {
        "label": "Visual Render",
        "review_focus": "ANCHOR_SLOT 치환, visual bundle, placeholder 잔존 여부 확인",
    },
    "S8": {
        "label": "Copyedit",
        "review_focus": "문체 정리, style issue 제거, anchor 균형 유지 확인",
    },
    "S8A": {
        "label": "Amplification",
        "review_focus": "원고 훼손 없이 독자 가치, 현장감, reader payoff가 강화되었는지 확인",
    },
    "S9": {
        "label": "Publication",
        "review_focus": "EPUB/PDF/SEO/manifest와 출판 검증 결과, 경고 잔존 여부 확인",
    },
}


def _artifact_summary(path: Path) -> dict[str, Any]:
    summary: dict[str, Any] = {
        "path": str(path),
        "exists": path.exists(),
    }
    if not path.exists():
        return summary

    summary["size_bytes"] = path.stat().st_size
    suffix = path.suffix.lower()
    if suffix in {".md", ".txt", ".html", ".xhtml", ".css"}:
        text = read_text(path)
        summary["word_count"] = count_words(text)
        summary["line_count"] = len(text.splitlines())
    elif suffix == ".json":
        payload = read_json(path, default=None)
        if isinstance(payload, dict):
            summary["top_level_keys"] = sorted(payload.keys())
        elif isinstance(payload, list):
            summary["item_count"] = len(payload)
    return summary


def _output_summary(outputs: list[dict[str, Any]]) -> dict[str, Any]:
    declared = len(outputs)
    existing = sum(1 for item in outputs if item.get("exists"))
    missing = declared - existing
    return {
        "declared": declared,
        "existing": existing,
        "missing": missing,
        "complete": missing == 0,
    }


def _stage_review_focus(stage_id: str) -> str:
    return STAGE_REVIEW_GUIDANCE.get(stage_id, {}).get("review_focus", "")


def _stage_label(stage_id: str) -> str:
    return STAGE_REVIEW_GUIDANCE.get(stage_id, {}).get("label", stage_id)


def _status_counts(chapters: dict[str, Any], stage_id: str) -> dict[str, int]:
    counts = {"completed": 0, "pending": 0, "gate_failed": 0, "blocked": 0, "in_progress": 0, "other": 0}
    for chapter in chapters.values():
        status = chapter["stages"][stage_id]["status"]
        if status in counts:
            counts[status] += 1
        else:
            counts["other"] += 1
    return counts


def _book_stage_entries(book_id: str, book_root: Path, payload: dict[str, Any]) -> list[dict[str, Any]]:
    entries: list[dict[str, Any]] = []
    for stage_id in BOOK_STAGE_SEQUENCE:
        contract = resolve_stage_contract(book_id, book_root, stage_id)
        state = payload["book_level_stages"][stage_id]
        input_summaries = [_artifact_summary(Path(path)) for path in contract["inputs"]]
        output_summaries = [_artifact_summary(Path(path)) for path in contract["outputs"]]
        entries.append(
            {
                "stage_id": stage_id,
                "label": _stage_label(stage_id),
                "agent": contract["agent"],
                "status": state["status"],
                "updated_at": state["updated_at"],
                "note": state.get("note", ""),
                "review_focus": _stage_review_focus(stage_id),
                "inputs": input_summaries,
                "outputs": output_summaries,
                "output_summary": _output_summary(output_summaries),
            }
        )
    return entries


def _chapter_stage_entries(book_id: str, book_root: Path, payload: dict[str, Any]) -> list[dict[str, Any]]:
    chapters = payload["chapters"]
    sequence = payload.get("chapter_sequence", list(chapters.keys()))
    entries: list[dict[str, Any]] = []
    for stage_id in CHAPTER_STAGE_SEQUENCE:
        contract_meta = resolve_stage_contract(book_id, book_root, stage_id, sequence[0])
        chapter_rows: list[dict[str, Any]] = []
        for chapter_id in sequence:
            contract = resolve_stage_contract(book_id, book_root, stage_id, chapter_id)
            chapter_state = chapters[chapter_id]["stages"][stage_id]
            output_summaries = [_artifact_summary(Path(path)) for path in contract["outputs"]]
            chapter_rows.append(
                {
                    "chapter_id": chapter_id,
                    "title": chapters[chapter_id]["title"],
                    "status": chapter_state["status"],
                    "updated_at": chapter_state["updated_at"],
                    "note": chapter_state.get("note", ""),
                    "outputs": output_summaries,
                    "output_summary": _output_summary(output_summaries),
                }
            )
        entries.append(
            {
                "stage_id": stage_id,
                "label": _stage_label(stage_id),
                "agent": contract_meta["agent"],
                "review_focus": _stage_review_focus(stage_id),
                "status_counts": _status_counts(chapters, stage_id),
                "chapters": chapter_rows,
            }
        )
    return entries


def _render_markdown(payload: dict[str, Any]) -> str:
    lines = [
        f"# Stage Review Index: {payload['book']['book_id']}",
        "",
        f"- Generated at: {payload['generated_at']}",
        f"- Book root: `{payload['book']['book_root']}`",
        f"- Chapter count: {payload['chapter_count']}",
        "",
        "## Book-Level Stages",
    ]

    for entry in payload["book_level_stages"]:
        lines.extend(
            [
                f"### {entry['stage_id']} {entry['label']} ({entry['agent']})",
                f"- Status: `{entry['status']}`",
                f"- Updated at: `{entry['updated_at']}`",
                f"- Review focus: {entry['review_focus']}",
                f"- Output coverage: {entry['output_summary']['existing']}/{entry['output_summary']['declared']}",
            ]
        )
        if entry["note"]:
            lines.append(f"- Note: {entry['note']}")
        lines.append("- Outputs:")
        for output in entry["outputs"]:
            suffix = ""
            if output.get("word_count") is not None:
                suffix = f" | words={output['word_count']}"
            elif output.get("top_level_keys") is not None:
                suffix = f" | keys={', '.join(output['top_level_keys'])}"
            lines.append(f"  - `{output['path']}` | exists={output['exists']}{suffix}")
        lines.append("")

    lines.append("## Chapter-Level Stages")
    for entry in payload["chapter_level_stages"]:
        counts = entry["status_counts"]
        lines.extend(
            [
                f"### {entry['stage_id']} {entry['label']} ({entry['agent']})",
                f"- Review focus: {entry['review_focus']}",
                f"- Status counts: completed={counts['completed']}, pending={counts['pending']}, gate_failed={counts['gate_failed']}, blocked={counts['blocked']}, in_progress={counts['in_progress']}",
                "",
                "| Chapter | Status | Output coverage | Representative output |",
                "| --- | --- | --- | --- |",
            ]
        )
        for chapter in entry["chapters"]:
            representative = next((item for item in chapter["outputs"] if item["exists"]), chapter["outputs"][0])
            coverage = chapter["output_summary"]
            lines.append(
                f"| `{chapter['chapter_id']}` {chapter['title']} | `{chapter['status']}` | `{coverage['existing']}/{coverage['declared']}` | `{representative['path']}` |"
            )
        lines.append("")

    if payload.get("runtime_alerts"):
        lines.extend(["## Runtime Alerts"])
        for alert in payload["runtime_alerts"]:
            lines.append(
                f"- `{alert['severity']}` `{alert['code']}` -> {alert.get('stage_id', '')}:{alert.get('chapter_id', '')} | {alert.get('resolution_hint', '')}"
            )
        lines.append("")

    if payload.get("publication_manifest"):
        manifest = payload["publication_manifest"]
        validation = manifest.get("validation", {})
        platform = validation.get("platform_validation", {})
        visual_asset_status = manifest.get("visual_asset_status", {})
        placeholder_by_mode = visual_asset_status.get("placeholder_by_mode", {})
        placeholder_details = visual_asset_status.get("placeholder_details", [])
        mode_summary = ", ".join(
            f"{mode}:{count}" for mode, count in sorted(placeholder_by_mode.items())
        ) or "none"
        lines.extend(
            [
                "## Publication Snapshot",
                f"- Metadata validation: `{validation.get('metadata_validation', {}).get('passed')}`",
                f"- SEO validation: `{validation.get('seo_validation', {}).get('passed')}`",
                f"- Platform validation: `{platform.get('passed')}`",
                f"- Platform warnings: {', '.join(platform.get('warnings', [])) or 'none'}",
                (
                    f"- Placeholder summary: `{visual_asset_status.get('placeholder_rendered', 0)}` remaining "
                    f"(with asset `{visual_asset_status.get('placeholder_with_asset', 0)}`, "
                    f"missing asset `{visual_asset_status.get('placeholder_missing_asset', 0)}`) | {mode_summary}"
                ),
                "",
            ]
        )
        for item in placeholder_details:
            pending_note = item.get("pending_note") or item.get("provenance_status") or "pending"
            lines.append(
                f"- Pending visual `{item.get('chapter_id', '')}:{item.get('anchor_id', '')}` "
                f"`{item.get('asset_mode', '')}` | {pending_note}"
            )
        if placeholder_details:
            lines.append("")

    return "\n".join(lines).rstrip() + "\n"


def build_stage_review_index(book_id: str, book_root: Path) -> dict[str, Any]:
    payload = load_book_db(book_root)
    verification_root = ensure_dir(book_root / "verification")
    work_order = read_json(book_root / "db" / "WORK_ORDER.local.json", default={})
    publication_manifest = read_json(book_root / "publication" / "output" / "publication_manifest.json", default={})

    review_payload = {
        "generated_at": now_iso(),
        "book": payload["book"],
        "chapter_count": len(payload.get("chapter_sequence", [])),
        "book_level_stages": _book_stage_entries(book_id, book_root, payload),
        "chapter_level_stages": _chapter_stage_entries(book_id, book_root, payload),
        "runtime_alerts": work_order.get("runtime_alerts", []),
        "publication_manifest": publication_manifest,
    }

    json_path = verification_root / "stage_review_index.json"
    md_path = verification_root / "stage_review_index.md"
    write_json(json_path, review_payload)
    write_text(md_path, _render_markdown(review_payload))
    return {
        "book_id": book_id,
        "book_root": str(book_root),
        "json_path": str(json_path),
        "markdown_path": str(md_path),
        "chapter_count": review_payload["chapter_count"],
        "runtime_alert_count": len(review_payload["runtime_alerts"]),
    }
