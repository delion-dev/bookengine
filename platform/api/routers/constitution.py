from __future__ import annotations

"""engine.constitution — Dynamic Constitutional Prompting endpoints."""

from fastapi import APIRouter, HTTPException

from engine_core.constitution_parser import (
    build_constitutional_injection,
    build_minimal_injection,
    list_parsed_articles,
    list_parsed_sops,
    reload_all,
)
from ..models import ConstitutionInjectRequest

router = APIRouter(prefix="/engine/constitution", tags=["constitution"])


@router.get("/articles")
def get_articles():
    """List all parsed constitution articles (summary)."""
    return {"articles": list_parsed_articles()}


@router.get("/sops")
def get_sops():
    """List all parsed agent SOPs (summary)."""
    return {"sops": list_parsed_sops()}


@router.post("/inject")
def inject(req: ConstitutionInjectRequest):
    """Build a constitutional injection block for a (stage_id, agent_id) pair."""
    try:
        return build_constitutional_injection(
            req.stage_id,
            req.agent_id,
            include_sop=req.include_sop,
            max_rules=req.max_rules,
        )
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))


@router.get("/minimal/{stage_id}")
def minimal_injection(stage_id: str):
    """Return a compact prompt prefix string for a given stage."""
    return {"stage_id": stage_id, "prompt_block": build_minimal_injection(stage_id)}


@router.post("/reload")
def reload_constitution():
    """Clear the parse cache and reload CONSTITUTION.md + AGENT_SOPS.md."""
    reload_all()
    return {"ok": True, "reloaded": ["CONSTITUTION.md", "AGENT_SOPS.md"]}
