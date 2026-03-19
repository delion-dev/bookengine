from __future__ import annotations

"""App settings router — API key management, persisted locally."""

import json
from pathlib import Path

from fastapi import APIRouter

from engine_api.models import AppSettings

router = APIRouter(prefix="/engine/settings", tags=["settings"])

_SETTINGS_FILE = Path.home() / "AppData" / "Roaming" / "BookEngine" / "settings.json"


def _load() -> dict:
    if _SETTINGS_FILE.exists():
        try:
            return json.loads(_SETTINGS_FILE.read_text(encoding="utf-8"))
        except Exception:
            pass
    return {}


def _save(data: dict) -> None:
    _SETTINGS_FILE.parent.mkdir(parents=True, exist_ok=True)
    _SETTINGS_FILE.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


@router.get("")
def get_settings() -> AppSettings:
    """Return current app settings."""
    data = _load()
    return AppSettings(
        gemini_api_key=data.get("gemini_api_key", ""),
        openai_api_key=data.get("openai_api_key", ""),
        default_model=data.get("default_model", "gemini-2.0-flash"),
        app_version="0.1.0",
    )


@router.put("")
def update_settings(req: AppSettings) -> AppSettings:
    """Save app settings (API keys etc.)."""
    data = _load()
    if req.gemini_api_key is not None:
        data["gemini_api_key"] = req.gemini_api_key
    if req.openai_api_key is not None:
        data["openai_api_key"] = req.openai_api_key
    if req.default_model is not None:
        data["default_model"] = req.default_model
    _save(data)
    return get_settings()
