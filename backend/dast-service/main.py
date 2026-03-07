# backend/dast-service/main.py

"""
DAST Microservice — runs on port 7095
Separate from vibe-secure-gen (port 8000) for isolation.

Endpoints:
  POST /dast/analyze   — run full DAST on a code blob
  GET  /dast/health    — health check
  GET  /dast/docker    — check Docker availability
"""

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field
from analyzer import run_dast

app = FastAPI(title="DAST Security Microservice", version="1.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ── Request / Response models ─────────────────────────────────────────────

class DastRequest(BaseModel):
    code_blob: str = Field(min_length=10, description="The code blob to analyze")
    language:  str = Field(default="", description="Optional language hint")

# ── Routes ────────────────────────────────────────────────────────────────

@app.post("/dast/analyze")
async def analyze(req: DastRequest):
    """Run DAST analysis on a code blob."""
    result = run_dast(req.code_blob, language_hint=req.language)
    return result

@app.get("/dast/health")
def health():
    """Health check."""
    return {"ok": True, "service": "dast-service", "port": 7095}

@app.get("/dast/docker")
def docker_status():
    """Check if Docker is available for sandbox execution."""
    from sandbox import is_docker_available, get_available_images
    available = is_docker_available()
    images    = get_available_images() if available else []
    return {
        "docker_available": available,
        "sandbox_images":   images,
    }