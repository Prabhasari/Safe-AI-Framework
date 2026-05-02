"""
backend/vibe-secure-gen/stages/uml_pipeline.py

UML pipeline entry point used by pipeline.py.

- Materializes the LLM-generated code blob into temp files
- Filters to supported languages (java, python)
- Calls /parse/project on parser-core for each language
- Merges all CIRs into one if multiple languages are present
- Generates diagrams via rule-based (uml-gen-regex) and AI-based (uml-gen-ai)
- Returns a unified report

Diagram types: class, package, sequence, component, activity"""

from __future__ import annotations

import datetime
import tempfile
import time
from typing import Dict, Any, List, Optional

import requests

from .files_from_blob import materialize_files, strip_fence, detect_languages

# ──────────────────────────────────────────────────────────────────────────────
#  Service endpoints
# ──────────────────────────────────────────────────────────────────────────────
PARSER_PROJECT_URL = "http://127.0.0.1:7070/parse/project"
UML_REGEX_URL      = "http://127.0.0.1:7080/uml/regex"
AI_UML_URL         = "http://127.0.0.1:7081/uml/ai"
RENDER_URL         = "http://127.0.0.1:7090/render/svg"

_SUPPORTED_LANGUAGES = {"java", "python"}
_EXT_TO_LANG: Dict[str, str] = {".java": "java", ".py": "python"}
_DIAGRAM_TYPES = ("class", "package", "sequence", "component", "activity")

# Diagram-type icons shown in terminal
_DTYPE_ICON = {
    "class":     "◈",
    "package":   "⬡",
    "sequence":  "⟿",
    "component": "⬢",
    "activity":  "⬟",
}


# ──────────────────────────────────────────────────────────────────────────────
#  Terminal pretty-printer  (self-contained, no external deps)
# ──────────────────────────────────────────────────────────────────────────────

class _T:
    """ANSI escape-code constants."""
    RESET   = "\033[0m"
    BOLD    = "\033[1m"
    DIM     = "\033[2m"
    CYAN    = "\033[96m"
    BLUE    = "\033[94m"
    GREEN   = "\033[92m"
    YELLOW  = "\033[93m"
    RED     = "\033[91m"
    MAGENTA = "\033[95m"
    WHITE   = "\033[97m"
    ORANGE  = "\033[38;5;208m"
    GREY    = "\033[38;5;245m"


_W = 72   # total width of the terminal box (characters)


def _bar(char: str = "─", width: int = _W - 4) -> str:
    return char * width


def _tlog(line: str = "") -> None:
    """Print to stdout immediately (no buffering)."""
    print(line, flush=True)


# ── Box / header helpers ──────────────────────────────────────────────────────

def _banner(title: str) -> None:
    """Full-width double-line banner (pipeline start/end)."""
    bar = "═" * (_W - 2)
    inner = f"  {title}"
    pad = _W - 2 - len(inner)
    _tlog(f"\n{_T.CYAN}{_T.BOLD}╔{bar}╗")
    _tlog(f"║{inner}{' ' * pad}║")
    _tlog(f"╚{bar}╝{_T.RESET}")


def _step_header(n: int, total: int, title: str, color: str = _T.BLUE) -> None:
    """Bold step separator with step counter."""
    tag    = f" STEP {n}/{total} "
    bar_l  = "━" * 4
    bar_r  = "━" * (_W - len(tag) - 6)
    _tlog(f"\n{color}{_T.BOLD}{bar_l}{tag}{bar_r}{_T.RESET}")
    _tlog(f"  {_T.BOLD}{color}{title}{_T.RESET}")


def _section(title: str, color: str = _T.BLUE) -> None:
    """Thin sub-section line (used inside a step)."""
    _tlog(f"\n  {color}{_T.BOLD}┌─ {title}{_T.RESET}")


def _divider(color: str = _T.DIM) -> None:
    _tlog(f"  {color}{_bar()}{_T.RESET}")


# ── Line helpers ──────────────────────────────────────────────────────────────

def _ok(label: str, detail: str = "", indent: int = 4) -> None:
    sp = " " * indent
    d = f"  {_T.DIM}{detail}{_T.RESET}" if detail else ""
    _tlog(f"{sp}{_T.GREEN}✔{_T.RESET}  {_T.BOLD}{label}{_T.RESET}{d}")


