from __future__ import annotations

from typing import Any

from .anchors import load_anchor_catalog
from .common import now_iso


def build_reference_index(
    book_id: str,
    research_plan: dict[str, Any],
    anchor_policy: dict[str, Any],
) -> dict[str, Any]:
    catalog = {
        item["anchor_type"]: item
        for item in load_anchor_catalog().get("anchor_types", [])
    }
    chapter_policy_map = {
        chapter["chapter_id"]: chapter
        for chapter in anchor_policy.get("chapters", [])
    }
    chapters: list[dict[str, Any]] = []

    for chapter in research_plan.get("chapters", []):
        chapter_id = chapter["chapter_id"]
        reference_entries = []

        reference_slots = chapter.get("reference_slots", [])
        if reference_slots:
            for slot in reference_slots:
                reference_entries.append(
                    {
                        "reference_id": slot["reference_id"],
                        "chapter_id": chapter_id,
                        "reference_domain": "body_text",
                        "source_type": slot["source_type"],
                        "source_kind": "external_reference",
                        "status": "planned",
                        "appendix_required": True,
                        "required_fields": ["title", "source_name", "url_or_identifier", "access_date", "usage_note"],
                        "claim_role": slot.get("claim_role", ""),
                        "verification_goal": slot.get("verification_goal", ""),
                        "preferred_source_profile": slot.get("preferred_source_profile", []),
                        "query_hint": slot.get("query_hint", ""),
                        "section_alignment": slot.get("section_alignment", []),
                        "freshness_window_days": slot.get("freshness_window_days"),
                        "verification_mode": slot.get("verification_mode", "grounded_required"),
                        "usage_constraint": slot.get("usage_constraint", ""),
                    }
                )
        else:
            for index, source_type in enumerate(chapter.get("source_types", []), start=1):
                reference_entries.append(
                    {
                        "reference_id": f"REF_{chapter_id.upper()}_{index:03d}",
                        "chapter_id": chapter_id,
                        "reference_domain": "body_text",
                        "source_type": source_type,
                        "source_kind": "external_reference",
                        "status": "planned",
                        "appendix_required": True,
                        "required_fields": ["title", "source_name", "url_or_identifier", "access_date", "usage_note"],
                    }
                )

        for index, anchor_type in enumerate(chapter_policy_map.get(chapter_id, {}).get("preferred_anchor_types", []), start=1):
            asset_mode = catalog[anchor_type]["default_asset_mode"]
            if asset_mode == "ai_generated_image":
                source_kind = "ai_generated_image"
            elif asset_mode == "external_image":
                source_kind = "external_reference"
            else:
                source_kind = "structured_visual"
            reference_entries.append(
                {
                    "reference_id": f"REF_{chapter_id.upper()}_VIS_{index:03d}",
                    "chapter_id": chapter_id,
                    "reference_domain": "visual_anchor",
                    "source_type": anchor_type,
                    "source_kind": source_kind,
                    "status": "planned",
                    "appendix_required": True,
                    "required_fields": ["creator_or_model", "url_or_prompt_record", "rights_note", "usage_note"],
                    "acquisition_mode": "offline" if source_kind in {"external_reference", "ai_generated_image"} else "in_pipeline",
                    "asset_file_stub": f"ASSET_{chapter_id.upper()}_{anchor_type}_{index:03d}",
                    "collection_stage_id": "S6A",
                }
            )

        chapters.append(
            {
                "chapter_id": chapter_id,
                "title": chapter["title"],
                "entries": reference_entries,
            }
        )

    return {
        "version": "1.0",
        "generated_at": now_iso(),
        "book_id": book_id,
        "chapters": chapters,
        "policy": {
            "all_external_materials_must_appear_in_appendix": True,
            "all_ai_generated_images_must_record_model_prompt_and_revision": True,
        },
    }


def build_image_manifest(
    book_id: str,
    anchor_policy: dict[str, Any],
) -> dict[str, Any]:
    catalog = {
        item["anchor_type"]: item
        for item in load_anchor_catalog().get("anchor_types", [])
    }
    items: list[dict[str, Any]] = []

    for chapter in anchor_policy.get("chapters", []):
        for index, anchor_type in enumerate(chapter.get("preferred_anchor_types", []), start=1):
            asset_mode = catalog[anchor_type]["default_asset_mode"]
            if asset_mode == "external_image":
                source_mode = "external_image"
                fallback_mode = "ai_generated_image"
            elif asset_mode == "ai_generated_image":
                source_mode = "ai_generated_image"
                fallback_mode = "manual_design"
            else:
                source_mode = asset_mode
                fallback_mode = "manual_design"
            items.append(
                {
                    "image_id": f"IMG_{chapter['chapter_id'].upper()}_{index:03d}",
                    "chapter_id": chapter["chapter_id"],
                    "planned_anchor_type": anchor_type,
                    "source_mode": source_mode,
                    "fallback_mode": fallback_mode,
                    "rights_status": "needs_review",
                    "appendix_reference_id": f"REF_{chapter['chapter_id'].upper()}_VIS_{index:03d}",
                    "status": "planned",
                    "acquisition_mode": "offline" if source_mode in {"external_image", "ai_generated_image", "video_embed"} else "in_pipeline",
                    "offline_acquisition_required": source_mode in {"external_image", "ai_generated_image", "video_embed"},
                    "target_filename_stub": f"ASSET_{chapter['chapter_id'].upper()}_{anchor_type}_{index:03d}",
                    "target_filename_pattern": f"ASSET_{chapter['chapter_id'].upper()}_{anchor_type}_{index:03d}_v001.ext",
                    "planned_storage_dir": f"publication/assets/cleared/{chapter['chapter_id']}",
                    "collection_stage_id": "S6A",
                }
            )

    return {
        "version": "1.0",
        "generated_at": now_iso(),
        "book_id": book_id,
        "items": items,
    }


