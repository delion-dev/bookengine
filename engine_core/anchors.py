from __future__ import annotations

import re
from typing import Any

from .common import PLATFORM_CORE_ROOT, now_iso, read_json
from .section_labels import display_section_label
from .targets import get_chapter_target


ANCHOR_CATALOG_PATH = PLATFORM_CORE_ROOT / "anchor_type_catalog.json"


def load_anchor_catalog() -> dict[str, Any]:
    payload = read_json(ANCHOR_CATALOG_PATH, default=None)
    if payload is None:
        raise FileNotFoundError(f"Missing anchor catalog: {ANCHOR_CATALOG_PATH}")
    return payload


def _catalog_map() -> dict[str, dict[str, Any]]:
    return {
        item["anchor_type"]: item
        for item in load_anchor_catalog().get("anchor_types", [])
    }


def _chapter_code(chapter_id: str) -> str:
    if chapter_id == "intro":
        return "CH00"
    if chapter_id == "outro":
        return "CH99"
    match = re.match(r"ch(\d+)", chapter_id, re.IGNORECASE)
    if match:
        return f"CH{int(match.group(1)):02d}"
    return "CH00"


def create_anchor_id(book_id: str, chapter_id: str, anchor_type: str, index: int) -> str:
    catalog_item = _catalog_map()[anchor_type]
    type_code = catalog_item.get("type_code", catalog_item["anchor_type"])
    return f"{_chapter_code(chapter_id)}_{type_code}_{index:03d}"


def render_anchor_block(anchor: dict[str, Any]) -> str:
    caption = anchor["caption"].replace('"', "'").strip()
    reference_ids = ",".join(anchor.get("reference_ids", []))
    start = (
        f'<!-- ANCHOR_START id="{anchor["anchor_id"]}" '
        f'type="{anchor["anchor_type"]}" '
        f'placement="{anchor["placement"]}" '
        f'asset_mode="{anchor["asset_mode"]}" '
        f'priority="{anchor["priority"]}" '
        f'reference_ids="{reference_ids}" '
        f'appendix_ref="{anchor.get("appendix_ref_id", "")}" '
        f'caption="{caption}" -->'
    )
    slot = f'[ANCHOR_SLOT:{anchor["anchor_id"]}]'
    end = f'<!-- ANCHOR_END id="{anchor["anchor_id"]}" -->'
    return "\n".join([start, slot, end])


def _part_anchor_types(chapter: dict[str, Any]) -> list[str]:
    part = chapter.get("part", "")
    title = chapter["title"]
    if chapter["chapter_id"] == "intro":
        return ["SB", "DS"]
    if chapter["chapter_id"] == "outro":
        return ["SB", "AI"]
    if "CINEMA" in part:
        ordered = ["BT", "CO", "DS"]
        if "[HOT ISSUE]" in title:
            ordered = ["TL", "BT", "CO"]
        return ordered
    if "HISTORY" in part:
        return ["TL", "RM", "FN"]
    if "TRAVEL" in part:
        return ["EP", "PF", "CO"]
    if "TASTE" in part:
        return ["EP", "BT", "SB"]
    return ["SB", "DS"]


def _chapter_anchor_types(chapter: dict[str, Any], budget: int) -> list[str]:
    preferred = _part_anchor_types(chapter)
    return preferred[:budget]


def _caption_text(chapter: dict[str, Any], anchor_type: str) -> str:
    title = chapter["title"]
    catalog_item = _catalog_map()[anchor_type]
    captions = {
        "BT": f"{title}의 핵심 비교 항목을 구조화한 블록 테이블",
        "PF": f"{title}와 연결된 절차나 동선을 보여주는 프로세스 플로우",
        "HN": f"{title}의 위계와 포함 관계를 보여주는 계층 노드",
        "TL": f"{title}의 시간 순서와 변화를 보여주는 타임라인",
        "DS": f"{title} 관련 수치와 추이를 시각화한 데이터 스탯",
        "RM": f"{title}의 인물·개념 관계를 보여주는 릴레이션 맵",
        "AI": f"{title}의 분위기와 상징을 압축한 AI 일러스트",
        "EP": f"{title}와 직접 연결되는 외부 사진 또는 스틸",
        "TD": f"{title}를 설명하는 기술 도면 또는 고해상도 자산",
        "VE": f"{title}와 연결된 영상 참조 또는 QR 자산",
        "SB": f"{title}의 핵심을 먼저 잡아주는 요약 박스",
        "CO": f"{title}를 읽는 데 필요한 팁·경고·노트를 강조하는 콜아웃",
        "FN": f"{title}의 용어와 참고 지점을 보강하는 각주",
        "MF": f"{title}와 연결된 계산식 또는 공식 렌더링",
        "CB": f"{title} 관련 코드 또는 설정 블록",
        "HL": f"{title}와 연결되는 내부·외부 하이퍼링크",
    }
    return captions.get(anchor_type, f"{title} 관련 {catalog_item['anchor_name']}")


def _placement(anchor_type: str) -> str:
    return _catalog_map()[anchor_type]["default_placement"]


