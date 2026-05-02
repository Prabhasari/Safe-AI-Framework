# backend/dast-service/sandbox.py
"""
Layer 2 — Docker sandbox execution with verbose logging.

FIXED:
  1. openjdk:17-alpine was REMOVED from Docker Hub — replaced with
     eclipse-temurin:17-jdk-alpine (the official successor image).
  2. Properly handles multi-file code blobs via === FILE: === separators.
  3. Captures execution PROOF: container ID, image digest, timing, output.
  4. Java: compiles with javac, detects main class, runs with java.

ADDED LANGUAGES:
  5. PHP    — php:8.2-cli-alpine       (direct run, no compile)
  6. Ruby   — ruby:3.2-alpine          (direct run, no compile)
  7. C#     — mono:latest              (mcs compile + mono run)
  8. Rust   — rust:1.75-alpine         (rustc compile + run)
"""

from __future__ import annotations

import os
import re
import subprocess
import tempfile
import time
from typing import Any, Dict, List, Optional

# ─────────────────────────────────────────────────────────────────────────────
#  Java main-class detector
# ─────────────────────────────────────────────────────────────────────────────

_JAVA_MAIN_RE = re.compile(
    r"public\s+(?:static\s+)?(?:final\s+)?class\s+(\w+)[\s\S]*?"
    r"public\s+static\s+void\s+main\s*\(\s*String",
    re.M,
)


def _find_java_main_class(files: Dict[str, str]) -> Optional[str]:
    """
    Scan all .java file contents for 'public static void main(String'.
    Returns the fully-qualified class name (e.g. com.pms.App).
    """
    for filename, content in files.items():
        if not filename.endswith(".java"):
            continue
        m = _JAVA_MAIN_RE.search(content)
        if m:
            class_name = m.group(1)
            pkg_match  = re.search(r"^\s*package\s+([\w.]+)\s*;", content, re.M)
            if pkg_match:
                return f"{pkg_match.group(1)}.{class_name}"
            return class_name
    return None


# ─────────────────────────────────────────────────────────────────────────────
#  Language runner helpers
# ─────────────────────────────────────────────────────────────────────────────

def _java_runner(entrypoint: str) -> List[str]:
    """
    Compile all .java files under /sandbox, then run the main class.
    Uses /tmp/classes (mounted as tmpfs) for .class output.
    """
    return [
        "sh", "-c",
        f"find /sandbox -name '*.java' | xargs javac -d /tmp/classes 2>&1 && "
        f"java -cp /tmp/classes {entrypoint} 2>&1"
    ]


def _csharp_runner(entrypoint: str) -> List[str]:
    """
    Compile all .cs files under /sandbox using mcs (Mono C# compiler),
    then run the compiled binary with mono.
    mono:latest image provides both mcs (compiler) and mono (runtime).
    Output binary written to /tmp/app.exe (tmpfs mounted writable).
    """
    return [
        "sh", "-c",
        "find /sandbox -name '*.cs' | xargs mcs -out:/tmp/app.exe 2>&1 && "
        "mono /tmp/app.exe 2>&1"
    ]


def _rust_runner(entrypoint: str) -> List[str]:
    """
    Compile the main .rs entry file with rustc, then run the output binary.
    Output binary written to /tmp/program (tmpfs mounted writable).
    """
    return [
        "sh", "-c",
        f"rustc /sandbox/{entrypoint} -o /tmp/program 2>&1 && "
        "/tmp/program 2>&1"
    ]


# ─────────────────────────────────────────────────────────────────────────────
#  Sandbox image config
#
#  ⚠️  openjdk:17-alpine was REMOVED from Docker Hub in Feb 2024.
#     The official replacement is eclipse-temurin:17-jdk-alpine (Eclipse Adoptium).
#     It provides the same JDK 17 with javac + java, same Alpine base.
# ─────────────────────────────────────────────────────────────────────────────

