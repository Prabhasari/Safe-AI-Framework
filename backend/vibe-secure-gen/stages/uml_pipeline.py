# backend/vibe-secure-gen/uml_pipeline.py

from __future__ import annotations

import tempfile
from typing import Dict, Any, List

import requests

from .files_from_blob import materialize_files, strip_fence, detect_languages

# Project-level parse endpoint in parser-core
PARSER_PROJECT_URL = "http://127.0.0.1:7070/parse/project"

# Existing UML + render services (rule-based)
UML_URL = "http://127.0.0.1:7080/uml/regex"
RENDER_URL = "http://127.0.0.1:7090/render/svg"

# NEW: AI-based UML service
AI_UML_URL = "http://127.0.0.1:7081/uml/ai"


def _parse_project_to_cir(java_files: Dict[str, str]) -> Dict[str, Any]:
    """
    Given a map: rel_path -> abs_path for .java files,
    call parser-core /parse/project ONCE and get merged CIR.
    """
    print("\n[UML PIPELINE] ===== PARSE PROJECT TO CIR =====")
    print(f"[UML PIPELINE] Java files detected ({len(java_files)}):")
    for rel in java_files.keys():
        print(f"  - {rel}")

    files_payload: List[Dict[str, str]] = []

    for rel, abs_path in java_files.items():
        with open(abs_path, "r", encoding="utf-8") as f:
            code = f.read()
        files_payload.append({"filename": rel, "code": code})

    payload = {"language": "java", "files": files_payload}

    print("[UML PIPELINE] Sending files to parser-core /parse/project ...")
    resp = requests.post(PARSER_PROJECT_URL, json=payload, timeout=40)
    resp.raise_for_status()
    data = resp.json() or {}
    cir = data.get("cir")
    if not cir:
        print("[UML PIPELINE] ERROR: parser-core did not return CIR")
        raise RuntimeError("Project parse did not return CIR")

    nodes = len(cir.get("nodes", []))
    edges = len(cir.get("edges", []))
    print(f"[UML PIPELINE] CIR received from parser-core: {nodes} nodes, {edges} edges")

    return cir


def _cir_to_plantuml_and_svg_rule_based(cir: Dict[str, Any]) -> Dict[str, Any]:
    """
    Given merged CIR, call uml-gen-regex and uml-renderer
    to produce class + package + sequence + component diagrams (PlantUML + SVG).
    This is the existing RULE-BASED path.
    """
    print("\n[UML PIPELINE] ===== CIR -> UML (RULE-BASED) =====")
    out: Dict[str, Any] = {}
    out["validation"] = {}

    for diag_type in ("class", "package", "sequence", "component"):
        print(f"[UML PIPELINE] [RB] Generating {diag_type.upper()} diagram ...")

        # CIR -> PlantUML (regex/rule-based)
        uml_payload = {"cir": cir, "diagram_type": diag_type}
        print(f"[UML PIPELINE] [RB]  -> POST {UML_URL} (diagram_type={diag_type})")
        uml_resp = requests.post(UML_URL, json=uml_payload, timeout=20)
        uml_resp.raise_for_status()

        uml_data = uml_resp.json() or {}
        plantuml = uml_data.get("plantuml", "") or ""
        ok = bool(uml_data.get("ok", True))
        validation_errors = uml_data.get("validation_errors") or []

        out[f"{diag_type}_plantuml"] = plantuml
        out["validation"][diag_type] = {
            "ok": ok,
            "errors": validation_errors,
        }

        print(
            f"[UML PIPELINE] [RB]  <- PlantUML for {diag_type} "
            f"({len(plantuml.splitlines())} lines) | ok={ok} | errors={len(validation_errors)}"
        )

        # If validation failed, do NOT render SVG
        if not ok:
            out[f"{diag_type}_svg"] = None
            print(f"[UML PIPELINE] [RB]  !! Skipping SVG render (validation failed) for {diag_type}")
            continue

        # PlantUML -> SVG (renderer service)
        render_payload = {"plantuml": plantuml}
        print(f"[UML PIPELINE] [RB]  -> POST {RENDER_URL} (render to SVG)")
        render_resp = requests.post(RENDER_URL, json=render_payload, timeout=30)
        render_resp.raise_for_status()
        render_data = render_resp.json() or {}
        svg = render_data.get("svg", "") or ""
        out[f"{diag_type}_svg"] = svg

        print(
            f"[UML PIPELINE] [RB]  <- SVG generated for {diag_type} "
            f"(length ~ {len(svg)} characters)"
        )

    print("[UML PIPELINE] Rule-based UML generation finished.")
    return out