def _warn(label: str, detail: str = "", indent: int = 4) -> None:
    sp = " " * indent
    d = f"  {_T.DIM}{detail}{_T.RESET}" if detail else ""
    _tlog(f"{sp}{_T.YELLOW}⚠{_T.RESET}  {_T.BOLD}{_T.YELLOW}{label}{_T.RESET}{d}")


def _err(label: str, detail: str = "", indent: int = 4) -> None:
    sp = " " * indent
    d = f"  {_T.DIM}{detail}{_T.RESET}" if detail else ""
    _tlog(f"{sp}{_T.RED}✘{_T.RESET}  {_T.RED}{_T.BOLD}{label}{_T.RESET}{d}")


def _info(label: str, detail: str = "", indent: int = 4) -> None:
    sp = " " * indent
    d = f"  {_T.DIM}{detail}{_T.RESET}" if detail else ""
    _tlog(f"{sp}{_T.CYAN}›{_T.RESET}  {_T.BOLD}{label}{_T.RESET}{d}")


def _sub(label: str, detail: str = "", indent: int = 4) -> None:
    sp = " " * indent
    d = f"  {_T.DIM}{detail}{_T.RESET}" if detail else ""
    _tlog(f"{sp}{_T.DIM}·{_T.RESET}  {label}{d}")


def _file_tree(files: List[str], indent: int = 6) -> None:
    sp = " " * indent
    for i, f in enumerate(files):
        connector = "└─" if i == len(files) - 1 else "├─"
        _tlog(f"{sp}{_T.DIM}{connector}{_T.RESET}  {_T.WHITE}{f}{_T.RESET}")


def _kv_table(rows: List[tuple], indent: int = 6, label_w: int = 22) -> None:
    """Print a two-column key/value table."""
    sp = " " * indent
    _tlog(f"{sp}{_T.CYAN}{'Metric':<{label_w}}{_T.WHITE}{'Value'}{_T.RESET}")
    _tlog(f"{sp}{_T.DIM}{_bar('─', label_w + 10)}{_T.RESET}")
    for k, v, is_total in rows:
        vc = f"{_T.GREEN}{_T.BOLD}" if is_total else f"{_T.WHITE}{_T.BOLD}"
        _tlog(f"{sp}{_T.DIM}·{_T.RESET}  {k:<{label_w - 2}}{vc}{v}{_T.RESET}")


def _summary_box(rows: List[tuple], ok: bool = True) -> None:
    """Final double-line summary table."""
    bar   = "═" * (_W - 2)
    hdr   = "PIPELINE COMPLETE — SUCCESS" if ok else "PIPELINE COMPLETE — FAILED"
    hc    = _T.GREEN if ok else _T.RED
    pad   = _W - 2 - len(hdr)
    left  = pad // 2
    right = pad - left
    _tlog(f"\n{hc}{_T.BOLD}╔{bar}╗")
    _tlog(f"║{' ' * left}{hdr}{' ' * right}║")
    _tlog(f"╠{bar}╣{_T.RESET}")
    for label, value in rows:
        inner = f"  {_T.BOLD}{label:<22}{_T.RESET}  {value}"
        # strip ANSI for length calc
        import re as _re
        clean = _re.sub(r"\033\[[0-9;]*m", "", inner)
        padding = _W - 2 - len(clean)
        _tlog(f"{hc}{_T.BOLD}║{_T.RESET}{inner}{' ' * max(padding, 0)}{hc}{_T.BOLD}║{_T.RESET}")
    _tlog(f"{hc}{_T.BOLD}╚{bar}╝{_T.RESET}\n")


def _dtype_header(dtype: str, color: str) -> None:
    icon = _DTYPE_ICON.get(dtype, "▸")
    _tlog(f"\n    {color}{_T.BOLD}{icon}  {dtype.upper()} DIAGRAM{_T.RESET}")


def _elapsed(t0: float) -> str:
    return f"{time.time() - t0:.2f}s"


# ──────────────────────────────────────────────────────────────────────────────
#  Internal: parse a group of same-language files into CIR
# ──────────────────────────────────────────────────────────────────────────────