SANDBOX_CONFIG: Dict[str, Dict[str, Any]] = {
    # ── Original languages ─────────────────────────────────────────────────
    "python": {
        "image":  "python:3.11-alpine",
        "ext":    ".py",
        "runner": lambda ep: ["python", f"/sandbox/{ep}"],
    },
    "javascript": {
        "image":  "node:18-alpine",
        "ext":    ".js",
        "runner": lambda ep: ["node", f"/sandbox/{ep}"],
    },
    "typescript": {
        "image":  "node:18-alpine",
        "ext":    ".js",
        "runner": lambda ep: ["node", f"/sandbox/{ep}"],
    },
    "go": {
        "image":  "golang:1.21-alpine",
        "ext":    ".go",
        "runner": lambda ep: ["sh", "-c", "cd /sandbox && go run ."],
    },
    "java": {
        # FIX: openjdk:17-alpine was removed from Docker Hub.
        #      eclipse-temurin:17-jdk-alpine is the official Adoptium replacement.
        "image":  "eclipse-temurin:17-jdk-alpine",
        "ext":    ".java",
        "runner": lambda ep: _java_runner(ep),
    },

    # ── NEW: Additional languages ──────────────────────────────────────────
    "php": {
        # php:8.2-cli-alpine is lightweight (~50MB), runs PHP scripts directly.
        # No compilation needed — identical pattern to Python.
        "image":  "php:8.2-cli-alpine",
        "ext":    ".php",
        "runner": lambda ep: ["php", f"/sandbox/{ep}"],
    },
    "ruby": {
        # ruby:3.2-alpine is lightweight (~60MB), runs Ruby scripts directly.
        # No compilation needed — identical pattern to Python.
        "image":  "ruby:3.2-alpine",
        "ext":    ".rb",
        "runner": lambda ep: ["ruby", f"/sandbox/{ep}"],
    },
    "csharp": {
        # mono:latest provides mcs (Mono C# compiler) + mono (runtime).
        # Lighter than the full dotnet SDK image (~800MB compressed).
        # mcs compiles to /tmp/app.exe, mono runs it.
        "image":  "mono:latest",
        "ext":    ".cs",
        "runner": lambda ep: _csharp_runner(ep),
    },
    "rust": {
        # rust:1.75-alpine provides rustc compiler.
        # rustc compiles to /tmp/program, then it is executed directly.
        "image":  "rust:1.75-alpine",
        "ext":    ".rs",
        "runner": lambda ep: _rust_runner(ep),
    },
}

# Languages that require compilation before running.
# These need /tmp writable and higher memory limits.
_COMPILE_LANGS = {"java", "csharp", "rust"}

# ─────────────────────────────────────────────────────────────────────────────
#  Multi-file blob parser
# ─────────────────────────────────────────────────────────────────────────────

_FENCE_RE    = re.compile(r"^```[a-zA-Z0-9_+\-]*\s*\n([\s\S]*?)\n```$", re.M)
_FILE_SEP_RE = re.compile(r"^===\s*FILE:\s*(.+?)\s*===$", re.M)


def _strip_fence(blob: str) -> str:
    m = _FENCE_RE.search(blob.strip())
    return m.group(1).strip() if m else blob.strip()


def _split_into_files(inner: str) -> Dict[str, str]:
    separators = list(_FILE_SEP_RE.finditer(inner))
    if not separators:
        return {"main.py": inner}

    files: Dict[str, str] = {}
    for i, sep in enumerate(separators):
        filename      = sep.group(1).strip().replace("\\", "/")
        content_start = sep.end()
        content_end   = separators[i + 1].start() if i + 1 < len(separators) else len(inner)
        files[filename] = inner[content_start:content_end].strip()
    return files


