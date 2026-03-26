from __future__ import annotations

import copy
import json
import os
import re
import socket
import time
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any
from urllib import error, parse, request

from functools import lru_cache

from .common import PLATFORM_CORE_ROOT, REPO_ROOT, append_jsonl, ensure_dir, now_iso, read_json, write_json


ENV_PATH = REPO_ROOT / ".env"


@lru_cache(maxsize=1)
def _load_model_config() -> dict:
    """Load model defaults from model_config.json. Cached for process lifetime."""
    payload = read_json(PLATFORM_CORE_ROOT / "model_config.json", default={}) or {}
    return payload


def _model_defaults() -> dict:
    cfg = _load_model_config()
    gw = cfg.get("gateway_defaults", {})
    mdl = cfg.get("default_models", {})
    return {
        "text_model":              mdl.get("text_model", "gemini-2.5-pro"),
        "structured_model":        mdl.get("structured_model", "gemini-2.5-pro"),
        "research_model":          mdl.get("research_model", "gemini-2.5-pro"),
        "safety_model":            mdl.get("safety_model", "gemini-2.5-flash"),
        "fast_model":              mdl.get("fast_model", "gemini-2.5-flash"),
        "timeout_seconds":         int(gw.get("timeout_seconds", 90)),
        "request_min_interval_ms": int(gw.get("request_min_interval_ms", 2000)),
        "request_jitter_ms":       int(gw.get("request_jitter_ms", 0)),
        "max_retries":             int(gw.get("max_retries", 2)),
        "retry_backoff_seconds":   float(gw.get("retry_backoff_seconds", 6.0)),
        "api_version":             str(gw.get("api_version", "v1")),
        "gemini_api_version":      str(gw.get("gemini_api_version", "v1beta")),
    }


# Module-level constants resolved once at import (overridable via env)
_MD = _model_defaults()
_DEFAULT_API_VERSION: str         = _MD["api_version"]
_DEFAULT_GEMINI_API_VERSION: str  = _MD["gemini_api_version"]
_DEFAULT_TIMEOUT_SECONDS: int     = _MD["timeout_seconds"]


class ModelGatewayError(RuntimeError):
    """Base error for model gateway operations."""


class ModelGatewayConfigError(ModelGatewayError):
    """Raised when the runtime configuration is missing or invalid."""


class ModelGatewayRequestError(ModelGatewayError):
    """Raised when the Vertex REST API call fails."""

    def __init__(
        self,
        message: str,
        *,
        status_code: int | None = None,
        response_body: str | None = None,
        variant_label: str | None = None,
        hint: str | None = None,
    ) -> None:
        super().__init__(message)
        self.status_code = status_code
        self.response_body = response_body
        self.variant_label = variant_label
        self.hint = hint

    def to_dict(self) -> dict[str, Any]:
        hint = self.hint
        response_excerpt = (self.response_body or "")[:500]
        if hint is None and self.status_code == 401 and "API keys are not supported by this API" in (self.response_body or ""):
            hint = (
                "Current request is reaching a Vertex endpoint that requires OAuth2/ADC. "
                "If you want full Vertex REST with project/location, use VERTEX_AUTH_MODE=access_token and provide "
                "VERTEX_ACCESS_TOKEN. If you want API-key auth, use an express-mode key with express-mode endpoints only."
            )
        return {
            "message": str(self),
            "status_code": self.status_code,
            "variant_label": self.variant_label,
            "response_body_excerpt": response_excerpt,
            "hint": hint,
        }


@dataclass(frozen=True)
class ModelGatewayConfig:
    provider: str
    project_id: str
    location: str
    api_version: str
    auth_mode: str
    endpoint_mode: str
    api_key: str | None
    access_token: str | None
    enable_live_calls: bool
    timeout_seconds: int
    request_min_interval_ms: int
    request_jitter_ms: int
    max_retries: int
    retry_backoff_seconds: float
    text_model: str
    structured_model: str
    research_model: str
    safety_model: str
    fast_model: str


def _detect_source(env: dict[str, str], *keys: str) -> str | None:
    for key in keys:
        value = env.get(key)
        if value:
            return key
    return None


def _parse_env_file(path: Path) -> dict[str, str]:
    if not path.exists():
        return {}
    payload: dict[str, str] = {}
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        if line.startswith("export "):
            line = line[7:].strip()
        if "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip()
        if value and value[0] in {"'", '"'} and value[-1] == value[0]:
            value = value[1:-1]
        payload[key] = value
    return payload


def load_repo_env() -> dict[str, str]:
    file_env = _parse_env_file(ENV_PATH)
    merged = dict(file_env)
    merged.update({key: value for key, value in os.environ.items() if isinstance(value, str)})
    return merged


def _first(env: dict[str, str], *keys: str, default: str | None = None) -> str | None:
    for key in keys:
        value = env.get(key)
        if value:
            return value
    return default


def _as_bool(value: str | None, default: bool = False) -> bool:
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


def _as_int(value: str | None, default: int) -> int:
    try:
        return int(value) if value is not None else default
    except ValueError:
        return default


def _mask_secret(value: str | None) -> str | None:
    if not value:
        return None
    if len(value) <= 8:
        return "*" * len(value)
    return f"{value[:4]}...{value[-4:]}"


