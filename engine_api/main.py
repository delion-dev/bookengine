from __future__ import annotations

"""Core Engine FastAPI Server

Entry point: `uvicorn platform.api.main:app --reload`
Or via CLI:  `python tools/core_engine_cli.py run-server --host 0.0.0.0 --port 8000`

API namespaces:
  GET  /                               — health check
  GET  /engine/registry/books          — list books
  GET  /engine/registry/books/{id}     — book detail
  GET  /engine/stage/handlers          — list stage handlers
  GET  /engine/stage/definition/{id}   — stage definition
  POST /engine/stage/contract/resolve  — resolve artifact contract
  POST /engine/stage/contract/validate — validate inputs exist
  POST /engine/stage/run               — run a stage (sync)
  POST /engine/stage/transition        — manual status transition
  GET  /engine/stage/pipeline/{book_id}— pipeline status board
  GET  /engine/gate/definitions        — list all gates
  GET  /engine/gate/definitions/{id}   — gate detail
  POST /engine/gate/evaluate           — evaluate gate
  POST /engine/gate/refresh            — re-evaluate & update status
  POST /engine/work-order/issue        — issue/refresh work order
  GET  /engine/work-order/telemetry    — runtime telemetry
  GET  /engine/healing/status          — pipeline health
  POST /engine/healing/scan            — scan + heal gate failures
  GET  /engine/healing/log             — healing event log
  GET  /engine/constitution/articles   — parsed constitution articles
  GET  /engine/constitution/sops       — parsed agent SOPs
  POST /engine/constitution/inject     — build constitutional injection block
  GET  /engine/constitution/minimal/{stage_id} — compact prompt prefix
  POST /engine/constitution/reload     — reload parse cache
  POST /engine/mesh/build              — rebuild knowledge mesh
  GET  /engine/mesh/bridge             — bridge context for chapter
  POST /engine/mesh/query              — keyword search
  POST /engine/mesh/node/update        — update chapter node
"""

import sys
from pathlib import Path

# Ensure repo root is on sys.path so engine_core imports work
_REPO_ROOT = Path(__file__).resolve().parent.parent.parent
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from engine_api.routers import constitution, gate, healing, license, mesh, publish, qa, registry, settings, stage, work_order

app = FastAPI(
    title="Core Engine API",
    description="Solar Book Platform — Core Engine HTTP API",
    version="1.0.0",
    docs_url="/docs",
    redoc_url="/redoc",
)

# CORS — allow local Next.js dev server and Tauri webview
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:3000",
        "http://localhost:3001",
        "tauri://localhost",
        "https://tauri.localhost",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Mount routers
app.include_router(registry.router)
app.include_router(stage.router)
app.include_router(gate.router)
app.include_router(work_order.router)
app.include_router(healing.router)
app.include_router(qa.router)
app.include_router(constitution.router)
app.include_router(mesh.router)
app.include_router(license.router)
app.include_router(settings.router)
app.include_router(publish.router)


@app.get("/", tags=["health"])
def health():
    """API health check."""
    return {
        "ok": True,
        "service": "core-engine-api",
        "version": "1.0.0",
        "docs": "/docs",
    }


@app.get("/engine/status", tags=["health"])
def engine_status():
    """Quick engine diagnostics — registry + handler count."""
    from engine_core.registry import get_registry
    from engine_core.stage_api import list_stage_handlers

    registry_data = get_registry()
    handlers = list_stage_handlers()
    return {
        "ok": True,
        "registered_books": len(registry_data.get("books", [])),
        "stage_handlers": len(handlers),
        "handlers": [h["stage_id"] for h in handlers],
    }
