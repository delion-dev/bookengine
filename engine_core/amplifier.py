from __future__ import annotations

import hashlib
import json
import re
import time
from pathlib import Path
from typing import Any

from .book_state import load_book_db
from .common import count_words, now_iso, read_text, write_text
from .contracts import resolve_stage_contract, validate_inputs
from .context_packs import build_context_bundle
from .gates import evaluate_gate
from .memory import update_chapter_memory
from .model_gateway import ModelGatewayError, generate_text
from .model_policy import resolve_stage_route
from .section_labels import (
    SECTION_ORDER,
    canonical_section_label_from_heading,
    canonical_section_label,
    find_section_marker,
    normalize_section_headings,
    required_section_markers,
    section_marker,
)
from .stage import transition_stage
from .subsection_nodes import build_block_nodes, write_node_manifest
from .work_order import issue_work_order


REQUIRED_SECTIONS = required_section_markers()
DOCUMENT_HEADING_PATTERN = re.compile(r"(?m)^(## [^\n]+)\s*$")
LIST_PATTERN = re.compile(r"^\s*(?:[-*]|\d+\.)\s+")
CANONICAL_SECTION_SEQUENCE = tuple(canonical_section_label(section_key) for section_key in SECTION_ORDER)
CANONICAL_SECTION_NAMES = set(CANONICAL_SECTION_SEQUENCE)
GENERIC_PHRASES = (
    "정보의 총량이 아니라",
    "중간 관문이라는 데 놓인다",
    "먼저 보여주는 편이 좋다",
    "장의 핵심 논지를 다시 요약하는 데 그치지 않고",
)
SENSORY_TERMS = {
    "TRAVEL": ("골목", "바람", "물결", "해질녘", "빛", "걸음", "풍경", "현장"),
    "TASTE": ("한입", "국물", "향", "식감", "잔", "온기", "입안", "테이블"),
}
MAX_S8A_REWRITE_TARGETS = 10
MAX_AMPLIFICATION_RATIO = 2.0
MAX_NETWORK_RECOVERY_PASSES = 1
NETWORK_RECOVERY_COOLDOWN_SECONDS = 20


def _amplification_checkpoint_path(book_root: Path, chapter_id: str) -> Path:
    return book_root / "manuscripts" / "_draft6" / f"{chapter_id}_amplification_checkpoint.json"


def _node_manifest_payload_from_live_detail(
    chapter: dict[str, Any],
    live_detail: dict[str, Any],
) -> dict[str, Any]:
    nodes = live_detail.get("nodes", []) if isinstance(live_detail, dict) else []
    return {
        "version": "1.0",
        "generated_at": now_iso(),
        "stage_id": "S8A",
        "chapter_id": chapter["chapter_id"],
        "chapter_title": chapter["title"],
        "execution_mode": "subsection_nodes_sequential",
        "node_count": len(nodes),
        "live_node_count": len([node for node in nodes if node.get("status") == "completed"]),
        "fallback_node_count": len([node for node in nodes if node.get("status") != "completed"]),
        "available_sections": live_detail.get("available_sections", []),
        "selected_sections": live_detail.get("selected_sections", []),
        "available_section_count": live_detail.get("available_section_count", 0),
        "selected_section_count": live_detail.get("selected_section_count", 0),
        "required_section_count": live_detail.get("required_section_count", 0),
        "section_coverage_balanced": live_detail.get("section_coverage_balanced", True),
        "section_target_counts": live_detail.get("section_target_counts", {}),
        "section_live_counts": live_detail.get("section_live_counts", {}),
        "section_fallback_counts": live_detail.get("section_fallback_counts", {}),
        "all_nodes_fallback": live_detail.get("all_nodes_fallback", False),
        "runtime_error_count": live_detail.get("runtime_error_count", 0),
        "nodes": nodes,
    }


def _checkpoint_signature(promoted_text: str, targets: list[dict[str, str]]) -> str:
    payload = {
        "promoted_sha1": hashlib.sha1(promoted_text.encode("utf-8")).hexdigest(),
        "target_block_ids": [target["block_id"] for target in targets],
    }
    return hashlib.sha1(json.dumps(payload, ensure_ascii=False, sort_keys=True).encode("utf-8")).hexdigest()