def _normalize_provider(raw_value: str | None, auth_mode: str) -> str:
    value = (raw_value or "").strip().lower()
    aliases = {
        "vertex": "vertex_ai",
        "vertex_ai": "vertex_ai",
        "vertexai": "vertex_ai",
        "gemini": "gemini_api",
        "gemini_api": "gemini_api",
        "google_ai": "gemini_api",
        "google_ai_studio": "gemini_api",
        "google_gemini_api": "gemini_api",
    }
    if not value:
        return "vertex_ai" if auth_mode == "access_token" else "vertex_ai"
    normalized = aliases.get(value)
    if normalized:
        return normalized
    raise ModelGatewayConfigError(
        "MODEL_GATEWAY_PROVIDER must be 'vertex_ai' or 'gemini_api'."
    )


def load_model_gateway_config() -> ModelGatewayConfig:
    env = load_repo_env()
    auth_mode = (_first(env, "VERTEX_AUTH_MODE", default="api_key") or "api_key").strip().lower()
    if auth_mode not in {"api_key", "access_token"}:
        raise ModelGatewayConfigError("VERTEX_AUTH_MODE must be 'api_key' or 'access_token'.")

    provider = _normalize_provider(
        _first(env, "MODEL_GATEWAY_PROVIDER", "GOOGLE_MODEL_PROVIDER", "GOOGLE_LLM_PROVIDER"),
        auth_mode,
    )
    if provider == "gemini_api" and auth_mode != "api_key":
        raise ModelGatewayConfigError(
            "gemini_api provider currently supports API-key auth only. Use VERTEX_AUTH_MODE=api_key or switch provider to vertex_ai."
        )

    endpoint_mode = _first(env, "VERTEX_ENDPOINT_MODE")
    if provider == "gemini_api":
        endpoint_mode = "direct"
        api_version = (_first(env, "GEMINI_API_VERSION", "VERTEX_API_VERSION", default=_DEFAULT_GEMINI_API_VERSION) or _DEFAULT_GEMINI_API_VERSION).strip()
        api_key = _first(env, "GEMINI_API_KEY", "GOOGLE_API_KEY", "VERTEX_API_KEY")
    else:
        if endpoint_mode is None:
            endpoint_mode = "express" if auth_mode == "api_key" else "standard"
        endpoint_mode = endpoint_mode.strip().lower()

        if auth_mode == "api_key" and endpoint_mode != "express":
            raise ModelGatewayConfigError(
                "API key mode is standardized on the official express endpoint. "
                "Set VERTEX_ENDPOINT_MODE=express or switch to access_token auth."
            )
        if auth_mode == "access_token" and endpoint_mode != "standard":
            raise ModelGatewayConfigError(
                "Access token mode is standardized on the official standard endpoint. "
                "Set VERTEX_ENDPOINT_MODE=standard or switch to api_key auth."
            )
        api_version = (_first(env, "VERTEX_API_VERSION", default=_DEFAULT_API_VERSION) or _DEFAULT_API_VERSION).strip()
        api_key = _first(env, "VERTEX_API_KEY", "GOOGLE_API_KEY", "GEMINI_API_KEY")

    return ModelGatewayConfig(
        provider=provider,
        project_id=_first(env, "VERTEX_PROJECT_ID", "GOOGLE_CLOUD_PROJECT", default="").strip(),
        location=_first(env, "VERTEX_REGION", "GOOGLE_CLOUD_LOCATION", "GOOGLE_CLOUD_REGION", default="global").strip(),
        api_version=api_version,
        auth_mode=auth_mode,
        endpoint_mode=endpoint_mode,
        api_key=api_key,
        access_token=_first(env, "VERTEX_ACCESS_TOKEN", "GOOGLE_OAUTH_ACCESS_TOKEN"),
        enable_live_calls=_as_bool(_first(env, "VERTEX_ENABLE_LIVE_CALLS"), default=False),
        timeout_seconds=_as_int(_first(env, "VERTEX_TIMEOUT_SECONDS"), _MD["timeout_seconds"]),
        request_min_interval_ms=_as_int(_first(env, "VERTEX_REQUEST_MIN_INTERVAL_MS"), _MD["request_min_interval_ms"]),
        request_jitter_ms=_as_int(_first(env, "VERTEX_REQUEST_JITTER_MS"), _MD["request_jitter_ms"]),
        max_retries=_as_int(_first(env, "VERTEX_MAX_RETRIES"), _MD["max_retries"]),
        retry_backoff_seconds=float(_first(env, "VERTEX_RETRY_BACKOFF_SECONDS", default=str(_MD["retry_backoff_seconds"])) or _MD["retry_backoff_seconds"]),
        text_model=(_first(env, "VERTEX_MODEL_TEXT", "GEMINI_CONTENT_MODEL", default=_MD["text_model"]) or _MD["text_model"]).strip(),
        structured_model=(_first(env, "VERTEX_MODEL_STRUCTURED", "GEMINI_CONTENT_MODEL", default=_MD["structured_model"]) or _MD["structured_model"]).strip(),
        research_model=(_first(env, "VERTEX_MODEL_RESEARCH", "GEMINI_CONTENT_MODEL", default=_MD["research_model"]) or _MD["research_model"]).strip(),
        safety_model=(_first(env, "VERTEX_MODEL_SAFETY", "GEMINI_CONTENT_MODEL", default=_MD["safety_model"]) or _MD["safety_model"]).strip(),
        fast_model=(_first(env, "VERTEX_MODEL_FAST", "VERTEX_MODEL_FLASH", "VERTEX_MODEL_SAFETY", default=_MD["fast_model"]) or _MD["fast_model"]).strip(),
    )


