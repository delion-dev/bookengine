from __future__ import annotations

"""License validation router — offline HMAC-based verification."""

import hashlib
import hmac
import json
import os
from pathlib import Path

from fastapi import APIRouter

from engine_api.models import LicenseValidateRequest, LicenseStatusResponse

router = APIRouter(prefix="/engine/license", tags=["license"])

# Secret embedded at build time (override via env var BOOKENGINE_LICENSE_SECRET)
_SECRET = os.environ.get("BOOKENGINE_LICENSE_SECRET", "bookengine-dev-secret-2026")

# License cache file
_LICENSE_FILE = Path.home() / "AppData" / "Roaming" / "BookEngine" / "license.json"

TRIAL_KEY = "BKENG-TRIAL-00000-00000-00000"


def _compute_expected(key_body: str) -> str:
    """Compute HMAC-SHA256 checksum for a license key body."""
    return hmac.new(_SECRET.encode(), key_body.encode(), hashlib.sha256).hexdigest()[:8].upper()


def _validate_key(key: str) -> tuple[bool, str]:
    """Validate license key. Returns (is_valid, plan)."""
    key = key.strip().upper()

    if key == TRIAL_KEY:
        return True, "trial"

    parts = key.split("-")
    if len(parts) != 5 or parts[0] != "BKENG":
        return False, ""

    # Format: BKENG-PLAN1-XXXXX-XXXXX-CHKSM
    plan_code = parts[1]
    key_body = "-".join(parts[:4])
    checksum = parts[4]

    expected = _compute_expected(key_body)
    if checksum != expected:
        return False, ""

    plan_map = {"PRO01": "pro", "BASIC": "basic", "ENTPR": "enterprise"}
    plan = plan_map.get(plan_code, "pro")
    return True, plan


def _save_license(key: str, plan: str) -> None:
    _LICENSE_FILE.parent.mkdir(parents=True, exist_ok=True)
    _LICENSE_FILE.write_text(json.dumps({"key": key, "plan": plan}), encoding="utf-8")


def _load_license() -> dict:
    if _LICENSE_FILE.exists():
        try:
            return json.loads(_LICENSE_FILE.read_text(encoding="utf-8"))
        except Exception:
            pass
    return {}


@router.post("/validate")
def validate_license(req: LicenseValidateRequest) -> LicenseStatusResponse:
    """Validate a license key and persist if valid."""
    is_valid, plan = _validate_key(req.key)
    if is_valid:
        _save_license(req.key, plan)
    return LicenseStatusResponse(
        valid=is_valid,
        plan=plan if is_valid else "",
        key_masked=f"{req.key[:8]}****" if len(req.key) > 8 else "****",
    )


@router.get("/status")
def license_status() -> LicenseStatusResponse:
    """Return current license status from local cache."""
    data = _load_license()
    if not data:
        return LicenseStatusResponse(valid=False, plan="", key_masked="")
    is_valid, plan = _validate_key(data.get("key", ""))
    key = data.get("key", "")
    return LicenseStatusResponse(
        valid=is_valid,
        plan=plan if is_valid else "",
        key_masked=f"{key[:8]}****" if len(key) > 8 else "****",
    )
