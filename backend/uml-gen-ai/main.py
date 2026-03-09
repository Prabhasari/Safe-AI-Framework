# backend/uml-gen-ai/main.py

from __future__ import annotations

from typing import Literal, Optional, Dict, Any

import requests
from fastapi import FastAPI, HTTPException  # type: ignore
from fastapi.middleware.cors import CORSMiddleware  # type: ignore
from pydantic import BaseModel  # type: ignore

from llm_client import generate_plantuml_from_context
from summarize_cir import summarize_cir_for_llm
from uml_validate import validate_plantuml

UML_RENDER_URL = "http://127.0.0.1:7090/render/svg"

app = FastAPI(title="AI UML Generator (Gemini + PlantUML)", version="0.3.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:5173",
        "http://localhost:3000",
        "http://127.0.0.1:5173",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


class UMLAIRequest(BaseModel):
    diagram_type: Literal["class", "package", "sequence", "component", "activity"] = "class"
    # Either send CIR (preferred) OR raw code (fallback)
    cir: Optional[Dict[str, Any]] = None
    code: Optional[str] = None


class UMLAIResponse(BaseModel):
    ok: bool = True
    diagram_type: str
    plantuml: str
    svg: Optional[str] = None
    error: Optional[str] = None


@app.get("/health")
def health():
    return {"status": "ok"}


@app.post("/uml/ai", response_model=UMLAIResponse)
def uml_ai(req: UMLAIRequest) -> UMLAIResponse:
    # 1) Build context: prefer CIR summary
    if req.cir:
        context = summarize_cir_for_llm(req.cir, req.diagram_type)
    elif req.code and req.code.strip():
        context = req.code
    else:
        raise HTTPException(status_code=400, detail="Provide either 'cir' or 'code'.")

    # 2) LLM -> PlantUML
    try:
        plantuml = generate_plantuml_from_context(context, req.diagram_type)
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"AI UML generation failed: {type(e).__name__}: {e}",
        ) from e

    # 3) Validate PlantUML (safety)
    ok, errs = validate_plantuml(plantuml)
    if not ok:
        return UMLAIResponse(
            ok=False,
            diagram_type=req.diagram_type,
            plantuml=plantuml,
            svg=None,
            error="; ".join(errs[:10]),
        )

    # 4) Render PlantUML -> SVG
    try:
        r = requests.post(UML_RENDER_URL, json={"plantuml": plantuml}, timeout=200)
        r.raise_for_status()
        svg = (r.json() or {}).get("svg", "")
    except Exception as e:
        return UMLAIResponse(
            ok=False,
            diagram_type=req.diagram_type,
            plantuml=plantuml,
            svg=None,
            error=f"SVG render failed: {type(e).__name__}: {e}",
        )

    return UMLAIResponse(
        ok=True,
        diagram_type=req.diagram_type,
        plantuml=plantuml,
        svg=svg,
        error=None,
    )