from __future__ import annotations

import json
import os
import re
from html import escape
from pathlib import Path
from typing import Any

from .book_state import load_book_db
from .common import ensure_dir, now_iso, read_json, read_text, write_json, write_text
from .contracts import validate_inputs
from .gates import evaluate_gate
from .memory import update_chapter_memory
from .references import build_reference_appendix
from .stage import transition_stage
from .work_order import issue_work_order


def _pending_s7_chapters(book_root: Path) -> list[str]:
    payload = load_book_db(book_root)
    return [
        chapter_id
        for chapter_id in payload["chapter_sequence"]
        if payload["chapters"][chapter_id]["stages"]["S7"]["status"] in {"pending", "in_progress", "gate_failed"}
        or (
            payload["chapters"][chapter_id]["stages"]["S7"]["status"] == "completed"
            and (
                not (book_root / "manuscripts" / "_draft4" / f"{chapter_id}_draft4.md").exists()
                or not (book_root / "manuscripts" / "_draft4" / f"{chapter_id}_visual_bundle.json").exists()
            )
        )
    ]


def _all_s7_chapters(book_root: Path) -> list[str]:
    payload = load_book_db(book_root)
    return [
        chapter_id
        for chapter_id in payload["chapter_sequence"]
        if payload["chapters"][chapter_id]["stages"]["S7"]["status"] in {"completed", "gate_failed"}
    ]


def _chapter_reference_entries(reference_index: dict[str, Any], chapter_id: str) -> list[dict[str, Any]]:
    for chapter in reference_index.get("chapters", []):
        if chapter["chapter_id"] == chapter_id:
            return chapter.get("entries", [])
    raise KeyError(f"Missing reference index entry for {chapter_id}")


def _reference_entry(reference_entries: list[dict[str, Any]], appendix_ref_id: str) -> dict[str, Any]:
    for entry in reference_entries:
        if entry["reference_id"] == appendix_ref_id:
            return entry
    raise KeyError(f"Missing reference entry for {appendix_ref_id}")


def _image_item(image_manifest: dict[str, Any], appendix_ref_id: str) -> dict[str, Any]:
    for item in image_manifest.get("items", []):
        if item["appendix_reference_id"] == appendix_ref_id:
            return item
    raise KeyError(f"Missing image manifest item for {appendix_ref_id}")


def _asset_request_map(asset_collection_manifest: dict[str, Any] | None) -> dict[str, dict[str, Any]]:
    if not isinstance(asset_collection_manifest, dict):
        return {}
    return {
        item.get("anchor_id"): item
        for item in asset_collection_manifest.get("asset_requests", [])
        if item.get("anchor_id")
    }


def _first_cleared_asset(book_root: Path, asset_request: dict[str, Any] | None) -> Path | None:
    if not isinstance(asset_request, dict):
        return None
    for relative_path in asset_request.get("detected_files", []):
        candidate = (book_root / relative_path).resolve()
        if candidate.exists() and candidate.is_file():
            return candidate
    return None


def _load_visual_support(book_root: Path, chapter_id: str) -> dict[str, Any]:
    payload = read_json(book_root / "manuscripts" / "_draft3" / f"{chapter_id}_visual_support.json", default=None)
    if payload is None:
        raise FileNotFoundError(f"Missing visual support for {chapter_id}")
    return payload


def _trim(text: str, limit: int = 60) -> str:
    cleaned = " ".join(text.split())
    if len(cleaned) <= limit:
        return cleaned
    return cleaned[: limit - 3].rstrip() + "..."


def _safe_svg_text(text: str) -> str:
    return escape(text, quote=True)


def _relative_asset_path(draft4_path: Path, asset_path: Path) -> str:
    relative = os.path.relpath(asset_path, draft4_path.parent)
    return relative.replace("\\", "/")


def _asset_status(source_mode: str) -> str:
    if source_mode in {"external_image", "ai_generated_image", "video_embed"}:
        return "placeholder_rendered"
    return "structured_rendered"


def _anchor_reader_label(task: dict[str, Any]) -> str:
    mapping = {
        "BT": "비교 표",
        "PF": "흐름도",
        "HN": "구조도",
        "TL": "타임라인",
        "DS": "데이터 차트",
        "RM": "관계도",
        "AI": "AI 이미지",
        "EP": "외부 이미지",
        "TD": "기술 도해",
        "VE": "영상 링크",
        "SB": "요약 상자",
        "CO": "콜아웃",
        "FN": "각주",
        "MF": "수식",
        "CB": "코드 블록",
        "HL": "부록 링크",
    }
    anchor_type = str(task.get("anchor_type") or "")
    return mapping.get(anchor_type, str(task.get("anchor_name") or anchor_type or "시각 자료"))


