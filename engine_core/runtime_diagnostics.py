from __future__ import annotations

import json
import os
import platform
import socket
import subprocess
import sys
from collections import Counter
from pathlib import Path
from typing import Any

from .common import REPO_ROOT, now_iso
from .model_gateway import (
    ModelGatewayRequestError,
    describe_model_gateway,
    diagnose_vertex_live_probe,
    generate_text,
    grounded_research,
    route_provider,
)


_MODEL_HOST = "aiplatform.googleapis.com"
_MODEL_PORT = 443
_MODEL_CALL_LOG_PATH = REPO_ROOT / "platform" / "core_engine" / "runtime" / "model_call_log.jsonl"


def _read_recent_model_events(limit: int = 200) -> list[dict[str, Any]]:
    if not _MODEL_CALL_LOG_PATH.exists():
        return []
    lines = _MODEL_CALL_LOG_PATH.read_text(encoding="utf-8").splitlines()[-limit:]
    events: list[dict[str, Any]] = []
    for line in lines:
        try:
            payload = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(payload, dict):
            events.append(payload)
    return events


def _event_matches_10013(event: dict[str, Any]) -> bool:
    reason = str(event.get("reason") or "").lower()
    return "winerror 10013" in reason


def _event_matches_timeout(event: dict[str, Any]) -> bool:
    if event.get("status") == "timeout":
        return True
    reason = str(event.get("reason") or "").lower()
    return "timed out" in reason or "timeout" in reason


def _summarize_recent_model_events(events: list[dict[str, Any]]) -> dict[str, Any]:
    if not events:
        return {
            "event_count": 0,
            "status_counts": {},
            "latest_ok": None,
            "latest_10013": None,
            "latest_timeout": None,
            "mixed_success_and_10013": False,
        }

    status_counts = Counter(str(event.get("status") or "unknown") for event in events)
    latest_ok = next((event for event in reversed(events) if event.get("status") == "ok"), None)
    latest_10013 = next((event for event in reversed(events) if _event_matches_10013(event)), None)
    latest_timeout = next((event for event in reversed(events) if _event_matches_timeout(event)), None)
    models = sorted({str(event.get("model") or "") for event in events if event.get("model")})
    request_variants = sorted(
        {str(event.get("request_variant") or "") for event in events if event.get("request_variant")}
    )
    stages = sorted({str(event.get("stage_id") or "") for event in events if event.get("stage_id")})
    return {
        "event_count": len(events),
        "status_counts": dict(status_counts),
        "latest_event": events[-1],
        "latest_ok": latest_ok,
        "latest_10013": latest_10013,
        "latest_timeout": latest_timeout,
        "mixed_success_and_10013": latest_ok is not None and latest_10013 is not None,
        "models": models,
        "request_variants": request_variants,
        "stages_seen": stages,
    }


def _environment_proxy_settings() -> dict[str, str]:
    keys = [
        "HTTP_PROXY",
        "HTTPS_PROXY",
        "ALL_PROXY",
        "NO_PROXY",
        "http_proxy",
        "https_proxy",
        "all_proxy",
        "no_proxy",
    ]
    return {key: value for key in keys if (value := os.environ.get(key))}


def _winhttp_proxy_settings() -> dict[str, Any]:
    if platform.system() != "Windows":
        return {"available": False, "reason": "windows_only"}
    try:
        result = subprocess.run(
            ["netsh", "winhttp", "show", "proxy"],
            capture_output=True,
            text=True,
            timeout=10,
            check=False,
        )
    except Exception as exc:  # pragma: no cover - diagnostic fallback
        return {"available": True, "ok": False, "error": str(exc)}
    return {
        "available": True,
        "ok": result.returncode == 0,
        "stdout": result.stdout.strip(),
        "stderr": result.stderr.strip(),
        "returncode": result.returncode,
    }


def _wininet_proxy_settings() -> dict[str, Any]:
    if platform.system() != "Windows":
        return {"available": False, "reason": "windows_only"}
    try:
        import winreg
    except ImportError:  # pragma: no cover - only on non-Windows Python builds
        return {"available": True, "ok": False, "error": "winreg_unavailable"}

    key_path = r"Software\Microsoft\Windows\CurrentVersion\Internet Settings"
    result: dict[str, Any] = {"available": True, "ok": True}
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, key_path) as handle:
            for name in ("ProxyEnable", "ProxyServer", "AutoConfigURL"):
                try:
                    value, _ = winreg.QueryValueEx(handle, name)
                except FileNotFoundError:
                    value = None
                result[name] = value
    except OSError as exc:
        result["ok"] = False
        result["error"] = str(exc)
    return result