def _pick_entrypoint(files: Dict[str, str], lang: str, ext: str) -> Optional[str]:
    # Java: detect the class containing main()
    if lang == "java":
        main_class = _find_java_main_class(files)
        if main_class:
            print(f"     Java main class detected: {main_class}")
            return main_class
        for simple in ["Main", "App", "Application"]:
            for fname in files:
                if fname.endswith(f"/{simple}.java") or fname == f"{simple}.java":
                    return simple
        return None

    # C#: mcs compiles ALL .cs files — just need any .cs file to exist.
    # The runner uses 'find /sandbox -name *.cs' so entrypoint is not used
    # directly in the command, but we return the most likely main file name
    # for logging purposes.
    if lang == "csharp":
        priority_cs = ["Program.cs", "Main.cs", "main.cs", "App.cs"]
        for name in priority_cs:
            if name in files:
                return name
        for name in files:
            if name.endswith(".cs"):
                return name
        return None

    # All other languages: use priority list then fall back to extension match
    priority = [
        # Python
        "main.py", "app.py", "server.py", "run.py",
        # JavaScript / TypeScript
        "main.js", "app.js", "index.js", "server.js",
        # Go
        "main.go",
        # PHP
        "main.php", "index.php", "app.php",
        # Ruby
        "main.rb", "app.rb", "run.rb",
        # Rust
        "main.rs",
    ]
    for name in priority:
        if name in files:
            return name
    for name in files:
        if name.endswith(ext):
            return name
    return None


def _write_files(td: str, files: Dict[str, str]) -> None:
    for rel_path, content in files.items():
        parts    = [p for p in rel_path.replace("\\", "/").split("/") if p and p != ".."]
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
#  Proof of execution helpers
# ─────────────────────────────────────────────────────────────────────────────

def _get_image_id(image: str) -> Optional[str]:
    try:
        r = subprocess.run(
            ["docker", "image", "inspect", "--format", "{{.Id}}", image],
            capture_output=True, text=True, timeout=5,
        )
        if r.returncode == 0 and r.stdout.strip():
            return r.stdout.strip()[:19] + "…"
    except Exception:
        pass
    return None


def _run_with_container_id(docker_cmd: List[str], timeout: int) -> Dict[str, Any]:
    import tempfile as _tf
    cid_file = _tf.NamedTemporaryFile(delete=False, suffix=".cid")
    cid_file.close()
    os.unlink(cid_file.name)

    cmd_with_cid = docker_cmd[:2] + [f"--cidfile={cid_file.name}"] + docker_cmd[2:]
    t_start      = time.monotonic()

    try:
        result = subprocess.run(
            cmd_with_cid,
            capture_output=True, text=True,
            encoding="utf-8", errors="replace",
            timeout=timeout + 5,
        )
        elapsed_ms = int((time.monotonic() - t_start) * 1000)

        container_id: Optional[str] = None
        try:
            if os.path.exists(cid_file.name):
                with open(cid_file.name) as f:
                    cid = f.read().strip()
                container_id = cid[:12] if cid else None
                os.unlink(cid_file.name)
        except Exception:
            pass

        return {
            "success": True, "returncode": result.returncode,
            "stdout": result.stdout, "stderr": result.stderr,
            "elapsed_ms": elapsed_ms, "container_id": container_id, "timed_out": False,
        }

    except subprocess.TimeoutExpired:
        elapsed_ms = int((time.monotonic() - t_start) * 1000)
        try:
            if os.path.exists(cid_file.name):
                os.unlink(cid_file.name)
        except Exception:
            pass
        return {
            "success": False, "returncode": -1,
            "stdout": "", "stderr": f"Execution timed out after {timeout}s",
            "elapsed_ms": elapsed_ms, "container_id": None, "timed_out": True,
        }

    except FileNotFoundError:
        return {
            "success": False, "returncode": -1,
            "stdout": "", "stderr": "Docker not found in PATH",
            "elapsed_ms": 0, "container_id": None, "timed_out": False,
        }

    except Exception as exc:
        return {
            "success": False, "returncode": -1,
            "stdout": "", "stderr": str(exc),
            "elapsed_ms": 0, "container_id": None, "timed_out": False,
        }


