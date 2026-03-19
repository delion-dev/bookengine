from __future__ import annotations

from typing import Any

from .common import POSTPROCESS_RULE_CANDIDATES_PATH, now_iso, read_json, write_json


def _default_registry() -> dict[str, Any]:
    return {
        "version": "1.0",
        "generated_at": now_iso(),
        "candidates": [],
    }


def load_postprocess_candidates() -> dict[str, Any]:
    payload = read_json(POSTPROCESS_RULE_CANDIDATES_PATH, default=None)
    if not isinstance(payload, dict):
        payload = _default_registry()
    if "candidates" not in payload or not isinstance(payload["candidates"], list):
        payload["candidates"] = []
    return payload


def upsert_postprocess_candidates(candidates: list[dict[str, Any]]) -> dict[str, Any]:
    registry = load_postprocess_candidates()
    existing_by_id = {
        item.get("rule_id"): item
        for item in registry.get("candidates", [])
        if isinstance(item, dict) and item.get("rule_id")
    }

    for candidate in candidates:
        rule_id = candidate.get("rule_id")
        if not rule_id:
            continue
        existing = existing_by_id.get(rule_id)
        if existing is None:
            entry = {
                "rule_id": rule_id,
                "status": candidate.get("status", "candidate"),
                "scope": candidate.get("scope", "global"),
                "source_stage": candidate.get("source_stage", ""),
                "title": candidate.get("title", ""),
                "description": candidate.get("description", ""),
                "detection_hint": candidate.get("detection_hint", ""),
                "proposed_fix": candidate.get("proposed_fix", ""),
                "promotion_policy": candidate.get(
                    "promotion_policy",
                    "Promote only after multi-chapter validation and no regression.",
                ),
                "chapters_observed": list(dict.fromkeys(candidate.get("chapters_observed", []))),
                "first_seen_at": candidate.get("first_seen_at", now_iso()),
                "last_seen_at": now_iso(),
            }
            registry["candidates"].append(entry)
            existing_by_id[rule_id] = entry
            continue

        for field in [
            "status",
            "scope",
            "source_stage",
            "title",
            "description",
            "detection_hint",
            "proposed_fix",
            "promotion_policy",
        ]:
            if candidate.get(field):
                existing[field] = candidate[field]

        observed = existing.get("chapters_observed", [])
        observed.extend(candidate.get("chapters_observed", []))
        existing["chapters_observed"] = list(dict.fromkeys(item for item in observed if item))
        existing["last_seen_at"] = now_iso()

    registry["generated_at"] = now_iso()
    write_json(POSTPROCESS_RULE_CANDIDATES_PATH, registry)
    return registry
