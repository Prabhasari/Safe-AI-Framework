# backend/dast-service/analyzer.py

"""
Orchestrates Layer 1 (pattern scan) + Layer 2 (Docker sandbox).

Supported sandbox languages: python, javascript, typescript, go, java,
                              php, ruby, csharp, rust

Compile-based languages:
  - Java   uses eclipse-temurin:17-jdk-alpine : javac (compile) + java (run)
  - C#     uses mono:latest                   : mcs   (compile) + mono (run)
  - Rust   uses rust:1.75-alpine              : rustc (compile) + run binary

Direct-run languages:
  - Python     python:3.11-alpine
  - JavaScript node:18-alpine
  - TypeScript node:18-alpine
  - Go         golang:1.21-alpine   (go run compiles internally)
  - PHP        php:8.2-cli-alpine
  - Ruby       ruby:3.2-alpine

TIMEOUT GUIDE:
  - Java   90s  : javac compile + JVM startup + run (first-run image pull ~30s)
  - C#     90s  : mcs compile + Mono startup + run
  - Rust   90s  : rustc compile (slow first run) + binary execution
  - Go     30s  : go run compiles internally
  - Others 15s  : direct script execution, no compile step

NOTE ON LLM FIX:
  Layer 3 (LLM fix) has been intentionally removed from this service.
  Reason: pipeline.py Stage 6 already calls fix_with_llm() after receiving
  the DAST findings. Running it here too causes:
    - Duplicate LLM fix attempts printing AFTER the pipeline summary
    - Extra /api/dast-fix POST requests appearing in the terminal after 200 OK
    - Double LLM API quota usage
  The fix is now fully delegated to pipeline.py Stage 6.
"""

from __future__ import annotations

import re
import time
from typing import Any, Dict, List

from scanner import run_pattern_scan
from sandbox import (
    analyze_sandbox_output,
    execute_in_sandbox,
    is_docker_available,
    SANDBOX_CONFIG,
)

# ─────────────────────────────────────────────────────────────────────────────
#  Language detection
# ─────────────────────────────────────────────────────────────────────────────

_FENCE_RE = re.compile(r"^```([a-zA-Z0-9_+-]*)\s*\n([\s\S]*?)\n```$", re.M)

_LANG_ALIAS = {
    "js":     "javascript",
    "ts":     "typescript",
    "py":     "python",
    "golang": "go",
    "cs":     "csharp",
    "rs":     "rust",
    "rb":     "ruby",
}

_SANDBOXABLE = set(SANDBOX_CONFIG.keys())

# ── Per-language sandbox timeouts (seconds) ───────────────────────────────
# Compile-based languages get 90s to cover: image pull (first run) +
# compiler startup + actual compilation + program execution.
_SANDBOX_TIMEOUTS: Dict[str, int] = {
    # Compiled languages — need time for compiler + runtime
    "java":       90,   # javac compile + JVM startup + run
    "csharp":     90,   # mcs compile + Mono startup + run
    "rust":       90,   # rustc compile (slow on first run) + binary run
    # Go compiles internally but go run is fast
    "go":         30,
    # Interpreted — direct execution, no compile step
    "python":     15,
    "javascript": 15,
    "typescript": 15,
    "php":        15,
    "ruby":       15,
}

# Human-readable names for compiled languages (used in log messages)
_COMPILE_LANG_NAMES: Dict[str, str] = {
    "java":   "Java",
    "csharp": "C#",
    "rust":   "Rust",
}


def _strip_fence(blob: str):
    m = _FENCE_RE.search(blob.strip())
    if not m:
        return "", blob.strip()
    return (m.group(1) or "").strip().lower(), (m.group(2) or "").strip()