def build_reference_appendix(
    book_id: str,
    reference_index: dict[str, Any],
    image_manifest: dict[str, Any],
    citations_payload: dict[str, Any] | None = None,
) -> str:
    lines = [
        "# REFERENCE_INDEX",
        "",
        f"- Book ID: `{book_id}`",
        "- Rule: 모든 외부 텍스트 출처와 모든 이미지/AI 시각 자료는 이 부록 인덱스에 등록되어야 한다.",
        "- Rule: AI 생성 이미지는 모델명, 프롬프트 요약, 리비전 정보를 반드시 기록한다.",
        "- Rule: 오프라인 자산 수집 파일명은 `ASSET_{CHAPTER}_{ANCHORTYPE}_{SEQ}_v001.ext` 규칙을 따른다.",
        "- Rule: `Appendix Ref`와 `Support Gap`은 운영/검수 정보이며 독자 노출 본문이 아니라 인덱스와 sidecar에서 관리한다.",
        "",
        "## Text References",
        "| Ref ID | Chapter | Source Type | Claim Role | Source Name | Title | URL / Identifier | Access Date | Trust | Rights Risk | Clearance | Status |",
        "| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |",
    ]

    for chapter in reference_index.get("chapters", []):
        for entry in chapter.get("entries", []):
            if entry["reference_domain"] != "body_text":
                continue
            lines.append(
                "| "
                + " | ".join(
                    [
                        entry["reference_id"],
                        entry["chapter_id"],
                        entry["source_type"],
                        entry.get("claim_role", ""),
                        entry.get("source_name", ""),
                        entry.get("title", ""),
                        entry.get("url_or_identifier", ""),
                        entry.get("access_date", ""),
                        entry.get("trust_level", ""),
                        entry.get("rights_risk_level", ""),
                        entry.get("clearance_status", ""),
                        entry["status"],
                    ]
                )
                + " |"
            )

    lines.extend(
        [
            "",
            "## Visual / Image References",
            "| Ref ID | Image ID | Chapter | Anchor Type | Source Mode | Rights Status | Clearance Action | Status | Provenance |",
            "| --- | --- | --- | --- | --- | --- | --- | --- | --- |",
        ]
    )

    image_lookup = {
        item["appendix_reference_id"]: item
        for item in image_manifest.get("items", [])
    }
    for chapter in reference_index.get("chapters", []):
        for entry in chapter.get("entries", []):
            if entry["reference_domain"] != "visual_anchor":
                continue
            image = image_lookup.get(entry["reference_id"], {})
            lines.append(
                f"| {entry['reference_id']} | {image.get('image_id', '')} | {entry['chapter_id']} | {entry['source_type']} | {image.get('source_mode', entry['source_kind'])} | {image.get('rights_status', entry.get('clearance_status', ''))} | {image.get('clearance_action', entry.get('required_action', ''))} | {entry['status']} | {entry.get('provenance_status', '')} |"
            )

    lines.extend(
        [
            "",
            "## Supplemental / Low-Trust Signals",
            "| Chapter | Source Name | Title | URL / Identifier | Trust | Reason |",
            "| --- | --- | --- | --- | --- | --- |",
        ]
    )
    supplemental_rows = 0
    if isinstance(citations_payload, dict):
        for chapter in citations_payload.get("chapters", []):
            for source in chapter.get("supplemental_sources", []):
                supplemental_rows += 1
                lines.append(
                    "| "
                    + " | ".join(
                        [
                            chapter.get("chapter_id", ""),
                            source.get("source_name", ""),
                            source.get("title", ""),
                            source.get("url_or_identifier", ""),
                            source.get("trust_level", ""),
                            source.get("trust_reason", ""),
                        ]
                    )
                    + " |"
                )
    if supplemental_rows == 0:
        lines.append("|  |  |  |  |  |  |")

    lines.extend(
        [
            "",
            "## AI Provenance Checklist",
            "- `creator_or_model`: 사용한 모델명 또는 외부 제작자",
            "- `url_or_prompt_record`: 원본 URL 또는 프롬프트 기록 위치",
            "- `rights_note`: 사용 허가 또는 자체 생성 여부",
            "- `usage_note`: 본문/부록에서 어떻게 사용되는지",
        ]
    )
    return "\n".join(lines) + "\n"
