"""Steelshield API: deterministic local policy evaluation only."""

from __future__ import annotations

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.v1.routes import router as v1_router

app = FastAPI(
    title="Steelshield Agent Control Plane",
    version="0.2.0",
    description=(
        "Synthetic evaluation with fixture twins or declared-gateway LLM agents. "
        "Deterministic canary/state oracles remain the pass/fail authority. "
        "It never accepts a client-supplied chatbot URL."
    ),
)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000", "http://127.0.0.1:3000"],
    allow_credentials=False,
    allow_methods=["GET", "POST"],
    allow_headers=["Content-Type"],
)
app.include_router(v1_router)
