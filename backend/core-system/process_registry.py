# SAFE-AI-FRAMEWORK/backend/process_registry.py
from pathlib import Path
from typing import Optional, List, Dict
import json, psutil, shutil

# -----------------------------------------------------------------------------
# Storage layout (outside backend to prevent uvicorn reload loops)
# -----------------------------------------------------------------------------
REPO_ROOT   = Path(__file__).parent.parent.resolve()
STORAGE_DIR = (REPO_ROOT / "storage")
STORAGE_DIR.mkdir(parents=True, exist_ok=True)

PID_FILE    = STORAGE_DIR / "core.pid"          # legacy single-pid
PIDS_FILE   = STORAGE_DIR / "core.pids.json"    # multi-pid (frontend/backend)
META_FILE   = STORAGE_DIR / "core.meta.json"
JAR_FILE    = STORAGE_DIR / "core.jar"          # legacy single-jar path
PROJECT_DIR = STORAGE_DIR / "core_project"      # full uploaded project

# New: container tracking (for Docker-run core apps)
CONTAINERS_FILE = STORAGE_DIR / "containers.json"

# -----------------------------------------------------------------------------
# Single PID helpers (legacy)
# -----------------------------------------------------------------------------
def write_pid(pid: int) -> None:
    PID_FILE.write_text(str(pid), encoding="utf-8")

def read_pid() -> Optional[int]:
    if PID_FILE.exists():
        try:
            return int(PID_FILE.read_text().strip())
        except Exception:
            return None
    return None

def clear_pid() -> None:
    PID_FILE.unlink(missing_ok=True)

def is_running() -> bool:
    pid = read_pid()
    if not pid:
        return False
    try:
        p = psutil.Process(pid)
        return p.is_running() and p.status() != psutil.STATUS_ZOMBIE
    except psutil.Error:
        return False

# -----------------------------------------------------------------------------
# Multi-PID helpers (for starting multiple node apps)
# -----------------------------------------------------------------------------
def read_pids() -> Dict[str, Dict]:
    if PIDS_FILE.exists():
        try:
            return json.loads(PIDS_FILE.read_text(encoding="utf-8"))
        except Exception:
            return {}
    return {}

def write_pids(data: Dict) -> None:
    PIDS_FILE.parent.mkdir(parents=True, exist_ok=True)
    PIDS_FILE.write_text(json.dumps(data, indent=2), encoding="utf-8")

def add_pid(name: str, pid: int, cwd: Optional[Path] = None) -> None:
    """
    Store a pid under a human-readable key (e.g. 'frontend', 'backend').
    'cwd' is optional so calls like add_pid(name, pid) still work.
    """
    data = read_pids()
    rec: Dict[str, str | int] = {"pid": pid}
    if cwd is not None:
        rec["cwd"] = str(cwd)
    data[name] = rec
    write_pids(data)

def clear_pids() -> None:
    write_pids({})

# -----------------------------------------------------------------------------
# Docker container tracking (used by /core/docker/* endpoints in main.py)
# -----------------------------------------------------------------------------
def read_containers() -> Dict[str, Dict]:
    """
    Returns a mapping: subdir -> { "id": <container_id>, "info": {...} }
    """
    if CONTAINERS_FILE.exists():
        try:
            return json.loads(CONTAINERS_FILE.read_text(encoding="utf-8"))
        except Exception:
            return {}
    return {}

def write_containers(data: Dict[str, Dict]) -> None:
    CONTAINERS_FILE.parent.mkdir(parents=True, exist_ok=True)
    CONTAINERS_FILE.write_text(json.dumps(data, indent=2), encoding="utf-8")

def add_container(name: str, container_id: str, info: Optional[Dict] = None) -> None:
    """
    Track a started container under a human-readable key (usually the project subdir).
    Example info: {"name": "safeai_frontend", "port": 5173}
    """
    data = read_containers()
    data[name] = {"id": container_id, "info": info or {}}
    write_containers(data)

def remove_container(name: str) -> None:
    data = read_containers()
    if name in data:
        del data[name]
        write_containers(data)

def clear_containers() -> None:
    write_containers({})

# -----------------------------------------------------------------------------
# Project presence & metadata
# -----------------------------------------------------------------------------
def write_meta(info: dict) -> None:
    META_FILE.write_text(json.dumps(info, indent=2), encoding="utf-8")

def project_present() -> bool:
    """
    Treat project as present if the project directory exists and has at least
    one entry (file OR folder).
    """
    if not PROJECT_DIR.exists():
        return False
    try:
        next(PROJECT_DIR.iterdir())
        return True
    except StopIteration:
        return False

