# -*- mode: python ; coding: utf-8 -*-
# BookEngine Server — PyInstaller spec
#
# Build (from project root):
#   pyinstaller tools/bookengine_server.spec --distpath frontend/src-tauri/binaries
#
# Output: frontend/src-tauri/binaries/book_engine_server.exe   (Windows)
#         frontend/src-tauri/binaries/book_engine_server       (macOS/Linux)

import os
import sys
from pathlib import Path

ROOT = Path(SPECPATH).parent  # project root (one level above tools/)

# ---------------------------------------------------------------------------
# Hidden imports — FastAPI / uvicorn / engine packages
# ---------------------------------------------------------------------------

hidden_imports = [
    # uvicorn internals
    "uvicorn.logging",
    "uvicorn.loops",
    "uvicorn.loops.auto",
    "uvicorn.loops.asyncio",
    "uvicorn.protocols",
    "uvicorn.protocols.http",
    "uvicorn.protocols.http.auto",
    "uvicorn.protocols.websockets",
    "uvicorn.protocols.websockets.auto",
    "uvicorn.lifespan",
    "uvicorn.lifespan.on",
    # fastapi
    "fastapi",
    "fastapi.responses",
    "fastapi.middleware",
    "fastapi.middleware.cors",
    "starlette",
    "starlette.routing",
    "starlette.middleware",
    "starlette.middleware.cors",
    "pydantic",
    "pydantic.fields",
    "pydantic.validators",
    # engine routers (ensure all are discovered)
    "engine_api.app",
    "engine_api.routers.constitution",
    "engine_api.routers.gate",
    "engine_api.routers.healing",
    "engine_api.routers.license",
    "engine_api.routers.mesh",
    "engine_api.routers.publish",
    "engine_api.routers.qa",
    "engine_api.routers.registry",
    "engine_api.routers.settings",
    "engine_api.routers.stage",
    "engine_api.routers.work_order",
    # engine_core — all modules
    "engine_core",
    "engine_core.common",
    "engine_core.book_state",
    "engine_core.contracts",
    "engine_core.context_packs",
    "engine_core.constitution_parser",
    "engine_core.gates",
    "engine_core.knowledge_mesh",
    "engine_core.memory",
    "engine_core.model_gateway",
    "engine_core.model_policy",
    "engine_core.s4_orchestrator",
    "engine_core.self_healing",
    "engine_core.stage",
    "engine_core.stage_api",
    "engine_core.work_order",
    "engine_core.writer",
]

# ---------------------------------------------------------------------------
# Data files — platform JSON configs, templates, CONSTITUTION
# ---------------------------------------------------------------------------

datas = [
    # Platform core engine config JSONs
    (str(ROOT / "platform" / "core_engine"), "platform/core_engine"),
    # CONSTITUTION + SOP prompts
    (str(ROOT / "platform" / "constitution"), "platform/constitution"),
    # Any Jinja2 / text templates
    (str(ROOT / "platform" / "templates"), "platform/templates"),
]

# Filter out non-existent paths to avoid build errors
datas = [(src, dst) for src, dst in datas if Path(src).exists()]

# ---------------------------------------------------------------------------
# Analysis
# ---------------------------------------------------------------------------

a = Analysis(
    [str(ROOT / "tools" / "server_entry.py")],
    pathex=[str(ROOT)],
    binaries=[],
    datas=datas,
    hiddenimports=hidden_imports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=["tkinter", "matplotlib", "PIL", "pytest"],
    noarchive=False,
)

pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name="book_engine_server",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=True,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)
