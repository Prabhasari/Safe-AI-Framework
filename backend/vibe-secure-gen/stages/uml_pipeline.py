# backend/vibe-secure-gen/stages/uml_pipeline.py

import os
import tempfile
from typing import Dict, Any, List

import requests

from .files_from_blob import materialize_files, strip_fence, detect_languages

# New project-level parse endpoint in parser-core
PARSER_PROJECT_URL = "http://127.0.0.1:7070/parse/project"

# Existing UML + render services
UML_URL = "http://127.0.0.1:7080/uml/regex"
RENDER_URL = "http://127.0.0.1:7090/render/svg"


def _parse_project_to_cir(java_files: Dict[str, str]) -> Dict[str, Any]:
    """
    Given a map: rel_path -> abs_path for .java files,
    call parser-core /parse/project ONCE and get merged CIR.
    """
    files_payload: List[Dict[str, str]] = []

    for rel, abs_path in java_files.items():
        with open(abs_path, "r", encoding="utf-8") as f:
            code = f.read()
        files_payload.append(
            {
                "filename": rel,
                "code": code,
            }
        )

    payload = {
        "language": "java",
        "files": files_payload,
    }

    resp = requests.post(PARSER_PROJECT_URL, json=payload, timeout=40)
    resp.raise_for_status()
    data = resp.json()
    cir = data.get("cir")
    if not cir:
        raise RuntimeError("Project parse did not return CIR")
    return cir


def _cir_to_plantuml_and_svg(cir: Dict[str, Any]) -> Dict[str, Any]:
    """
    Given merged CIR, call uml-gen-regex and uml-renderer
    to produce class + package diagrams (PlantUML + SVG).
    """
    out: Dict[str, Any] = {}

    for diag_type in ("class", "package"):
        # CIR -> PlantUML
        uml_payload = {"cir": cir, "diagram_type": diag_type}
        uml_resp = requests.post(UML_URL, json=uml_payload, timeout=20)
        uml_resp.raise_for_status()
        uml_data = uml_resp.json()
        plantuml = uml_data.get("plantuml", "")
        out[f"{diag_type}_plantuml"] = plantuml

        # PlantUML -> SVG
        render_payload = {"plantuml": plantuml}
        render_resp = requests.post(RENDER_URL, json=render_payload, timeout=30)
        render_resp.raise_for_status()
        render_data = render_resp.json()
        svg = render_data.get("svg", "")
        out[f"{diag_type}_svg"] = svg

    return out


def run_uml_pipeline_over_blob(code_blob: str) -> Dict[str, Any]:
    """
    Main entry used by pipeline.py.

    - Takes the LLM-generated code blob (possibly multi-file)
    - Materializes files to a temp folder
    - Filters Java files
    - Sends ALL Java files to /parse/project
    - Gets merged CIR (with cross-file relations)
    - Generates class + package SVG diagrams
    """
    try:
        fence_lang, _ = strip_fence(code_blob)

        with tempfile.TemporaryDirectory() as td:
            # Split LLM blob into physical files (same helper used by Semgrep)
            rel_to_abs = materialize_files(td, code_blob)
            if not rel_to_abs:
                return {
                    "ok": False,
                    "file_count": 0,
                    "error": "No files could be materialized from LLM output.",
                    "class_svg": None,
                    "package_svg": None,
                }

            # Language detection is only for info / error messages
            langs = detect_languages(sorted(rel_to_abs.keys()), fence_lang)

            # Only Java files will be used for UML for now
            java_files: Dict[str, str] = {
                rel: abs_path
                for rel, abs_path in rel_to_abs.items()
                if rel.lower().endswith(".java")
            }

            if not java_files:
                return {
                    "ok": False,
                    "file_count": len(rel_to_abs),
                    "error": f"No Java files in generated code (languages detected: {', '.join(langs) or 'unknown'})",
                    "class_svg": None,
                    "package_svg": None,
                }

            # Project-level parse: this sees types across files
            merged_cir = _parse_project_to_cir(java_files)

            # CIR -> PlantUML + SVG
            uml_out = _cir_to_plantuml_and_svg(merged_cir)

            return {
                "ok": True,
                "file_count": len(java_files),
                "error": None,
                "class_svg": uml_out.get("class_svg"),
                "package_svg": uml_out.get("package_svg"),
            }

    except Exception as e:
        return {
            "ok": False,
            "file_count": 0,
            "error": f"UML pipeline failed: {type(e).__name__}: {e}",
            "class_svg": None,
            "package_svg": None,
        }
