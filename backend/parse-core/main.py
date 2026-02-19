from __future__ import annotations

import os
import tempfile
from typing import List, Literal, Optional, Dict, Any

from fastapi import FastAPI, HTTPException # type: ignore
from fastapi.middleware.cors import CORSMiddleware # type: ignore
from pydantic import BaseModel # type: ignore

from adapters.java_adapter import JavaAdapter
from detect import detect_language

# ---------------------------------------------------------
# FastAPI app + CORS
# ---------------------------------------------------------

app = FastAPI(title="Parser Core Service", version="0.1.0")

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


# ---------------------------------------------------------
# Health check
# ---------------------------------------------------------

@app.get("/health")
def health() -> Dict[str, str]:
    return {"status": "ok"}


# ---------------------------------------------------------
# Language detection (very simple heuristic)
# ---------------------------------------------------------

class DetectRequest(BaseModel):
    code: str

class DetectResponse(BaseModel):
    language: Literal["java", "python", "javascript", "typescript", "unknown"]
    confidence: float
    reason: str

# def _detect_language_from_code(code: str) -> str:
#     """Very lightweight heuristic language detector for code."""
#     snippet = code.lower()

#     # Java
#     if "package " in snippet or "public class " in snippet or "import java." in snippet:
#         return "java"

#     # Python
#     if "def " in snippet or "import " in snippet and "{" not in snippet and ";" not in snippet:
#         return "python"

#     # JavaScript / TS
#     if "function " in snippet or "=> {" in snippet or "import {" in snippet and " from " in snippet:
#         return "javascript"

#     return "unknown"

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
    # optional language; if not given, we try to detect
    language: Optional[Literal["java", "python", "javascript","typesript"]] = None


class ParseResponse(BaseModel):
    language: str
    file_count: int
    cir: Dict[str, Any]


@app.post("/parse", response_model=ParseResponse)
def parse(req: ParseRequest) -> ParseResponse:
    """
    Parse a single code snippet into CIR.
    For now, only Java is supported.
    """
    if req.language:
        lang = req.language
        conf, reason = 1.0, "explicit"
    else:
        lang, conf, reason = detect_language(req.code, filename=req.filename)


    if lang != "java":
        raise HTTPException(
            status_code=400,
            detail=f"Only 'java' is supported by /parse at the moment (detected: {lang}).",
        )

    adapter = JavaAdapter()
    # JavaAdapter is expected to work on a code string
    graph = adapter.build_cir_graph_for_code(req.code, filename=req.filename)  # type: ignore[arg-type]
    cir = graph.to_debug_json()

    return ParseResponse(
        language="java",
        file_count=1,
        cir=cir,
    )


# ---------------------------------------------------------
# Project-level parse (multiple Java files) → merged CIR
# ---------------------------------------------------------

class ProjectFile(BaseModel):
    filename: str
    code: str


class ProjectParseRequest(BaseModel):
    # we only support Java for project parse right now
    language: Literal["java"] = "java"
    files: List[ProjectFile]


class ProjectParseResponse(BaseModel):
    language: str
    file_count: int
    cir: Dict[str, Any]
    parse_errors: List[Dict[str, str]] = []


@app.post("/parse/project", response_model=ProjectParseResponse)
def parse_project(req: ProjectParseRequest) -> ProjectParseResponse:
    """
    Accept multiple Java files and build ONE merged CIR graph
    using JavaAdapter.build_cir_graph_for_files(...).

    This is what allows cross-file relationships like
      LibraryService  -->  Book
      LibraryApp      -->  LibraryService
    to be captured in CIR.
    """
    if req.language != "java":
        raise HTTPException(
            status_code=400,
            detail="Only 'java' is supported for /parse/project at the moment.",
        )

    adapter = JavaAdapter()

    # JavaAdapter.build_cir_graph_for_files expects file paths,
    # so we materialize each file under a temporary directory.
    with tempfile.TemporaryDirectory() as td:
        paths: List[str] = []

        for f in req.files:
            path = os.path.join(td, f.filename)
            os.makedirs(os.path.dirname(path), exist_ok=True)
            with open(path, "w", encoding="utf-8") as fh:
                fh.write(f.code)
            paths.append(path)

        graph = adapter.build_cir_graph_for_files(paths)  # type: ignore[arg-type]
        cir = graph.to_debug_json()
        cir["parse_errors"] = graph.g.graph.get("parse_errors", [])

    return ProjectParseResponse(
        language="java",
        file_count=len(req.files),
        cir=cir,
        parse_errors=cir.get("parse_errors", []),
    )


# # ---------------------------------------------------------
# # Local run (optional)
# # ---------------------------------------------------------

# if __name__ == "__main__":
#     import uvicorn

#     uvicorn.run(
#         "main:app",
#         host="127.0.0.1",
#         port=7070,
#         reload=True,
#     )