# ─────────────────────────────────────────────────────────────────────────────
#  Main sandbox executor
# ─────────────────────────────────────────────────────────────────────────────

def execute_in_sandbox(
    code_blob: str,
    lang: str,
    timeout: int = 30,
) -> Dict[str, Any]:
    cfg = SANDBOX_CONFIG.get(lang)
    if not cfg:
        return {
            "executed": False, "skipped": True,
            "reason": f"No sandbox config for language: {lang}",
            "exit_code": -1, "stdout": "", "stderr": "", "timed_out": False,
            "proof_of_execution": None,
        }

    inner    = _strip_fence(code_blob)
    file_map = _split_into_files(inner)

    # Filter files to only the relevant extension for compiled languages
    if lang == "java":
        lang_files = {k: v for k, v in file_map.items() if k.endswith(".java")}
        if not lang_files:
            lang_files = file_map
    elif lang == "csharp":
        lang_files = {k: v for k, v in file_map.items() if k.endswith(".cs")}
        if not lang_files:
            lang_files = file_map
    elif lang == "rust":
        lang_files = {k: v for k, v in file_map.items() if k.endswith(".rs")}
        if not lang_files:
            lang_files = file_map
    else:
        lang_files = file_map

    entrypoint = _pick_entrypoint(lang_files, lang, cfg["ext"])
    run_cmd    = cfg["runner"](entrypoint) if entrypoint else None

    # ── Strategy label for logging ─────────────────────────────────────────
    strategy_map = {
        "java":   "javac (compile all) → java (run main class)",
        "csharp": "mcs (compile all .cs) → mono (run app.exe)",
        "rust":   "rustc (compile main.rs) → run binary",
        "go":     "go run . (compile + run)",
    }

    print(f"\n  {'='*60}")
    print(f"  🐳 DOCKER SANDBOX EXECUTION")
    print(f"  {'='*60}")
    print(f"  Language   : {lang}")
    print(f"  Image      : {cfg['image']}")
    if lang in strategy_map:
        print(f"  Strategy   : {strategy_map[lang]}")
    if lang in ("java", "csharp"):
        print(f"  Entrypoint : {entrypoint or '(not found)'}")
    print(f"  Files ({len(lang_files)})  :")
    for fname in sorted(lang_files.keys()):
        print(f"    • {fname}  ({len(lang_files[fname])} chars)")
    print(f"  Timeout    : {timeout}s")

    # ── Memory label for logging ───────────────────────────────────────────
    mem = "256m" if lang in ("csharp", "rust") else ("128m" if lang == "java" else "64m")
    print(f"  Isolation  : --network=none  --read-only  --memory={mem}  --cap-drop=ALL")

    if not entrypoint:
        msg = (
            "No class with public static void main(String[] args) found"
            if lang == "java" else
            f"No entrypoint found among: {list(lang_files.keys())}"
        )
        print(f"  Result     : ❌ {msg} — skipping sandbox")
        print(f"  {'='*60}\n")
        return {
            "executed": False, "skipped": True, "reason": msg,
            "exit_code": -1, "stdout": "", "stderr": "", "timed_out": False,
            "proof_of_execution": None,
        }

    image_id   = _get_image_id(cfg["image"])
    started_at = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())

    with tempfile.TemporaryDirectory() as td:
        _write_files(td, lang_files)

        print(f"  Image ID   : {image_id or 'unknown'}")
        print(f"  Started at : {started_at}")

        # ── Build docker run command based on language requirements ────────
        if lang == "java":
            # Java needs /tmp/classes tmpfs for compiled .class files
            docker_cmd = [
                "docker", "run", "--rm",
                "--network=none",
                "--read-only",
                "--memory=128m",
                "--memory-swap=128m",
                "--cpus=0.5",
                "--security-opt=no-new-privileges",
                "--cap-drop=ALL",
                f"--volume={td}:/sandbox:ro",
                "--tmpfs=/tmp:size=64m",
                "--tmpfs=/tmp/classes:size=32m",
                "--pids-limit=100",
                cfg["image"],
                *run_cmd,
            ]
        elif lang in ("csharp", "rust"):
            # C# and Rust both need /tmp writable for compiled output binary.
            # Higher memory: Mono/rustc compiler needs more RAM than a Python script.
            docker_cmd = [
                "docker", "run", "--rm",
                "--network=none",
                "--read-only",
                "--memory=256m",
                "--memory-swap=256m",
                "--cpus=0.5",
                "--security-opt=no-new-privileges",
                "--cap-drop=ALL",
                f"--volume={td}:/sandbox:ro",
                "--tmpfs=/tmp:size=128m",
                "--pids-limit=100",
                cfg["image"],
                *run_cmd,
            ]
        else:
            # Python, JS, TS, Go, PHP, Ruby — interpreted or lightweight compile
            docker_cmd = [
                "docker", "run", "--rm",
                "--network=none",
                "--read-only",
                "--memory=64m",
                "--memory-swap=64m",
                "--cpus=0.5",
                "--security-opt=no-new-privileges",
                "--cap-drop=ALL",
                f"--volume={td}:/sandbox:ro",
                "--tmpfs=/tmp:size=10m,noexec",
                "--pids-limit=50",
                cfg["image"],
                *run_cmd,
            ]

        print(f"  Command    : docker run --rm --network=none ... {cfg['image']}")
        if lang in _COMPILE_LANGS:
            print(f"  Run cmd    : {' '.join(run_cmd)}")

        run_result = _run_with_container_id(docker_cmd, timeout)

        elapsed_ms   = run_result["elapsed_ms"]
        container_id = run_result["container_id"]
        timed_out    = run_result["timed_out"]
        returncode   = run_result["returncode"]
        stdout       = run_result["stdout"]
        stderr       = run_result["stderr"]

        # ── Compile error detection (Java, C#, Rust) ──────────────────────
        java_compile_error = (
            lang == "java" and returncode != 0 and
            ("error:" in stderr.lower() or "cannot find symbol" in stderr.lower()
             or "javac" in stderr.lower())
        )
        csharp_compile_error = (
            lang == "csharp" and returncode != 0 and
            ("error" in stderr.lower() or "mcs" in stderr.lower()
             or "compilation failed" in stderr.lower())
        )
        rust_compile_error = (
            lang == "rust" and returncode != 0 and
            ("error" in stderr.lower() or "rustc" in stderr.lower()
             or "aborting due to" in stderr.lower())
        )

        # Single flag used for all compile-time error handling below
        compile_error = java_compile_error or csharp_compile_error or rust_compile_error

        stdout_lines = stdout.strip().splitlines()
        stderr_lines = stderr.strip().splitlines()

        # ── Build proof dict ───────────────────────────────────────────────
        proof = {
            "image":         cfg["image"],
            "image_id":      image_id,
            "container_id":  container_id,
            "started_at":    started_at,
            "elapsed_ms":    elapsed_ms,
            "exit_code":     returncode,
            "timed_out":     timed_out,
            "stdout_lines":  stdout_lines[:20],
            "stderr_lines":  stderr_lines[:20],
            "entrypoint":    entrypoint,
            "files":         sorted(lang_files.keys()),
            "compile_error": compile_error,
            "isolation": {
                "network":    "none",
                "read_only":  True,
                "memory":     mem,
                "cpus":       "0.5",
                "pids_limit": 100 if lang in _COMPILE_LANGS else 50,
                "cap_drop":   "ALL",
            },
        }

        print(f"  Container  : {container_id or '(--rm removed before capture)'}")
        print(f"  Elapsed    : {elapsed_ms}ms")
        print(f"  Exit code  : {returncode}")

        # ── Print output ───────────────────────────────────────────────────
        if compile_error:
            lang_names = {"java": "Java", "csharp": "C#", "rust": "Rust"}
            print(f"  ⚠️  {lang_names.get(lang, lang)} compilation errors detected:")
            for line in stderr_lines[:10]:
                print(f"    │ {line}")
        else:
            if stdout_lines:
                print(f"  STDOUT     :")
                for line in stdout_lines[:15]:
                    print(f"    │ {line}")
            if stderr_lines:
                print(f"  STDERR     :")
                for line in stderr_lines[:15]:
                    print(f"    │ {line}")

        if timed_out:
            print(f"  Result     : ⏰ TIMED OUT after {timeout}s!")
        elif compile_error:
            print(f"  Result     : ⚠️  Compiled with errors (runtime signals still checked)")
        elif returncode == 0:
            print(f"  Result     : ✔ Executed successfully")
        else:
            print(f"  Result     : ⚠️  Non-zero exit (analyzing for security signals...)")
        print(f"  {'='*60}\n")

        if timed_out:
            return {
                "executed": True, "timed_out": True,
                "exit_code": -1, "stdout": "",
                "stderr": f"Execution timed out after {timeout}s",
                "skipped": False,
                "proof_of_execution": proof,
                "files_executed": list(lang_files.keys()),
                "entrypoint": entrypoint, "lang": lang,
            }

        if not run_result["success"] and "Docker not found" in stderr:
            return {
                "executed": False, "skipped": True, "reason": "Docker not found",
                "exit_code": -1, "stdout": "", "stderr": "", "timed_out": False,
                "proof_of_execution": None,
            }

        return {
            "executed":           True,
            "exit_code":          returncode,
            "stdout":             stdout[:2000],
            "stderr":             stderr[:2000],
            "timed_out":          False,
            "skipped":            False,
            "java_compile_error": compile_error,   # kept for frontend compatibility
            "files_executed":     list(lang_files.keys()),
            "entrypoint":         entrypoint,
            "lang":               lang,
            "proof_of_execution": proof,
        }


