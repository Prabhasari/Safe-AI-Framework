# backend/vibe-secure-gen/stages/semgrep_smart_fix.py

"""
Smart Semgrep integration with native autofix support.
Categorizes findings by autofix availability and applies fixes selectively.
"""

import json
import subprocess
import tempfile
import sys
import os
from typing import Dict, Any, List, Tuple
from pathlib import Path

from .files_from_blob import materialize_files, strip_fence, detect_languages

# Find semgrep executable
def _find_semgrep_path() -> str:
    """Find semgrep executable."""
    if sys.platform == "win32":
        venv_paths = [
            Path(sys.prefix) / "Scripts" / "semgrep.exe",
            Path(sys.executable).parent / "semgrep.exe",
        ]
        for venv_path in venv_paths:
            if venv_path.exists():
                return str(venv_path)
    
    import shutil
    which_result = shutil.which("semgrep")
    if which_result:
        return which_result
    
    return "semgrep"

_SEMGREP_PATH = _find_semgrep_path()

# Rule packs configuration
BASE_PACKS = ["p/owasp-top-ten", "p/security-audit", "p/secrets"]  # FIX: added p/secrets

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
    "rust": ["p/rust"],
}


def _run_semgrep_scan(
    target_dir: str,
    packs: List[str],
    autofix: bool = False,
    timeout: int = 120
) -> Tuple[int, str, str]:
    """Run semgrep with or without autofix."""
    cmd = [
        _SEMGREP_PATH,
        "--json",
        "--metrics=off",
        "--timeout", str(timeout),
        "--no-git-ignore",
    ]
    
    if autofix:
        cmd.append("--autofix")
    
    for pack in packs:
        cmd.extend(["--config", pack])
    
    cmd.append(target_dir)
    
    try:
        creationflags = subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0

        # FIX: Force UTF-8 encoding to prevent UnicodeDecodeError on Windows (cp1252 crash)
        _env = os.environ.copy()
        _env["PYTHONUTF8"] = "1"
        _env["PYTHONIOENCODING"] = "utf-8"
        
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            encoding="utf-8",       # FIX: explicit UTF-8 (was missing, caused reader thread crash)
            errors="replace",       # FIX: don't crash on bad bytes, replace them
            timeout=timeout + 30,
            creationflags=creationflags,
            env=_env                # FIX: use env with UTF-8 vars
        )
        return result.returncode, result.stdout, result.stderr
    
    except subprocess.TimeoutExpired:
        return -1, "", "Semgrep scan timed out"
    except Exception as e:
        return -1, "", str(e)


def _categorize_findings(findings: List[Dict]) -> Dict[str, List[Dict]]:
    """
    Categorize findings by whether they have autofix available.
    Semgrep includes 'fix' or 'fix-regex' field for auto-fixable rules.
    """
    auto_fixable = []
    manual_only = []
    
    for finding in findings:
        extra = finding.get("extra", {})
        
        # Check if rule has autofix capability
        has_fix = (
            "fix" in extra or 
            "fix-regex" in extra or
            (extra.get("metadata", {}) or {}).get("fix") is not None
        )
        
        formatted_finding = {
            "check_id": finding.get("check_id"),
            "severity": extra.get("severity", "INFO"),
            "message": extra.get("message", ""),
            "path": finding.get("path"),
            "start": finding.get("start", {}),
            "end": finding.get("end", {}),
            "metadata": extra.get("metadata", {}),
            "has_autofix": has_fix,
        }
        
        if has_fix:
            auto_fixable.append(formatted_finding)
        else:
            manual_only.append(formatted_finding)
    
    return {
        "auto_fixable": auto_fixable,
        "manual_only": manual_only
    }


def _reconstruct_code_blob(files: Dict[str, str], fence_lang: str) -> str:
    """Reconstruct code blob from file dictionary."""
    if len(files) == 1:
        content = list(files.values())[0]
        lang = fence_lang or "txt"
        return f"```{lang}\n{content}\n```"
    
    parts = ["```txt"]
    for rel_path, content in sorted(files.items()):
        parts.append(f"=== FILE: {rel_path} ===")
        parts.append(content)
        parts.append("")
    parts.append("```")
    return "\n".join(parts)


