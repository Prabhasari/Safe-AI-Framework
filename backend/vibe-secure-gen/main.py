from dotenv import load_dotenv
load_dotenv()

from fastapi import FastAPI, Response
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field
from typing import List, Any

from pipeline import run_pipeline
from history_router import router as history_router

app = FastAPI(title="Secure-by-Design Code Generator")

# CORS for local dev (Vite @ 5173, etc.)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(history_router, prefix="/api")

@app.options("/api/generate")
def options_generate():
    return Response(status_code=200)

class GenerateIn(BaseModel):
    prompt: str = Field(min_length=5, description="Describe the code to generate")

@app.post("/api/generate")
async def generate(inp: GenerateIn):
    return await run_pipeline(prompt=inp.prompt)

@app.get("/api/health")
def health():
    return {"ok": True}

@app.get("/api/model")
def model_name():
    from stages.llm import _MODEL_NAME
    return {"model": _MODEL_NAME}


# ── DAST fix endpoint (called by dast-service/analyzer.py) ───────────────────

class DastFixRequest(BaseModel):
    code_blob: str = Field(min_length=10, description="The code blob to fix")
    findings:  List[Any] = Field(default_factory=list, description="DAST findings to fix")


@app.post("/api/dast-fix")
async def dast_fix(req: DastFixRequest):
    """
    Called by dast-service to get LLM fixes for CRITICAL/HIGH DAST findings.
    Attempts an LLM fix, re-verifies with Semgrep, and returns fixed code
    plus any findings that still remain (unfixable).
    """
    from stages.llm_fix import fix_with_llm
    from stages.semgrep_smart_fix import run_semgrep_smart_fix

    if not req.findings:
        return {
            "fixed":             False,
            "fixed_code":        None,
            "fixes_applied":     0,
            "remaining_findings": [],
            "error":             "No findings provided",
        }

    # Only attempt CRITICAL / HIGH findings automatically
    critical_high = [
        f for f in req.findings
        if f.get("severity", "").upper() in ("CRITICAL", "HIGH")
    ]

    if not critical_high:
        return {
            "fixed":             False,
            "fixed_code":        None,
            "fixes_applied":     0,
            "remaining_findings": req.findings,
            "error":             "No CRITICAL/HIGH findings to fix",
        }

    # Cap at 10 to avoid overwhelming the LLM
    to_fix = critical_high[:10]

    result = await fix_with_llm(req.code_blob, to_fix, max_attempts=2)

    if not result.get("fixed"):
        return {
            "fixed":             False,
            "fixed_code":        None,
            "fixes_applied":     0,
            "remaining_findings": req.findings,
            "error":             result.get("error", "LLM fix failed"),
        }

    fixed_code = result["code"]

    # Re-scan fixed code with Semgrep to find what still remains
    rescan     = run_semgrep_smart_fix(fixed_code)
    remaining  = (
        rescan.get("categorized_findings", {}).get("still_remaining", []) or
        rescan.get("categorized_findings", {}).get("manual_only", [])
    )

    return {
        "fixed":             True,
        "fixed_code":        fixed_code,
        "fixes_applied":     result.get("fixes_applied", 0),
        "remaining_findings": remaining,
        "error":             None,
    }