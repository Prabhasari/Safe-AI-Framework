import json
import subprocess
import tempfile
from typing import Dict, Any, List, Tuple

from .files_from_blob import materialize_files, strip_fence, detect_languages

BASE_PACKS = [
    "p/owasp-top-ten",
    "p/security-audit",
    "p/secrets",
]

LANG_PACKS = {
    "java": ["p/java"],
    "kotlin": ["p/kotlin"],
    "python": ["p/python"],
    "go": ["p/go"],
    "javascript": ["p/javascript"],
    "typescript": ["p/typescript"],
    "php": ["p/php"],
    "ruby": ["p/ruby"],
    "csharp": ["p/csharp"],
    "scala": ["p/scala"],
    "rust": ["p/rust"],
}

def _ensure_semgrep() -> Tuple[bool, str]:
    try:
        out = subprocess.run(
            ["semgrep", "--version"],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
        )
        if out.returncode == 0:
            return True, out.stdout.strip()
        return False, out.stderr.strip()
    except Exception as e:
        return False, str(e)

def _run_semgrep_on_dir(src_dir: str, packs: List[str]) -> Dict[str, Any]:
    cmd = ["semgrep", "--json", "--error", "--timeout", "180"]
    for p in packs:
        cmd += ["--config", p]
    cmd.append(src_dir)

    proc = subprocess.run(
        cmd,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )

    try:
        data = json.loads(proc.stdout or "{}")
    except Exception:
        data = {"results": [], "errors": [{"message": "Failed to parse semgrep JSON output"}]}

    findings: List[Dict[str, Any]] = []
    for r in data.get("results", []):
        extra = r.get("extra", {}) or {}
        findings.append({
            "check_id": r.get("check_id"),
            "severity": extra.get("severity", "INFO"),
            "message": extra.get("message", ""),
            "metadata": extra.get("metadata", {}),
            "path": r.get("path"),
            "start": r.get("start", {}),
            "end": r.get("end", {}),
        })

    return {
        "ok": proc.returncode in (0, 1),  # 0 = no findings, 1 = findings
        "exit_code": proc.returncode,
        "findings": findings,
        "errors": data.get("errors", []),
        "stats": data.get("stats", {}),
    }

def run_semgrep_registry_over_blob(code_blob: str) -> Dict[str, Any]:
    present, msg = _ensure_semgrep()
    if not present:
        return {"ok": False, "tool": "semgrep", "error": f"Semgrep not available: {msg}"}

    fence_lang, _ = strip_fence(code_blob)

    with tempfile.TemporaryDirectory() as td:
        rel_to_abs = materialize_files(td, code_blob)
        langs = detect_languages(sorted(rel_to_abs.keys()), fence_lang)

        packs: List[str] = BASE_PACKS.copy()
        for lg in langs:
            packs += LANG_PACKS.get(lg, [])

        # de-dup while preserving order
        seen = set()
        packs = [p for p in packs if not (p in seen or seen.add(p))]

        result = _run_semgrep_on_dir(td, packs)
        result.update({
            "file_count": len(rel_to_abs),
            "files": sorted(rel_to_abs.keys()),
            "languages": langs,
            "packs": packs,
        })
        return result