# ─────────────────────────────────────────────────────────────────────────────
#  Runtime signal analyzer
# ─────────────────────────────────────────────────────────────────────────────

_RUNTIME_SIGNALS = [
    ("connection refused",     "runtime-network-attempt",     "HIGH",     "Network connection attempt blocked by sandbox — SSRF risk.",              "A10 - SSRF"),
    ("network unreachable",    "runtime-network-attempt",     "HIGH",     "Network connection attempt blocked by sandbox — SSRF risk.",              "A10 - SSRF"),
    ("name or service not",    "runtime-network-attempt",     "HIGH",     "DNS lookup attempted (blocked) — SSRF risk.",                             "A10 - SSRF"),
    ("unknownhostexception",   "runtime-network-attempt",     "HIGH",     "Java DNS lookup attempted (blocked) — SSRF risk.",                        "A10 - SSRF"),
    ("connectexception",       "runtime-network-attempt",     "HIGH",     "Java network connection attempted (blocked) — SSRF risk.",                "A10 - SSRF"),
    ("could not connect",      "runtime-network-attempt",     "HIGH",     "Network connection attempted (blocked) — SSRF risk.",                     "A10 - SSRF"),
    ("failed to connect",      "runtime-network-attempt",     "HIGH",     "Network connection attempted (blocked) — SSRF risk.",                     "A10 - SSRF"),
    ("permission denied",      "runtime-unauthorized-access", "HIGH",     "Unauthorized file/resource access attempted at runtime.",                 "A01 - Broken Access Control"),
    ("accesscontrolexception", "runtime-unauthorized-access", "HIGH",     "Java AccessControlException — unauthorized access attempted.",            "A01 - Broken Access Control"),
    ("segmentation fault",     "runtime-memory-corruption",   "CRITICAL", "Segmentation fault — memory safety vulnerability.",                      "A06 - Vulnerable Components"),
    ("stack overflow",         "runtime-stack-overflow",      "HIGH",     "Stack overflow detected — unbounded recursion.",                          "A06 - Vulnerable Components"),
    ("stackoverflowerror",     "runtime-stack-overflow",      "HIGH",     "Java StackOverflowError — unbounded recursion detected.",                 "A06 - Vulnerable Components"),
    ("recursionerror",         "runtime-stack-overflow",      "HIGH",     "RecursionError — unbounded recursion detected.",                          "A06 - Vulnerable Components"),
    ("stack level too deep",   "runtime-stack-overflow",      "HIGH",     "Ruby stack level too deep — unbounded recursion detected.",               "A06 - Vulnerable Components"),
    ("outofmemoryerror",       "runtime-memory-exhaustion",   "MEDIUM",   "Java OutOfMemoryError — memory exhaustion vulnerability.",                "A06 - Vulnerable Components"),
    ("memoryerror",            "runtime-memory-exhaustion",   "MEDIUM",   "MemoryError — memory exhaustion vulnerability.",                          "A06 - Vulnerable Components"),
    ("out of memory",          "runtime-memory-exhaustion",   "MEDIUM",   "Out of memory — memory exhaustion vulnerability.",                        "A06 - Vulnerable Components"),
    ("classnotfoundexception", "runtime-classpath-issue",     "LOW",      "Java ClassNotFoundException — missing dependency at runtime.",            "A06 - Vulnerable Components"),
    ("sql syntax",             "runtime-sql-error",           "HIGH",     "SQL syntax error at runtime — possible injection or unparameterized query.", "A03 - Injection"),
    ("sqlexception",           "runtime-sql-error",           "MEDIUM",   "Java SQLException at runtime — database error detected.",                 "A03 - Injection"),
    ("php fatal error",        "runtime-php-fatal",           "HIGH",     "PHP Fatal Error detected at runtime.",                                    "A06 - Vulnerable Components"),
    ("php warning",            "runtime-php-warning",         "LOW",      "PHP Warning detected at runtime — potential unsafe operation.",           "A06 - Vulnerable Components"),
    ("undefined method",       "runtime-undefined-method",    "MEDIUM",   "Undefined method called at runtime — potential logic error.",             "A06 - Vulnerable Components"),
    ("nosuchmethoderror",      "runtime-undefined-method",    "MEDIUM",   "NoSuchMethodError — method not found at runtime.",                        "A06 - Vulnerable Components"),
]


