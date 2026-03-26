from __future__ import annotations

"""Pydantic request/response schemas for the Core Engine API."""

from typing import Any

from pydantic import BaseModel, Field


# ---------------------------------------------------------------------------
# Common
# ---------------------------------------------------------------------------

class OkResponse(BaseModel):
    ok: bool = True
    detail: str = ""


# ---------------------------------------------------------------------------
# Stage
# ---------------------------------------------------------------------------

class StageRunRequest(BaseModel):
    book_id: str
    stage_id: str
    chapter_id: str | None = None
    rerun_completed: bool = False


class StageRunResponse(BaseModel):
    stage_id: str
    status: str
    result: dict[str, Any]


class StageTransitionRequest(BaseModel):
    book_id: str
    stage_id: str
    to_status: str
    chapter_id: str | None = None
    note: str = ""


# ---------------------------------------------------------------------------
# Gate
# ---------------------------------------------------------------------------

class GateEvalRequest(BaseModel):
    book_id: str
    stage_id: str
    chapter_id: str | None = None


class GateEvalResponse(BaseModel):
    stage_id: str
    chapter_id: str | None
    gate_id: str
    passed: bool
    checks: list[dict[str, Any]]
    output_checks: list[dict[str, Any]]
    on_fail: dict[str, Any]


class GateRefreshRequest(BaseModel):
    book_id: str
    stage_id: str
    chapter_id: str | None = None


# ---------------------------------------------------------------------------
# Work Order
# ---------------------------------------------------------------------------

class WorkOrderResponse(BaseModel):
    order_id: str
    book_id: str
    issued_at: str
    priority_queue: list[dict[str, Any]]
    blocked_items: list[dict[str, Any]]
    gate_failures: list[dict[str, Any]]
    runtime_alerts: list[dict[str, Any]]


# ---------------------------------------------------------------------------
# Self-Healing
# ---------------------------------------------------------------------------

class HealRequest(BaseModel):
    book_id: str
    dry_run: bool = False


class HealResponse(BaseModel):
    book_id: str
    dry_run: bool
    gate_failure_count: int
    summary: dict[str, int]
    healing_actions: list[dict[str, Any]]
    escalations: list[dict[str, Any]]
    skipped: list[dict[str, Any]]


# ---------------------------------------------------------------------------
# Knowledge Mesh
# ---------------------------------------------------------------------------

class MeshBuildRequest(BaseModel):
    book_id: str


class MeshQueryRequest(BaseModel):
    book_id: str
    query: str


class MeshNodeUpdateRequest(BaseModel):
    book_id: str
    chapter_id: str
    summary: str | None = None
    claims: list[str] | None = None
    unresolved_issues: list[str] | None = None
    citations_summary: list[str] | None = None
    visual_notes: list[str] | None = None


# ---------------------------------------------------------------------------
# License
# ---------------------------------------------------------------------------

class LicenseValidateRequest(BaseModel):
    key: str


class LicenseStatusResponse(BaseModel):
    valid: bool
    plan: str  # "trial" | "basic" | "pro" | "enterprise" | ""
    key_masked: str


# ---------------------------------------------------------------------------
# App Settings
# ---------------------------------------------------------------------------

class AppSettings(BaseModel):
    gemini_api_key: str = ""
    openai_api_key: str = ""
    default_model: str = "gemini-2.0-flash"
    app_version: str = "0.1.0"


# ---------------------------------------------------------------------------
# Bootstrap Book
# ---------------------------------------------------------------------------

class BootstrapBookRequest(BaseModel):
    book_id: str
    display_name: str
    book_root: str
    source_file: str


# ---------------------------------------------------------------------------
# Constitution
# ---------------------------------------------------------------------------

class ConstitutionInjectRequest(BaseModel):
    stage_id: str
    agent_id: str | None = None
    include_sop: bool = True
    max_rules: int = Field(default=12, ge=1, le=30)