def describe_model_gateway() -> dict[str, Any]:
    config = load_model_gateway_config()
    env = load_repo_env()
    if config.provider == "gemini_api":
        api_key_source = _detect_source(env, "GEMINI_API_KEY", "GOOGLE_API_KEY", "VERTEX_API_KEY")
        api_version_source = _detect_source(env, "GEMINI_API_VERSION", "VERTEX_API_VERSION")
    else:
        api_key_source = _detect_source(env, "VERTEX_API_KEY", "GOOGLE_API_KEY", "GEMINI_API_KEY")
        api_version_source = _detect_source(env, "VERTEX_API_VERSION")
    project_source = _detect_source(env, "VERTEX_PROJECT_ID", "GOOGLE_CLOUD_PROJECT")
    region_source = _detect_source(env, "VERTEX_REGION", "GOOGLE_CLOUD_LOCATION", "GOOGLE_CLOUD_REGION")
    model_source = _detect_source(env, "VERTEX_MODEL_TEXT", "GEMINI_CONTENT_MODEL")
    provider_source = _detect_source(env, "MODEL_GATEWAY_PROVIDER", "GOOGLE_MODEL_PROVIDER", "GOOGLE_LLM_PROVIDER")
    required_fields: dict[str, bool] = {}
    if config.provider == "vertex_ai" and config.endpoint_mode == "standard":
        required_fields["project_id"] = bool(config.project_id)
        required_fields["location"] = bool(config.location)
    if config.auth_mode == "access_token":
        required_fields["access_token"] = bool(config.access_token)
    else:
        required_fields["api_key"] = bool(config.api_key)
    notes: list[str] = []
    if config.provider == "vertex_ai" and config.auth_mode == "api_key" and config.endpoint_mode == "express":
        notes.append(
            "API key mode is using Vertex express-mode endpoints. In this mode, project_id/location metadata is not used in the request URL."
        )
    if config.provider == "gemini_api":
        notes.append(
            "Gemini API direct mode is using generativelanguage.googleapis.com with API-key auth. This bypasses Vertex express routing and can help if endpoint-security rules are host-specific."
        )
    if config.provider == "vertex_ai" and config.auth_mode == "api_key" and config.project_id and config.location:
        notes.append(
            "Full Vertex REST endpoints that include project/location require OAuth2 or ADC after you upgrade from express mode."
        )
    if env.get("GOOGLE_API_KEY") and not env.get("VERTEX_API_KEY"):
        notes.append(
            "The runtime is currently reading GOOGLE_API_KEY as a fallback. Set VERTEX_API_KEY explicitly if you intend to stay in express mode."
        )
    if config.text_model == "gemini-3.1-pro-preview":
        notes.append(
            "The current public Vertex AI model pages prominently document Gemini 3 Pro as gemini-3-pro-preview. Because this runtime is configured with gemini-3.1-pro-preview, keep model ID validation on the checklist whenever environment and auth checks are clean."
        )
    return {
        "provider": config.provider,
        "env_path": str(ENV_PATH),
        "config_loaded": ENV_PATH.exists(),
        "live_calls_enabled": config.enable_live_calls,
        "ready_for_live_calls": all(required_fields.values()) and config.enable_live_calls,
        "required_fields": required_fields,
        "notes": notes,
        "source_resolution": {
            "provider": provider_source,
            "api_key": api_key_source,
            "api_version": api_version_source,
            "project_id": project_source,
            "location": region_source,
            "text_model": model_source,
        },
        "config": {
            **asdict(config),
            "api_key": _mask_secret(config.api_key),
            "access_token": _mask_secret(config.access_token),
        },
    }


def classify_auth_failure(error_payload: dict[str, Any]) -> dict[str, Any]:
    status_code = error_payload.get("status_code")
    body = error_payload.get("response_body_excerpt", "")
    message = str(error_payload.get("message", ""))
    category = "unknown"
    recommended_next_step = "Check the live diagnostic payload and the current auth mode."

    if "winerror 10013" in message.lower():
        category = "local_socket_access_blocked"
        recommended_next_step = (
            "Allow outbound access to aiplatform.googleapis.com:443 for the current Python/PowerShell runtime, "
            "then rerun a single Vertex auth probe."
        )
    elif status_code == 401 and "API keys are not supported by this API" in body:
        category = "api_key_not_accepted_for_current_vertex_endpoint"
        recommended_next_step = (
            "Use a Vertex express-mode API key in VERTEX_API_KEY, or switch to access_token mode for full Vertex REST."
        )
    elif status_code == 403:
        category = "api_key_restricted_or_service_not_enabled"
        recommended_next_step = (
            "Check API restrictions for the key and confirm Vertex AI API is enabled for the target project."
        )
    elif status_code == 404:
        category = "model_or_endpoint_not_found"
        recommended_next_step = (
            "Verify the model ID against the current express-mode model list and confirm the endpoint path."
        )
    elif status_code == 429:
        category = "quota_or_rate_limit_exhausted"
        recommended_next_step = (
            "Do not keep retrying immediately. Wait for the retry window or switch to a different provider/model tier before resuming batch stages."
        )

    return {
        "category": category,
        "recommended_next_step": recommended_next_step,
    }


def _model_for_task(config: ModelGatewayConfig, task_type: str) -> str:
    normalized = task_type.strip().lower()
    if normalized in {"text", "generate_text"}:
        return config.text_model
    if normalized in {"structured", "generate_structured"}:
        return config.structured_model
    if normalized in {"grounded_research", "research"}:
        return config.research_model
    if normalized in {"safety", "safety_check"}:
        return config.safety_model
    raise ModelGatewayConfigError(f"Unsupported task type: {task_type}")