def _support_packet_map(visual_support: dict[str, Any]) -> dict[str, dict[str, Any]]:
    return {
        item["anchor_id"]: item
        for item in visual_support.get("anchor_support", [])
        if item.get("anchor_id")
    }


def _quote_mermaid_label(value: str) -> str:
    return '"' + value.replace('"', "'") + '"'


def _number_unit_multiplier(unit: str) -> float:
    mapping = {
        "억": 100000000,
        "천만": 10000000,
        "만": 10000,
        "천": 1000,
        "백": 100,
        "십": 10,
        "명": 1,
        "배": 1,
    }
    return mapping.get(unit, 1)


def _numeric_series_from_packet(packet: dict[str, Any]) -> tuple[list[str], list[float], str, list[str]]:
    findings = packet.get("numeric_findings", []) if isinstance(packet, dict) else []
    viewer_points: list[tuple[str, float]] = []
    growth_points: list[tuple[str, float]] = []

    for finding in findings:
        if not isinstance(finding, str):
            continue
        if "관객" in finding:
            for raw, unit in re.findall(r"(\d[\d,]*(?:\.\d+)?)\s*(억|천만|만|천|백|명)", finding):
                normalized_raw = raw.replace(",", "")
                value = float(normalized_raw) * _number_unit_multiplier(unit)
                label = "누적 관객"
                if "삼일절" in finding:
                    label = "삼일절 관객"
                elif "3월 15일" in finding or "기준" in finding:
                    label = "3월 15일 누적"
                elif "약 한 달 만" in finding or "3월 초" in finding:
                    label = "초기 천만 돌파"
                viewer_points.append((label, value))
        if "전년 대비" in finding and "배" in finding:
            for raw in re.findall(r"(\d[\d,]*(?:\.\d+)?)\s*배", finding):
                growth_points.append(("방문객 증가", float(raw.replace(",", ""))))

    deduped_points: list[tuple[str, float]] = []
    seen_labels: set[str] = set()
    for label, value in viewer_points:
        if label in seen_labels:
            continue
        deduped_points.append((label, value))
        seen_labels.add(label)

    if len(deduped_points) >= 2:
        labels = [label for label, _ in deduped_points[:3]]
        values = [round(value / 10000, 1) for _, value in deduped_points[:3]]
        return labels, values, "관객(만 명)", []

    if growth_points:
        labels = [label for label, _ in growth_points[:3]]
        values = [value for _, value in growth_points[:3]]
        return labels, values, "증가 배수", []

    fallback_labels = ["도입", "맥락", "실전"]
    fallback_values = [35, 60, 85]
    return fallback_labels, fallback_values, "상대 비중", ["numeric_series_unparsed"]


def _svg_placeholder_asset(
    book_root: Path,
    draft4_path: Path,
    task: dict[str, Any],
    chapter_title: str,
) -> tuple[str, str]:
    asset_dir = ensure_dir(book_root / "publication" / "assets" / "generated")
    asset_path = asset_dir / f"{task['anchor_id']}.svg"
    title = _safe_svg_text(_anchor_reader_label(task))
    chapter = _safe_svg_text(_trim(chapter_title, 54))
    caption = _safe_svg_text(_trim(task["caption"], 76))
    appendix_ref = _safe_svg_text(task["appendix_ref_id"])
    source_mode = _safe_svg_text(task["source_mode"])
    svg = f"""<svg xmlns="http://www.w3.org/2000/svg" width="1200" height="675" viewBox="0 0 1200 675" role="img" aria-labelledby="{task['anchor_id']}-title">
  <title id="{task['anchor_id']}-title">{title}</title>
  <!-- appendix_ref={appendix_ref} source_mode={source_mode} -->
  <rect width="1200" height="675" fill="#f4efe6"/>
  <rect x="32" y="32" width="1136" height="611" rx="24" fill="#fffdfa" stroke="#d8c7ad" stroke-width="4"/>
  <text x="60" y="116" font-family="Georgia, serif" font-size="34" font-weight="700" fill="#59452b">{title}</text>
  <text x="60" y="170" font-family="Georgia, serif" font-size="24" fill="#786246">{chapter}</text>
  <text x="60" y="252" font-family="Arial, sans-serif" font-size="26" fill="#3e3a36">설명</text>
  <text x="60" y="292" font-family="Arial, sans-serif" font-size="24" fill="#3e3a36">{caption}</text>
  <text x="60" y="388" font-family="Arial, sans-serif" font-size="22" fill="#3e3a36">임시 시각 카드</text>
  <text x="60" y="426" font-family="Arial, sans-serif" font-size="22" fill="#3e3a36">확정 자산 연결 전 검수용 영역</text>
  <text x="60" y="520" font-family="Arial, sans-serif" font-size="22" fill="#8a5a2a">세부 provenance는 부록 인덱스에서 관리</text>
</svg>
"""
    write_text(asset_path, svg)
    return str(asset_path), _relative_asset_path(draft4_path, asset_path)


