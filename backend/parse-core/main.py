"""
FastAPI service that exposes:
  GET  /health
  POST /detect          - language detection
  POST /parse           - single-file  CIR (java OR python OR javascript/typescript)
  POST /parse/project   - multi-file   CIR (java OR python OR javascript/typescript)
"""
from __future__ import annotations

import os
import tempfile
from typing import List, Literal, Optional, Dict, Any

from fastapi import FastAPI, HTTPException  # type: ignore
from fastapi.middleware.cors import CORSMiddleware  # type: ignore
from pydantic import BaseModel  # type: ignore

from adapters.java_adapter import JavaAdapter
from adapters.python_adapter import PythonAdapter
from adapters.js_adapter import JSAdapter
from detect import detect_language

# ---------------------------------------------------------
# App + CORS
# ---------------------------------------------------------

app = FastAPI(title="Parser Core Service", version="0.3.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:5173",
        "http://localhost:3000",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Pre-instantiate adapters (they are stateless/reusable)
_java_adapter   = JavaAdapter()
_python_adapter = PythonAdapter()
_js_adapter     = JSAdapter()

# Languages supported for /parse and /parse/project
_SUPPORTED_LANGUAGES = {"java", "python", "javascript", "typescript"}

# File-extension → language mapping used by /parse/project
_EXT_TO_LANG: Dict[str, str] = {
    ".java": "java",
    ".py":   "python",
    ".js":   "javascript",
    ".jsx":  "javascript",
    ".ts":   "typescript",
    ".tsx":  "typescript",
    ".mjs":  "javascript",
    ".cjs":  "javascript",
}


def _get_adapter(lang: str):
    """Return the right adapter for a given language string."""
    if lang == "java":
        return _java_adapter
    if lang == "python":
        return _python_adapter
    if lang in ("javascript", "typescript"):
        return _js_adapter
    return None


# ---------------------------------------------------------
# Health
# ---------------------------------------------------------

@app.get("/health")
def health() -> Dict[str, str]:
    return {"status": "ok"}


# ---------------------------------------------------------
# Language detection
# ---------------------------------------------------------

class DetectRequest(BaseModel):
    code: str


class DetectResponse(BaseModel):
    language: Literal["java", "python", "javascript", "typescript", "unknown"]
    confidence: float
    reason: str


@app.post("/detect", response_model=DetectResponse)
def detect(req: DetectRequest) -> DetectResponse:
    lang, conf, reason = detect_language(req.code or "")
    if lang not in ("java", "python", "javascript", "typescript"):
        lang, conf, reason = "unknown", 0.0, "none"
    return DetectResponse(language=lang, confidence=conf, reason=reason)


# ---------------------------------------------------------
# Single-file parse → CIR
# ---------------------------------------------------------

class ParseRequest(BaseModel):
    code: str
    filename: str
    language: Optional[Literal["java", "python", "javascript", "typescript"]] = None


class ParseResponse(BaseModel):
    language: str
    file_count: int
    cir: Dict[str, Any]


@app.post("/parse", response_model=ParseResponse)
def parse(req: ParseRequest) -> ParseResponse:
    """
    Parse a single code snippet into CIR.
    Supports: java, python, javascript, typescript
    """
    if req.language:
        lang = req.language
    else:
        lang, _conf, _reason = detect_language(req.code, filename=req.filename)

    if lang not in _SUPPORTED_LANGUAGES:
        raise HTTPException(
            status_code=400,
            detail=(
                f"Language '{lang}' is not supported by /parse. "
                f"Supported languages: {sorted(_SUPPORTED_LANGUAGES)}."
            ),
        )

    adapter = _get_adapter(lang)
    graph = adapter.build_cir_graph_for_code(req.code, filename=req.filename)
    cir = graph.to_debug_json()

    return ParseResponse(
        language=lang,
        file_count=1,
        cir=cir,
    )


# ---------------------------------------------------------
# Project-level parse → merged CIR
# ---------------------------------------------------------

class ProjectFile(BaseModel):
    filename: str
    code: str


class ProjectParseRequest(BaseModel):
    language: Literal["java", "python", "javascript", "typescript"] = "java"
    files: List[ProjectFile]


class ProjectParseResponse(BaseModel):
    language: str
    file_count: int
    cir: Dict[str, Any]
    parse_errors: List[Dict[str, str]] = []


@app.post("/parse/project", response_model=ProjectParseResponse)
def parse_project(req: ProjectParseRequest) -> ProjectParseResponse:
    """
    Accept multiple source files and build ONE merged CIR graph.

    For java:                  uses JavaAdapter.build_cir_graph_for_files(...)
    For python:                uses PythonAdapter.build_cir_graph_for_files(...)
    For javascript/typescript: uses JSAdapter.build_cir_graph_for_files(...)

    Cross-file relationships are resolved because all files are parsed
    together into a shared type namespace.
    """
    if req.language not in _SUPPORTED_LANGUAGES:
        raise HTTPException(
            status_code=400,
            detail=(
                f"Language '{req.language}' is not supported for /parse/project. "
                f"Supported: {sorted(_SUPPORTED_LANGUAGES)}."
            ),
        )

    adapter = _get_adapter(req.language)

    # Determine the file extension for the temp files
    _lang_to_ext: Dict[str, str] = {
        "java":       ".java",
        "python":     ".py",
        "javascript": ".js",
        "typescript": ".ts",
    }
    ext = _lang_to_ext.get(req.language, ".js")

    with tempfile.TemporaryDirectory() as td:
        paths: List[str] = []

        for f in req.files:
            fname = f.filename
            # Normalise extension
            if not any(fname.endswith(e) for e in _EXT_TO_LANG):
                fname = fname + ext

            path = os.path.join(td, fname)
            os.makedirs(os.path.dirname(path), exist_ok=True)
            with open(path, "w", encoding="utf-8") as fh:
                fh.write(f.code)
            paths.append(path)

        graph = adapter.build_cir_graph_for_files(paths)
        cir = graph.to_debug_json()
        cir["parse_errors"] = graph.g.graph.get("parse_errors", [])

    return ProjectParseResponse(
        language=req.language,
        file_count=len(req.files),
        cir=cir,
        parse_errors=cir.get("parse_errors", []),
    )