def _parse_project_to_cir(
    lang: str,
    files: Dict[str, str],
    step_n: int,
    step_total: int,
) -> Dict[str, Any]:
    _step_header(step_n, step_total,
                 f"CIR GENERATION  ·  parse-core :7070  [{lang.upper()}]",
                 _T.MAGENTA)

    _info("Target endpoint", f"POST {PARSER_PROJECT_URL}")
    _info(f"Sending {len(files)} {lang} file(s)")
    _file_tree(sorted(files.keys()))

    files_payload: List[Dict[str, str]] = []
    for rel, abs_path in files.items():
        with open(abs_path, "r", encoding="utf-8") as f:
            code = f.read()
        files_payload.append({"filename": rel, "code": code})

    payload = {"language": lang, "files": files_payload}

    t0 = time.time()
    resp = requests.post(PARSER_PROJECT_URL, json=payload, timeout=40)
    elapsed = _elapsed(t0)
    resp.raise_for_status()

    data = resp.json() or {}
    cir  = data.get("cir")
    if not cir:
        raise RuntimeError(f"parser-core did not return CIR for language '{lang}'")

    nodes = cir.get("nodes", [])
    edges = cir.get("edges", [])

    # Classify nodes
    type_decl_count  = sum(1 for n in nodes if n.get("kind") == "TypeDecl")
    field_count      = sum(1 for n in nodes if n.get("kind") == "Field")
    method_count     = sum(1 for n in nodes if n.get("kind") == "Method")
    param_count      = sum(1 for n in nodes if n.get("kind") == "Parameter")

    # Classify edges
    inherits_count   = sum(1 for e in edges if e.get("type") == "INHERITS")
    implements_count = sum(1 for e in edges if e.get("type") == "IMPLEMENTS")
    assoc_count      = sum(1 for e in edges if e.get("type") == "ASSOCIATES")
    depends_count    = sum(1 for e in edges if e.get("type") == "DEPENDS_ON")
    calls_count      = sum(1 for e in edges if e.get("type") == "CALLS")
    has_count        = sum(1 for e in edges
                           if e.get("type") in ("HAS_METHOD", "HAS_FIELD", "PARAM_OF"))

    _ok(f"Response received", f"HTTP {resp.status_code}  ·  {elapsed}")
    _tlog("")
    _kv_table([
        ("TypeDecl nodes",   str(type_decl_count),  False),
        ("Field nodes",      str(field_count),       False),
        ("Method nodes",     str(method_count),      False),
        ("Parameter nodes",  str(param_count),       False),
        ("Total nodes",      str(len(nodes)),         True),
        ("INHERITS edges",   str(inherits_count),    False),
        ("IMPLEMENTS edges", str(implements_count),  False),
        ("ASSOCIATES edges", str(assoc_count),       False),
        ("DEPENDS_ON edges", str(depends_count),     False),
        ("CALLS edges",      str(calls_count),       False),
        ("HAS_* edges",      str(has_count),         False),
        ("Total edges",      str(len(edges)),         True),
    ])
    return cir


# ──────────────────────────────────────────────────────────────────────────────
#  Internal: CIR → PlantUML + SVG  (rule-based)
# ──────────────────────────────────────────────────────────────────────────────