def _svg_text_block(lines: list[str], *, x: int, y: int, size: int, fill: str, line_height: int | None = None, weight: str = "400") -> str:
    safe_lines = [_safe_svg_text(line) for line in lines if line]
    if not safe_lines:
        return ""
    height = line_height or int(size * 1.45)
    tspans = [
        f'<tspan x="{x}" dy="{0 if index == 0 else height}">{line}</tspan>'
        for index, line in enumerate(safe_lines)
    ]
    return (
        f'<text x="{x}" y="{y}" font-family="Arial, sans-serif" font-size="{size}" '
        f'font-weight="{weight}" fill="{fill}">{"".join(tspans)}</text>'
    )


def _structured_svg_asset(
    book_root: Path,
    draft4_path: Path,
    task: dict[str, Any],
    chapter_title: str,
    support_packet: dict[str, Any] | None = None,
) -> tuple[str, str, list[str]]:
    asset_dir = ensure_dir(book_root / "publication" / "assets" / "generated")
    asset_path = asset_dir / f"{task['anchor_id']}.svg"
    title = _safe_svg_text(_anchor_reader_label(task))
    caption = _trim(task["caption"], 88)
    chapter = _trim(chapter_title, 56)
    accent = "#8a5a2a"
    panel = "#fffaf2"
    border = "#d8c7ad"
    ink = "#3e3326"
    soft = "#786246"
    packet_gaps: list[str] = []
    body_markup = ""

    if task["asset_mode"] == "chart":
        labels, values, y_axis_label, packet_gaps = _numeric_series_from_packet(support_packet or {})
        max_value = max(values) if values else 1
        left = 140
        baseline = 520
        chart_height = 240
        width = 660
        slot_width = width / max(1, len(values))
        bar_width = max(46, int(slot_width * 0.55))
        bars: list[str] = [
            f'<line x1="{left}" y1="{baseline}" x2="{left + width}" y2="{baseline}" stroke="{border}" stroke-width="3"/>',
            f'<line x1="{left}" y1="{baseline - chart_height}" x2="{left}" y2="{baseline}" stroke="{border}" stroke-width="3"/>',
        ]
        for index, (label, value) in enumerate(zip(labels, values), start=0):
            height = 0 if max_value == 0 else int((value / max_value) * (chart_height - 24))
            x = int(left + index * slot_width + (slot_width - bar_width) / 2)
            y = baseline - height
            bars.append(
                f'<rect x="{x}" y="{y}" width="{bar_width}" height="{height}" rx="10" fill="#c78e48"/>'
            )
            bars.append(
                f'<text x="{x + bar_width / 2}" y="{y - 14}" text-anchor="middle" font-family="Arial, sans-serif" font-size="22" fill="{ink}">{_safe_svg_text(str(int(value) if float(value).is_integer() else round(value, 1)))}</text>'
            )
            bars.append(
                f'<text x="{x + bar_width / 2}" y="{baseline + 34}" text-anchor="middle" font-family="Arial, sans-serif" font-size="20" fill="{soft}">{_safe_svg_text(_trim(label, 14))}</text>'
            )
        body_markup = "\n".join(
            [
                _svg_text_block([y_axis_label], x=140, y=236, size=24, fill=accent, weight="700"),
                *bars,
            ]
        )
    elif task["asset_mode"] == "timeline":
        steps = [chapter, "검증된 맥락 정리", _trim(caption, 28)]
        points = [210, 510, 810]
        shapes = [
            f'<line x1="{points[0]}" y1="360" x2="{points[-1]}" y2="360" stroke="{accent}" stroke-width="8" stroke-linecap="round"/>'
        ]
        for point, label in zip(points, steps):
            shapes.append(f'<circle cx="{point}" cy="360" r="18" fill="{accent}"/>')
            shapes.append(
                _svg_text_block([label], x=point - 100, y=430, size=22, fill=ink, line_height=28, weight="700")
            )
        body_markup = "\n".join(shapes)
    else:
        left_box = '<rect x="120" y="260" width="250" height="110" rx="22" fill="#f4efe6" stroke="#d8c7ad" stroke-width="3"/>'
        center_box = '<rect x="475" y="220" width="250" height="110" rx="22" fill="#fff4de" stroke="#c78e48" stroke-width="3"/>'
        right_box = '<rect x="830" y="260" width="250" height="110" rx="22" fill="#f4efe6" stroke="#d8c7ad" stroke-width="3"/>'
        connectors = [
            f'<line x1="370" y1="315" x2="475" y2="275" stroke="{accent}" stroke-width="5" stroke-linecap="round"/>',
            f'<line x1="725" y1="275" x2="830" y2="315" stroke="{accent}" stroke-width="5" stroke-linecap="round"/>',
        ]
        body_markup = "\n".join(
            [
                left_box,
                center_box,
                right_box,
                *connectors,
                _svg_text_block([chapter], x=150, y=304, size=22, fill=ink, line_height=28, weight="700"),
                _svg_text_block([f"{_anchor_reader_label(task)} 핵심"], x=510, y=270, size=22, fill=accent, line_height=28, weight="700"),
                _svg_text_block([_trim(caption, 24)], x=860, y=304, size=22, fill=ink, line_height=28, weight="700"),
            ]
        )

    diagnostic_comment = f"appendix_ref={_safe_svg_text(task['appendix_ref_id'])}"
    if packet_gaps:
        diagnostic_comment += f" support_gaps={_safe_svg_text(','.join(packet_gaps))}"
    svg = f"""<svg xmlns="http://www.w3.org/2000/svg" width="1200" height="675" viewBox="0 0 1200 675" role="img" aria-labelledby="{task['anchor_id']}-title">
  <title id="{task['anchor_id']}-title">{title}</title>
  <!-- {diagnostic_comment} -->
  <rect width="1200" height="675" fill="#f4efe6"/>
  <rect x="32" y="32" width="1136" height="611" rx="24" fill="{panel}" stroke="{border}" stroke-width="4"/>
  <text x="60" y="110" font-family="Georgia, serif" font-size="34" font-weight="700" fill="{accent}">{title}</text>
  <text x="60" y="160" font-family="Georgia, serif" font-size="24" fill="{soft}">{_safe_svg_text(chapter)}</text>
  {_svg_text_block([caption], x=60, y=208, size=24, fill=ink, line_height=30)}
  {body_markup}
  <text x="60" y="574" font-family="Arial, sans-serif" font-size="20" fill="{soft}">구조 시안</text>
</svg>
"""
    write_text(asset_path, svg)
    return str(asset_path), _relative_asset_path(draft4_path, asset_path), packet_gaps


