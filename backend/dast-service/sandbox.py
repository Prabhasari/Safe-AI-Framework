# backend/dast-service/sandbox.py
"""
Layer 2 — Docker sandbox execution with verbose logging.
FIXED: properly handles multi-file code blobs by splitting
       === FILE: xxx.py === separators into real files.
"""

from __future__ import annotations

import os
import re
import subprocess
import tempfile
from typing import Any, Dict, List, Optional

# ─────────────────────────────────────────────────────────────────────────────
#  Sandbox image config
# ─────────────────────────────────────────────────────────────────────────────

SANDBOX_CONFIG: Dict[str, Dict[str, Any]] = {
    "python": {
        "image":   "python:3.11-alpine",
        "ext":     ".py",
        "runner":  lambda ep: ["python", f"/sandbox/{ep}"],
    },
    "javascript": {
        "image":   "node:18-alpine",
        "ext":     ".js",
        "runner":  lambda ep: ["node", f"/sandbox/{ep}"],
    },
    "typescript": {
        "image":   "node:18-alpine",
        "ext":     ".js",
        "runner":  lambda ep: ["node", f"/sandbox/{ep}"],
    },
    "go": {
        "image":   "golang:1.21-alpine",
        "ext":     ".go",
        "runner":  lambda ep: ["sh", "-c", "cd /sandbox && go run ."],
    },
}

# ─────────────────────────────────────────────────────────────────────────────
#  Multi-file blob parser
# ─────────────────────────────────────────────────────────────────────────────

_FENCE_RE    = re.compile(r"^```[a-zA-Z0-9_+\-]*\s*\n([\s\S]*?)\n```$", re.M)
_FILE_SEP_RE = re.compile(r"^===\s*FILE:\s*(.+?)\s*===$", re.M)


def _strip_fence(blob: str) -> str:
    m = _FENCE_RE.search(blob.strip())
    return m.group(1).strip() if m else blob.strip()


def _split_into_files(inner: str) -> Dict[str, str]:
    """
    Split a multi-file blob into {filename: content}.
    Handles separators like:  === FILE: config.py ===
    Falls back to {"main.py": inner} for single-file blobs.
    """
    separators = list(_FILE_SEP_RE.finditer(inner))
    if not separators:
        return {"main.py": inner}

    files: Dict[str, str] = {}
    for i, sep in enumerate(separators):
        filename     = sep.group(1).strip().replace("\\", "/")
        content_start = sep.end()
        content_end   = separators[i + 1].start() if i + 1 < len(separators) else len(inner)
        content       = inner[content_start:content_end].strip()
        files[filename] = content

    return files


def _pick_entrypoint(files: Dict[str, str], ext: str) -> Optional[str]:
    """Choose the best file to execute as entrypoint."""
    priority = [
        "main.py", "app.py", "server.py", "run.py",
        "main.js", "app.js", "index.js", "server.js",
        "main.go",
    ]
    for name in priority:
        if name in files:
            return name
    # fallback: first file with matching extension
    for name in files:
        if name.endswith(ext):
            return name
    return None


def _write_files(td: str, files: Dict[str, str]) -> None:
    """Write all parsed files into the temp directory."""
    for rel_path, content in files.items():
        # Sanitize: no absolute paths, no traversal
        parts = [p for p in rel_path.replace("\\", "/").split("/")
                 if p and p != ".."]
        if not parts:
            continue
        abs_path = os.path.join(td, *parts)
        os.makedirs(os.path.dirname(abs_path), exist_ok=True)
        with open(abs_path, "w", encoding="utf-8") as f:
            f.write(content)


# ─────────────────────────────────────────────────────────────────────────────
#  Docker availability helpers
# ─────────────────────────────────────────────────────────────────────────────

def is_docker_available() -> bool:
    try:
        r = subprocess.run(["docker", "info"], capture_output=True, timeout=5)
        return r.returncode == 0
    except Exception:
        return False


def get_available_images() -> List[str]:
    available = []
    for cfg in SANDBOX_CONFIG.values():
        try:
            r = subprocess.run(
                ["docker", "image", "inspect", cfg["image"]],
                capture_output=True, timeout=5,
            )
            if r.returncode == 0:
                available.append(cfg["image"])
        except Exception:
            pass
    return list(set(available))


