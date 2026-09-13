"""
main.py — FastAPI application entry point
==========================================
Starts the Wafer Yield Root Cause & Defect Pattern Analyser API.

Run from the repo root:
    uvicorn src.backend.main:app --reload --port 8000

Or from src/:
    uvicorn backend.main:app --reload --port 8000
"""

from __future__ import annotations

import os
import sys

# Allow running from repo root or from src/
_HERE = os.path.dirname(__file__)
_SRC  = os.path.abspath(os.path.join(_HERE, ".."))
if _SRC not in sys.path:
    sys.path.insert(0, _SRC)

# Load .env before anything else
from dotenv import load_dotenv
load_dotenv(os.path.join(_SRC, ".env"), override=False)

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from .routers import lots as lots_router
from .routers import analysis as analysis_router

# ---------------------------------------------------------------------------
# App
# ---------------------------------------------------------------------------

app = FastAPI(
    title="Wafer Yield Root Cause & Defect Pattern Analyser",
    description=(
        "AI-powered semiconductor yield analysis tool. "
        "Detects low-yield patterns, ranks root causes, predicts batch risk, "
        "and recommends corrective actions — powered by IBM watsonx.ai."
    ),
    version="1.0.0",
    docs_url="/docs",
    redoc_url="/redoc",
)

# ---------------------------------------------------------------------------
# CORS — allow all origins in development; tighten for production
# ---------------------------------------------------------------------------

_ALLOWED_ORIGINS = os.getenv("CORS_ORIGINS", "*").split(",")

app.add_middleware(
    CORSMiddleware,
    allow_origins=_ALLOWED_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ---------------------------------------------------------------------------
# Routers
# ---------------------------------------------------------------------------

app.include_router(lots_router.router)
app.include_router(analysis_router.router)

# ---------------------------------------------------------------------------
# Health check
# ---------------------------------------------------------------------------

@app.get("/health", tags=["meta"])
def health() -> dict:
    return {"status": "ok", "service": "wafer-yield-analyser"}


# ---------------------------------------------------------------------------
# Dashboard — serve index.html at root
# ---------------------------------------------------------------------------

# React build output: src/frontend/dist/
_FRONTEND_DIST = os.path.abspath(os.path.join(_HERE, "..", "frontend", "dist"))

@app.get("/", include_in_schema=False)
def dashboard():
    return FileResponse(os.path.join(_FRONTEND_DIST, "index.html"))

# Serve Vite assets (JS/CSS bundles are under /assets inside dist/)
# Mount AFTER all /api routes so API is never shadowed.
if os.path.isdir(_FRONTEND_DIST):
    app.mount("/", StaticFiles(directory=_FRONTEND_DIST, html=True), name="frontend")