def build_anchor_policy(
    book_id: str,
    working_title: str,
    intake_manifest: dict[str, Any],
    word_targets: dict[str, Any],
) -> dict[str, Any]:
    catalog = load_anchor_catalog()
    chapters = []
    total_budget = 0
    for chapter in intake_manifest.get("chapters_detected", []):
        target = get_chapter_target(word_targets, chapter["chapter_id"])
        anchor_types = _chapter_anchor_types(chapter, target["anchor_budget"])
        total_budget += len(anchor_types)
        chapters.append(
            {
                "chapter_id": chapter["chapter_id"],
                "anchor_budget": target["anchor_budget"],
                "preferred_anchor_types": anchor_types,
                "default_placements": [
                    {
                        "anchor_type": anchor_type,
                        "placement": _placement(anchor_type),
                    }
                    for anchor_type in anchor_types
                ],
            }
        )

    return {
        "version": "1.0",
        "generated_at": now_iso(),
        "book_id": book_id,
        "working_title": working_title,
        "catalog_version": catalog["version"],
        "grammar": {
            "block_type": "html_comment_anchor_block",
            "start_pattern": "<!-- ANCHOR_START id=\"{anchor_id}\" type=\"{anchor_type}\" placement=\"{placement}\" asset_mode=\"{asset_mode}\" priority=\"{priority}\" reference_ids=\"{reference_ids}\" appendix_ref=\"{appendix_ref}\" caption=\"{caption}\" -->",
            "slot_pattern": "[ANCHOR_SLOT:{anchor_id}]",
            "end_pattern": "<!-- ANCHOR_END id=\"{anchor_id}\" -->",
            "pair_rule": "ANCHOR_START and ANCHOR_END must use the same anchor_id and contain exactly one ANCHOR_SLOT",
            "insertion_rule": "inject after the declared manuscript section unless a later visual stage overrides placement with a validated patch",
        },
        "reference_policy": {
            "external_materials_must_be_indexed": True,
            "ai_generated_images_must_record_prompt_provenance": True,
            "appendix_reference_file": "publication/appendix/REFERENCE_INDEX.md",
            "commercial_publication_rights_review_required": True,
            "news_text_must_be_paraphrased": True,
            "ugc_requires_consent_or_aggregation": True,
            "third_party_visuals_require_permission_or_safe_replacement": True,
            "map_or_platform_screenshots_require_license_review": True,
        },
        "visual_source_priority": [
            "self_shot_or_self_created",
            "public_license_or_public_domain",
            "written_permission_asset",
            "illustrated_reinterpretation",
            "engine_structured_visual",
            "ai_generated_image_with_provenance",
        ],
        "total_anchor_budget": total_budget,
        "chapters": chapters,
    }


def build_anchor_plan_for_chapter(
    book_id: str,
    chapter: dict[str, Any],
    chapter_target: dict[str, Any],
    chapter_policy: dict[str, Any],
) -> dict[str, Any]:
    catalog = _catalog_map()
    anchors = []
    for index, anchor_type in enumerate(chapter_policy.get("preferred_anchor_types", []), start=1):
        catalog_item = catalog[anchor_type]
        anchor_id = create_anchor_id(book_id, chapter["chapter_id"], anchor_type, index)
        reference_id = f"REF_{chapter['chapter_id'].upper()}_VIS_{index:03d}"
        anchor = {
            "anchor_id": anchor_id,
            "global_anchor_key": f"{book_id}::{anchor_id}",
            "anchor_type": anchor_type,
            "anchor_name": catalog_item["anchor_name"],
            "type_code": catalog_item.get("type_code", catalog_item["anchor_type"]),
            "anchor_mode": catalog_item["anchor_mode"],
            "category": catalog_item["category"],
            "placement": catalog_item["default_placement"],
            "asset_mode": catalog_item["default_asset_mode"],
            "renderer_hint": catalog_item["renderer_hint"],
            "major_engine": catalog_item["major_engine"],
            "grammar": catalog_item["grammar"],
            "quality_gate": catalog_item["quality_gate"],
            "priority": "high" if index == 1 else "medium",
            "caption": _caption_text(chapter, anchor_type),
            "appendix_ref_id": reference_id,
            "reference_ids": [reference_id],
            "reference_requirements": catalog_item["reference_requirements"],
            "justification": catalog_item["decision_rule"],
        }
        anchor["injection_block"] = render_anchor_block(anchor)
        anchors.append(anchor)

    return {
        "version": "1.0",
        "generated_at": now_iso(),
        "book_id": book_id,
        "chapter_id": chapter["chapter_id"],
        "chapter_title": chapter["title"],
        "target_words": chapter_target["target_words"],
        "anchor_budget": chapter_target["anchor_budget"],
        "anchors": anchors,
    }


def get_chapter_policy(anchor_policy: dict[str, Any], chapter_id: str) -> dict[str, Any]:
    for chapter in anchor_policy.get("chapters", []):
        if chapter["chapter_id"] == chapter_id:
            return chapter
    raise KeyError(f"Missing anchor policy for {chapter_id}")


def inject_anchor_blocks(markdown: str, anchor_plan: dict[str, Any]) -> str:
    lines = markdown.splitlines()
    insertions: list[tuple[int, list[str]]] = []

    for anchor in anchor_plan.get("anchors", []):
        placement = anchor["placement"]
        section_name = placement.split(":", 1)[1] if ":" in placement else "Insight"
        section_key = section_name.lower()
        heading_candidates = [f"## {section_name}"]
        if section_key in {"hook", "context", "insight", "takeaway"}:
            heading_candidates.append(f"## {display_section_label(section_key)}")
        index = len(lines)
        mode = "after_section"
        if placement.startswith("after_heading:"):
            mode = "after_heading"

        for line_index, line in enumerate(lines):
            if line.strip() not in heading_candidates:
                continue
            if mode == "after_heading":
                index = line_index + 1
            else:
                index = line_index + 1
                while index < len(lines) and not lines[index].startswith("## "):
                    index += 1
            break

        block_lines = ["", *anchor["injection_block"].splitlines(), ""]
        insertions.append((index, block_lines))

    for index, block_lines in sorted(insertions, key=lambda item: item[0], reverse=True):
        lines[index:index] = block_lines

    return "\n".join(lines).strip() + "\n"