def route_provider(
    task_type: str,
    cost_profile: str = "balanced",
    grounding_required: bool = False,
    model_override: str | None = None,
    stage_id: str | None = None,
    policy_id: str | None = None,
) -> dict[str, Any]:
    config = load_model_gateway_config()
    model = (model_override or _model_for_task(config, task_type)).strip()
    if config.provider == "gemini_api":
        resource_name = f"models/{model}"
    elif config.endpoint_mode == "standard":
        resource_name = (
            f"projects/{config.project_id}/locations/{config.location}/publishers/google/models/{model}"
        )
    else:
        resource_name = f"publishers/google/models/{model}"
    return {
        "provider": config.provider,
        "task_type": task_type,
        "cost_profile": cost_profile,
        "grounding_required": grounding_required,
        "model": model,
        "api_version": config.api_version,
        "auth_mode": config.auth_mode,
        "endpoint_mode": config.endpoint_mode,
        "project_id": config.project_id,
        "location": config.location,
        "resource_name": resource_name,
        "timeout_seconds": config.timeout_seconds,
        "live_call_enabled": config.enable_live_calls,
        "stage_id": stage_id,
        "policy_id": policy_id,
    }


def _assert_live_ready(config: ModelGatewayConfig, route: dict[str, Any]) -> None:
    missing = []
    if route["provider"] == "vertex_ai" and route["endpoint_mode"] == "standard":
        if not config.project_id:
            missing.append("VERTEX_PROJECT_ID")
        if not config.location:
            missing.append("VERTEX_REGION")
    if config.auth_mode == "api_key" and not config.api_key:
        missing.append("VERTEX_API_KEY")
    if config.auth_mode == "access_token" and not config.access_token:
        missing.append("VERTEX_ACCESS_TOKEN")
    if missing:
        raise ModelGatewayConfigError(f"Missing required Vertex runtime values: {', '.join(missing)}")
    if not config.enable_live_calls:
        raise ModelGatewayConfigError(
            "Live model calls are disabled. Set VERTEX_ENABLE_LIVE_CALLS=true in .env to enable REST requests."
        )
    if route["provider"] == "vertex_ai" and route["endpoint_mode"] == "standard" and not config.project_id:
        raise ModelGatewayConfigError("Standard endpoint mode requires VERTEX_PROJECT_ID.")


def _build_url(config: ModelGatewayConfig, route: dict[str, Any], method_name: str) -> str:
    if route["provider"] == "gemini_api":
        return f"https://generativelanguage.googleapis.com/{config.api_version}/{route['resource_name']}:{method_name}"
    base = f"https://aiplatform.googleapis.com/{config.api_version}/{route['resource_name']}:{method_name}"
    if config.auth_mode == "api_key":
        return f"{base}?{parse.urlencode({'key': config.api_key or ''})}"
    return base


def _runtime_dir() -> Path:
    return ensure_dir(REPO_ROOT / "platform" / "core_engine" / "runtime")


def _rate_limit_state_path() -> Path:
    return _runtime_dir() / "model_rate_limit_state.json"


def _call_log_path() -> Path:
    return _runtime_dir() / "model_call_log.jsonl"


def _apply_call_spacing(config: ModelGatewayConfig, route: dict[str, Any], variant_label: str) -> dict[str, Any]:
    min_interval_seconds = max(0.0, config.request_min_interval_ms / 1000)
    state_path = _rate_limit_state_path()
    state = read_json(state_path, default={}) or {}
    previous_started_at = float(state.get("last_request_started_at_epoch", 0.0) or 0.0)
    now_epoch = time.time()
    elapsed = now_epoch - previous_started_at
    wait_seconds = max(0.0, round(min_interval_seconds - elapsed, 3))
    if wait_seconds > 0:
        time.sleep(wait_seconds)
    started_at = time.time()
    write_json(
        state_path,
        {
            "last_request_started_at_epoch": started_at,
            "last_request_started_at_iso": now_iso(),
            "task_type": route["task_type"],
            "variant_label": variant_label,
            "min_interval_ms": config.request_min_interval_ms,
        },
    )
    return {
        "wait_seconds": wait_seconds,
        "min_interval_ms": config.request_min_interval_ms,
        "started_at_epoch": started_at,
    }


def _log_model_call(event: dict[str, Any]) -> None:
    append_jsonl(_call_log_path(), event)


def _headers(config: ModelGatewayConfig) -> dict[str, str]:
    headers = {
        "Content-Type": "application/json; charset=utf-8",
    }
    if config.provider == "gemini_api" and config.api_key:
        headers["x-goog-api-key"] = config.api_key
    if config.auth_mode == "access_token" and config.access_token:
        headers["Authorization"] = f"Bearer {config.access_token}"
    return headers


def _provider_label(route: dict[str, Any]) -> str:
    return "Gemini API" if route.get("provider") == "gemini_api" else "Vertex"


def _policy_text(system_policy_ref: Any) -> str:
    if system_policy_ref is None:
        return ""
    if isinstance(system_policy_ref, str):
        return system_policy_ref.strip()
    if isinstance(system_policy_ref, list):
        return "\n\n".join(_policy_text(item) for item in system_policy_ref if item)
    if isinstance(system_policy_ref, dict):
        return json.dumps(system_policy_ref, ensure_ascii=False, indent=2)
    return str(system_policy_ref)


def _context_text(context_artifacts: list[Any] | None) -> str:
    if not context_artifacts:
        return ""
    blocks: list[str] = []
    for item in context_artifacts:
        if isinstance(item, str):
            blocks.append(item.strip())
            continue
        if isinstance(item, dict):
            label = item.get("label", "context")
            text = item.get("text")
            if text:
                blocks.append(f"[{label}]\n{text.strip()}")
    return "\n\n".join(block for block in blocks if block)