def _render_structured_visual_block(
    book_root: Path,
    draft4_path: Path,
    task: dict[str, Any],
    chapter_title: str,
    support_packet: dict[str, Any] | None = None,
) -> tuple[str, dict[str, Any]]:
    asset_path, relative_path, packet_gaps = _structured_svg_asset(
        book_root,
        draft4_path,
        task,
        chapter_title,
        support_packet,
    )
    lines = [
        f"<!-- VISUAL_RENDER anchor_id=\"{task['anchor_id']}\" renderer=\"{task['renderer_hint']}\" status=\"structured_rendered\" appendix_ref=\"{task['appendix_ref_id']}\" -->",
        f"![{task['caption']}]({relative_path})",
        "",
        f"*그림.* {task['caption']}",
    ]
    if packet_gaps:
        lines.append(f"<!-- SUPPORT_GAPS {task['anchor_id']}: {', '.join(packet_gaps)} -->")
    return "\n".join(lines), {
        "asset_path": asset_path,
        "asset_relative_path": relative_path,
        "render_support_gaps": packet_gaps,
    }


def _render_table(task: dict[str, Any]) -> str:
    return "\n".join(
        [
            f"<!-- VISUAL_RENDER anchor_id=\"{task['anchor_id']}\" renderer=\"{task['renderer_hint']}\" status=\"structured_rendered\" appendix_ref=\"{task['appendix_ref_id']}\" -->",
            "| 항목 | 내용 |",
            "| --- | --- |",
            f"| 분류 | {_anchor_reader_label(task)} |",
            f"| 핵심 포인트 | {task['caption']} |",
        ]
    )