def analyze_sandbox_output(exec_result: Dict[str, Any]) -> List[Dict[str, Any]]:
    if not exec_result.get("executed"):
        return []

    findings: List[Dict[str, Any]] = []
    combined = (
        (exec_result.get("stdout") or "") +
        (exec_result.get("stderr") or "")
    ).lower()

    seen:  set  = set()
    proof = exec_result.get("proof_of_execution")

    for signal, check_id, sev, message, owasp in _RUNTIME_SIGNALS:
        if signal in combined and check_id not in seen:
            seen.add(check_id)
            print(f"  🚨 Runtime signal: '{signal}' → {check_id} [{sev}]")
            findings.append({
                "check_id":           f"dast-{check_id}",
                "severity":           sev,
                "message":            message,
                "owasp":              owasp,
                "cwe":                None,
                "line":               None,
                "file":               proof.get("entrypoint") if proof else None,
                "snippet":            combined[:200],
                "source":             "docker_execution",
                "runtime":            True,
                "proof_of_execution": proof,
            })

    if exec_result.get("timed_out"):
        print(f"  🚨 Runtime signal: timeout → dast-runtime-timeout [MEDIUM]")
        findings.append({
            "check_id":           "dast-runtime-timeout",
            "severity":           "MEDIUM",
            "message":            "Code timed out — possible infinite loop or resource exhaustion.",
            "owasp":              "A06 - Vulnerable Components",
            "cwe":                "CWE-400",
            "line":               None,
            "file":               proof.get("entrypoint") if proof else None,
            "snippet":            None,
            "source":             "docker_execution",
            "runtime":            True,
            "proof_of_execution": proof,
        })

    if not findings:
        print(f"  ✔ No runtime security signals detected")

    return findings