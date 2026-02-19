import json
import subprocess
import tempfile
import sys
import os
import threading
from pathlib import Path
from typing import Dict, Any, List, Tuple, Optional

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

# Global cache for semgrep availability
_SEMGREP_CACHE: Optional[Dict[str, Any]] = None
_CACHE_LOCK = threading.Lock()

def _find_semgrep_path() -> str:
    """Find semgrep executable with multiple fallback strategies."""
    
    # Strategy 1: Check virtual environment Scripts folder (Windows)
    if sys.platform == "win32":
        venv_paths = [
            Path(sys.prefix) / "Scripts" / "semgrep.exe",
            Path(sys.executable).parent / "semgrep.exe",
        ]
        for venv_path in venv_paths:
            if venv_path.exists() and venv_path.is_file():
                return str(venv_path)
    
    # Strategy 2: Use shutil.which
    import shutil
    which_result = shutil.which("semgrep")
    if which_result:
        return which_result
    
    # Strategy 3: Check if semgrep is in PATH via direct test
    try:
        result = subprocess.run(
            ["semgrep", "--version"],
            capture_output=True,
            timeout=3,
            creationflags=subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0
        )
        if result.returncode == 0:
            return "semgrep"
    except Exception:
        pass
    
    return "semgrep"  # Fallback

_SEMGREP_PATH = _find_semgrep_path()

def _check_semgrep_quick() -> Tuple[bool, str]:
    """Quick check without full version query - just test if executable exists."""
    semgrep_path = Path(_SEMGREP_PATH)
    
    # If it's an absolute path, check if file exists
    if semgrep_path.is_absolute():
        if semgrep_path.exists() and semgrep_path.is_file():
            return True, f"Found at {_SEMGREP_PATH}"
        else:
            return False, f"Semgrep not found at {_SEMGREP_PATH}"
    
    # If it's just "semgrep", try which
    import shutil
    if shutil.which(_SEMGREP_PATH):
        return True, "Found in PATH"
    
    return False, f"Semgrep executable '{_SEMGREP_PATH}' not found"

def _ensure_semgrep() -> Tuple[bool, str]:
    """Check if semgrep is available - with caching to avoid repeated checks."""
    global _SEMGREP_CACHE
    
    with _CACHE_LOCK:
        # Return cached result if available
        if _SEMGREP_CACHE is not None:
            return _SEMGREP_CACHE["available"], _SEMGREP_CACHE["message"]
        
        # First do a quick file existence check
        quick_check, quick_msg = _check_semgrep_quick()
        if not quick_check:
            _SEMGREP_CACHE = {"available": False, "message": quick_msg}
            return False, quick_msg
        
        # Now try a version check with short timeout
        try:
            creationflags = subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0
            
            result = subprocess.run(
                [_SEMGREP_PATH, "--version"],
                capture_output=True,
                text=True,
                timeout=5,
                creationflags=creationflags,
                env=os.environ.copy()
            )
            
            if result.returncode == 0:
                msg = f"Semgrep v{result.stdout.strip()}"
                _SEMGREP_CACHE = {"available": True, "message": msg}
                return True, msg
            else:
                msg = f"Semgrep check failed: {result.stderr.strip()}"
                _SEMGREP_CACHE = {"available": False, "message": msg}
                return False, msg
                
        except subprocess.TimeoutExpired:
            # Timeout likely means semgrep is trying to update rules on first run
            # Consider it available but warn about performance
            msg = "Semgrep found but slow to respond (may be updating rules)"
            _SEMGREP_CACHE = {"available": True, "message": msg}
            return True, msg
            
        except FileNotFoundError:
            msg = f"Semgrep not found at: {_SEMGREP_PATH}"
            _SEMGREP_CACHE = {"available": False, "message": msg}
            return False, msg
            
        except Exception as e:
            msg = f"Error checking semgrep: {type(e).__name__}: {str(e)}"
            _SEMGREP_CACHE = {"available": False, "message": msg}
            return False, msg

def _run_semgrep_on_dir(src_dir: str, packs: List[str]) -> Dict[str, Any]:
    """Run semgrep scan on a directory with proper error handling."""
    
    # Use --no-git-ignore and --metrics=off to speed things up
    cmd = [
        _SEMGREP_PATH,
        "--json",
        "--error",
        "--timeout", "120",
        "--no-git-ignore",
        "--metrics=off",
    ]
    
    for p in packs:
        cmd += ["--config", p]
    cmd.append(src_dir)

    try:
        creationflags = subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0
        
        proc = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=150,
            creationflags=creationflags,
            env=os.environ.copy()
        )
        
    except subprocess.TimeoutExpired:
        return {
            "ok": False,
            "exit_code": -1,
            "findings": [],
            "errors": [{"message": "Semgrep scan timed out. Try with fewer rule packs or smaller code."}],
            "stats": {}
        }
    except Exception as e:
        return {
            "ok": False,
            "exit_code": -1,
            "findings": [],
            "errors": [{"message": f"Semgrep execution failed: {type(e).__name__}: {str(e)}"}],
            "stats": {}
        }

    # Parse output
    try:
        data = json.loads(proc.stdout or "{}")
    except json.JSONDecodeError as e:
        # If JSON parsing fails, return the raw output for debugging
        return {
            "ok": False,
            "exit_code": proc.returncode,
            "findings": [],
            "errors": [
                {
                    "message": f"Failed to parse Semgrep output: {str(e)}",
                    "raw_stdout": proc.stdout[:500] if proc.stdout else "",
                    "raw_stderr": proc.stderr[:500] if proc.stderr else ""
                }
            ],
            "stats": {}
        }

    # Extract findings
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
        "ok": proc.returncode in (0, 1),  # 0 = no findings, 1 = findings found
        "exit_code": proc.returncode,
        "findings": findings,
        "errors": data.get("errors", []),
        "stats": data.get("stats", {}),
    }

def run_semgrep_registry_over_blob(code_blob: str) -> Dict[str, Any]:
    """Run semgrep analysis on generated code blob."""
    
    # Check if semgrep is available
    present, msg = _ensure_semgrep()
    if not present:
        return {
            "ok": False,
            "tool": "semgrep",
            "error": f"Semgrep not available: {msg}",
            "semgrep_path": _SEMGREP_PATH,
            "hint": "Run 'pip install semgrep' in your virtual environment"
        }

    fence_lang, _ = strip_fence(code_blob)

    with tempfile.TemporaryDirectory() as td:
        try:
            rel_to_abs = materialize_files(td, code_blob)
            langs = detect_languages(sorted(rel_to_abs.keys()), fence_lang)

            # Start with base packs
            packs: List[str] = BASE_PACKS.copy()
            
            # Add language-specific packs
            for lg in langs:
                packs += LANG_PACKS.get(lg, [])

            # De-duplicate while preserving order
            seen = set()
            packs = [p for p in packs if not (p in seen or seen.add(p))]

            result = _run_semgrep_on_dir(td, packs)
            result.update({
                "file_count": len(rel_to_abs),
                "files": sorted(rel_to_abs.keys()),
                "languages": langs,
                "packs": packs,
                "semgrep_path": _SEMGREP_PATH
            })
            return result
            
        except Exception as e:
            return {
                "ok": False,
                "tool": "semgrep",
                "error": f"Analysis error: {type(e).__name__}: {str(e)}",
                "semgrep_path": _SEMGREP_PATH
            }

def reset_semgrep_cache():
    """Reset the semgrep availability cache. Useful for testing."""
    global _SEMGREP_CACHE
    with _CACHE_LOCK:
        _SEMGREP_CACHE = None