def _render_summary_box(task: dict[str, Any]) -> str:
    return "\n".join(
        [
            f"<!-- VISUAL_RENDER anchor_id=\"{task['anchor_id']}\" renderer=\"{task['renderer_hint']}\" status=\"structured_rendered\" appendix_ref=\"{task['appendix_ref_id']}\" -->",
            "> [!NOTE]",
            f"> 핵심 정리",
            f"> {task['caption']}",
        ]
    )


def _render_summary_box_from_packet(task: dict[str, Any], support_packet: dict[str, Any] | None) -> str:
    summary_points = support_packet.get("summary_points", []) if isinstance(support_packet, dict) else []
    lines = [
        f"<!-- VISUAL_RENDER anchor_id=\"{task['anchor_id']}\" renderer=\"{task['renderer_hint']}\" status=\"structured_rendered\" appendix_ref=\"{task['appendix_ref_id']}\" -->",
        "> [!NOTE]",
        f"> 핵심 요약",
    ]
    if summary_points:
        for point in summary_points[:4]:
            lines.append(f"> - {point}")
    else:
        lines.append(f"> {task['caption']}")
    return "\n".join(lines)


def _render_callout(task: dict[str, Any]) -> str:
    return "\n".join(
        [
            f"<!-- VISUAL_RENDER anchor_id=\"{task['anchor_id']}\" renderer=\"{task['renderer_hint']}\" status=\"structured_rendered\" appendix_ref=\"{task['appendix_ref_id']}\" -->",
            "> [!IMPORTANT]",
            f"> 참고 포인트",
            f"> {task['caption']}",
        ]
    )


def _render_footnote(task: dict[str, Any]) -> str:
    return "\n".join(
        [
            f"<!-- VISUAL_RENDER anchor_id=\"{task['anchor_id']}\" renderer=\"footnote\" status=\"structured_rendered\" appendix_ref=\"{task['appendix_ref_id']}\" -->",
            f"[^{task['anchor_id']}]: {task['caption']}",
        ]
    )


def _render_math(task: dict[str, Any]) -> str:
    return "\n".join(
        [
            f"<!-- VISUAL_RENDER anchor_id=\"{task['anchor_id']}\" renderer=\"{task['renderer_hint']}\" status=\"structured_rendered\" appendix_ref=\"{task['appendix_ref_id']}\" -->",
            "$$",
            r"impact = context + verified\_evidence + reader\_takeaway",
            "$$",
            "*공식형 시각 메모*",
        ]
    )


def _render_code(task: dict[str, Any]) -> str:
    return "\n".join(
        [
            f"<!-- VISUAL_RENDER anchor_id=\"{task['anchor_id']}\" renderer=\"{task['renderer_hint']}\" status=\"structured_rendered\" appendix_ref=\"{task['appendix_ref_id']}\" -->",
            "```text",
            f"# {_anchor_reader_label(task)}",
            f"# {task['caption']}",
            "```",
        ]
    )


def _render_hyperlink(task: dict[str, Any]) -> str:
    return "\n".join(
        [
            f"<!-- VISUAL_RENDER anchor_id=\"{task['anchor_id']}\" renderer=\"{task['renderer_hint']}\" status=\"structured_rendered\" appendix_ref=\"{task['appendix_ref_id']}\" -->",
            f"[관련 부록 보기](#appendix-{task['appendix_ref_id'].lower()})",
        ]
    )


def _render_asset_block(
    book_root: Path,
    draft4_path: Path,
    task: dict[str, Any],
    chapter_title: str,
    asset_request: dict[str, Any] | None = None,
) -> tuple[str, dict[str, Any]]:
    cleared_asset = _first_cleared_asset(book_root, asset_request)
    if cleared_asset is not None and cleared_asset.suffix.lower() in {".gif", ".jpeg", ".jpg", ".png", ".svg", ".webp"}:
        relative_path = _relative_asset_path(draft4_path, cleared_asset)
        lines = [
            f"<!-- VISUAL_RENDER anchor_id=\"{task['anchor_id']}\" renderer=\"{task['renderer_hint']}\" status=\"asset_bound\" appendix_ref=\"{task['appendix_ref_id']}\" source_mode=\"{task['source_mode']}\" -->",
            f"![{task['caption']}]({relative_path})",
            "",
            f"*그림.* {task['caption']}",
            f"<!-- OFFLINE_ASSET_BOUND {task['anchor_id']}: {cleared_asset.name} -->",
        ]
        return "\n".join(lines), {
            "asset_path": str(cleared_asset),
            "asset_relative_path": relative_path,
            "render_status": "asset_bound",
            "provenance_status": "cleared_asset_bound",
        }

    asset_path, relative_path = _svg_placeholder_asset(book_root, draft4_path, task, chapter_title)
    lines = [
        f"<!-- VISUAL_RENDER anchor_id=\"{task['anchor_id']}\" renderer=\"{task['renderer_hint']}\" status=\"placeholder_rendered\" appendix_ref=\"{task['appendix_ref_id']}\" source_mode=\"{task['source_mode']}\" -->",
        f"![{task['caption']}]({relative_path})",
        "",
        f"*그림.* {task['caption']}",
    ]
    if task["source_mode"] == "external_image":
        lines.append("<!-- OFFLINE_ASSET_STATUS external_image_pending -->")
    elif task["source_mode"] == "ai_generated_image":
        lines.append("<!-- OFFLINE_ASSET_STATUS ai_generation_pending -->")
    elif task["source_mode"] == "video_embed":
        lines.append("<!-- OFFLINE_ASSET_STATUS video_binding_pending -->")
    else:
        lines.append("<!-- OFFLINE_ASSET_STATUS production_file_pending -->")
    return "\n".join(lines), {"asset_path": asset_path, "asset_relative_path": relative_path}