def _cir_to_uml_rule_based(
    cir: Dict[str, Any],
    step_n: int,
    step_total: int,
) -> Dict[str, Any]:
    _step_header(step_n, step_total,
                 "RULE-BASED DIAGRAM GENERATION  ·  uml-gen-regex :7080",
                 _T.ORANGE)
    _sub("Method", "Regex / AST static parsing  →  PlantUML  →  SVG")
    _sub("Endpoint", UML_REGEX_URL)

    out: Dict[str, Any] = {"validation": {}}
    success_count = 0

    for dt in _DIAGRAM_TYPES:
        _dtype_header(dt, _T.ORANGE)

        # ── PlantUML generation ───────────────────────────────────────────────
        _info(f"POST /uml/regex", f"diagram_type={dt}  →  {UML_REGEX_URL}")
        t0 = time.time()
        try:
            uml_resp = requests.post(
                UML_REGEX_URL, json={"cir": cir, "diagram_type": dt}, timeout=20
            )
            uml_resp.raise_for_status()
            uml_data = uml_resp.json() or {}
        except Exception as exc:
            _err("PlantUML generation failed",
                 f"{type(exc).__name__}: {exc}  ·  {_elapsed(t0)}")
            out[f"{dt}_plantuml"] = ""
            out[f"{dt}_svg"]      = None
            out["validation"][dt] = {"ok": False, "errors": [str(exc)]}
            _divider()
            continue

        plantuml = uml_data.get("plantuml", "") or ""
        ok_flag  = bool(uml_data.get("ok", True))
        errs     = uml_data.get("validation_errors") or []
        gen_time = _elapsed(t0)

        out[f"{dt}_plantuml"]    = plantuml
        out["validation"][dt]   = {"ok": ok_flag, "errors": errs}

        lines_count = plantuml.count("\n") + 1 if plantuml.strip() else 0

        if not ok_flag:
            _warn("PlantUML generated but validation failed",
                  f"{gen_time}  ·  {len(errs)} error(s)")
            for e_msg in errs[:3]:
                _sub(f"  {e_msg}", indent=8)
            out[f"{dt}_svg"] = None
            _divider()
            continue

        _ok("PlantUML generated",
            f"{lines_count} lines  ·  validation passed  ·  {gen_time}")

        # ── SVG render ────────────────────────────────────────────────────────
        _info("POST /render/svg", f"uml-renderer :7090  →  {RENDER_URL}")
        t1 = time.time()
        try:
            render_resp = requests.post(
                RENDER_URL, json={"plantuml": plantuml}, timeout=30
            )
            render_resp.raise_for_status()
            svg      = (render_resp.json() or {}).get("svg", "") or ""
            svg_time = _elapsed(t1)
            out[f"{dt}_svg"] = svg
            success_count += 1
            _ok("SVG rendered",
                f"{len(svg):,} chars  ·  {svg_time}")
        except Exception as exc:
            _err("SVG render failed",
                 f"{type(exc).__name__}: {exc}  ·  {_elapsed(t1)}")
            out[f"{dt}_svg"]      = None
            out["validation"][dt] = {
                "ok": False, "errors": [f"SVG render failed: {exc}"]
            }

        _divider()

    _tlog(f"\n    {_T.DIM}Rule-based summary: "
          f"{_T.RESET}{_T.BOLD}{_T.GREEN}{success_count}{_T.RESET}"
          f"{_T.DIM}/{len(_DIAGRAM_TYPES)} diagrams rendered successfully{_T.RESET}")
    out["_success_count"] = success_count
    return out


# ──────────────────────────────────────────────────────────────────────────────
#  Internal: CIR → PlantUML + SVG  (AI-based)
# ──────────────────────────────────────────────────────────────────────────────