def _dns_resolution(host: str = _MODEL_HOST) -> dict[str, Any]:
    try:
        rows = socket.getaddrinfo(host, _MODEL_PORT, type=socket.SOCK_STREAM)
    except OSError as exc:
        return {"ok": False, "host": host, "error": str(exc)}

    addresses: list[dict[str, Any]] = []
    seen = set()
    for family, socktype, proto, canonname, sockaddr in rows:
        address = sockaddr[0]
        key = (family, address)
        if key in seen:
            continue
        seen.add(key)
        addresses.append(
            {
                "family": "ipv6" if family == socket.AF_INET6 else "ipv4",
                "address": address,
                "socktype": socktype,
                "proto": proto,
            }
        )
    return {"ok": True, "host": host, "addresses": addresses}


def _tiny_plain_text_probe() -> dict[str, Any]:
    route = route_provider("generate_text")
    try:
        response = generate_text(
            route,
            system_policy_ref="Return one short Korean sentence.",
            prompt="짧게 상태만 말해줘.",
            context_artifacts=None,
            generation_config={"maxOutputTokens": 64, "temperature": 0.0},
        )
    except ModelGatewayRequestError as exc:
        return {"ok": False, "error": exc.to_dict()}
    return {
        "ok": True,
        "request_variant": response.get("request_variant"),
        "usage": response.get("usage"),
        "text_preview": str(response.get("generated_text") or "")[:120],
    }


def _tiny_grounded_probe() -> dict[str, Any]:
    route = route_provider("grounded_research", grounding_required=True)
    try:
        response = grounded_research(
            ["영월 장릉 최신 방문 정보"],
            {"source_types": ["official_site"], "freshness_window_days": 30},
            citation_required=True,
            system_policy_ref="Return concise Korean JSON only.",
            provider_route=route,
        )
    except ModelGatewayRequestError as exc:
        return {"ok": False, "error": exc.to_dict()}
    return {
        "ok": True,
        "request_variant": response.get("request_variant"),
        "usage": response.get("usage"),
        "source_count": len(response.get("sources") or []),
        "finding_count": len(response.get("key_findings") or []),
    }


def _assessment_notes(payload: dict[str, Any]) -> list[str]:
    notes: list[str] = []
    model_gateway = payload.get("model_gateway", {})
    recent = payload.get("recent_model_events", {})
    live_probes = payload.get("live_probes", {})
    env_proxy = payload.get("environment_proxy", {})
    dns = payload.get("dns_resolution", {})
    winhttp = payload.get("winhttp_proxy", {})
    wininet = payload.get("wininet_proxy", {})

    if model_gateway.get("ready_for_live_calls"):
        notes.append("Model gateway configuration is sufficient for live calls in the current auth mode.")
    if dns.get("ok"):
        notes.append("DNS resolution for aiplatform.googleapis.com is healthy.")
    if not env_proxy and "Direct access" in str(winhttp.get("stdout") or ""):
        notes.append("No proxy misconfiguration signal was detected in environment variables or WinHTTP.")
    if not wininet.get("ProxyEnable") and not wininet.get("ProxyServer") and not wininet.get("AutoConfigURL"):
        notes.append("User-level WinINet proxy settings appear disabled.")
    if recent.get("mixed_success_and_10013"):
        notes.append(
            "The same machine has both successful Vertex responses and WinError 10013 failures. This points to execution-context or endpoint-security interference more than a stable auth/request-format bug."
        )
    if recent.get("latest_10013") and recent.get("latest_ok"):
        notes.append(
            "Because successful calls exist with the same endpoint family, treat WinError 10013 as a local socket policy failure first."
        )
    probe_states = [
        bool(probe.get("ok"))
        for probe in live_probes.values()
        if isinstance(probe, dict) and "ok" in probe
    ]
    if probe_states and all(probe_states):
        notes.append("The current invocation context can complete all requested live probes successfully.")
    elif probe_states and not any(probe_states):
        notes.append("The current invocation context fails even minimal live probes, which reinforces a local socket/policy issue.")
    return notes


def diagnose_runtime(*, include_live_probes: bool = False, include_grounded_probe: bool = False) -> dict[str, Any]:
    recent_events = _read_recent_model_events()
    payload: dict[str, Any] = {
        "generated_at": now_iso(),
        "runtime": {
            "python_version": sys.version,
            "platform": platform.platform(),
            "system": platform.system(),
            "release": platform.release(),
            "machine": platform.machine(),
        },
        "model_gateway": describe_model_gateway(),
        "environment_proxy": _environment_proxy_settings(),
        "winhttp_proxy": _winhttp_proxy_settings(),
        "wininet_proxy": _wininet_proxy_settings(),
        "dns_resolution": _dns_resolution(),
        "recent_model_events": _summarize_recent_model_events(recent_events),
    }

    if include_live_probes:
        probes = {
            "vertex_auth_probe": diagnose_vertex_live_probe(),
            "plain_text_probe": _tiny_plain_text_probe(),
        }
        if include_grounded_probe:
            probes["grounded_research_probe"] = _tiny_grounded_probe()
        payload["live_probes"] = probes

    payload["assessment_notes"] = _assessment_notes(payload)
    return payload