def _render_task(
    book_root: Path,
    draft4_path: Path,
    task: dict[str, Any],
    chapter_title: str,
    support_packet: dict[str, Any] | None = None,
    asset_request: dict[str, Any] | None = None,
) -> dict[str, Any]:
    extra: dict[str, Any] = {}
    if task["source_mode"] in {"external_image", "ai_generated_image", "technical_asset", "video_embed"}:
        markup, extra = _render_asset_block(book_root, draft4_path, task, chapter_title, asset_request)
    elif task["asset_mode"] in {"flowchart", "timeline", "network", "chart", "diagram"}:
        markup, extra = _render_structured_visual_block(
            book_root,
            draft4_path,
            task,
            chapter_title,
            support_packet,
        )
    elif task["asset_mode"] == "table":
        markup = _render_table(task)
    elif task["asset_mode"] == "summary_box":
        markup = _render_summary_box_from_packet(task, support_packet)
    elif task["asset_mode"] == "callout":
        markup = _render_callout(task)
    elif task["asset_mode"] == "footnote":
        markup = _render_footnote(task)
    elif task["asset_mode"] == "math_formula":
        markup = _render_math(task)
    elif task["asset_mode"] == "code_block":
        markup = _render_code(task)
    elif task["asset_mode"] == "hyperlink":
        markup = _render_hyperlink(task)
    else:
        markup = "\n".join(
            [
                f"<!-- VISUAL_RENDER anchor_id=\"{task['anchor_id']}\" renderer=\"{task['renderer_hint']}\" status=\"structured_rendered\" appendix_ref=\"{task['appendix_ref_id']}\" -->",
                f"> 시각 메모",
                f"> {task['caption']}",
            ]
        )

    return {
        "anchor_id": task["anchor_id"],
        "anchor_type": task["anchor_type"],
        "anchor_name": task["anchor_name"],
        "asset_mode": task["asset_mode"],
        "source_mode": task["source_mode"],
        "renderer_hint": task["renderer_hint"],
        "appendix_ref_id": task["appendix_ref_id"],
        "priority": task["priority"],
        "render_status": extra.get("render_status", _asset_status(task["source_mode"])),
        "markup": markup,
        "provenance_status": extra.get(
            "provenance_status",
            "pending_fill" if task["source_mode"] in {"external_image", "ai_generated_image", "video_embed"} else "structural_ready",
        ),
        "support_packet_type": support_packet.get("packet_type") if isinstance(support_packet, dict) else None,
        "support_packet_status": support_packet.get("packet_status") if isinstance(support_packet, dict) else None,
        "support_gaps": [
            *(support_packet.get("gaps", []) if isinstance(support_packet, dict) else []),
            *extra.get("render_support_gaps", []),
        ],
        **extra,
    }


def _integrate_rendered_markup(draft3: str, rendered_items: list[dict[str, Any]]) -> tuple[str, list[str]]:
    lines = draft3.splitlines()
    if lines and lines[0].startswith("# DRAFT"):
        if ":" in lines[0]:
            _, suffix = lines[0].split(":", 1)
            lines[0] = f"# DRAFT4:{suffix}"
        else:
            lines[0] = "# DRAFT4"
    integrated = "\n".join(lines)
    unresolved_slots: list[str] = []
    for item in rendered_items:
        slot = f"[ANCHOR_SLOT:{item['anchor_id']}]"
        if slot not in integrated:
            unresolved_slots.append(item["anchor_id"])
            continue
        integrated = integrated.replace(slot, item["markup"])
    return integrated.rstrip() + "\n", unresolved_slots