def _cir_to_uml_ai(
    cir: Dict[str, Any],
    step_n: int,
    step_total: int,
) -> Dict[str, Any]:
    _step_header(step_n, step_total,
                 "AI-BASED DIAGRAM GENERATION  ·  uml-gen-ai :7081",
                 _T.MAGENTA)
    _sub("Method", "LLM semantic inference  →  PlantUML  →  SVG")
    _sub("Endpoint", AI_UML_URL)

    out: Dict[str, Any] = {"validation": {}}
    success_count = 0

    for dt in _DIAGRAM_TYPES:
        _dtype_header(dt, _T.MAGENTA)

        # ── PlantUML generation ───────────────────────────────────────────────
        _info("POST /uml/ai", f"diagram_type={dt}  →  {AI_UML_URL}")
        t0 = time.time()
        try:
            uml_resp = requests.post(
                AI_UML_URL, json={"cir": cir, "diagram_type": dt}, timeout=40
            )
            uml_resp.raise_for_status()
            uml_data = uml_resp.json() or {}
        except Exception as exc:
            _err("LLM inference failed",
                 f"{type(exc).__name__}: {exc}  ·  {_elapsed(t0)}")
            out[f"{dt}_plantuml"] = ""
            out[f"{dt}_svg"]      = None
            out["validation"][dt] = {"ok": False, "errors": [str(exc)]}
            _divider()
            continue

        plantuml = uml_data.get("plantuml", "") or ""
        ok_flag  = bool(uml_data.get("ok", True))
        errs     = uml_data.get("validation_errors") or []
        gen_time = _elapsed(t0)

        out[f"{dt}_plantuml"]   = plantuml
        out["validation"][dt]  = {"ok": ok_flag, "errors": errs}

        lines_count = plantuml.count("\n") + 1 if plantuml.strip() else 0

        if not plantuml.strip():
            _warn("LLM output empty",
                  f"{gen_time}  ·  {len(errs)} error(s)")
            for e_msg in errs[:3]:
                _sub(f"  {e_msg}", indent=8)
            out[f"{dt}_svg"] = None
            _divider()
            continue

        # Log a soft warning if ok_flag is False but we still have content
        if not ok_flag:
            _warn("LLM validation warnings (attempting render anyway)",
                  f"{gen_time}  ·  {len(errs)} error(s)")
            for e_msg in errs[:3]:
                _sub(f"  {e_msg}", indent=8)
        else:
            _ok("PlantUML generated",
                f"{lines_count} lines  ·  LLM inference  ·  {gen_time}")

        # ── SVG render ────────────────────────────────────────────────────────
        _info("POST /render/svg", f"uml-renderer :7090  →  {RENDER_URL}")
        t1 = time.time()
        try:
            render_resp = requests.post(
                RENDER_URL, json={"plantuml": plantuml}, timeout=30
            )
            render_resp.raise_for_status()
            svg      = (render_resp.json() or {}).get("svg", "") or ""
            svg_time = _elapsed(t1)
            out[f"{dt}_svg"] = svg
            success_count += 1
            _ok("SVG rendered", f"{len(svg):,} chars  ·  {svg_time}")
        except Exception as exc:
            _err("SVG render failed",
                 f"{type(exc).__name__}: {exc}  ·  {_elapsed(t1)}")
            out[f"{dt}_svg"]      = None
            out["validation"][dt] = {
                "ok": False, "errors": [f"SVG render failed: {exc}"]
            }

        _divider()

    _tlog(f"\n    {_T.DIM}AI-based summary: "
          f"{_T.RESET}{_T.BOLD}{_T.MAGENTA}{success_count}{_T.RESET}"
          f"{_T.DIM}/{len(_DIAGRAM_TYPES)} diagrams rendered successfully{_T.RESET}")
    out["_success_count"] = success_count
    return out


# ──────────────────────────────────────────────────────────────────────────────
#  Internal: merge multiple CIR graphs into one (node/edge union)
# ──────────────────────────────────────────────────────────────────────────────

def _merge_cirs(cirs: List[Dict[str, Any]]) -> Dict[str, Any]:
    if len(cirs) == 1:
        return cirs[0]

    all_nodes:    List[Dict[str, Any]] = []
    all_edges:    List[Dict[str, Any]] = []
    seen_node_ids: set = set()
    seen_edges:    set = set()

    for cir in cirs:
        for n in cir.get("nodes", []):
            nid = n.get("id")
            if nid and nid not in seen_node_ids:
                seen_node_ids.add(nid)
                all_nodes.append(n)
        for e in cir.get("edges", []):
            key = (e.get("src"), e.get("dst"), e.get("type"))
            if key not in seen_edges:
                seen_edges.add(key)
                all_edges.append(e)

    return {"nodes": all_nodes, "edges": all_edges}


# ──────────────────────────────────────────────────────────────────────────────
#  Public entry point
# ──────────────────────────────────────────────────────────────────────────────