def _default_generation_config(task_type: str) -> dict[str, Any]:
    normalized = task_type.strip().lower()
    if normalized in {"structured", "generate_structured"}:
        return {"temperature": 0.2, "topP": 0.9, "maxOutputTokens": 8192}
    if normalized in {"grounded_research", "research"}:
        return {"temperature": 0.1, "topP": 0.8, "maxOutputTokens": 8192}
    if normalized in {"safety", "safety_check"}:
        return {"temperature": 0.0, "topP": 0.8, "maxOutputTokens": 2048}
    return {"temperature": 0.5, "topP": 0.9, "maxOutputTokens": 8192}


def _build_request_body(
    route: dict[str, Any],
    *,
    prompt: str,
    system_policy_ref: Any = None,
    context_artifacts: list[Any] | None = None,
    generation_config: dict[str, Any] | None = None,
    response_schema: dict[str, Any] | None = None,
    schema_variant: str = "responseJsonSchema",
    grounding_variant: str | None = None,
) -> dict[str, Any]:
    body: dict[str, Any] = {
        "contents": [
            {
                "role": "user",
                "parts": [{"text": prompt.strip()}],
            }
        ],
        "generationConfig": {
            **_default_generation_config(route["task_type"]),
            **(generation_config or {}),
        },
    }
    context_text = _context_text(context_artifacts)
    if context_text:
        body["contents"][0]["parts"].insert(0, {"text": context_text})
    policy_text = _policy_text(system_policy_ref)
    if policy_text:
        body["systemInstruction"] = {
            "role": "system",
            "parts": [{"text": policy_text}],
        }
    if response_schema is not None:
        body["generationConfig"]["responseMimeType"] = "application/json"
        body["generationConfig"][schema_variant] = response_schema
    if grounding_variant:
        body["tools"] = [{grounding_variant: {}}]
    return body


def _extract_text(response_payload: dict[str, Any]) -> str:
    texts: list[str] = []
    for candidate in response_payload.get("candidates", []):
        content = candidate.get("content", {})
        for part in content.get("parts", []):
            text = part.get("text")
            if text:
                texts.append(text)
    return "\n".join(texts).strip()


def _extract_json_text(text: str) -> Any:
    stripped = text.strip()
    if stripped.startswith("```"):
        stripped = stripped.strip("`")
        if "\n" in stripped:
            stripped = stripped.split("\n", 1)[1]
        if stripped.endswith("```"):
            stripped = stripped[:-3]
        stripped = stripped.strip()
    return json.loads(stripped)


def _extract_grounding_sources(response_payload: dict[str, Any]) -> list[dict[str, Any]]:
    sources: list[dict[str, Any]] = []
    for candidate in response_payload.get("candidates", []):
        metadata = candidate.get("groundingMetadata", {})
        for chunk in metadata.get("groundingChunks", []):
            web = chunk.get("web", {})
            uri = web.get("uri") or web.get("url")
            if not uri:
                continue
            hostname = parse.urlparse(uri).netloc
            sources.append(
                {
                    "title": web.get("title") or hostname or uri,
                    "source_name": hostname or web.get("title") or uri,
                    "url_or_identifier": uri,
                    "access_date": now_iso()[:10],
                    "usage_note": "grounded_research",
                }
            )
    deduped: list[dict[str, Any]] = []
    seen = set()
    for source in sources:
        key = source["url_or_identifier"]
        if key in seen:
            continue
        seen.add(key)
        deduped.append(source)
    return deduped


def _usage_metadata(response_payload: dict[str, Any]) -> dict[str, Any]:
    usage = response_payload.get("usageMetadata", {})
    return {
        "prompt_token_count": usage.get("promptTokenCount"),
        "candidates_token_count": usage.get("candidatesTokenCount"),
        "total_token_count": usage.get("totalTokenCount"),
    }


def _network_reason_text(reason: Any) -> str:
    return str(reason or "").strip()


def _network_failure_hint(reason: Any) -> str | None:
    text = _network_reason_text(reason).lower()
    if "winerror 10013" in text:
        return (
            "Socket access was denied by the local execution environment. This usually points to sandboxing, "
            "firewall, proxy, or endpoint-security policy rather than a Vertex request-format or auth bug."
        )
    return None


def _is_retryable_network_reason(reason: Any) -> bool:
    text = _network_reason_text(reason).lower()
    retryable_markers = (
        "winerror 10048",
        "temporarily unavailable",
        "temporary failure",
        "timed out",
        "timeout",
        "connection reset",
        "connection aborted",
        "connection refused",
        "resource temporarily unavailable",
        "network is unreachable",
        "name or service not known",
    )
    return any(marker in text for marker in retryable_markers)


def _quota_retry_wait_seconds(response_body: str | None) -> float | None:
    text = response_body or ""
    match = re.search(r"Please retry in ([0-9.]+)s", text)
    if match:
        try:
            return float(match.group(1))
        except ValueError:
            return None
    return None


def _is_long_quota_exhaustion(response_body: str | None) -> bool:
    text = (response_body or "").lower()
    wait_seconds = _quota_retry_wait_seconds(response_body)
    return (
        "quota exceeded" in text
        or "resource_exhausted" in text
        or (wait_seconds is not None and wait_seconds >= 300)
    )


