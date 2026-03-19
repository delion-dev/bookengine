from __future__ import annotations

from typing import Any

from .common import PLATFORM_CORE_ROOT, read_json
from .model_gateway import load_model_gateway_config, route_provider


MODEL_ROUTING_POLICY_PATH = PLATFORM_CORE_ROOT / "model_routing_policy.json"


def load_model_routing_policy() -> dict[str, Any]:
    payload = read_json(MODEL_ROUTING_POLICY_PATH, default=None)
    if payload is None:
        raise FileNotFoundError(f"Missing model routing policy: {MODEL_ROUTING_POLICY_PATH}")
    return payload


def _profile_model_override(task_type: str, model_profile: str, config: Any) -> str | None:
    normalized_task = task_type.strip().lower()
    profile = model_profile.strip().lower()
    if profile == "fast" and normalized_task in {"generate_text", "generate_structured", "structured"}:
        return config.fast_model
    return None


def resolve_stage_route(
    stage_id: str,
    task_type: str,
    *,
    chapter_part: str | None = None,
    section_key: str | None = None,
    grounding_required: bool = False,
) -> dict[str, Any]:
    policy = load_model_routing_policy()
    config = load_model_gateway_config()
    stage_policy = policy.get("stage_policies", {}).get(stage_id, {})
    task_policy = stage_policy.get("task_policies", {}).get(task_type, {})
    resolved_policy = dict(policy.get("task_defaults", {}).get(task_type, {}))
    resolved_policy.update(task_policy.get("default", {}))

    if section_key:
        resolved_policy.update(task_policy.get("section_overrides", {}).get(section_key.lower(), {}))

    if chapter_part:
        normalized_part = chapter_part.upper()
        for part_key, override in task_policy.get("part_overrides", {}).items():
            if part_key.upper() in normalized_part:
                resolved_policy.update(override)

    model_profile = resolved_policy.get("model_profile", "balanced")
    cost_profile = resolved_policy.get("cost_profile", "balanced")
    model_override = _profile_model_override(task_type, model_profile, config)
    provider_route = route_provider(
        task_type,
        cost_profile=cost_profile,
        grounding_required=grounding_required,
        model_override=model_override,
        stage_id=stage_id,
        policy_id=f"{stage_id}:{task_type}",
    )
    provider_route["routing_policy"] = {
        "stage_id": stage_id,
        "task_type": task_type,
        "model_profile": model_profile,
        "cost_profile": cost_profile,
        "recommended_max_output_tokens": resolved_policy.get("recommended_max_output_tokens"),
        "note": resolved_policy.get("note", ""),
    }
    return provider_route