def pull_sandbox_images() -> Dict[str, bool]:
    results = {}
    for cfg in SANDBOX_CONFIG.values():
        image = cfg["image"]
        if image in results:
            continue
        check = subprocess.run(
            ["docker", "image", "inspect", image],
            capture_output=True, timeout=5,
        )
        if check.returncode == 0:
            print(f"  ✔ Already present: {image}")
            results[image] = True
            continue
        print(f"  ⬇️  Pulling: {image}...")
        try:
            pull = subprocess.run(
                ["docker", "pull", image],
                capture_output=True, timeout=300,
            )
            results[image] = pull.returncode == 0
            status = "✔ Pulled" if results[image] else "❌ Failed"
            print(f"  {status}: {image}")
        except Exception as e:
            results[image] = False
            print(f"  ❌ Error pulling {image}: {e}")
    return results


# ─────────────────────────────────────────────────────────────────────────────
#  Main sandbox executor
# ─────────────────────────────────────────────────────────────────────────────

def execute_in_sandbox(
    code_blob: str,
    lang: str,
    timeout: int = 15,
) -> Dict[str, Any]:
    """
    Run code_blob inside an isolated Docker container.

    Steps:
      1. Strip outer code fence
      2. Split multi-file blob into individual files
      3. Write each file to a temp directory
      4. Run the entrypoint file inside Docker
      5. Return stdout/stderr for security signal analysis
    """
    cfg = SANDBOX_CONFIG.get(lang)
    if not cfg:
        return {
            "executed": False, "skipped": True,
            "reason": f"No sandbox config for language: {lang}",
            "exit_code": -1, "stdout": "", "stderr": "", "timed_out": False,
        }

    # ── Step 1 & 2: Parse the blob ─────────────────────────────────────────
    inner      = _strip_fence(code_blob)
    file_map   = _split_into_files(inner)
    entrypoint = _pick_entrypoint(file_map, cfg["ext"])
    run_cmd    = cfg["runner"](entrypoint) if entrypoint else None

    # ── Verbose header ──────────────────────────────────────────────────────
    print(f"\n  {'='*60}")
    print(f"  🐳 DOCKER SANDBOX EXECUTION")
    print(f"  {'='*60}")
    print(f"  Language   : {lang}")
    print(f"  Image      : {cfg['image']}")
    print(f"  Files ({len(file_map)})  :")
    for fname in sorted(file_map.keys()):
        tag = " ← ENTRYPOINT" if fname == entrypoint else ""
        print(f"    • {fname}{tag}  ({len(file_map[fname])} chars)")
    print(f"  Timeout    : {timeout}s")
    print(f"  Isolation  : --network=none  --read-only  --memory=64m  --cap-drop=ALL")

    if not entrypoint:
        print(f"  Result     : ❌ No entrypoint found — skipping sandbox")
        print(f"  {'='*60}\n")
        return {
            "executed": False, "skipped": True,
            "reason": f"No entrypoint found among: {list(file_map.keys())}",
            "exit_code": -1, "stdout": "", "stderr": "", "timed_out": False,
        }

    # ── Step 3 & 4: Write files and run Docker ─────────────────────────────
    with tempfile.TemporaryDirectory() as td:
        _write_files(td, file_map)

        print(f"  Temp dir   : {td}")
        print(f"  Written    : {sorted(os.listdir(td))}")
        print(f"  Command    : docker run --rm --network=none ... {cfg['image']}")

        docker_cmd = [
            "docker", "run",
            "--rm",                              # auto-delete after exit
            "--network=none",                    # NO network access
            "--read-only",                       # immutable filesystem
            "--memory=64m",                      # 64MB memory limit
            "--memory-swap=64m",                 # no swap
            "--cpus=0.5",                        # half CPU core
            "--security-opt=no-new-privileges",  # no privilege escalation
            "--cap-drop=ALL",                    # drop all Linux capabilities
            f"--volume={td}:/sandbox:ro",        # mount code read-only
            "--tmpfs=/tmp:size=10m,noexec",      # tiny writable /tmp
            "--pids-limit=50",                   # max 50 processes
            cfg["image"],
            *run_cmd,
        ]

        try:
            result = subprocess.run(
                docker_cmd,
                capture_output=True, text=True,
                encoding="utf-8", errors="replace",
                timeout=timeout + 5,
            )

            print(f"  Exit code  : {result.returncode}")

            if result.stdout.strip():
                print(f"  STDOUT     :")
                for line in result.stdout.strip().splitlines()[:15]:
                    print(f"    │ {line}")

            if result.stderr.strip():
                print(f"  STDERR     :")
                for line in result.stderr.strip().splitlines()[:15]:
                    print(f"    │ {line}")

            status = "✔ Executed successfully" if result.returncode == 0 \
                     else "⚠️  Non-zero exit (analyzing for security signals...)"
            print(f"  Result     : {status}")
            print(f"  {'='*60}\n")

            return {
                "executed":         True,
                "exit_code":        result.returncode,
                "stdout":           result.stdout[:2000],
                "stderr":           result.stderr[:2000],
                "timed_out":        False,
                "skipped":          False,
                "files_executed":   list(file_map.keys()),
                "entrypoint":       entrypoint,
            }

        except subprocess.TimeoutExpired:
            print(f"  Result     : ⏰ TIMED OUT after {timeout}s!")
            print(f"  {'='*60}\n")
            return {
                "executed": True, "timed_out": True,
                "exit_code": -1, "stdout": "",
                "stderr": f"Execution timed out after {timeout}s",
                "skipped": False,
            }

        except FileNotFoundError:
            print(f"  Result     : ❌ Docker not found in PATH")
            print(f"  {'='*60}\n")
            return {
                "executed": False, "skipped": True,
                "reason": "Docker not found",
                "exit_code": -1, "stdout": "", "stderr": "", "timed_out": False,
            }

        except Exception as exc:
            print(f"  Result     : ❌ Unexpected error: {exc}")
            print(f"  {'='*60}\n")
            return {
                "executed": False, "error": str(exc),
                "exit_code": -1, "stdout": "", "stderr": "",
                "timed_out": False, "skipped": False,
            }