def _post_generate_content(
    route: dict[str, Any],
    *,
    body: dict[str, Any],
    variant_label: str,
    telemetry_context: dict[str, Any] | None = None,
) -> dict[str, Any]:
    config = load_model_gateway_config()
    _assert_live_ready(config, route)
    url = _build_url(config, route, "generateContent")
    payload = json.dumps(body, ensure_ascii=False).encode("utf-8")
    last_exception: ModelGatewayRequestError | None = None
    for attempt in range(config.max_retries + 1):
        pacing = _apply_call_spacing(config, route, variant_label)
        req = request.Request(
            url,
            data=payload,
            headers=_headers(config),
            method="POST",
        )
        try:
            with request.urlopen(req, timeout=route["timeout_seconds"]) as response:
                response_body = response.read().decode("utf-8")
                parsed = json.loads(response_body)
                _log_model_call(
                    {
                        "timestamp": now_iso(),
                        "status": "ok",
                        "provider": route["provider"],
                        "task_type": route["task_type"],
                        "model": route["model"],
                        "request_variant": variant_label,
                        "endpoint_mode": route["endpoint_mode"],
                        "auth_mode": route["auth_mode"],
                        "attempt": attempt + 1,
                        "wait_seconds": pacing["wait_seconds"],
                        "min_interval_ms": pacing["min_interval_ms"],
                        "url": url.split("?")[0],
                        "usage": _usage_metadata(parsed),
                        **(telemetry_context or {}),
                    }
                )
                return parsed
        except error.HTTPError as exc:
            response_body = exc.read().decode("utf-8", errors="replace")
            retryable = exc.code == 429 and not _is_long_quota_exhaustion(response_body)
            _log_model_call(
                {
                    "timestamp": now_iso(),
                    "status": "http_error",
                    "provider": route["provider"],
                    "task_type": route["task_type"],
                    "model": route["model"],
                    "request_variant": variant_label,
                    "endpoint_mode": route["endpoint_mode"],
                    "auth_mode": route["auth_mode"],
                    "attempt": attempt + 1,
                    "wait_seconds": pacing["wait_seconds"],
                    "min_interval_ms": pacing["min_interval_ms"],
                    "status_code": exc.code,
                    "response_excerpt": response_body[:500],
                    "url": url.split("?")[0],
                    "retryable": retryable,
                    **(telemetry_context or {}),
                }
            )
            last_exception = ModelGatewayRequestError(
                f"{_provider_label(route)} generateContent failed with HTTP {exc.code}.",
                status_code=exc.code,
                response_body=response_body,
                variant_label=variant_label,
                hint=(
                    "Current provider/model quota is exhausted for a sustained window. "
                    "Do not keep retrying this stage. Switch provider/model or wait until the retry window closes."
                    if exc.code == 429 and _is_long_quota_exhaustion(response_body)
                    else None
                ),
            )
            if retryable and attempt < config.max_retries:
                time.sleep(config.retry_backoff_seconds * (2 ** attempt))
                continue
            raise last_exception from exc
        except error.URLError as exc:
            reason_text = _network_reason_text(exc.reason)
            retryable = _is_retryable_network_reason(exc.reason)
            _log_model_call(
                {
                    "timestamp": now_iso(),
                    "status": "network_error",
                    "provider": route["provider"],
                    "task_type": route["task_type"],
                    "model": route["model"],
                    "request_variant": variant_label,
                    "endpoint_mode": route["endpoint_mode"],
                    "auth_mode": route["auth_mode"],
                    "attempt": attempt + 1,
                    "wait_seconds": pacing["wait_seconds"],
                    "min_interval_ms": pacing["min_interval_ms"],
                    "reason": reason_text,
                    "url": url.split("?")[0],
                    "retryable": retryable,
                    **(telemetry_context or {}),
                }
            )
            last_exception = ModelGatewayRequestError(
                f"{_provider_label(route)} generateContent network error: {reason_text}",
                variant_label=variant_label,
                hint=_network_failure_hint(exc.reason),
            )
            if retryable and attempt < config.max_retries:
                time.sleep(config.retry_backoff_seconds * (2 ** attempt))
                continue
            raise last_exception from exc
        except OSError as exc:
            reason_text = _network_reason_text(exc)
            retryable = _is_retryable_network_reason(exc)
            _log_model_call(
                {
                    "timestamp": now_iso(),
                    "status": "network_os_error",
                    "provider": route["provider"],
                    "task_type": route["task_type"],
                    "model": route["model"],
                    "request_variant": variant_label,
                    "endpoint_mode": route["endpoint_mode"],
                    "auth_mode": route["auth_mode"],
                    "attempt": attempt + 1,
                    "wait_seconds": pacing["wait_seconds"],
                    "min_interval_ms": pacing["min_interval_ms"],
                    "reason": reason_text,
                    "url": url.split("?")[0],
                    "retryable": retryable,
                    **(telemetry_context or {}),
                }
            )
            last_exception = ModelGatewayRequestError(
                f"{_provider_label(route)} generateContent OS/network error: {reason_text}",
                variant_label=variant_label,
                hint=_network_failure_hint(exc),
            )
            if retryable and attempt < config.max_retries:
                time.sleep(config.retry_backoff_seconds * (2 ** attempt))
                continue
            raise last_exception from exc
        except (TimeoutError, socket.timeout) as exc:
            _log_model_call(
                {
                    "timestamp": now_iso(),
                    "status": "timeout",
                    "provider": route["provider"],
                    "task_type": route["task_type"],
                    "model": route["model"],
                    "request_variant": variant_label,
                    "endpoint_mode": route["endpoint_mode"],
                    "auth_mode": route["auth_mode"],
                    "attempt": attempt + 1,
                    "wait_seconds": pacing["wait_seconds"],
                    "min_interval_ms": pacing["min_interval_ms"],
                    "url": url.split("?")[0],
                    "retryable": attempt < config.max_retries,
                    **(telemetry_context or {}),
                }
            )
            last_exception = ModelGatewayRequestError(
                "Vertex generateContent timed out while waiting for a response.",
                variant_label=variant_label,
            )
            if attempt < config.max_retries:
                time.sleep(config.retry_backoff_seconds * (2 ** attempt))
                continue
            raise last_exception from exc
    if last_exception is not None:
        raise last_exception
    raise ModelGatewayRequestError("Vertex generateContent failed without a captured exception.", variant_label=variant_label)