def _cir_to_plantuml_and_svg_ai(cir: Dict[str, Any]) -> Dict[str, Any]:
    """
    Given merged CIR, call the AI UML service + renderer
    to produce class + package + sequence + component diagrams (PlantUML + SVG)
    using the LLM-based approach.
    """
    print("\n[UML PIPELINE] ===== CIR -> UML (AI-BASED) =====")
    out: Dict[str, Any] = {}
    out["validation"] = {}

    for diag_type in ("class", "package", "sequence", "component"):
        print(f"[UML PIPELINE] [AI] Generating {diag_type.upper()} diagram ...")

        # CIR -> PlantUML via AI
        uml_payload = {"cir": cir, "diagram_type": diag_type}
        print(f"[UML PIPELINE] [AI]  -> POST {AI_UML_URL} (diagram_type={diag_type})")
        uml_resp = requests.post(AI_UML_URL, json=uml_payload, timeout=40)
        uml_resp.raise_for_status()

        uml_data = uml_resp.json() or {}
        plantuml = uml_data.get("plantuml", "") or ""
        ok = bool(uml_data.get("ok", True))
        validation_errors = uml_data.get("validation_errors") or []

        out[f"{diag_type}_plantuml"] = plantuml
        out["validation"][diag_type] = {
            "ok": ok,
            "errors": validation_errors,
        }

        print(
            f"[UML PIPELINE] [AI]  <- PlantUML for {diag_type} "
            f"({len(plantuml.splitlines())} lines) | ok={ok} | errors={len(validation_errors)}"
        )

        # If validation failed, do NOT render SVG
        if not ok or not plantuml.strip():
            out[f"{diag_type}_svg"] = None
            print(f"[UML PIPELINE] [AI]  !! Skipping SVG render (validation failed) for {diag_type}")
            continue

        # PlantUML -> SVG (same renderer)
        render_payload = {"plantuml": plantuml}
        print(f"[UML PIPELINE] [AI]  -> POST {RENDER_URL} (render to SVG)")
        render_resp = requests.post(RENDER_URL, json=render_payload, timeout=30)
        render_resp.raise_for_status()
        render_data = render_resp.json() or {}
        svg = render_data.get("svg", "") or ""
        out[f"{diag_type}_svg"] = svg

        print(
            f"[UML PIPELINE] [AI]  <- SVG generated for {diag_type} "
            f"(length ~ {len(svg)} characters)"
        )

    print("[UML PIPELINE] AI-based UML generation finished.")
    return out