# ─────────────────────────────────────────────────────────────────────────────
#  Runtime signal analyzer
# ─────────────────────────────────────────────────────────────────────────────

_RUNTIME_SIGNALS = [
    # (signal_text,             check_id,                      sev,        message,                                                                   owasp)
    ("connection refused",      "runtime-network-attempt",     "HIGH",     "Network connection attempt blocked by sandbox — SSRF risk.",              "A10 - SSRF"),
    ("network unreachable",     "runtime-network-attempt",     "HIGH",     "Network connection attempt blocked by sandbox — SSRF risk.",              "A10 - SSRF"),
    ("name or service not",     "runtime-network-attempt",     "HIGH",     "DNS lookup attempted (blocked) — SSRF risk.",                             "A10 - SSRF"),
    ("permission denied",       "runtime-unauthorized-access", "HIGH",     "Unauthorized file/resource access attempted at runtime.",                 "A01 - Broken Access Control"),
    ("segmentation fault",      "runtime-memory-corruption",   "CRITICAL", "Segmentation fault — memory safety vulnerability.",                      "A06 - Vulnerable Components"),
    ("stack overflow",          "runtime-stack-overflow",      "HIGH",     "Stack overflow detected — unbounded recursion.",                          "A06 - Vulnerable Components"),
    ("recursionerror",          "runtime-stack-overflow",      "HIGH",     "RecursionError — unbounded recursion detected.",                          "A06 - Vulnerable Components"),
    ("memoryerror",             "runtime-memory-exhaustion",   "MEDIUM",   "MemoryError — memory exhaustion vulnerability.",                          "A06 - Vulnerable Components"),
    ("outofmemoryerror",        "runtime-memory-exhaustion",   "MEDIUM",   "OutOfMemoryError — memory exhaustion vulnerability.",                     "A06 - Vulnerable Components"),
]


def analyze_sandbox_output(exec_result: Dict[str, Any]) -> List[Dict[str, Any]]:
    """Scan Docker output for runtime security signals."""
    if not exec_result.get("executed"):
        return []

    findings: List[Dict[str, Any]] = []
    combined = (
        (exec_result.get("stdout") or "") +
        (exec_result.get("stderr") or "")
    ).lower()

    seen: set = set()

    for signal, check_id, sev, message, owasp in _RUNTIME_SIGNALS:
        if signal in combined and check_id not in seen:
            seen.add(check_id)
            print(f"  🚨 Runtime signal: '{signal}' → {check_id} [{sev}]")
            findings.append({
                "check_id": f"dast-{check_id}",
                "severity": sev,
                "message":  message,
                "owasp":    owasp,
                "cwe":      None,
                "line":     None,
                "snippet":  combined[:200],
                "source":   "docker_execution",
                "runtime":  True,
            })

    if exec_result.get("timed_out"):
        print(f"  🚨 Runtime signal: timeout → dast-runtime-timeout [MEDIUM]")
        findings.append({
            "check_id": "dast-runtime-timeout",
            "severity": "MEDIUM",
            "message":  "Code timed out — possible infinite loop or resource exhaustion.",
            "owasp":    "A06 - Vulnerable Components",
            "cwe":      "CWE-400",
            "line":     None, "snippet": None,
            "source":   "docker_execution",
            "runtime":  True,
        })

    if not findings:
        print(f"  ✔ No runtime security signals detected")

    return findings