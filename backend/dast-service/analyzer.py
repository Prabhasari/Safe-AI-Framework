# backend/dast-service/analyzer.py

"""
Orchestrates Layer 1 (pattern scan) + Layer 2 (Docker sandbox).
Called by main.py and also by vibe-secure-gen/stages/dast_client.py
"""

from __future__ import annotations

import re
import tempfile
from typing import Any, Dict, List

from scanner import run_pattern_scan
from sandbox import (
    analyze_sandbox_output,
    execute_in_sandbox,
    is_docker_available,
    SANDBOX_CONFIG,
)

# ─────────────────────────────────────────────────────────────────────────────
#  Simple language + code extractor (no dependency on vibe-secure-gen)
# ─────────────────────────────────────────────────────────────────────────────

_FENCE_RE = re.compile(r"^```([a-zA-Z0-9_+-]*)\s*\n([\s\S]*?)\n```$", re.M)

_EXT_MAP = {
    ".py":  "python",
    ".js":  "javascript",
    ".ts":  "typescript",
    ".go":  "go",
    ".java":"java",
    ".rb":  "ruby",
    ".php": "php",
    ".cs":  "csharp",
}

_LANG_ALIAS = {
    "js": "javascript", "ts": "typescript",
    "py": "python",     "golang": "go",
}


def _strip_fence(blob: str):
    """Return (fence_lang, inner_code)."""
    m = _FENCE_RE.search(blob.strip())
    if not m:
        return "", blob.strip()
    lang  = (m.group(1) or "").strip().lower()
    inner = (m.group(2) or "").strip()
    return lang, inner


def _detect_lang(fence_lang: str, hint: str) -> List[str]:
    """Best-effort language detection from fence tag and hint."""
    langs = set()
    for raw in (fence_lang, hint):
        normalized = _LANG_ALIAS.get(raw.lower(), raw.lower())
        if normalized:
            langs.add(normalized)
    return sorted(langs)


# ─────────────────────────────────────────────────────────────────────────────
#  Main entry point
# ─────────────────────────────────────────────────────────────────────────────

def run_dast(code_blob: str, language_hint: str = "") -> Dict[str, Any]:
    """
    Full DAST analysis:
      1. Pattern scan  (always)
      2. Docker sandbox (if available + language supported)

    Returns complete result dict.
    """
    print("  🔬 DAST: starting analysis...")

    fence_lang, raw_inner = _strip_fence(code_blob)
    langs = _detect_lang(fence_lang, language_hint)
    print(f"   DAST: languages detected → {langs or ['unknown']}")

    # ── Layer 1: pattern scan ──────────────────────────────────────────────
    pattern_findings = run_pattern_scan(raw_inner)
    print(f"   DAST: pattern scan → {len(pattern_findings)} finding(s)")

    # ── Layer 2: Docker sandbox ────────────────────────────────────────────
    docker_available   = is_docker_available()
    execution_results: List[Dict[str, Any]] = []
    runtime_findings:  List[Dict[str, Any]] = []

    if docker_available:
        print("  🐳 DAST: Docker available — running sandbox execution...")
        for lang in langs:
            if lang in SANDBOX_CONFIG:
                print(f"     → executing {lang} sandbox...")
                exec_result = execute_in_sandbox(raw_inner, lang, timeout=15)
                exec_result["lang"] = lang
                execution_results.append(exec_result)

                if not exec_result.get("skipped"):
                    rt = analyze_sandbox_output(exec_result)
                    runtime_findings.extend(rt)
                    print(
                        f"     → {lang}: exit={exec_result.get('exit_code')} "
                        f"| runtime findings={len(rt)}"
                    )
    else:
        print("  ⚠️  DAST: Docker unavailable — pattern scan only")

    # ── Merge & deduplicate ────────────────────────────────────────────────
    all_findings   = pattern_findings + runtime_findings
    seen: set      = set()
    unique: List[Dict[str, Any]] = []
    for f in all_findings:
        key = (f["check_id"], f.get("line") or 0, f.get("source", ""))
        if key not in seen:
            seen.add(key)
            unique.append(f)

    # ── Summary ────────────────────────────────────────────────────────────
    sev: Dict[str, int] = {"CRITICAL": 0, "HIGH": 0, "MEDIUM": 0, "LOW": 0}
    for f in unique:
        s = f.get("severity", "LOW").upper()
        sev[s] = sev.get(s, 0) + 1

    owasp_coverage = sorted({f["owasp"] for f in unique if f.get("owasp")})

    print(
        f"  ✔ DAST complete: {len(unique)} finding(s) — "
        f"CRITICAL={sev['CRITICAL']} HIGH={sev['HIGH']} MEDIUM={sev['MEDIUM']}"
    )

    return {
        "ok":                True,
        "docker_available":  docker_available,
        "findings":          unique,
        "pattern_findings":  pattern_findings,
        "runtime_findings":  runtime_findings,
        "execution_results": execution_results,
        "languages":         langs,
        "summary": {
            "total":           len(unique),
            "critical":        sev["CRITICAL"],
            "high":            sev["HIGH"],
            "medium":          sev["MEDIUM"],
            "low":             sev["LOW"],
            "docker_executed": docker_available and len(execution_results) > 0,
            "owasp_coverage":  owasp_coverage,
        },
    }