def _update_reference_status(
    reference_index: dict[str, Any],
    image_manifest: dict[str, Any],
    chapter_id: str,
    rendered_items: list[dict[str, Any]],
) -> dict[str, list[str]]:
    reference_entries = _chapter_reference_entries(reference_index, chapter_id)
    updated_refs: list[str] = []
    updated_images: list[str] = []
    rendered_at = now_iso()

    for item in rendered_items:
        reference_entry = _reference_entry(reference_entries, item["appendix_ref_id"])
        reference_entry["status"] = item["render_status"]
        reference_entry["rendered_anchor_id"] = item["anchor_id"]
        reference_entry["rendered_at"] = rendered_at
        reference_entry["provenance_status"] = item["provenance_status"]
        image_item = _image_item(image_manifest, item["appendix_ref_id"])
        image_item["status"] = item["render_status"]
        image_item["rendered_anchor_id"] = item["anchor_id"]
        image_item["rendered_at"] = rendered_at
        image_item["renderer_hint"] = item["renderer_hint"]
        updated_refs.append(reference_entry["reference_id"])
        updated_images.append(image_item["image_id"])

    reference_index["generated_at"] = rendered_at
    image_manifest["generated_at"] = rendered_at
    return {"reference_ids": updated_refs, "image_ids": updated_images}


def _visual_bundle(
    book_id: str,
    chapter_id: str,
    chapter_title: str,
    visual_plan: dict[str, Any],
    rendered_items: list[dict[str, Any]],
    unresolved_slots: list[str],
) -> dict[str, Any]:
    total = len(rendered_items)
    resolved = total - len(unresolved_slots)
    return {
        "version": "1.0",
        "generated_at": now_iso(),
        "book_id": book_id,
        "chapter_id": chapter_id,
        "chapter_title": chapter_title,
        "render_strategy": visual_plan.get("render_strategy"),
        "status": "structurally_rendered" if not unresolved_slots else "partial_render",
        "priority_items": visual_plan.get("priority_items", []),
        "resolution": {
            "anchor_total": total,
            "resolved_anchor_count": resolved,
            "unresolved_anchor_ids": unresolved_slots,
            "anchor_resolve_rate": round((resolved / total), 4) if total else 0.0,
            "placeholder_asset_count": sum(
                1 for item in rendered_items if item["render_status"] == "placeholder_rendered"
            ),
        },
        "anchors": rendered_items,
    }