def reset_project_dir() -> None:
    if PROJECT_DIR.exists():
        shutil.rmtree(PROJECT_DIR)
    PROJECT_DIR.mkdir(parents=True, exist_ok=True)

# -----------------------------------------------------------------------------
# Java detection (legacy)
# -----------------------------------------------------------------------------
def find_runnable_jar() -> Optional[Path]:
    """
    Priority:
    1) storage/core.jar (explicit single upload)
    2) Any *.jar under storage/core_project (pick the first that looks runnable)
    """
    if JAR_FILE.exists():
        return JAR_FILE
    if project_present():
        candidates = [p for p in PROJECT_DIR.rglob("*.jar") if p.is_file()]
        def score(p: Path) -> int:
            s = 0
            if "target" in p.parts or "build" in p.parts: s += 2
            if "-sources" in p.name or "-javadoc" in p.name: s -= 5
            if p.stat().st_size > 1024 * 100: s += 1  # >100KB
            return s
        if candidates:
            return sorted(candidates, key=score, reverse=True)[0]
    return None

def java_present() -> bool:
    return bool(find_runnable_jar()) or (PROJECT_DIR / "pom.xml").exists() \
        or (PROJECT_DIR / "build.gradle").exists() or (PROJECT_DIR / "build.gradle.kts").exists()

# -----------------------------------------------------------------------------
# Node detection (monorepos supported)
# -----------------------------------------------------------------------------
def node_candidates(max_depth: int = 3) -> List[Path]:
    """
    Return candidate folders (relative to PROJECT_DIR) that contain package.json.
    Skips node_modules. Limits depth for performance.
    """
    if not PROJECT_DIR.exists():
        return []
    cands: List[Path] = []
    for pkg in PROJECT_DIR.rglob("package.json"):
        if "node_modules" in pkg.parts:
            continue
        try:
            rel = pkg.parent.relative_to(PROJECT_DIR)
        except ValueError:
            continue
        if len(rel.parts) <= max_depth:
            cands.append(rel)
    # Prefer shallow paths, then alphabetically
    return sorted(cands, key=lambda p: (len(p.parts), str(p)))

def _read_package_json(root: Path) -> dict:
    try:
        return json.loads((root / "package.json").read_text(encoding="utf-8"))
    except Exception:
        return {}

def _score_node_root(rel: Path) -> int:
    """
    Heuristic: prefer frontend/web/app/ui names, prefer start/dev scripts, prefer shallower.
    """
    root = PROJECT_DIR / rel
    pkg = _read_package_json(root)
    scripts = pkg.get("scripts") or {}
    score = 0
    name = rel.name.lower()
    if name in ("frontend", "web", "app", "ui"): score += 3
    if "start" in scripts: score += 3
    if "dev"   in scripts: score += 2
    if (root / "server.js").exists() or (root / "index.js").exists() or (root / "app.js").exists():
        score += 1
    score -= len(rel.parts)
    return score

def pick_best_node_root(candidates: List[Path]) -> Optional[Path]:
    best = None
    best_score = -10_000
    for rel in candidates:
        sc = _score_node_root(rel)
        if sc > best_score:
            best_score = sc
            best = rel
    return (PROJECT_DIR / best) if best else None

def node_project_root(subdir: Optional[str] = None) -> Optional[Path]:
    """
    Return the Node project root directory:
      - if `subdir` provided and contains package.json -> pick that
      - else scan several levels to find the best candidate
    """
    if subdir:
        cand = (PROJECT_DIR / subdir)
        if (cand / "package.json").exists():
            return cand
    cands = node_candidates()
    return pick_best_node_root(cands)

def node_present() -> bool:
    return node_project_root() is not None

# -----------------------------------------------------------------------------
# Project kind + status dictionary
# -----------------------------------------------------------------------------
def project_kind() -> Optional[str]:
    """Return 'node' | 'java' | None (prefers node if both present)."""
    if node_present():
        return "node"
    if java_present():
        return "java"
    return None

def status_dict() -> dict:
    pid = read_pid()
    running = is_running()
    jar = find_runnable_jar()
    meta = {}
    if META_FILE.exists():
        try:
            meta = json.loads(META_FILE.read_text())
        except Exception:
            meta = {}
    # annotate meta with detected kind for the UI
    # write it back so subsequent calls skip the expensive rglob scan
    if "kind" not in meta:
        k = project_kind()
        if k:
            meta["kind"] = k
            try:
                write_meta(meta)
            except Exception:
                pass
    return {
        "jar_present": bool(jar),
        "project_present": project_present(),
        "running": running,
        "pid": pid if running else None,
        "jar_path": str(jar) if jar else None,
        "meta": meta or None,
    }