def _run_variants(
    route: dict[str, Any],
    variants: list[tuple[str, dict[str, Any]]],
    telemetry_context: dict[str, Any] | None = None,
) -> tuple[dict[str, Any], str]:
    last_error: ModelGatewayRequestError | None = None
    for label, body in variants:
        try:
            return _post_generate_content(
                route,
                body=body,
                variant_label=label,
                telemetry_context=telemetry_context,
            ), label
        except ModelGatewayRequestError as exc:
            last_error = exc
            if exc.status_code not in {400, 404}:
                raise
    if last_error is not None:
        raise last_error
    raise ModelGatewayRequestError("No request variants were provided.")


def _grounding_variants_for_route(route: dict[str, Any]) -> tuple[str, ...]:
    model_name = str(route.get("model") or "").strip().lower()
    if model_name.startswith("gemini-1.5"):
        return ("googleSearchRetrieval", "googleSearch")
    return ("googleSearch",)


def generate_text(
    provider_route: dict[str, Any],
    *,
    system_policy_ref: Any,
    prompt: str,
    context_artifacts: list[Any] | None = None,
    generation_config: dict[str, Any] | None = None,
    telemetry_context: dict[str, Any] | None = None,
) -> dict[str, Any]:
    body = _build_request_body(
        provider_route,
        prompt=prompt,
        system_policy_ref=system_policy_ref,
        context_artifacts=context_artifacts,
        generation_config=generation_config,
    )
    response_payload, variant = _run_variants(
        provider_route,
        [("plain_text", body)],
        telemetry_context=telemetry_context,
    )
    return {
        "provider_route": provider_route,
        "request_variant": variant,
        "generated_text": _extract_text(response_payload),
        "usage": _usage_metadata(response_payload),
        "response_received_at": now_iso(),
    }


def generate_structured(
    provider_route: dict[str, Any],
    *,
    schema_id: str,
    response_schema: dict[str, Any],
    prompt: str,
    system_policy_ref: Any,
    context_artifacts: list[Any] | None = None,
    generation_config: dict[str, Any] | None = None,
    telemetry_context: dict[str, Any] | None = None,
) -> dict[str, Any]:
    variants = [
        (
            "responseJsonSchema",
            _build_request_body(
                provider_route,
                prompt=prompt,
                system_policy_ref=system_policy_ref,
                context_artifacts=context_artifacts,
                generation_config=generation_config,
                response_schema=response_schema,
                schema_variant="responseJsonSchema",
            ),
        ),
        (
            "responseSchema",
            _build_request_body(
                provider_route,
                prompt=prompt,
                system_policy_ref=system_policy_ref,
                context_artifacts=context_artifacts,
                generation_config=generation_config,
                response_schema=response_schema,
                schema_variant="responseSchema",
            ),
        ),
    ]
    response_payload, variant = _run_variants(
        provider_route,
        variants,
        telemetry_context=telemetry_context,
    )
    raw_text = _extract_text(response_payload)
    try:
        structured_payload = _extract_json_text(raw_text)
    except json.JSONDecodeError as exc:
        raise ModelGatewayRequestError(
            f"Model did not return valid JSON for schema {schema_id}.",
            variant_label=variant,
            response_body=raw_text,
        ) from exc
    return {
        "provider_route": provider_route,
        "request_variant": variant,
        "schema_id": schema_id,
        "structured_payload": structured_payload,
        "usage": _usage_metadata(response_payload),
        "response_received_at": now_iso(),
    }