def run_uml_pipeline_over_blob(code_blob: str) -> Dict[str, Any]:
    """
    Main entry used by pipeline.py.

    Stages
    ------
    1. File materialisation
    2. Language grouping & filter
    3. CIR generation   (one sub-step per language group)
    4. Rule-based UML generation  (uml-gen-regex + uml-renderer)
    5. AI-based UML generation    (uml-gen-ai + uml-renderer)
    Final summary table"""

    pipeline_t0 = time.time()
    started_at  = datetime.datetime.now().strftime("%H:%M:%S")

    # ── Banner ────────────────────────────────────────────────────────────────
    _banner("  UML VISUALIZATION PIPELINE  ·  vibe-secure-gen")
    _tlog(f"  {_T.DIM}Started {started_at}  ·  dual-mode (regex + AI)"
          f"  ·  services: parse-core:7070  regex:7080  ai:7081  renderer:7090{_T.RESET}")

    try:
        # ── STEP 1 : File materialisation ─────────────────────────────────────
        _step_header(1, 5, "FILE MATERIALISATION", _T.BLUE)

        fence_lang, _ = strip_fence(code_blob)
        _info("Fence language detected", fence_lang or "none")

        with tempfile.TemporaryDirectory() as td:
            t0 = time.time()
            rel_to_abs = materialize_files(td, code_blob)
            _ok(f"Materialised {len(rel_to_abs)} file(s) from code blob",
                f"{_elapsed(t0)}")

            if not rel_to_abs:
                return _error_result("No files could be materialised from LLM output.")

            _file_tree(sorted(rel_to_abs.keys()))

            langs = detect_languages(sorted(rel_to_abs.keys()), fence_lang)
            _info("Languages detected", ", ".join(langs) or "unknown")

            # ── STEP 2 : Language grouping & filter ───────────────────────────
            _step_header(2, 5, "LANGUAGE GROUPING  &  FILTER", _T.BLUE)

            lang_files: Dict[str, Dict[str, str]] = {}
            for rel, abs_path in rel_to_abs.items():
                for ext, lang_name in _EXT_TO_LANG.items():
                    if rel.lower().endswith(ext):
                        lang_files.setdefault(lang_name, {})[rel] = abs_path
                        break

            supported_files = {
                lang: files
                for lang, files in lang_files.items()
                if lang in _SUPPORTED_LANGUAGES and files
            }

            java_n    = len(lang_files.get("java",   {}))
            python_n  = len(lang_files.get("python", {}))
            skipped_n = len(rel_to_abs) - java_n - python_n

            _ok("File classification complete",
                f"{python_n} Python  ·  {java_n} Java"
                + (f"  ·  {skipped_n} skipped (unsupported)" if skipped_n else ""))

            if not supported_files:
                detected_str = ", ".join(langs) or "unknown"
                return _error_result(
                    f"No supported language files found "
                    f"(detected: {detected_str}; supported: {sorted(_SUPPORTED_LANGUAGES)}).",
                    file_count=len(rel_to_abs),
                )

            for lang_name, files in supported_files.items():
                _sub(f"→ {lang_name.capitalize()} queue",
                     f"{len(files)} file(s)  →  parse-core :7070")

            # ── STEP 3 : CIR generation (per language) ────────────────────────
            cir_parts: List[Dict[str, Any]] = []
            total_files = 0
            lang_list = sorted(supported_files.keys())

            for i, lang_name in enumerate(lang_list):
                cir = _parse_project_to_cir(
                    lang_name,
                    supported_files[lang_name],
                    step_n=3,
                    step_total=5,
                )
                cir_parts.append(cir)
                total_files += len(supported_files[lang_name])

            merged_cir = _merge_cirs(cir_parts)

            if len(cir_parts) > 1:
                _tlog(f"\n  {_T.CYAN}{_T.BOLD}◉  Merged {len(cir_parts)} CIR graphs{_T.RESET}"
                      f"  {_T.DIM}→  {len(merged_cir.get('nodes',[]))} nodes"
                      f"  ·  {len(merged_cir.get('edges',[]))} edges{_T.RESET}")

            # ── STEP 4 : Rule-based UML ────────────────────────────────────────
            uml_rule = _cir_to_uml_rule_based(merged_cir, step_n=4, step_total=5)

            # ── STEP 5 : AI-based UML ─────────────────────────────────────────
            try:
                uml_ai = _cir_to_uml_ai(merged_cir, step_n=5, step_total=5)
            except Exception as exc:
                _err("AI UML pipeline raised an unhandled exception",
                     f"{type(exc).__name__}: {exc}")
                uml_ai = {
                    "error":      f"AI UML pipeline failed: {type(exc).__name__}: {exc}",
                    "validation": {},
                    "_success_count": 0,
                }

            # ── Summary ───────────────────────────────────────────────────────
            rb_ok = uml_rule.get("_success_count", 0)
            ai_ok = uml_ai.get("_success_count",   0)
            total_duration = _elapsed(pipeline_t0)
            all_ok = (rb_ok + ai_ok) > 0

            cir_nodes = len(merged_cir.get("nodes", []))
            cir_edges = len(merged_cir.get("edges", []))

            _summary_box([
                ("Status",
                 f"{_T.GREEN}✔  SUCCESS{_T.RESET}" if all_ok
                 else f"{_T.YELLOW}⚠  PARTIAL{_T.RESET}"),
                ("Files processed",
                 f"{total_files}  ({', '.join(lang_list)})"),
                ("CIR graph",
                 f"{cir_nodes} nodes  ·  {cir_edges} edges"),
                ("Diagram types",
                 ", ".join(dt.capitalize() for dt in _DIAGRAM_TYPES)),
                ("Rule-based SVGs",
                 f"{rb_ok}/{len(_DIAGRAM_TYPES)}  generated"),
                ("AI-based SVGs",
                 f"{ai_ok}/{len(_DIAGRAM_TYPES)}  generated"),
                ("Total duration",
                 total_duration),
            ], ok=all_ok)

            # ── Build and return final result ──────────────────────────────────
            return {
                "ok":            True,
                "file_count":    total_files,
                "error":         None,

                # ── Rule-based SVGs (backward-compatible) ──────────────────
                "class_svg":     uml_rule.get("class_svg"),
                "package_svg":   uml_rule.get("package_svg"),
                "sequence_svg":  uml_rule.get("sequence_svg"),
                "component_svg": uml_rule.get("component_svg"),
                "activity_svg":  uml_rule.get("activity_svg"),

                # ── AI-generated SVGs
                "ai_class_svg":     uml_ai.get("class_svg"),
                "ai_package_svg":   uml_ai.get("package_svg"),
                "ai_sequence_svg":  uml_ai.get("sequence_svg"),
                "ai_component_svg": uml_ai.get("component_svg"),
                "ai_activity_svg":  uml_ai.get("activity_svg"),

                # ── PlantUML sources for both methods ──────────────────────
                "ai_class_plantuml":     uml_ai.get("class_plantuml"),
                "ai_package_plantuml":   uml_ai.get("package_plantuml"),
                "ai_sequence_plantuml":  uml_ai.get("sequence_plantuml"),
                "ai_component_plantuml": uml_ai.get("component_plantuml"),
                "ai_activity_plantuml":  uml_ai.get("activity_plantuml"),

                # ── Validation maps ────────────────────────────────────────
                "validation":    uml_rule.get("validation", {}),
                "ai_validation": uml_ai.get("validation", {}),

                # ── Raw sub-results (for debugging / future use) ───────────
                "rule_based":    uml_rule,
                "ai":            uml_ai,
            }

    except Exception as exc:
        _err("Unhandled exception in UML pipeline",
             f"{type(exc).__name__}: {exc}")
        return _error_result(f"UML pipeline failed: {type(exc).__name__}: {exc}")


# ──────────────────────────────────────────────────────────────────────────────
#  Helpers
# ──────────────────────────────────────────────────────────────────────────────

def _error_result(msg: str, file_count: int = 0) -> Dict[str, Any]:
    _err(msg)
    _summary_box([
        ("Status",         f"{_T.RED}✘  ERROR{_T.RESET}"),
        ("Message",        msg[:55] + ("…" if len(msg) > 55 else "")),
        ("Files processed", str(file_count)),
    ], ok=False)
    return {
        "ok":            False,
        "file_count":    file_count,
        "error":         msg,

        # Rule-based
        "class_svg":     None,
        "package_svg":   None,
        "sequence_svg":  None,
        "component_svg": None,
        "activity_svg":  None,

        "ai_class_svg":     None,
        "ai_package_svg":   None,
        "ai_sequence_svg":  None,
        "ai_component_svg": None,
        "ai_activity_svg":  None,

        "ai_class_plantuml":     None,
        "ai_package_plantuml":   None,
        "ai_sequence_plantuml":  None,
        "ai_component_plantuml": None,
        "ai_activity_plantuml":  None,

        "validation":    {},
        "ai_validation": {},
        "rule_based":    {},
        "ai":            {},
    }