def run_semgrep_smart_fix(code_blob: str) -> Dict[str, Any]:
    """
    Smart Semgrep analysis with selective autofix.
    """
    
    fence_lang, _ = strip_fence(code_blob)
    
    with tempfile.TemporaryDirectory() as td:
        try:
            rel_to_abs = materialize_files(td, code_blob)
            if not rel_to_abs:
                return {
                    "ok": False,
                    "error": "No files materialized",
                    "code": code_blob
                }
            
            langs = detect_languages(sorted(rel_to_abs.keys()), fence_lang)
            print(f"   Detected languages: {langs}")  # FIX: debug log to verify detection

            packs = BASE_PACKS.copy()
            for lg in langs:
                packs.extend(LANG_PACKS.get(lg, []))
            packs = list(dict.fromkeys(packs))
            print(f"   Using packs: {packs}")  # FIX: debug log to verify packs selected
            
            # Initial scan
            print(f"   Scanning with {len(packs)} rule packs...")
            exit_code, stdout, stderr = _run_semgrep_scan(td, packs, autofix=False)
            
            if exit_code == -1:
                return {"ok": False, "error": f"Scan failed: {stderr}", "code": code_blob}
            
            try:
                scan_data = json.loads(stdout or "{}")
            except json.JSONDecodeError as e:
                return {"ok": False, "error": f"Parse error: {e}", "code": code_blob}
            
            initial_findings = scan_data.get("results", [])
            
            if not initial_findings:
                print("  ✔ No security issues found")
                return {
                    "ok": True,
                    "autofix_applied": False,
                    "findings_before": 0,
                    "findings_after": 0,
                    "auto_fixable_count": 0,
                    "manual_only_count": 0,
                    "fixes_applied": 0,
                    "code": code_blob,
                    "original_code": code_blob,
                    "categorized_findings": {
                        "auto_fixable": [],
                        "manual_only": [],
                        "remaining_needs_llm": []
                    },
                    "file_count": len(rel_to_abs),
                    "languages": langs,
                    "packs": packs,
                }
            
            categorized = _categorize_findings(initial_findings)
            auto_fixable = categorized["auto_fixable"]
            manual_only = categorized["manual_only"]
            
            print(f"  📊 Found {len(initial_findings)} issues:")
            print(f"     ✔ {len(auto_fixable)} auto-fixable (Semgrep)")
            print(f"     🔧 {len(manual_only)} need LLM/manual")
            
            if auto_fixable:
                print(f"  🔧 Applying Semgrep autofix...")
                
                exit_code, stdout, stderr = _run_semgrep_scan(td, packs, autofix=True)
                
                fixed_files = {}
                for rel_path, abs_path in rel_to_abs.items():
                    with open(abs_path, 'r', encoding='utf-8') as f:
                        fixed_files[rel_path] = f.read()
                
                fixed_code_blob = _reconstruct_code_blob(fixed_files, fence_lang)
                
                print(f"  🔍 Verifying fixes...")
                exit_code, stdout, stderr = _run_semgrep_scan(td, packs, autofix=False)
                
                try:
                    rescan_data = json.loads(stdout or "{}")
                except json.JSONDecodeError:
                    rescan_data = {"results": []}
                
                remaining_findings = rescan_data.get("results", [])
                recategorized = _categorize_findings(remaining_findings)
                
                fixes_applied = len(initial_findings) - len(remaining_findings)
                print(f"  ✔ Semgrep fixed {fixes_applied} of {len(initial_findings)}")
                
                return {
                    "ok": True,
                    "autofix_applied": True,
                    "findings_before": len(initial_findings),
                    "findings_after": len(remaining_findings),
                    "auto_fixable_count": len(auto_fixable),
                    "manual_only_count": len(manual_only),
                    "fixes_applied": fixes_applied,
                    "code": fixed_code_blob,
                    "original_code": code_blob,
                    "categorized_findings": {
                        "initially_auto_fixable": auto_fixable,
                        "initially_manual_only": manual_only,
                        "still_remaining": recategorized["auto_fixable"] + recategorized["manual_only"],
                        "remaining_needs_llm": recategorized["manual_only"],
                    },
                    "file_count": len(rel_to_abs),
                    "languages": langs,
                    "packs": packs,
                }
            
            else:
                return {
                    "ok": True,
                    "autofix_applied": False,
                    "findings_before": len(initial_findings),
                    "findings_after": len(initial_findings),
                    "auto_fixable_count": 0,
                    "manual_only_count": len(manual_only),
                    "fixes_applied": 0,
                    "code": code_blob,
                    "original_code": code_blob,
                    "categorized_findings": {
                        "auto_fixable": [],
                        "manual_only": manual_only,
                        "remaining_needs_llm": manual_only,
                    },
                    "file_count": len(rel_to_abs),
                    "languages": langs,
                    "packs": packs,
                }
        
        except Exception as e:
            return {
                "ok": False,
                "error": f"Error: {type(e).__name__}: {e}",
                "code": code_blob
            }


def format_findings_for_llm(findings: List[Dict]) -> str:
    """Format findings for LLM to understand and fix."""
    if not findings:
        return "No issues to fix."
    
    parts = []
    for i, finding in enumerate(findings, 1):
        parts.append(f"Issue #{i}: {finding['check_id']}")
        parts.append(f"  Severity: {finding['severity']}")
        parts.append(f"  File: {finding['path']}")
        parts.append(f"  Line: {finding['start'].get('line', '?')}")
        parts.append(f"  Description: {finding['message']}")
        
        metadata = finding.get("metadata", {})
        if metadata.get("owasp"):
            parts.append(f"  OWASP: {metadata['owasp']}")
        if metadata.get("cwe"):
            parts.append(f"  CWE: {metadata['cwe']}")
        
        parts.append("")
    
    return "\n".join(parts)