def grounded_research(
    query_set: list[str],
    source_policy: dict[str, Any],
    *,
    citation_required: bool = True,
    system_policy_ref: Any = None,
    context_artifacts: list[Any] | None = None,
    provider_route: dict[str, Any] | None = None,
    telemetry_context: dict[str, Any] | None = None,
) -> dict[str, Any]:
    route = provider_route or route_provider("grounded_research", grounding_required=True)
    source_types = source_policy.get("source_types", [])
    freshness_window = source_policy.get("freshness_window_days")
    prompt = "\n".join(
        [
            "You are AG-02 in a Korean book-writing pipeline.",
            "Use grounded web retrieval to collect current, attributable evidence.",
            "Return Korean summaries, but keep source titles and publisher names in their original language when helpful.",
            f"Citation required: {citation_required}",
            f"Preferred source types: {', '.join(source_types) if source_types else 'not specified'}",
            f"Freshness window days: {freshness_window if freshness_window is not None else 'not specified'}",
            "Queries:",
            *[f"- {query}" for query in query_set],
        ]
    )
    json_only_prompt = "\n".join(
        [
            prompt,
            "",
            "Return ONLY a JSON object.",
            "Do not use markdown fences.",
            "Use this shape exactly:",
            '{',
            '  "grounded_summary": "string",',
            '  "key_findings": ["string"],',
            '  "sources": [',
            '    {',
            '      "title": "string",',
            '      "source_name": "string",',
            '      "url_or_identifier": "string",',
            '      "published_date": "string",',
            '      "access_date": "string",',
            '      "usage_note": "grounded_research",',
            '      "source_type_hint": "string"',
            "    }",
            "  ]",
            "}",
            "If a value is unknown, use an empty string. If no sources are available, return an empty array.",
        ]
    )
    schema = {
        "type": "object",
        "properties": {
            "grounded_summary": {"type": "string"},
            "key_findings": {
                "type": "array",
                "items": {"type": "string"},
            },
            "sources": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "title": {"type": "string"},
                        "source_name": {"type": "string"},
                        "url_or_identifier": {"type": "string"},
                        "published_date": {"type": "string"},
                        "access_date": {"type": "string"},
                        "usage_note": {"type": "string"},
                        "source_type_hint": {"type": "string"},
                    },
                    "required": [
                        "title",
                        "source_name",
                        "url_or_identifier",
                        "access_date",
                        "usage_note",
                    ],
                    "additionalProperties": False,
                },
            },
        },
        "required": ["grounded_summary", "key_findings", "sources"],
        "additionalProperties": False,
    }
    base_body = {
        "prompt": prompt,
        "system_policy_ref": system_policy_ref,
        "context_artifacts": context_artifacts,
        "generation_config": {"temperature": 0.1},
        "response_schema": schema,
    }
    variants = []
    grounding_variants = _grounding_variants_for_route(route)
    for grounding_variant in grounding_variants:
        variants.append(
            (
                f"{grounding_variant}.responseJsonSchema",
                _build_request_body(
                    route,
                    prompt=base_body["prompt"],
                    system_policy_ref=base_body["system_policy_ref"],
                    context_artifacts=base_body["context_artifacts"],
                    generation_config=base_body["generation_config"],
                    response_schema=base_body["response_schema"],
                    schema_variant="responseJsonSchema",
                    grounding_variant=grounding_variant,
                ),
            )
        )
        variants.append(
            (
                f"{grounding_variant}.jsonPrompt",
                _build_request_body(
                    route,
                    prompt=json_only_prompt,
                    system_policy_ref=base_body["system_policy_ref"],
                    context_artifacts=base_body["context_artifacts"],
                    generation_config=base_body["generation_config"],
                    grounding_variant=grounding_variant,
                ),
            )
        )
    response_payload, variant = _run_variants(route, variants, telemetry_context=telemetry_context)
    raw_text = _extract_text(response_payload)
    try:
        structured_payload = _extract_json_text(raw_text)
    except json.JSONDecodeError as exc:
        raise ModelGatewayRequestError(
            "Grounded research response was not valid JSON.",
            variant_label=variant,
            response_body=raw_text,
        ) from exc

    grounded_sources = _extract_grounding_sources(response_payload)
    merged_sources: list[dict[str, Any]] = []
    seen_urls = set()
    for source in structured_payload.get("sources", []):
        url = source.get("url_or_identifier")
        if url and url not in seen_urls:
            seen_urls.add(url)
            merged_sources.append(source)
    for source in grounded_sources:
        url = source.get("url_or_identifier")
        if url and url not in seen_urls:
            seen_urls.add(url)
            merged_sources.append(source)

    return {
        "provider_route": route,
        "request_variant": variant,
        "grounded_summary": structured_payload.get("grounded_summary", ""),
        "key_findings": structured_payload.get("key_findings", []),
        "sources": merged_sources,
        "usage": _usage_metadata(response_payload),
        "response_received_at": now_iso(),
    }


def safety_check(
    text: str,
    *,
    system_policy_ref: Any = None,
    provider_route: dict[str, Any] | None = None,
) -> dict[str, Any]:
    route = provider_route or route_provider("safety_check")
    schema = {
        "type": "object",
        "properties": {
            "risk_level": {"type": "string"},
            "issues": {
                "type": "array",
                "items": {"type": "string"},
            },
            "recommended_action": {"type": "string"},
        },
        "required": ["risk_level", "issues", "recommended_action"],
        "additionalProperties": False,
    }
    response = generate_structured(
        route,
        schema_id="safety_report@1.0",
        response_schema=schema,
        prompt="Assess the following text for safety, copyright, privacy, and defamation risk.\n\n" + text,
        system_policy_ref=system_policy_ref,
        context_artifacts=None,
        generation_config={"temperature": 0.0},
    )
    return {
        **response,
        "safety_report": response["structured_payload"],
    }


def build_generate_content_preview(
    task_type: str,
    *,
    prompt: str,
    system_policy_ref: Any = None,
    context_artifacts: list[Any] | None = None,
    response_schema: dict[str, Any] | None = None,
    grounded: bool = False,
) -> dict[str, Any]:
    route = route_provider(task_type, grounding_required=grounded)
    preview_grounding_variant = _grounding_variants_for_route(route)[0] if grounded else None
    body = _build_request_body(
        route,
        prompt=prompt,
        system_policy_ref=system_policy_ref,
        context_artifacts=context_artifacts,
        response_schema=response_schema,
        grounding_variant=preview_grounding_variant,
    )
    config = load_model_gateway_config()
    preview_route = copy.deepcopy(route)
    preview_route["url"] = _build_url(config, route, "generateContent").replace(config.api_key or "", "***")
    return {
        "provider_route": preview_route,
        "request_body": body,
    }


def diagnose_vertex_live_probe() -> dict[str, Any]:
    route = route_provider("generate_text")
    try:
        result = generate_text(
            route,
            system_policy_ref="Return one short sentence in Korean.",
            prompt="Vertex express auth probe.",
            context_artifacts=None,
            generation_config={"maxOutputTokens": 128, "temperature": 0.0},
        )
        return {
            "ok": True,
            "provider_route": route,
            "request_variant": result["request_variant"],
            "text_preview": result["generated_text"][:120],
        }
    except ModelGatewayRequestError as exc:
        payload = exc.to_dict()
        return {
            "ok": False,
            "provider_route": route,
            "error": payload,
            "classification": classify_auth_failure(payload),
        }