def _detect_lang(fence_lang: str, hint: str) -> List[str]:
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
    DAST analysis — two layers only:
      1. Pattern scan  (always, all languages)
      2. Docker sandbox (per-language timeout)

    Layer 3 (LLM fix) is intentionally skipped here.
    It is handled by pipeline.py Stage 6 after this service returns its findings.
    """
    t_total = time.monotonic()
    print("  🔬 DAST: starting analysis...")

    fence_lang, raw_inner = _strip_fence(code_blob)
    all_langs = _detect_lang(fence_lang, language_hint)
    print(f"   DAST: languages detected → {all_langs or ['unknown']}")

    # ── Layer 1: pattern scan ──────────────────────────────────────────────
    t0 = time.monotonic()
    pattern_findings = run_pattern_scan(code_blob)
    print(f"   DAST: pattern scan → {len(pattern_findings)} finding(s) in {time.monotonic()-t0:.1f}s")

    # ── Layer 2: Docker sandbox ─────────────────────────────────────────────
    docker_available     = is_docker_available()
    execution_results:   List[Dict[str, Any]] = []
    runtime_findings:    List[Dict[str, Any]] = []
    proof_of_executions: List[Dict[str, Any]] = []

    sandboxable_langs = [l for l in all_langs if l in _SANDBOXABLE]
    skipped_langs     = [l for l in all_langs if l not in _SANDBOXABLE]

    if skipped_langs:
        print(f"   DAST: no Docker config for: {skipped_langs} (pattern scan covers these)")

    if docker_available and sandboxable_langs:
        print(f"  🐳 DAST: Docker available — running sandbox for: {sandboxable_langs}")
        for lang in sandboxable_langs:
            sandbox_timeout = _SANDBOX_TIMEOUTS.get(lang, 15)
            print(f"     → executing {lang} sandbox (timeout={sandbox_timeout}s)...")

            # Info note for compile-based languages on first run
            if lang in _COMPILE_LANG_NAMES:
                lang_display = _COMPILE_LANG_NAMES[lang]
                print(f"        ℹ️  {lang_display}: compile + runtime startup can take 20-60s on first run")

            t0 = time.monotonic()
            exec_result = execute_in_sandbox(code_blob, lang, timeout=sandbox_timeout)
            exec_result["lang"] = lang
            execution_results.append(exec_result)

            proof = exec_result.get("proof_of_execution")
            if proof:
                proof_of_executions.append(proof)

            if not exec_result.get("skipped"):
                rt      = analyze_sandbox_output(exec_result)
                runtime_findings.extend(rt)
                elapsed = time.monotonic() - t0

                compile_note = " (compile error)" if exec_result.get("java_compile_error") else ""
                timeout_note = " ⏰ TIMED OUT" if exec_result.get("timed_out") else ""
                print(
                    f"     → {lang}: exit={exec_result.get('exit_code')}"
                    f"{compile_note}{timeout_note}"
                    f" | runtime findings={len(rt)} | {elapsed:.1f}s"
                )

                # Timeout warning for compile-based languages
                if exec_result.get("timed_out") and lang in _COMPILE_LANG_NAMES:
                    lang_display = _COMPILE_LANG_NAMES[lang]
                    print(f"        ⚠️  {lang_display} timed out after {sandbox_timeout}s.")
                    print(f"        Possible causes:")
                    print(f"          1. App is a server (runs forever) — expected for web apps")
                    print(f"          2. Docker image not cached yet (next run will be faster)")
                    print(f"          3. Code has an infinite loop")
                    print(f"        Set {lang.upper()}_SANDBOX_TIMEOUT env var to increase limit (current={sandbox_timeout}s)")

    elif not docker_available:
        print("  ⚠️  DAST: Docker unavailable — pattern scan only")
    else:
        print(f"  ℹ️  DAST: no sandboxable languages in {all_langs} — Docker skipped")

    # ── Merge & deduplicate ────────────────────────────────────────────────
    all_findings = pattern_findings + runtime_findings
    seen: set    = set()
    unique: List[Dict[str, Any]] = []
    for f in all_findings:
        key = (f["check_id"], f.get("line") or 0, f.get("file", ""), f.get("source", ""))
        if key not in seen:
            seen.add(key)
            unique.append(f)

    sev: Dict[str, int] = {"CRITICAL": 0, "HIGH": 0, "MEDIUM": 0, "LOW": 0}
    for f in unique:
        s = f.get("severity", "LOW").upper()
        sev[s] = sev.get(s, 0) + 1

    owasp_coverage = sorted({f["owasp"] for f in unique if f.get("owasp")})

    print(
        f"  ✔ DAST scan complete in {time.monotonic()-t_total:.1f}s: "
        f"{len(unique)} finding(s) — "
        f"CRITICAL={sev['CRITICAL']} HIGH={sev['HIGH']} MEDIUM={sev['MEDIUM']}"
    )

    # ── Layer 3: LLM fix — DELEGATED TO pipeline.py Stage 6 ───────────────
    # fix_result is returned with attempted=False so the frontend and pipeline
    # know no fix was attempted here. pipeline.py Stage 6 does the actual fix.
    fix_result: Dict[str, Any] = {
        "attempted":     False,
        "fixed":         False,
        "fixed_code":    None,
        "fixes_applied": 0,
        "unfixable":     unique,
        "error":         "Fix delegated to pipeline.py Stage 6",
    }

    return {
        "ok":                  True,
        "docker_available":    docker_available,
        "findings":            unique,
        "pattern_findings":    pattern_findings,
        "runtime_findings":    runtime_findings,
        "execution_results":   execution_results,
        "proof_of_executions": proof_of_executions,
        "languages":           all_langs,
        "sandboxable_langs":   sandboxable_langs,
        "fix_result":          fix_result,
        "summary": {
            "total":            len(unique),
            "critical":         sev["CRITICAL"],
            "high":             sev["HIGH"],
            "medium":           sev["MEDIUM"],
            "low":              sev["LOW"],
            "docker_executed":  docker_available and len(execution_results) > 0,
            "owasp_coverage":   owasp_coverage,
            "fix_attempted":    False,
            "fixes_applied":    0,
            "unfixable_count":  len(unique),
        },
    }