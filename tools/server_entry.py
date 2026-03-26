"""BookEngine Server Entry Point — PyInstaller sidecar target.

When bundled as a PyInstaller one-file executable this module:
  1. Ensures PLATFORM_CORE_ROOT resolves correctly inside _MEIPASS
  2. Launches the FastAPI server via uvicorn

Usage (standalone):  book_engine_server.exe [--host HOST] [--port PORT]
Usage (via Tauri):   spawned automatically by the desktop app
"""
from __future__ import annotations

import argparse
import sys

# ---------------------------------------------------------------------------
# PyInstaller sys._MEIPASS safety — make sure the bundled packages are on path
# ---------------------------------------------------------------------------
import os

if getattr(sys, "frozen", False):
    # Running as a PyInstaller bundle
    _bundle_dir = getattr(sys, "_MEIPASS", os.path.dirname(sys.executable))
    if _bundle_dir not in sys.path:
        sys.path.insert(0, _bundle_dir)

# ---------------------------------------------------------------------------
# Argument parsing
# ---------------------------------------------------------------------------

parser = argparse.ArgumentParser(description="BookEngine FastAPI server")
parser.add_argument("--host", default="127.0.0.1")
parser.add_argument("--port", type=int, default=8000)
parser.add_argument("--reload", action="store_true", default=False)
args = parser.parse_args()

# ---------------------------------------------------------------------------
# Launch uvicorn
# ---------------------------------------------------------------------------

import uvicorn  # noqa: E402 — after sys.path fixup

uvicorn.run(
    "engine_api.app:app",
    host=args.host,
    port=args.port,
    reload=args.reload,
    log_level="info",
)