def run_visual_render(
    book_id: str,
    book_root: Path,
    chapter_id: str | None = None,
    *,
    rerun_completed: bool = False,
) -> dict[str, Any]:
    reference_index = read_json(book_root / "research" / "reference_index.json", default=None)
    image_manifest = read_json(book_root / "research" / "image_manifest.json", default=None)
    citations_payload = read_json(book_root / "research" / "citations.json", default=None)
    if reference_index is None or image_manifest is None or citations_payload is None:
        raise FileNotFoundError("S7 requires reference_index.json, image_manifest.json, and citations.json.")

    book_db = load_book_db(book_root)
    target_chapters = [chapter_id] if chapter_id else (
        _all_s7_chapters(book_root) if rerun_completed else _pending_s7_chapters(book_root)
    )
    if not target_chapters:
        return {
            "stage_id": "S7",
            "status": "no_op",
            "message": "No pending S7 chapters found.",
        }

    results = []
    for current_chapter_id in target_chapters:
        contract_status = validate_inputs(book_id, book_root, "S7", current_chapter_id)
        if not contract_status["valid"]:
            raise FileNotFoundError(f"S7 inputs missing for {current_chapter_id}: {contract_status['missing_inputs']}")

        chapter = {
            "chapter_id": current_chapter_id,
            "title": book_db["chapters"][current_chapter_id]["title"],
            "part": book_db["chapters"][current_chapter_id].get("part"),
        }
        draft3_path = book_root / "manuscripts" / "_draft3" / f"{current_chapter_id}_draft3.md"
        visual_plan_path = book_root / "manuscripts" / "_draft3" / f"{current_chapter_id}_visual_plan.json"
        visual_support_path = book_root / "manuscripts" / "_draft3" / f"{current_chapter_id}_visual_support.json"
        draft4_path = book_root / "manuscripts" / "_draft4" / f"{current_chapter_id}_draft4.md"
        visual_bundle_path = book_root / "manuscripts" / "_draft4" / f"{current_chapter_id}_visual_bundle.json"
        current_status = book_db["chapters"][current_chapter_id]["stages"]["S7"]["status"]
        missing_outputs = [
            path
            for path in (draft4_path, visual_bundle_path)
            if not path.exists()
        ]
        if current_status == "gate_failed":
            transition_stage(
                book_root,
                "S7",
                "pending",
                current_chapter_id,
                note="AG-04 visual render rerun requested.",
            )
            transition_stage(
                book_root,
                "S7",
                "in_progress",
                current_chapter_id,
                note="AG-04 visual render restarted.",
            )
        elif current_status == "completed" and rerun_completed:
            transition_stage(
                book_root,
                "S7",
                "in_progress",
                current_chapter_id,
                note="AG-04 visual render rerun requested for refreshed draft3.",
            )
        elif current_status != "completed":
            transition_stage(
                book_root,
                "S7",
                "in_progress",
                current_chapter_id,
                note="AG-04 visual render started.",
            )
        elif missing_outputs:
            transition_stage(
                book_root,
                "S7",
                "in_progress",
                current_chapter_id,
                note="AG-04 visual render regeneration started from missing outputs.",
            )

        draft3 = read_text(draft3_path)
        visual_plan = read_json(visual_plan_path, default=None)
        visual_support = read_json(visual_support_path, default=None)
        asset_collection_manifest = read_json(Path(contract_status["existing_inputs"][3]), default=None)
        if visual_plan is None:
            raise FileNotFoundError(f"Missing visual plan for {current_chapter_id}")
        if visual_support is None:
            raise FileNotFoundError(f"Missing visual support for {current_chapter_id}")
        support_map = _support_packet_map(visual_support)
        asset_request_map = _asset_request_map(asset_collection_manifest)

        rendered_items = [
            _render_task(
                book_root,
                draft4_path,
                task,
                chapter["title"],
                support_map.get(task["anchor_id"]),
                asset_request_map.get(task["anchor_id"]),
            )
            for task in visual_plan.get("anchors", [])
        ]
        draft4, unresolved_slots = _integrate_rendered_markup(draft3, rendered_items)
        bundle = _visual_bundle(book_id, current_chapter_id, chapter["title"], visual_plan, rendered_items, unresolved_slots)

        sync_result = _update_reference_status(reference_index, image_manifest, current_chapter_id, rendered_items)
        appendix_text = build_reference_appendix(book_id, reference_index, image_manifest, citations_payload)

        write_text(draft4_path, draft4)
        write_json(visual_bundle_path, bundle)
        write_json(book_root / "research" / "reference_index.json", reference_index)
        write_json(book_root / "research" / "image_manifest.json", image_manifest)
        write_text(book_root / "publication" / "appendix" / "REFERENCE_INDEX.md", appendix_text)

        update_chapter_memory(
            book_root,
            current_chapter_id,
            summary=f"Draft4 visual render ready for {chapter['title']}",
            claims=[
                "Every planned visual anchor was structurally rendered through the AG-04 dispatcher.",
                "Appendix reference statuses were synchronized with visual render outputs.",
            ],
            citations_summary=sync_result["reference_ids"],
            unresolved_issues=[f"slot_missing:{anchor_id}" for anchor_id in unresolved_slots],
            visual_notes=[item["anchor_id"] for item in rendered_items],
        )

        gate_result = evaluate_gate(book_id, book_root, "S7", current_chapter_id)
        if not gate_result["passed"]:
            transition_stage(
                book_root,
                "S7",
                "gate_failed",
                current_chapter_id,
                note=json.dumps(gate_result, ensure_ascii=False),
            )
            results.append(
                {
                    "chapter_id": current_chapter_id,
                    "status": "gate_failed",
                    "gate_result": gate_result,
                }
            )
            continue

        transition_stage(
            book_root,
            "S7",
            "completed",
            current_chapter_id,
            note="AG-04 visual render completed.",
        )
        results.append(
            {
                "chapter_id": current_chapter_id,
                "status": "completed",
                "outputs": [
                    str(draft4_path),
                    str(visual_bundle_path),
                ],
                "resolved_anchor_rate": bundle["resolution"]["anchor_resolve_rate"],
                "updated_reference_ids": sync_result["reference_ids"],
                "gate_result": gate_result,
            }
        )

    work_order = issue_work_order(book_id, book_root)
    return {
        "stage_id": "S7",
        "requested_chapters": target_chapters,
        "results": results,
        "work_order": {
            "order_id": work_order["order_id"],
            "priority_queue_size": len(work_order["priority_queue"]),
            "first_items": work_order["priority_queue"][:5],
        },
    }