def run_uml_pipeline_over_blob(code_blob: str) -> Dict[str, Any]:
    """
    Main entry used by pipeline.py.

    - Takes the LLM-generated code blob (possibly multi-file)
    - Materializes files to a temp folder
    - Filters Java files
    - Sends ALL Java files to /parse/project
    - Gets merged CIR (with cross-file relations)
    - Generates UML diagrams via:
        1) Rule-based generator (regex)
        2) AI-based generator (Gemini)
    - Returns both in one report object.
    """
    print("\n================= UML PIPELINE START =================")
    try:
        fence_lang, _ = strip_fence(code_blob)
        print(f"[UML PIPELINE] Detected fence language: {fence_lang or 'unknown'}")

        with tempfile.TemporaryDirectory() as td:
            # Split LLM blob into physical files (same helper used by Semgrep)
            rel_to_abs = materialize_files(td, code_blob)
            print(f"[UML PIPELINE] Materialized {len(rel_to_abs)} file(s) from LLM output.")
            if rel_to_abs:
                print("[UML PIPELINE] Files:")
                for rel in sorted(rel_to_abs.keys()):
                    print(f"  - {rel}")

            if not rel_to_abs:
                print("[UML PIPELINE] ERROR: No files materialized from LLM output.")
                print("================= UML PIPELINE END (ERROR) =================\n")
                return {
                    "ok": False,
                    "file_count": 0,
                    "error": "No files could be materialized from LLM output.",
                    "class_svg": None,
                    "package_svg": None,
                    "sequence_svg": None,
                    "component_svg": None,
                    "validation": {},
                    "rule_based": {},
                    "ai": {},
                }

            # Language detection is only for info / error messages
            langs = detect_languages(sorted(rel_to_abs.keys()), fence_lang)
            print(
                f"[UML PIPELINE] Detected languages from filenames: "
                f"{', '.join(langs) or 'unknown'}"
            )

            # Only Java files will be used for UML for now
            java_files: Dict[str, str] = {
                rel: abs_path
                for rel, abs_path in rel_to_abs.items()
                if rel.lower().endswith(".java")
            }

            print(f"[UML PIPELINE] Java files selected for UML: {len(java_files)}")
            if not java_files:
                msg = (
                    f"No Java files in generated code "
                    f"(languages detected: {', '.join(langs) or 'unknown'})"
                )
                print(f"[UML PIPELINE] WARNING: {msg}")
                print("================= UML PIPELINE END (NO JAVA) ===============\n")
                return {
                    "ok": False,
                    "file_count": len(rel_to_abs),
                    "error": msg,
                    "class_svg": None,
                    "package_svg": None,
                    "sequence_svg": None,
                    "component_svg": None,
                    "validation": {},
                    "rule_based": {},
                    "ai": {},
                }

            # Project-level parse: this sees types across files
            merged_cir = _parse_project_to_cir(java_files)

            # Rule-based UML
            uml_rule = _cir_to_plantuml_and_svg_rule_based(merged_cir)

            # AI-based UML (non-fatal if it fails)
            try:
                uml_ai = _cir_to_plantuml_and_svg_ai(merged_cir)
            except Exception as e:
                print("================= UML PIPELINE AI ERROR =================")
                print(f"[UML PIPELINE] AI UML error: {type(e).__name__}: {e}")
                uml_ai = {
                    "error": f"AI UML pipeline failed: {type(e).__name__}: {e}",
                    "validation": {},
                }

            print("================= UML PIPELINE END (OK) =====================\n")
            return {
                "ok": True,
                "file_count": len(java_files),
                "error": None,

                "cir": merged_cir,
                
                # Keep existing top-level fields = RULE-BASED (backward compatible)
                "class_svg": uml_rule.get("class_svg"),
                "package_svg": uml_rule.get("package_svg"),
                "sequence_svg": uml_rule.get("sequence_svg"),
                "component_svg": uml_rule.get("component_svg"),
                "validation": uml_rule.get("validation", {}),
                # New extra blocks so you can compare RB vs AI later in frontend / paper
                "rule_based": uml_rule,
                "ai": uml_ai,
            }

    except Exception as e:
        print("================= UML PIPELINE ERROR =================")
        print(f"[UML PIPELINE] Exception: {type(e).__name__}: {e}")
        print("=======================================================\n")
        return {
            "ok": False,
            "file_count": 0,
            "error": f"UML pipeline failed: {type(e).__name__}: {e}",
            "class_svg": None,
            "package_svg": None,
            "sequence_svg": None,
            "component_svg": None,
            "validation": {},
            "rule_based": {},
            "ai": {},
        }