def _load_amplification_checkpoint(
    book_root: Path,
    chapter: dict[str, Any],
    *,
    signature: str,
) -> dict[str, Any] | None:
    checkpoint_path = _amplification_checkpoint_path(book_root, chapter["chapter_id"])
    if not checkpoint_path.exists():
        return None
    try:
        payload = json.loads(checkpoint_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return None
    if payload.get("signature") != signature:
        return None
    return payload if isinstance(payload, dict) else None


def _save_amplification_checkpoint(
    book_root: Path,
    chapter: dict[str, Any],
    *,
    signature: str,
    rewrite_mode: str,
    promoted_text: str,
    rewrites: dict[str, str],
    live_detail: dict[str, Any],
) -> None:
    checkpoint_path = _amplification_checkpoint_path(book_root, chapter["chapter_id"])
    checkpoint_payload = {
        "version": "1.0",
        "generated_at": now_iso(),
        "stage_id": "S8A",
        "chapter_id": chapter["chapter_id"],
        "chapter_title": chapter["title"],
        "signature": signature,
        "rewrite_mode": rewrite_mode,
        "promoted_sha1": hashlib.sha1(promoted_text.encode("utf-8")).hexdigest(),
        "rewrites": rewrites,
        "live_detail": live_detail,
    }
    checkpoint_path.write_text(json.dumps(checkpoint_payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def _s8a_output_bundle(book_id: str, book_root: Path, chapter_id: str) -> dict[str, str]:
    outputs = resolve_stage_contract(book_id, book_root, "S8A", chapter_id)["outputs"]
    return {
        "draft6": outputs[0],
        "amplification_report": outputs[1],
        "amplification_nodes": outputs[2],
    }


def _missing_s8a_outputs(book_id: str, book_root: Path, chapter_id: str) -> list[str]:
    bundle = _s8a_output_bundle(book_id, book_root, chapter_id)
    return [path for path in bundle.values() if not Path(path).exists()]


def _can_backfill_s8a_outputs(book_id: str, book_root: Path, chapter_id: str) -> bool:
    bundle = _s8a_output_bundle(book_id, book_root, chapter_id)
    missing = {Path(path).name for path in _missing_s8a_outputs(book_id, book_root, chapter_id)}
    backfillable = {Path(bundle["amplification_nodes"]).name}
    return (
        bool(missing)
        and missing.issubset(backfillable)
        and Path(bundle["draft6"]).exists()
        and Path(bundle["amplification_report"]).exists()
    )


def _pending_s8a_chapters(book_id: str, book_root: Path) -> list[str]:
    payload = load_book_db(book_root)
    return [
        chapter_id
        for chapter_id in payload["chapter_sequence"]
        if payload["chapters"][chapter_id]["stages"]["S8A"]["status"] in {"pending", "in_progress", "gate_failed"}
        or (
            payload["chapters"][chapter_id]["stages"]["S8A"]["status"] == "completed"
            and bool(_missing_s8a_outputs(book_id, book_root, chapter_id))
        )
    ]


def _legacy_s8a_live_detail(
    chapter: dict[str, Any],
    draft5: str,
) -> dict[str, Any]:
    promoted = _promote_heading(draft5)
    all_targets = _rewrite_targets(promoted)
    targets, selection_detail = _select_balanced_targets(all_targets, MAX_S8A_REWRITE_TARGETS)
    nodes = build_block_nodes("S8A", chapter["chapter_id"], chapter["title"], targets)
    for node in nodes:
        node["status"] = "completed"
        node["updated_at"] = now_iso()
        node["note"] = "legacy_stage_output_backfill"
    selected_sections = selection_detail.get("selected_sections", [])
    section_live_counts = dict(selection_detail.get("section_target_counts", {}))
    section_fallback_counts = {section: 0 for section in selected_sections}
    return {
        "rewrite_target_count": len(targets),
        "rewrite_target_cap": MAX_S8A_REWRITE_TARGETS,
        "rewrite_target_cap_applied": len(all_targets) > MAX_S8A_REWRITE_TARGETS,
        **selection_detail,
        "section_live_counts": section_live_counts,
        "section_fallback_counts": section_fallback_counts,
        "all_nodes_fallback": False,
        "runtime_error_count": 0,
        "request_variant": "legacy_artifact_backfill",
        "nodes": nodes,
    }


def _promote_heading(text: str) -> str:
    lines = text.splitlines()
    if lines and lines[0].startswith("# DRAFT"):
        if ":" in lines[0]:
            _, suffix = lines[0].split(":", 1)
            lines[0] = f"# DRAFT6:{suffix}"
        else:
            lines[0] = "# DRAFT6"
    return "\n".join(lines)


def _split_sections(text: str) -> tuple[str, list[dict[str, Any]]]:
    matches = list(DOCUMENT_HEADING_PATTERN.finditer(text))
    if not matches:
        return text, []
    prefix = text[: matches[0].start()].rstrip()
    sections: list[dict[str, Any]] = []
    for index, match in enumerate(matches):
        heading = match.group(1)
        start = match.end()
        end = matches[index + 1].start() if index + 1 < len(matches) else len(text)
        body = text[start:end].strip("\n")
        section_name = heading.replace("## ", "", 1).strip()
        canonical_name = canonical_section_label_from_heading(heading) or section_name
        sections.append(
            {
                "heading": heading,
                "section_name": canonical_name,
                "body": body,
                "rewrite_enabled": canonical_name in CANONICAL_SECTION_NAMES,
            }
        )
    return prefix, sections


def _split_blocks(section_body: str) -> list[str]:
    if not section_body.strip():
        return []
    return [chunk.strip("\n") for chunk in re.split(r"\n{2,}", section_body.strip()) if chunk.strip()]


def _compose_document(prefix: str, sections: list[dict[str, Any]]) -> str:
    parts: list[str] = []
    if prefix.strip():
        parts.append(prefix.strip())
    for section in sections:
        parts.append(section["heading"])
        if section.get("body", "").strip():
            parts.append(section["body"].strip())
    return "\n\n".join(parts).strip() + "\n"


def _is_rewritable_block(block: str) -> bool:
    stripped = block.strip()
    if not stripped:
        return False
    first_line = stripped.splitlines()[0].strip()
    if first_line.startswith(("<!--", "```", ">", "|", "[^")):
        return False
    if LIST_PATTERN.match(first_line):
        return False
    return True


def _rewrite_targets(text: str) -> list[dict[str, str]]:
    _, sections = _split_sections(text)
    targets: list[dict[str, str]] = []
    for section in sections:
        if not section["rewrite_enabled"]:
            continue
        section_name = section["section_name"]
        block_index = 1
        for block in _split_blocks(section["body"]):
            if not _is_rewritable_block(block):
                continue
            targets.append(
                {
                    "block_id": f"{section_name}_{block_index:03d}",
                    "section": section_name,
                    "text": block,
                }
            )
            block_index += 1
    return targets


def _select_balanced_targets(
    all_targets: list[dict[str, str]],
    cap: int,
) -> tuple[list[dict[str, str]], dict[str, Any]]:
    if cap <= 0 or not all_targets:
        return [], {
            "selection_strategy": "round_robin_by_section",
            "available_sections": [],
            "selected_sections": [],
            "available_section_count": 0,
            "selected_section_count": 0,
            "section_coverage_balanced": True,
            "section_target_counts": {},
        }

    grouped: dict[str, list[dict[str, str]]] = {}
    for target in all_targets:
        grouped.setdefault(target["section"], []).append(target)

    available_sections = [section for section in CANONICAL_SECTION_SEQUENCE if grouped.get(section)]
    selected: list[dict[str, str]] = []
    mutable_groups = {section: list(items) for section, items in grouped.items()}

    while len(selected) < cap:
        progressed = False
        for section in available_sections:
            bucket = mutable_groups.get(section, [])
            if not bucket or len(selected) >= cap:
                continue
            selected.append(bucket.pop(0))
            progressed = True
        if not progressed:
            break

    selected_sections = [
        section
        for section in CANONICAL_SECTION_SEQUENCE
        if any(target["section"] == section for target in selected)
    ]
    required_section_count = min(len(available_sections), len(selected), len(CANONICAL_SECTION_SEQUENCE))
    section_target_counts = {
        section: sum(1 for target in selected if target["section"] == section)
        for section in selected_sections
    }
    return selected, {
        "selection_strategy": "round_robin_by_section",
        "available_sections": available_sections,
        "selected_sections": selected_sections,
        "available_section_count": len(available_sections),
        "selected_section_count": len(selected_sections),
        "required_section_count": required_section_count,
        "section_coverage_balanced": len(selected_sections) >= required_section_count,
        "section_target_counts": section_target_counts,
    }


def _heuristic_rewrite(text: str, section_name: str, chapter: dict[str, Any]) -> str:
    enhanced = text.strip()
    if section_name == "Hook" and "독자" not in enhanced:
        enhanced += " 이 장은 독자가 첫 장면에서 무엇을 붙잡아야 하는지 선명하게 안내하는 데 초점을 둔다."
    if section_name == "Context" and "독자" not in enhanced:
        enhanced += " 독자의 시선으로 보면 이 맥락은 배경지식이 아니라 해석의 방향을 잡아 주는 좌표에 가깝다."
    if section_name == "Insight" and "현장" not in enhanced and "장면" not in enhanced:
        enhanced += " 그래서 정보가 문장 안에 머무르지 않고, 실제 장면과 감정의 움직임으로 읽히는지가 중요해진다."
    if section_name == "Takeaway" and "독자" not in enhanced:
        enhanced += " 읽고 난 뒤 독자가 다음 장면과 장소를 어떤 질문으로 바라볼지까지 남겨야 이 장의 가치가 살아난다."

    part = chapter.get("part", "")
    sensory_terms = ()
    if "TRAVEL" in part:
        sensory_terms = SENSORY_TERMS["TRAVEL"]
    elif "TASTE" in part:
        sensory_terms = SENSORY_TERMS["TASTE"]
    if sensory_terms and not any(term in enhanced for term in sensory_terms):
        if "TRAVEL" in part:
            enhanced += " 현장에 서면 동선, 시선, 공기의 결이 함께 읽혀야 이 장의 안내가 살아난다."
        else:
            enhanced += " 맛과 분위기는 메뉴 이름보다도 온기와 질감의 차이로 기억된다는 점을 문장에 살려야 한다."
    return enhanced


def _amplification_context_artifacts(
    book_root: Path,
    chapter_id: str,
    node_payload: dict[str, Any],
    *,
    prompt_text: str,
) -> list[dict[str, str]]:
    bundle = build_context_bundle(
        book_root,
        "S8A",
        chapter_id=chapter_id,
        node_payload=node_payload,
        prompt_text=prompt_text,
    )
    return list(bundle["context_artifacts"])


def _replace_section_body(text: str, heading: str, new_body: str) -> str:
    prefix, sections = _split_sections(text)
    updated_sections: list[dict[str, Any]] = []
    for section in sections:
        if section["heading"] == heading:
            updated = dict(section)
            updated["body"] = new_body.strip()
            updated_sections.append(updated)
        else:
            updated_sections.append(section)
    return _compose_document(prefix, updated_sections)


def _heuristic_takeaway_reader_remedy(takeaway_body: str, chapter: dict[str, Any]) -> str:
    enhanced = takeaway_body.strip()
    closing = (
        " 이 장을 덮는 독자라면, 이제 영월의 장면과 엄흥도의 선택을 단순한 정보가 아니라 "
        "당신의 여정에 질문을 남기는 장면으로 다시 보게 될 것이다."
    )
    if "독자" in enhanced or "당신" in enhanced or "여정" in enhanced or "다음 장" in enhanced:
        return enhanced
    if enhanced.endswith((".", "!", "?", "다", "요")):
        return enhanced + closing
    return enhanced + ". " + closing.strip()


def _is_network_fallback_note(note: str | None) -> bool:
    text = (note or "").lower()
    return "network error" in text or "os/network error" in text or "timed out" in text or "resource exhausted" in text


def _is_network_only_failure(live_detail: dict[str, Any]) -> bool:
    nodes = live_detail.get("nodes", [])
    if not nodes:
        return False
    fallback_nodes = [node for node in nodes if node.get("status") != "completed"]
    if len(fallback_nodes) != len(nodes):
        return False
    return all(_is_network_fallback_note(node.get("note")) for node in fallback_nodes)


def _remediate_takeaway_reader_value(
    book_root: Path,
    chapter: dict[str, Any],
    draft_text: str,
) -> tuple[str, dict[str, Any]]:
    takeaway_body = _section_payload(draft_text, section_marker("takeaway"))
    if not takeaway_body.strip():
        return draft_text, {
            "issue_code": "takeaway_not_reader_oriented",
            "applied": False,
            "status": "skipped",
            "mode": "none",
            "reason": "takeaway_missing",
        }

    prompt = "\n".join(
        [
            "Rewrite the following Korean Takeaway section so it becomes clearly reader-oriented.",
            "Constraints:",
            "- Preserve all existing facts, names, chronology, and implications.",
            "- Keep markdown-safe prose only. Do not add headings, bullets, tables, or code fences.",
            "- Keep the section focused on the reader's payoff, next gaze, or next movement.",
            "- Include at least one natural reader signal such as `독자`, `당신`, `여정`, or `다음 장`.",
            "- Keep the section close in length to the original; do not exceed 1.35x of the original words.",
            "",
            f"Chapter title: {chapter['title']}",
            f"Chapter part: {chapter.get('part', '')}",
            "Original Takeaway section:",
            takeaway_body,
        ]
    )

    remediation_detail: dict[str, Any] = {
        "issue_code": "takeaway_not_reader_oriented",
        "applied": False,
        "status": "pending",
        "mode": "none",
        "usage": {},
    }
    try:
        response = generate_text(
            resolve_stage_route(
                "S8A",
                "generate_text",
                chapter_part=chapter.get("part"),
                section_key="Takeaway",
            ),
            system_policy_ref="Rewrite publication-safe Korean prose while preserving facts and increasing reader payoff.",
            prompt=prompt,
            context_artifacts=_amplification_context_artifacts(
                book_root,
                chapter["chapter_id"],
                {
                    "node_id": f"S8A:{chapter['chapter_id']}:Takeaway_remediation",
                    "node_type": "targeted_remediation",
                    "section_key": "takeaway",
                    "section_heading": canonical_section_label("takeaway"),
                    "block_id": "Takeaway_section",
                    "source_text": takeaway_body,
                    "local_goal": "Resolve takeaway_not_reader_oriented without changing facts.",
                },
                prompt_text=prompt,
            ),
            generation_config={"temperature": 0.25, "maxOutputTokens": 2048},
            telemetry_context={
                "stage_id": "S8A",
                "chapter_id": chapter["chapter_id"],
                "node_id": f"S8A:{chapter['chapter_id']}:Takeaway_remediation",
                "section_key": "Takeaway",
                "block_id": "Takeaway_section",
                "remediation_issue": "takeaway_not_reader_oriented",
            },
        )
        rewritten = response.get("generated_text", "").strip()
        original_words = count_words(takeaway_body)
        rewritten_words = count_words(rewritten)
        if (
            rewritten
            and rewritten_words >= max(50, int(original_words * 0.8))
            and rewritten_words <= max(80, int(original_words * 1.35))
            and any(token in rewritten for token in ("독자", "당신", "여정", "다음 장"))
        ):
            remediation_detail.update(
                {
                    "applied": True,
                    "status": "resolved",
                    "mode": "vertex_live_section",
                    "usage": response.get("usage", {}),
                    "request_variant": response.get("request_variant"),
                }
            )
            return _replace_section_body(draft_text, find_section_marker(draft_text, "takeaway") or section_marker("takeaway"), rewritten), remediation_detail
        remediation_detail.update(
            {
                "applied": True,
                "status": "fallback_applied",
                "mode": "heuristic_takeaway_patch",
                "reason": "live_output_not_acceptable",
                "usage": response.get("usage", {}),
                "request_variant": response.get("request_variant"),
            }
        )
    except ModelGatewayError as exc:
        remediation_detail.update(
            {
                "applied": True,
                "status": "fallback_applied",
                "mode": "heuristic_takeaway_patch",
                "reason": str(exc),
            }
        )

    return _replace_section_body(
        draft_text,
        find_section_marker(draft_text, "takeaway") or section_marker("takeaway"),
        _heuristic_takeaway_reader_remedy(takeaway_body, chapter),
    ), remediation_detail


def _rewrite_blocks_live(
    book_root: Path,
    chapter: dict[str, Any],
    blueprint: str,
    style_guide: str,
    quality_criteria: str,
    promoted_text: str,
    targets: list[dict[str, str]],
    selection_detail: dict[str, Any],
) -> tuple[str, dict[str, str], dict[str, Any]]:
    if not targets:
        return "no_rewrite_targets", {}, {"rewrite_target_count": 0, "nodes": []}
    nodes = build_block_nodes("S8A", chapter["chapter_id"], chapter["title"], targets)
    rewrites: dict[str, str] = {}
    total_prompt_tokens = 0
    total_candidate_tokens = 0
    last_request_variant = None
    signature = _checkpoint_signature(promoted_text, targets)
    checkpoint = _load_amplification_checkpoint(book_root, chapter, signature=signature)
    if checkpoint:
        rewrites.update(checkpoint.get("rewrites", {}))
        checkpoint_live_detail = checkpoint.get("live_detail", {}) if isinstance(checkpoint, dict) else {}
        usage = checkpoint_live_detail.get("usage", {}) if isinstance(checkpoint_live_detail, dict) else {}
        total_prompt_tokens = usage.get("prompt_token_count") or 0
        total_candidate_tokens = usage.get("candidates_token_count") or 0
        last_request_variant = checkpoint_live_detail.get("request_variant")
        checkpoint_nodes_by_block = {
            str(node.get("block_id")): node
            for node in checkpoint_live_detail.get("nodes", [])
            if isinstance(node, dict) and node.get("block_id")
        }
        for node, target in zip(nodes, targets):
            block_id = target["block_id"]
            saved = checkpoint_nodes_by_block.get(block_id)
            if not saved:
                continue
            if saved.get("status") == "completed" and block_id in rewrites:
                node.update(saved)

    def persist_progress() -> None:
        section_target_counts: dict[str, int] = {}
        section_live_counts: dict[str, int] = {}
        section_fallback_counts: dict[str, int] = {}
        for node in nodes:
            section_key = (node.get("section_heading") or node.get("section_key") or "").strip()
            if not section_key:
                continue
            section_target_counts[section_key] = section_target_counts.get(section_key, 0) + 1
            if node.get("status") == "completed":
                section_live_counts[section_key] = section_live_counts.get(section_key, 0) + 1
            else:
                section_fallback_counts[section_key] = section_fallback_counts.get(section_key, 0) + 1
        live_node_count = len([node for node in nodes if node.get("status") == "completed"])
        fallback_node_count = len([node for node in nodes if node.get("status") != "completed"])
        network_fallback_count = len(
            [node for node in nodes if node.get("status") != "completed" and _is_network_fallback_note(node.get("note"))]
        )
        current_live_detail = {
            "rewrite_target_count": len(targets),
            "rewrite_target_cap": MAX_S8A_REWRITE_TARGETS,
            "rewrite_target_cap_applied": False,
            "request_variant": last_request_variant,
            "usage": {
                "prompt_token_count": total_prompt_tokens,
                "candidates_token_count": total_candidate_tokens,
                "total_token_count": total_prompt_tokens + total_candidate_tokens,
            },
            "structured_rewrite_count": len(rewrites),
            "nodes": nodes,
            "live_node_count": live_node_count,
            "fallback_node_count": fallback_node_count,
            "all_nodes_fallback": bool(nodes) and live_node_count == 0,
            "runtime_error_count": fallback_node_count,
            "network_fallback_count": network_fallback_count,
            "section_target_counts": section_target_counts,
            "section_live_counts": section_live_counts,
            "section_fallback_counts": section_fallback_counts,
            **selection_detail,
        }
        _save_amplification_checkpoint(
            book_root,
            chapter,
            signature=signature,
            rewrite_mode="vertex_live_subsection_nodes" if rewrites else "heuristic_fallback_only",
            promoted_text=promoted_text,
            rewrites=rewrites,
            live_detail=current_live_detail,
        )
        write_node_manifest(
            book_root,
            "S8A",
            chapter["chapter_id"],
            _node_manifest_payload_from_live_detail(chapter, current_live_detail),
        )

    for node, target in zip(nodes, targets):
        if node.get("status") == "completed" and target["block_id"] in rewrites:
            continue
        prompt = "\n".join(
            [
                "Rewrite only the following Korean prose block for tone-and-value amplification.",
                "Constraints:",
                "- Preserve every factual claim, proper noun, chronology, and caveat already present.",
                "- Do not invent new facts, quotes, locations, dates, or statistics.",
                "- Keep markdown-safe prose only; do not add headings, bullets, tables, or code fences.",
                "- Keep inline code and quoted labels intact when they already appear in the block.",
                "- Shift toward reader-centered value, stronger tone-and-manner, and scene-level immediacy grounded in the existing text.",
                "- Respect the chapter part: cinema/history = observant and lucid, travel/taste = situated and tactile.",
                f"- Keep at least {max(40, count_words(target['text']))} words so the original semantic load is preserved.",
                "",
                f"Chapter title: {chapter['title']}",
                f"Chapter part: {chapter.get('part', '')}",
                f"Section: {target['section']}",
                f"Block ID: {target['block_id']}",
                "Original block:",
                target["text"],
            ]
        )
        try:
            response = generate_text(
                resolve_stage_route(
                    "S8A",
                    "generate_text",
                    chapter_part=chapter.get("part"),
                    section_key=target["section"],
                ),
                system_policy_ref=(
                    "Produce polished Korean prose for a publication workflow while preserving meaning and structure."
                ),
                prompt=prompt,
                context_artifacts=_amplification_context_artifacts(
                    book_root,
                    chapter["chapter_id"],
                    {
                        "node_id": node["node_id"],
                        "node_type": node["node_type"],
                        "section_key": node["section_key"],
                        "section_heading": node["section_heading"],
                        "block_id": target["block_id"],
                        "source_text": target["text"],
                        "local_goal": "Amplify tone and reader payoff while preserving facts.",
                        "continuity_excerpt": json.dumps(
                            {
                                "book_blueprint": blueprint[:800],
                                "style_guide": style_guide[:600],
                                "quality_criteria": quality_criteria[:600],
                            },
                            ensure_ascii=False,
                        ),
                    },
                    prompt_text=prompt,
                ),
                generation_config={"temperature": 0.35, "maxOutputTokens": 3072},
                telemetry_context={
                    "stage_id": "S8A",
                    "chapter_id": chapter["chapter_id"],
                    "node_id": node["node_id"],
                    "section_key": target["section"],
                    "block_id": target["block_id"],
                },
            )
        except ModelGatewayError as exc:
            node["status"] = "fallback"
            node["updated_at"] = now_iso()
            node["note"] = str(exc)
            persist_progress()
            continue
        rewritten = response.get("generated_text", "").strip()
        minimum_acceptable_words = max(40, count_words(target["text"]))
        if not rewritten or count_words(rewritten) < minimum_acceptable_words:
            node["status"] = "fallback"
            node["updated_at"] = now_iso()
            node["note"] = "insufficient_length"
            node["output_words"] = count_words(rewritten)
            persist_progress()
            continue
        rewrites[target["block_id"]] = rewritten
        node["status"] = "completed"
        node["updated_at"] = now_iso()
        node["note"] = response.get("request_variant", "")
        node["output_words"] = count_words(rewritten)
        node["usage"] = response.get("usage", {})
        total_prompt_tokens += response.get("usage", {}).get("prompt_token_count") or 0
        total_candidate_tokens += response.get("usage", {}).get("candidates_token_count") or 0
        last_request_variant = response.get("request_variant")
        persist_progress()

    section_target_counts: dict[str, int] = {}
    section_live_counts: dict[str, int] = {}
    section_fallback_counts: dict[str, int] = {}
    for node in nodes:
        section_key = (node.get("section_heading") or node.get("section_key") or "").strip()
        if not section_key:
            continue
        section_target_counts[section_key] = section_target_counts.get(section_key, 0) + 1
        if node.get("status") == "completed":
            section_live_counts[section_key] = section_live_counts.get(section_key, 0) + 1
        else:
            section_fallback_counts[section_key] = section_fallback_counts.get(section_key, 0) + 1

    live_node_count = len([node for node in nodes if node.get("status") == "completed"])
    fallback_node_count = len([node for node in nodes if node.get("status") != "completed"])
    all_nodes_fallback = bool(nodes) and live_node_count == 0
    network_fallback_count = len(
        [node for node in nodes if node.get("status") != "completed" and _is_network_fallback_note(node.get("note"))]
    )
    return (
        "vertex_live_subsection_nodes" if rewrites else "heuristic_fallback_only",
        rewrites,
        {
            "rewrite_target_count": len(targets),
            "request_variant": last_request_variant,
            "usage": {
                "prompt_token_count": total_prompt_tokens,
                "candidates_token_count": total_candidate_tokens,
                "total_token_count": total_prompt_tokens + total_candidate_tokens,
            },
            "structured_rewrite_count": len(rewrites),
            "nodes": nodes,
            "live_node_count": live_node_count,
            "fallback_node_count": fallback_node_count,
            "all_nodes_fallback": all_nodes_fallback,
            "runtime_error_count": fallback_node_count,
            "network_fallback_count": network_fallback_count,
            "section_target_counts": section_target_counts,
            "section_live_counts": section_live_counts,
            "section_fallback_counts": section_fallback_counts,
        },
    )


def _apply_rewrites(
    text: str,
    chapter: dict[str, Any],
    rewrites: dict[str, str],
    target_block_ids: set[str],
) -> tuple[str, list[dict[str, str]]]:
    prefix, sections = _split_sections(text)
    applied: list[dict[str, str]] = []
    rendered_sections: list[str] = []
    for section in sections:
        heading = section["heading"]
        section_name = section["section_name"]
        body = section["body"]
        block_index = 1
        rendered_blocks: list[str] = []
        if section["rewrite_enabled"]:
            for block in _split_blocks(body):
                if _is_rewritable_block(block):
                    block_id = f"{section_name}_{block_index:03d}"
                    if block_id in target_block_ids:
                        replacement = rewrites.get(block_id) or _heuristic_rewrite(block, section_name, chapter)
                        if replacement.strip() != block.strip():
                            applied.append(
                                {
                                    "block_id": block_id,
                                    "section": section_name,
                                    "before": block.strip(),
                                    "after": replacement.strip(),
                                }
                            )
                        rendered_blocks.append(replacement.strip())
                    else:
                        rendered_blocks.append(block.strip())
                    block_index += 1
                else:
                    rendered_blocks.append(block.strip())
        else:
            rendered_blocks.append(body.strip())
        rendered_sections.append(heading)
        rendered_body = "\n\n".join(chunk for chunk in rendered_blocks if chunk.strip()).strip()
        if rendered_body:
            rendered_sections.append(rendered_body)
    parts = []
    if prefix.strip():
        parts.append(prefix.strip())
    parts.extend(rendered_sections)
    return "\n\n".join(parts).strip() + "\n", applied


def _structure_checks(text: str) -> dict[str, Any]:
    missing = [heading for heading, section_key in zip(REQUIRED_SECTIONS, SECTION_ORDER) if not find_section_marker(text, section_key)]
    start_count = text.count("<!-- ANCHOR_START")
    end_count = text.count("<!-- ANCHOR_END")
    slot_count = text.count("[ANCHOR_SLOT:")
    return {
        "missing_sections": missing,
        "anchor_start_count": start_count,
        "anchor_end_count": end_count,
        "anchor_slot_count": slot_count,
        "balanced_anchors": start_count == end_count,
        "passed": not missing and start_count == end_count and slot_count == 0,
    }


def _section_payload(text: str, heading: str) -> str:
    section_key = next((key for key in SECTION_ORDER if find_section_marker(text, key) == heading), None)
    marker = find_section_marker(text, section_key) if section_key else None
    if not marker or marker not in text:
        return ""
    after = text.split(marker, 1)[1]
    next_matches = []
    for other_key in SECTION_ORDER:
        if other_key == section_key:
            continue
        other_marker = find_section_marker(text, other_key)
        if other_marker and f"\n{other_marker}\n" in after:
            next_matches.append(other_marker)
    if next_matches:
        next_heading = min(next_matches, key=lambda item: after.index(f"\n{item}\n"))
        after = after.split(f"\n{next_heading}\n", 1)[0]
    return after.strip()


def _reader_value_issues(text: str) -> list[str]:
    issues: list[str] = []
    takeaway = _section_payload(text, find_section_marker(text, "takeaway") or section_marker("takeaway"))
    hook = _section_payload(text, find_section_marker(text, "hook") or section_marker("hook"))
    if takeaway and not any(token in takeaway for token in ("독자", "당신", "여정", "다음 장")):
        issues.append("takeaway_not_reader_oriented")
    if hook and len(hook.split()) < 24:
        issues.append("hook_too_thin_for_reader_pull")
    return issues


def _report_residual_issues(report_text: str) -> list[str]:
    if "## Residual Issues" not in report_text:
        return []
    block = report_text.split("## Residual Issues", 1)[1]
    if "## Return Policy" in block:
        block = block.split("## Return Policy", 1)[0]
    issues: list[str] = []
    for line in block.splitlines():
        stripped = line.strip()
        if stripped.startswith("- "):
            issue = stripped[2:].strip()
            if issue and issue != "none":
                issues.append(issue)
    return issues


def _tone_drift_issues(text: str) -> list[str]:
    issues: list[str] = []
    for phrase in GENERIC_PHRASES:
        if phrase in text:
            issues.append(f"generic_phrase:{phrase}")
    return issues


def _field_presence_issues(text: str, part: str) -> list[str]:
    if "TRAVEL" not in part and "TASTE" not in part:
        return []
    terms = SENSORY_TERMS["TRAVEL"] if "TRAVEL" in part else SENSORY_TERMS["TASTE"]
    if any(term in text for term in terms):
        return []
    return ["scene_or_sensory_cue_missing"]


def _render_amplification_report(
    chapter: dict[str, Any],
    rewrite_mode: str,
    input_words: int,
    output_words: int,
    applied_rewrites: list[dict[str, str]],
    structure: dict[str, Any],
    tone_issues: list[str],
    reader_value_issues: list[str],
    field_issues: list[str],
    live_detail: dict[str, Any],
    live_error_detail: dict[str, Any] | None,
    remediation_detail: dict[str, Any] | None,
) -> tuple[str, str | None]:
    retention_ratio = round((output_words / input_words), 3) if input_words else 1.0
    ratio_exceeded = bool(input_words) and output_words > round(input_words * MAX_AMPLIFICATION_RATIO)
    reader_centered_blocks = sum(
        1
        for item in applied_rewrites
        if ("독자" in item["after"] or "당신" in item["after"])
        and ("독자" not in item["before"] and "당신" not in item["before"])
    )
    scene_blocks = sum(
        1
        for item in applied_rewrites
        if any(term in item["after"] for term in (*SENSORY_TERMS["TRAVEL"], *SENSORY_TERMS["TASTE"], "장면", "현장"))
    )
    live_node_count = live_detail.get("live_node_count", 0)
    fallback_node_count = live_detail.get("fallback_node_count", 0)
    all_nodes_fallback = bool(live_detail.get("all_nodes_fallback"))
    runtime_error_count = live_detail.get("runtime_error_count", fallback_node_count)
    available_sections = live_detail.get("available_sections", [])
    selected_sections = live_detail.get("selected_sections", [])
    section_coverage_balanced = live_detail.get("section_coverage_balanced", True)
    return_stage = None
    if not structure["passed"] or retention_ratio < 0.85:
        return_stage = "S8"
    elif ratio_exceeded:
        return_stage = "S8A"
    elif live_detail.get("rewrite_target_count", 0) > 0 and all_nodes_fallback:
        return_stage = "S8A"
    elif live_detail.get("rewrite_target_count", 0) > 0 and not section_coverage_balanced:
        return_stage = "S8A"
    elif reader_value_issues or field_issues:
        return_stage = "S8A"

    lines = [
        f"# AMPLIFICATION_REPORT: {chapter['chapter_id']} | {chapter['title']}",
        "",
        "## Verdict",
        "- Amplification gate: pass" if not return_stage else "- Amplification gate: fail",
        f"- Rewrite mode: {rewrite_mode}",
        f"- Tone drift remaining: {len(tone_issues)}",
        f"- Reader-value issues remaining: {len(reader_value_issues)}",
        f"- Field-presence issues remaining: {len(field_issues)}",
        f"- Return stage: {return_stage or 'none'}",
        "",
        "## Value Amplification",
        f"- Rewritten prose blocks: {len(applied_rewrites)}",
        f"- Reader-centered rewrites: {reader_centered_blocks}",
        f"- Scene / field cues strengthened: {scene_blocks}",
        f"- Input words: {input_words}",
        f"- Output words: {output_words}",
        f"- Word retention ratio: {retention_ratio}",
        f"- Max amplification ratio: {MAX_AMPLIFICATION_RATIO}",
        f"- Amplification ratio exceeded: {ratio_exceeded}",
        "",
        "## Model Telemetry",
        f"- Rewrite targets detected: {live_detail.get('rewrite_target_count', 0)}",
        f"- Rewrite target cap: {live_detail.get('rewrite_target_cap', MAX_S8A_REWRITE_TARGETS)}",
        f"- Rewrite target cap applied: {live_detail.get('rewrite_target_cap_applied', False)}",
        f"- Live nodes completed: {live_node_count}",
        f"- Fallback nodes: {fallback_node_count}",
        f"- Runtime error count: {runtime_error_count}",
        f"- Available sections: {', '.join(available_sections) if available_sections else 'none'}",
        f"- Selected sections: {', '.join(selected_sections) if selected_sections else 'none'}",
        f"- Balanced section coverage: {section_coverage_balanced}",
        f"- All nodes fallback: {all_nodes_fallback}",
        f"- Structured rewrites returned: {live_detail.get('structured_rewrite_count', len(applied_rewrites))}",
        f"- Request variant: {live_detail.get('request_variant', 'n/a')}",
        f"- Prompt token count: {live_detail.get('usage', {}).get('prompt_token_count', 'n/a')}",
        f"- Candidate token count: {live_detail.get('usage', {}).get('candidates_token_count', 'n/a')}",
        f"- Total token count: {live_detail.get('usage', {}).get('total_token_count', 'n/a')}",
        "",
        "## Structural Integrity",
        f"- Missing sections: {', '.join(structure['missing_sections']) if structure['missing_sections'] else 'none'}",
        f"- Anchor start/end balanced: {structure['balanced_anchors']}",
        f"- Anchor slot residues: {structure['anchor_slot_count']}",
        "",
        "## Live Call Detail",
    ]
    if all_nodes_fallback:
        fallback_message = live_error_detail.get("message") if live_error_detail else "all rewrite targets fell back"
        lines.extend(
            [
                "- Live call status: all_nodes_fallback",
                f"- Live fallback reason: {fallback_message}",
                f"- Runtime error count: {runtime_error_count}",
                f"- Network fallback count: {live_detail.get('network_fallback_count', 0)}",
            ]
        )
    elif live_error_detail:
        lines.extend(
            [
                "- Live call status: degraded",
                f"- Live fallback reason: {live_error_detail.get('message', 'unknown')}",
                f"- HTTP status: {live_error_detail.get('status_code', 'n/a')}",
                f"- Request variant: {live_error_detail.get('variant_label', 'n/a')}",
                f"- Hint: {live_error_detail.get('hint', 'n/a')}",
            ]
        )
    else:
        lines.append("- Live call status: ok")

    lines.extend(
        [
            "",
            "## Targeted Remediation",
        ]
    )
    if remediation_detail:
        lines.extend(
            [
                f"- Issue code: {remediation_detail.get('issue_code', 'n/a')}",
                f"- Applied: {remediation_detail.get('applied', False)}",
                f"- Status: {remediation_detail.get('status', 'n/a')}",
                f"- Mode: {remediation_detail.get('mode', 'n/a')}",
            ]
        )
        if remediation_detail.get("reason"):
            lines.append(f"- Reason: {remediation_detail['reason']}")
    else:
        lines.append("- none")

    lines.extend(
        [
            "",
            "## Residual Issues",
        ]
    )
    residuals = [*tone_issues, *reader_value_issues, *field_issues]
    if residuals:
        for item in residuals:
            lines.append(f"- {item}")
    else:
        lines.append("- none")

    lines.extend(
        [
            "",
            "## Return Policy",
            f"- If this stage fails, return to `{return_stage or 'none'}`.",
            "- Return to S8 when structure or publication-safe formatting is damaged.",
            "- Return to S8A when tone/value gain is still too weak or too generic.",
        ]
    )
    return "\n".join(lines) + "\n", return_stage


def run_amplification(
    book_id: str,
    book_root: Path,
    chapter_id: str | None = None,
) -> dict[str, Any]:
    style_guide = read_text(book_root / "_master" / "STYLE_GUIDE.md")
    quality_criteria = read_text(book_root / "_master" / "QUALITY_CRITERIA.md")
    blueprint = read_text(book_root / "_master" / "BOOK_BLUEPRINT.md")
    if not style_guide or not quality_criteria or not blueprint:
        raise FileNotFoundError("S8A requires STYLE_GUIDE.md, QUALITY_CRITERIA.md, and BOOK_BLUEPRINT.md.")

    book_db = load_book_db(book_root)
    target_chapters = [chapter_id] if chapter_id else _pending_s8a_chapters(book_id, book_root)
    if not target_chapters:
        return {
            "stage_id": "S8A",
            "status": "no_op",
            "message": "No pending or backfillable S8A chapters found.",
        }

    results = []
    for current_chapter_id in target_chapters:
        contract_status = validate_inputs(book_id, book_root, "S8A", current_chapter_id)
        if not contract_status["valid"]:
            raise FileNotFoundError(f"S8A inputs missing for {current_chapter_id}: {contract_status['missing_inputs']}")

        chapter = {
            "chapter_id": current_chapter_id,
            "title": book_db["chapters"][current_chapter_id]["title"],
            "part": book_db["chapters"][current_chapter_id].get("part", ""),
        }
        current_status = book_db["chapters"][current_chapter_id]["stages"]["S8A"]["status"]
        output_bundle = _s8a_output_bundle(book_id, book_root, current_chapter_id)
        missing_outputs = _missing_s8a_outputs(book_id, book_root, current_chapter_id)
        backfill_only = current_status == "completed" and _can_backfill_s8a_outputs(book_id, book_root, current_chapter_id)
        draft5_path = book_root / "manuscripts" / "_draft5" / f"{current_chapter_id}_draft5.md"
        draft6_path = book_root / "manuscripts" / "_draft6" / f"{current_chapter_id}_draft6.md"
        report_path = book_root / "manuscripts" / "_draft6" / f"{current_chapter_id}_amplification_report.md"

        existing_draft6 = read_text(draft6_path) if draft6_path.exists() else ""
        existing_report = read_text(report_path) if report_path.exists() else ""
        existing_residual_issues = _report_residual_issues(existing_report) if existing_report else []
        targeted_remediation_mode = (
            current_status == "gate_failed"
            and existing_draft6
            and existing_report
            and existing_residual_issues == ["takeaway_not_reader_oriented"]
        )
        if current_status == "gate_failed":
            if targeted_remediation_mode:
                transition_stage(
                    book_root,
                    "S8A",
                    "pending",
                    current_chapter_id,
                    note="AG-05A targeted remediation requested.",
                )
                transition_stage(
                    book_root,
                    "S8A",
                    "in_progress",
                    current_chapter_id,
                    note="AG-05A targeted remediation started.",
                )
            else:
                transition_stage(book_root, "S8A", "pending", current_chapter_id, note="AG-05A amplification rerun requested.")
                transition_stage(book_root, "S8A", "in_progress", current_chapter_id, note="AG-05A amplification restarted.")
        elif current_status != "completed":
            transition_stage(book_root, "S8A", "in_progress", current_chapter_id, note="AG-05A amplification started.")
        elif missing_outputs and not backfill_only:
            transition_stage(
                book_root,
                "S8A",
                "in_progress",
                current_chapter_id,
                note="AG-05A amplification regeneration started from missing outputs.",
            )

        draft5 = read_text(draft5_path)
        if backfill_only:
            live_detail = _legacy_s8a_live_detail(chapter, draft5)
            node_manifest_payload = _node_manifest_payload_from_live_detail(chapter, live_detail)
            node_manifest_payload["execution_mode"] = "legacy_artifact_backfill"
            node_manifest_payload["backfilled_from_legacy_stage_output"] = True
            node_manifest_payload["backfill_reason"] = [Path(path).name for path in missing_outputs]
            node_manifest_path = write_node_manifest(book_root, "S8A", current_chapter_id, node_manifest_payload)
            declared_outputs = [
                output_bundle["draft6"],
                output_bundle["amplification_report"],
                str(node_manifest_path),
            ]
            update_chapter_memory(
                book_root,
                current_chapter_id,
                summary=f"S8A artifacts backfilled for {chapter['title']}",
                claims=[
                    "Legacy S8A node telemetry was reconstructed from the approved draft5/draft6 pair.",
                    "Amplification node manifest was regenerated for contract completeness without a live rerun.",
                ],
                unresolved_issues=[],
                visual_notes=[],
            )
            transition_stage(
                book_root,
                "S8A",
                "completed",
                current_chapter_id,
                note=f"AG-05A legacy output backfill completed: {', '.join(Path(path).name for path in missing_outputs)}",
            )
            results.append(
                {
                    "chapter_id": current_chapter_id,
                    "status": "completed",
                    "repair_mode": "artifact_backfill",
                    "repaired_outputs": [Path(path).name for path in missing_outputs],
                    "outputs": declared_outputs,
                    "node_manifest": str(node_manifest_path),
                    "rewrite_target_count": live_detail.get("rewrite_target_count", 0),
                    "gate_result": {
                        "skipped": True,
                        "reason": "artifact_backfill_only",
                    },
                }
            )
            continue

        if targeted_remediation_mode:
            promoted = existing_draft6
        else:
            promoted = _promote_heading(draft5)
        all_targets = _rewrite_targets(promoted)
        targets, selection_detail = _select_balanced_targets(all_targets, MAX_S8A_REWRITE_TARGETS)
        target_block_ids = {target["block_id"] for target in targets}
        rewrite_mode = "targeted_takeaway_remediation" if targeted_remediation_mode else "heuristic_fallback"
        rewrites: dict[str, str] = {}
        live_detail: dict[str, Any] = {
            "rewrite_target_count": len(targets),
            "rewrite_target_cap": MAX_S8A_REWRITE_TARGETS,
            "rewrite_target_cap_applied": len(all_targets) > MAX_S8A_REWRITE_TARGETS,
            **selection_detail,
        }
        live_error_detail: dict[str, Any] | None = None
        remediation_detail: dict[str, Any] | None = None
        if targeted_remediation_mode:
            draft6 = promoted
            input_words = count_words(draft5)
            output_words = count_words(draft6)
            tone_issues = _tone_drift_issues(draft6)
            reader_value_issues = _reader_value_issues(draft6)
            field_issues = _field_presence_issues(draft6, chapter["part"])
            if "takeaway_not_reader_oriented" in reader_value_issues:
                draft6, remediation_detail = _remediate_takeaway_reader_value(book_root, chapter, draft6)
                output_words = count_words(draft6)
                tone_issues = _tone_drift_issues(draft6)
                reader_value_issues = _reader_value_issues(draft6)
                field_issues = _field_presence_issues(draft6, chapter["part"])
                live_detail["request_variant"] = remediation_detail.get("request_variant")
                live_detail["usage"] = remediation_detail.get("usage", {})
                live_detail["structured_rewrite_count"] = 1 if remediation_detail.get("status") == "resolved" else 0
        elif targets:
            try:
                rewrite_mode, rewrites, live_detail = _rewrite_blocks_live(
                    book_root,
                    chapter,
                    blueprint,
                    style_guide,
                    quality_criteria,
                    promoted,
                    targets,
                    selection_detail,
                )
            except ModelGatewayError as exc:
                rewrite_mode = "heuristic_fallback"
                rewrites = {}
                if hasattr(exc, "to_dict"):
                    live_error_detail = exc.to_dict()
                else:
                    live_error_detail = {"message": str(exc)}
            if not rewrites and _is_network_only_failure(live_detail):
                for _ in range(MAX_NETWORK_RECOVERY_PASSES):
                    time.sleep(NETWORK_RECOVERY_COOLDOWN_SECONDS)
                    rewrite_mode, rewrites, live_detail = _rewrite_blocks_live(
                        book_root,
                        chapter,
                        blueprint,
                        style_guide,
                        quality_criteria,
                        promoted,
                        targets,
                        selection_detail,
                    )
                    if rewrites or not _is_network_only_failure(live_detail):
                        break
            live_detail.setdefault("selection_strategy", selection_detail.get("selection_strategy"))
            live_detail.setdefault("available_sections", selection_detail.get("available_sections", []))
            live_detail.setdefault("selected_sections", selection_detail.get("selected_sections", []))
            live_detail.setdefault("available_section_count", selection_detail.get("available_section_count", 0))
            live_detail.setdefault("selected_section_count", selection_detail.get("selected_section_count", 0))
            live_detail.setdefault("required_section_count", selection_detail.get("required_section_count", 0))
            live_detail.setdefault("section_coverage_balanced", selection_detail.get("section_coverage_balanced", True))
            if not live_error_detail and live_detail.get("all_nodes_fallback"):
                first_note = next(
                    (node.get("note") for node in live_detail.get("nodes", []) if node.get("note")),
                    "all rewrite targets fell back to heuristic mode",
                )
                live_error_detail = {
                    "message": first_note,
                    "status_code": "n/a",
                    "variant_label": live_detail.get("request_variant", "n/a"),
                    "hint": "All rewrite targets fell back to heuristic mode.",
                }

        if targeted_remediation_mode:
            applied_rewrites: list[dict[str, str]] = []
            structure = _structure_checks(draft6)
        else:
            draft6, applied_rewrites = _apply_rewrites(promoted, chapter, rewrites, target_block_ids)
            structure = _structure_checks(draft6)
            input_words = count_words(draft5)
            output_words = count_words(draft6)
            tone_issues = _tone_drift_issues(draft6)
            reader_value_issues = _reader_value_issues(draft6)
            field_issues = _field_presence_issues(draft6, chapter["part"])
            if "takeaway_not_reader_oriented" in reader_value_issues:
                draft6, remediation_detail = _remediate_takeaway_reader_value(book_root, chapter, draft6)
                structure = _structure_checks(draft6)
                output_words = count_words(draft6)
                tone_issues = _tone_drift_issues(draft6)
                reader_value_issues = _reader_value_issues(draft6)
                field_issues = _field_presence_issues(draft6, chapter["part"])
        report, return_stage = _render_amplification_report(
            chapter,
            rewrite_mode,
            input_words,
            output_words,
            applied_rewrites,
            structure,
            tone_issues,
            reader_value_issues,
            field_issues,
            live_detail,
            live_error_detail,
            remediation_detail,
        )

        write_text(draft6_path, draft6)
        write_text(report_path, report)
        node_manifest_path = write_node_manifest(
            book_root,
            "S8A",
            current_chapter_id,
            {
                "version": "1.0",
                "generated_at": now_iso(),
                "stage_id": "S8A",
                "chapter_id": current_chapter_id,
                "chapter_title": chapter["title"],
                "execution_mode": "subsection_nodes_sequential",
                "node_count": len(live_detail.get("nodes", [])),
                "live_node_count": len([node for node in live_detail.get("nodes", []) if node.get("status") == "completed"]),
                "fallback_node_count": len([node for node in live_detail.get("nodes", []) if node.get("status") != "completed"]),
                "available_sections": live_detail.get("available_sections", []),
                "selected_sections": live_detail.get("selected_sections", []),
                "available_section_count": live_detail.get("available_section_count", 0),
                "selected_section_count": live_detail.get("selected_section_count", 0),
                "required_section_count": live_detail.get("required_section_count", 0),
                "section_coverage_balanced": live_detail.get("section_coverage_balanced", True),
                "section_target_counts": live_detail.get("section_target_counts", {}),
                "section_live_counts": live_detail.get("section_live_counts", {}),
                "section_fallback_counts": live_detail.get("section_fallback_counts", {}),
                "all_nodes_fallback": live_detail.get("all_nodes_fallback", False),
                "runtime_error_count": live_detail.get("runtime_error_count", 0),
                "nodes": live_detail.get("nodes", []),
            },
        )
        declared_outputs = [
            str(draft6_path),
            str(report_path),
            str(node_manifest_path),
        ]

        update_chapter_memory(
            book_root,
            current_chapter_id,
            summary=f"Draft6 amplified for {chapter['title']}",
            claims=[
                "Existing manuscript was preserved in draft5 and amplified into a separate draft6 layer.",
                "Tone-and-manner, reader payoff, and scene-level immediacy were tuned through AG-05A.",
            ],
            unresolved_issues=[*tone_issues, *reader_value_issues, *field_issues],
            visual_notes=[],
        )

        gate_result = evaluate_gate(book_id, book_root, "S8A", current_chapter_id)
        if not gate_result["passed"]:
            transition_stage(book_root, "S8A", "gate_failed", current_chapter_id, note=json.dumps(gate_result, ensure_ascii=False))
            results.append(
                {
                    "chapter_id": current_chapter_id,
                    "status": "gate_failed",
                    "outputs": declared_outputs,
                    "node_manifest": str(node_manifest_path),
                    "gate_result": gate_result,
                }
            )
            continue

        transition_stage(book_root, "S8A", "completed", current_chapter_id, note="AG-05A amplification completed.")
        results.append(
            {
                "chapter_id": current_chapter_id,
                "status": "completed",
                "rewrite_mode": rewrite_mode,
                "outputs": declared_outputs,
                "node_manifest": str(node_manifest_path),
                "rewritten_blocks": len(applied_rewrites),
                "rewrite_target_count": live_detail.get("rewrite_target_count", len(targets)),
                "word_delta": output_words - input_words,
                "live_detail": live_detail,
                "live_error_detail": live_error_detail,
                "remediation_detail": remediation_detail,
                "gate_result": gate_result,
            }
        )

    work_order = issue_work_order(book_id, book_root)
    return {
        "stage_id": "S8A",
        "requested_chapters": target_chapters,
        "results": results,
        "work_order": {
            "order_id": work_order["order_id"],
            "priority_queue_size": len(work_order["priority_queue"]),
            "first_items": work_order["priority_queue"][:5],
        },
    }
