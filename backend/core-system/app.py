# SAFE-AI-FRAMEWORK/backend/main.py
from pathlib import Path
from datetime import datetime
import os
import json
import shutil
import re, subprocess
import logging
from typing import List, Optional, Dict

import requests as http_requests
from fastapi import FastAPI, UploadFile, File, HTTPException, Form, Query, Body
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
from plugin_router import router as plugins_router
from file_router import router as file_router

log = logging.getLogger("core-system")

CA_SERVICE_URL = os.environ.get("CA_SERVICE_URL", "http://127.0.0.1:8011")



from process_registry import (
    STORAGE_DIR, PROJECT_DIR, JAR_FILE, META_FILE,
    write_pid, read_pid, clear_pid,
    is_running, find_runnable_jar, reset_project_dir, status_dict, write_meta,
    # Docker container registry helpers (must exist in process_registry.py)
    read_containers, add_container, remove_container, clear_containers
)

# ==============================================================================
# FastAPI & CORS
# ==============================================================================
app = FastAPI(title="Core System Loader API", version="0.8.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://localhost:3000", "http://localhost:5000"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Static mount for AI plugins inside the uploaded project
PLUGINS_DIR = PROJECT_DIR / "ai_plugins"
PLUGINS_DIR.mkdir(parents=True, exist_ok=True)
app.mount("/plugins", StaticFiles(directory=str(PLUGINS_DIR), html=False), name="plugins")

# ==============================================================================
# Models
# ==============================================================================
class Status(BaseModel):
    jar_present: bool
    project_present: bool
    running: bool
    pid: Optional[int] = None
    jar_path: Optional[str] = None
    meta: Optional[dict] = None

class StartBothReq(BaseModel):
    subdirs: List[str]                       # e.g. ["frontend","backend"]
    urls: Optional[Dict[str, str]] = None    # optional preview map { subdir: "http://localhost:5173" }

# --- Docker requests ---
class DockerStartReq(BaseModel):
    subdir: str                               # relative to PROJECT_DIR
    image: str = "node:18-alpine"             # base image (override if needed)
    name: Optional[str] = None                # docker --name
    workdir: str = "/app"                     # container working directory
    # ⬇️ Only install if node_modules is missing
    install: str = (
        "if [ -d node_modules ]; then "
        "  echo 'node_modules present — skipping install'; "
        "else "
        "  if [ -f package-lock.json ]; then npm ci; else npm install; fi; "
        "fi"
    )
    start: str = ("npm run start || npm run dev || npm run serve || "
                  "node server.js || node index.js")
    env: Optional[Dict[str, str]] = None      # e.g. {"PORT":"5173"}
    ports: Optional[List[str]] = None         # e.g. ["5173:5173","3001:3001"]

class DockerStartManyReq(BaseModel):
    apps: List[DockerStartReq]

# ==============================================================================
# Utilities
# ==============================================================================
def _safe_join(base: Path, rel: str) -> Path:
    p = (base / rel).resolve()
    if not str(p).startswith(str(base.resolve())):
        raise HTTPException(400, detail="Invalid path")
    return p

def _project_present() -> bool:
    return PROJECT_DIR.exists() and any(PROJECT_DIR.rglob("*"))

def _npm_exe() -> str:
    return "npm.cmd" if os.name == "nt" else "npm"

def _node_exe() -> str:
    return "node.exe" if os.name == "nt" else "node"

def _docker_exe() -> str:
    return "docker.exe" if os.name == "nt" else "docker"

def _which(cmd: str) -> Optional[str]:
    return shutil.which(cmd)

def _ensure_docker():
    if not _which(_docker_exe()):
        raise HTTPException(500, detail="`docker` not found on PATH. Install Docker Desktop/Engine and restart the terminal.")
    # quick ping to engine (won’t spam logs)
    try:
        subprocess.run([_docker_exe(), "info"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=True)
    except Exception:
        raise HTTPException(500, detail="Docker daemon is not running.")

# ==============================================================================
# Build log helpers (optional but handy)
# ==============================================================================
BUILD_LOG = STORAGE_DIR / "build.log"

def _append_log(msg: str):
    BUILD_LOG.parent.mkdir(parents=True, exist_ok=True)
    with BUILD_LOG.open("a", encoding="utf-8") as f:
        f.write(f"[{datetime.now().isoformat(timespec='seconds')}] {msg}\n")

def _run(cmd: List[str], cwd: Path, timeout: int = 900) -> int:
    _append_log(f"RUN: {' '.join(cmd)} (cwd={cwd})")
    try:
        proc = subprocess.run(
            cmd, cwd=str(cwd),
            stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
            timeout=timeout, check=False,
        )
        with BUILD_LOG.open("a", encoding="utf-8") as f:
            f.write(proc.stdout.decode(errors="ignore"))
        _append_log(f"EXIT: {proc.returncode}")
        return proc.returncode
    except subprocess.TimeoutExpired:
        _append_log("TIMEOUT")
        return 124
    except Exception as e:
        _append_log(f"ERROR: {e}")
        return 1

@app.get("/core/build-log")
def core_build_log():
    if not BUILD_LOG.exists():
        return {"log": ""}
    txt = BUILD_LOG.read_text(encoding="utf-8")
    return {"log": txt[-100_000:]}  # last 100KB

# ==============================================================================
# Upload (webkitdirectory)
# ==============================================================================
@app.post("/core/upload-folder")
async def upload_folder(
    files: List[UploadFile] = File(..., description="Multiple files with webkitRelativePath"),
    root: str = Form("core_project"),
):
    reset_project_dir()
    saved = 0
    for uf in files:
        rel_path = Path(uf.filename)  # contains relative path from browser
        dest = PROJECT_DIR / rel_path
        dest.parent.mkdir(parents=True, exist_ok=True)
        with dest.open("wb") as f:
            while chunk := await uf.read(1024 * 1024):
                f.write(chunk)
        saved += 1
    write_meta({"mode": "folder", "root": root, "files": saved})
    return {"ok": True, "message": f"Folder uploaded with {saved} files."}

# ==============================================================================
# Explorer + Editor
# ==============================================================================
@app.get("/core/status", response_model=Status)
def status():
    return status_dict()

@app.get("/core/tree")
def core_tree(dir: str = ""):
    if not _project_present():
        raise HTTPException(404, detail="No project uploaded")
    base = _safe_join(PROJECT_DIR, dir)
    if not base.exists() or not base.is_dir():
        raise HTTPException(404, detail="Folder not found")

    # os.scandir caches is_file/is_dir from the OS directory listing
    # avoiding a separate stat() call per entry
    with os.scandir(str(base)) as scanner:
        entries = sorted(scanner, key=lambda e: (e.is_file(), e.name.lower()))
        items = [
            {
                "name": e.name,
                "path": str(Path(e.path).relative_to(PROJECT_DIR)),
                "type": "file" if e.is_file() else "dir",
            }
            for e in entries
        ]
    return {"cwd": str(base.relative_to(PROJECT_DIR)), "items": items}

@app.get("/core/file")
def core_file(path: str = Query(..., description="Relative path inside project")):
    if not _project_present():
        raise HTTPException(404, detail="No project uploaded")
    fpath = _safe_join(PROJECT_DIR, path)
    if not fpath.exists() or not fpath.is_file():
        raise HTTPException(404, detail="File not found")
    if fpath.stat().st_size > 1_000_000:
        raise HTTPException(413, detail="File too large to preview")
    content = fpath.read_text(encoding="utf-8", errors="ignore")
    return {"path": path, "content": content}

@app.post("/core/save")
def core_save(
    path: str = Query(..., description="Relative path to save inside project"),
    content: str = Body(..., media_type="text/plain"),
):
    if not _project_present():
        raise HTTPException(404, detail="No project uploaded")
    fpath = _safe_join(PROJECT_DIR, path)
    fpath.parent.mkdir(parents=True, exist_ok=True)
    fpath.write_text(content, encoding="utf-8")
    return {"ok": True, "path": path}

# ==============================================================================
# Plugin certificate helpers
# ==============================================================================
SLUG_RE_CERT = re.compile(r"^[A-Za-z0-9._-]+$")

def _issue_and_store_plugin_cert(slug: str) -> bool:
    """
    Request a persistent certificate from CA Service for *slug* and store it
    alongside the plugin files in  ai_plugins/<slug>/cert/ .

    Returns True on success, False on failure (logged but non-fatal so that
    plugin creation itself still succeeds — the cert can be retried later).
    """
    plugin_dir = (PLUGINS_DIR / slug).resolve()
    cert_dir = plugin_dir / "cert"

    # Safety: slug must be valid and plugin_dir must be inside PLUGINS_DIR
    if not SLUG_RE_CERT.match(slug):
        log.warning("[CERT] Invalid slug for cert issuance: %s", slug)
        return False
    if PLUGINS_DIR.resolve() not in plugin_dir.parents:
        log.warning("[CERT] Path traversal detected for slug: %s", slug)
        return False

    # Already has a cert – skip
    if (cert_dir / "cert.pem").exists() and (cert_dir / "key.pem").exists():
        log.info("[CERT] Plugin '%s' already has a certificate — skipping issuance", slug)
        return True

    try:
        resp = http_requests.post(
            f"{CA_SERVICE_URL}/issue-cert",
            json={"plugin_id": slug, "persistent": True},
            timeout=10,
        )
        if resp.status_code != 200:
            log.error("[CERT] CA Service returned %s for '%s': %s", resp.status_code, slug, resp.text)
            return False

        data = resp.json()
        cert_pem = data["certificate_pem"]
        key_pem = data["plugin_private_key_pem"]
        serial_number = data.get("serial_number", "")
        expires_at = data.get("expires_at", "")

        cert_dir.mkdir(parents=True, exist_ok=True)
        (cert_dir / "cert.pem").write_text(cert_pem, encoding="utf-8")
        (cert_dir / "key.pem").write_text(key_pem, encoding="utf-8")
        (cert_dir / "meta.json").write_text(
            json.dumps({"serial_number": serial_number, "expires_at": expires_at, "plugin_id": slug}, indent=2),
            encoding="utf-8",
        )
        log.info("[CERT] Persistent certificate issued & stored for plugin '%s' (serial=%s)", slug, serial_number)
        return True

    except Exception as exc:
        log.error("[CERT] Failed to issue cert for plugin '%s': %s", slug, exc)
        return False


# ==============================================================================
# Plugins (files + discovery)
# ==============================================================================
@app.post("/core/plugin/new")
def create_plugin(
    path: str = Query(..., description="Relative path under ai_plugins/"),
    content: str = Body(..., media_type="text/plain"),
):
    dest = _safe_join(PLUGINS_DIR, path)
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_text(content, encoding="utf-8")

    # ── Auto-issue certificate when plugin becomes complete ──────────
    # A plugin is "complete" when its directory contains manifest.json.
    # We issue the cert once and never again (idempotent).
    parts = Path(path).parts
    if len(parts) >= 1:
        slug = parts[0]  # e.g. "my-plugin" from "my-plugin/manifest.json"
        plugin_dir = (PLUGINS_DIR / slug).resolve()
        if (plugin_dir / "manifest.json").exists():
            _issue_and_store_plugin_cert(slug)

    return {"ok": True, "path": str(dest.relative_to(PROJECT_DIR))}

@app.get("/core/plugins")
def list_plugins():
    out = []
    if not PLUGINS_DIR.exists():
        return {"plugins": out}
    # Plugins are always exactly one level deep: ai_plugins/<slug>/manifest.json
    # Use os.scandir for a single shallow scan instead of recursive rglob
    with os.scandir(str(PLUGINS_DIR)) as scanner:
        for entry in scanner:
            if not entry.is_dir():
                continue
            mf = Path(entry.path) / "manifest.json"
            if not mf.exists():
                continue
            try:
                data = json.loads(mf.read_text(encoding="utf-8"))
                name = data.get("name") or entry.name
                out.append({
                    "name": name,
                    "title": data.get("title", name),
                    "path": entry.name,
                    "entry": data.get("entry", "entry.js"),
                    "runtime": data.get("runtime", "browser"),
                    "permissions": data.get("permissions", []),
                })
            except Exception:
                pass
    return {"plugins": out}

# ==============================================================================
# Node project discovery + start helpers (HOST mode)
# ==============================================================================
def _read_package_json(root: Path) -> dict:
    try:
        return json.loads((root / "package.json").read_text(encoding="utf-8"))
    except Exception:
        return {}

def _node_candidates(max_depth: int = 3) -> List[Path]:
    if not PROJECT_DIR.exists():
        return []
    out: List[Path] = []
    for pkg in PROJECT_DIR.rglob("package.json"):
        if "node_modules" in pkg.parts:
            continue
        try:
            rel = pkg.parent.relative_to(PROJECT_DIR)
        except ValueError:
            continue
        if len(rel.parts) <= max_depth:
            out.append(rel)
    return sorted(out, key=lambda p: (len(p.parts), str(p)))

def _pick_best_node_root(candidates: List[Path]) -> Optional[Path]:
    best = None
    best_score = -10_000
    for rel in candidates:
        root = PROJECT_DIR / rel
        pkg = _read_package_json(root)
        scripts = pkg.get("scripts") or {}

        score = 0
        name = rel.name.lower()
        if name in ("frontend", "web", "app", "ui"): score += 3
        if "start" in scripts: score += 3
        if "dev" in scripts: score += 2
        if (root / "server.js").exists() or (root / "index.js").exists() or (root / "app.js").exists():
            score += 1
        score -= len(rel.parts)
        if score > best_score:
            best_score = score
            best = root
    return best

def _node_project_root(subdir: Optional[str]) -> Optional[Path]:
    if subdir:
        cand = (PROJECT_DIR / subdir)
        if (cand / "package.json").exists():
            return cand
    cands = _node_candidates()
    return _pick_best_node_root(cands)

@app.get("/core/node-candidates")
def node_candidates():
    return {"candidates": [str(p).replace("\\", "/") for p in _node_candidates()]}

def _ensure_node_deps(root: Path):
    npm = _which(_npm_exe())
    if not npm:
        raise HTTPException(500, detail="`npm` not found on PATH. Install Node.js and start uvicorn from that terminal.")
    cmd = [npm, "ci"] if (root / "package-lock.json").exists() else [npm, "install"]
    rc = _run(cmd, cwd=root, timeout=1800)
    if rc != 0:
        raise HTTPException(500, detail=f"`{' '.join(cmd)}` failed in {root}. See /core/build-log.")

def _pick_node_start_command(pkg: dict, root: Path) -> List[str]:
    scripts = (pkg.get("scripts") or {})
    npm = _which(_npm_exe()) or _npm_exe()
    node = _which(_node_exe()) or _node_exe()
    if "start" in scripts: return [npm, "run", "start"]
    if "dev"   in scripts: return [npm, "run", "dev"]
    if "serve" in scripts: return [npm, "run", "serve"]
    for entry in ("server.js", "index.js", "app.js"):
        if (root / entry).exists():
            return [node, entry]
    raise HTTPException(400, detail=f"No start/dev script or server.js/index.js/app.js found in {root}")

# ==============================================================================
# Start (single app) – Node (host) or Java (fallback) on HOST
# ==============================================================================
def _start_java(port: Optional[int]) -> dict:
    jar = find_runnable_jar()
    if not jar:
        raise HTTPException(404, detail="No runnable JAR found.")
    if is_running():
        return {"ok": True, "message": "Core already running.", "pid": read_pid(), "jar": str(jar)}

    extra_args: List[str] = []
    if port:
        extra_args.append(f"--server.port={port}")

    try:
        proc = subprocess.Popen(
            ["java", "-jar", str(jar), *extra_args],
            cwd=str(jar.parent),
            stdout=subprocess.DEVNULL, stderr=subprocess.STDOUT,
        )
        write_pid(proc.pid)
        return {"ok": True, "pid": proc.pid, "jar": str(jar),
                "app_url": f"http://localhost:{port}" if port else None}
    except FileNotFoundError:
        raise HTTPException(500, detail="`java` not found on PATH.")
    except Exception as e:
        raise HTTPException(500, detail=f"Failed to start core: {e}")

@app.post("/core/start")
def start_core(
    port: Optional[int] = Query(None, description="Only for preview if your dev server listens on this port"),
    prefer: Optional[str] = Query(None, description="Force 'node' or 'java'"),
    subdir: Optional[str] = Query(None, description="Node app subdir (contains package.json)"),
):
    node_root = _node_project_root(subdir)

    try_node_first = (prefer == "node") or (prefer is None and node_root is not None)
    try_java_first = (prefer == "java")

    if try_node_first and node_root:
        _ensure_node_deps(node_root)
        cmd = _pick_node_start_command(_read_package_json(node_root), node_root)
        env = os.environ.copy()
        if port:
            env["PORT"] = str(port)
        try:
            proc = subprocess.Popen(
                cmd, cwd=str(node_root), env=env,
                stdout=subprocess.DEVNULL, stderr=subprocess.STDOUT,
            )
            write_pid(proc.pid)  # legacy single PID
            return {
                "ok": True,
                "pid": proc.pid,
                "node_root": str(node_root),
                "app_url": f"http://localhost:{port}" if port else None,
            }
        except FileNotFoundError:
            raise HTTPException(500, detail="Failed to execute npm/node. Ensure Node.js is installed.")
        except Exception as e:
            raise HTTPException(500, detail=f"Failed to start Node app: {e}")

    # Fallback: Java
    return _start_java(port)

# ==============================================================================
# Start BOTH (host mode)
# ==============================================================================
PIDS_FILE = STORAGE_DIR / "pids.json"

def _read_pids() -> Dict[str, int]:
    if PIDS_FILE.exists():
        try:
            return json.loads(PIDS_FILE.read_text(encoding="utf-8"))
        except Exception:
            return {}
    return {}

def _write_pids(pids: Dict[str, int]) -> None:
    PIDS_FILE.write_text(json.dumps(pids, indent=2), encoding="utf-8")

def _add_pid(key: str, pid: int) -> None:
    p = _read_pids()
    p[key] = pid
    _write_pids(p)

def _clear_pids() -> None:
    try:
        PIDS_FILE.unlink(missing_ok=True)
    except Exception:
        pass

@app.post("/core/start-both")
def start_both(req: StartBothReq):
    if not req.subdirs:
        raise HTTPException(400, detail="Provide at least one subdir")
    if not PROJECT_DIR.exists():
        raise HTTPException(404, detail="No project uploaded")

    started: Dict[str, int] = {}
    app_urls: Dict[str, str] = {}

    for rel in req.subdirs:
        rel = rel.strip().strip("/").replace("\\", "/")
        root = (PROJECT_DIR / rel).resolve()
        if not str(root).startswith(str(PROJECT_DIR.resolve())):
            raise HTTPException(400, detail=f"Invalid subdir: {rel}")
        if not (root / "package.json").exists():
            raise HTTPException(404, detail=f"package.json not found in {rel}")

        _ensure_node_deps(root)
        cmd = _pick_node_start_command(_read_package_json(root), root)

        try:
            proc = subprocess.Popen(
                cmd, cwd=str(root),
                stdout=subprocess.DEVNULL, stderr=subprocess.STDOUT,
            )
            started[rel] = proc.pid
            _add_pid(rel, proc.pid)
            if req.urls and rel in req.urls:
                app_urls[rel] = req.urls[rel]
        except FileNotFoundError:
            raise HTTPException(500, detail=f"Failed to execute npm/node in {rel}. Is Node.js installed?")
        except Exception as e:
            raise HTTPException(500, detail=f"Failed to start {rel}: {e}")

    if started:
        first_pid = list(started.values())[0]
        write_pid(first_pid)  # for legacy Status.running

    return {"ok": True, "pids": started, "app_urls": app_urls}

# ==============================================================================
# Docker RUN (per-subdir)
# ==============================================================================
def _docker_run_for_subdir(cfg: DockerStartReq) -> Dict[str, str]:
    """
    docker run -d --restart unless-stopped
      --name <name>
      -e KEY=VALUE ...           (we set HOST/BIND/VITE_HOST=0.0.0.0 by default)
      -p host:container ...      (auto: if env PORT=n set but no -p, add n:n)
      -w /app
      -v <PROJECT_DIR/subdir>:/app
      <image> sh -lc "<install> && <start>"
    """
    _ensure_docker()

    # Normalize and validate subdir
    rel = cfg.subdir.strip().strip("/").replace("\\", "/")
    host_path = (PROJECT_DIR / rel).resolve()
    if not str(host_path).startswith(str(PROJECT_DIR.resolve())):
        raise HTTPException(400, detail=f"Invalid subdir: {cfg.subdir}")
    if not (host_path / "package.json").exists():
        raise HTTPException(404, detail=f"package.json not found in {cfg.subdir}")

    # Stable, human-friendly container name from the subdir
    safe_rel = re.sub(r"[\\/]+", "_", rel)
    name = cfg.name or f"safeai_{safe_rel}"
    docker = _docker_exe()

    # --- PRE-CLEAN: remove any existing container with the same name ---
    try:
        probe = subprocess.run(
            [docker, "ps", "-a", "--filter", f"name=^{name}$", "--format", "{{.ID}}"],
            stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, check=False, text=True
        )
        existing_id = (probe.stdout or "").strip()
        if existing_id:
            subprocess.run([docker, "rm", "-f", name], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            try:
                remove_container(rel)
            except Exception:
                pass
    except Exception:
        pass
    # -------------------------------------------------------------------

    # Build base args
    args = [docker, "run", "-d", "--restart", "unless-stopped", "--name", name]

    # ---- Environment defaults + port auto-map ----
    env_map = dict(cfg.env or {})
    env_map.setdefault("HOST", "0.0.0.0")
    env_map.setdefault("BIND", "0.0.0.0")
    env_map.setdefault("VITE_HOST", "0.0.0.0")

    # If a PORT exists but no -p mapping provided, add host:container
    auto_ports = list(cfg.ports or [])
    if "PORT" in env_map:
        try:
            p = int(str(env_map["PORT"]).strip())
            already = any(
                str(p) == part.split(":")[0] or str(p) == part.split(":")[-1]
                for part in auto_ports
            )
            if not already:
                auto_ports.append(f"{p}:{p}")
        except Exception:
            pass

    # Apply envs
    for k, v in env_map.items():
        args += ["-e", f"{k}={v}"]

    # Apply port mappings (now that auto_ports is finalized)
    for p in auto_ports:
        args += ["-p", p]

    # Workdir + bind mount
    args += ["-w", cfg.workdir, "-v", f"{str(host_path)}:{cfg.workdir}"]

    # Image + command (install then start)
    cmd = f"{cfg.install} && {cfg.start}"
    args += [cfg.image, "sh", "-lc", cmd]

    _append_log(f"DOCKER: {' '.join(args)}")
    proc = subprocess.run(args, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, check=False, text=True)
    out = (proc.stdout or "").strip()
    with BUILD_LOG.open("a", encoding="utf-8") as f:
        f.write(out + "\n")

    if proc.returncode != 0 or not out:
        raise HTTPException(500, detail=f"Docker failed to run {cfg.subdir}: {out or proc.returncode}")

    container_id = out.splitlines()[-1].strip()  # docker prints the new id on success
    add_container(rel, container_id, info={
        "name": name,
        "image": cfg.image,
        "ports": auto_ports,
        "workdir": cfg.workdir
    })
    return {"id": container_id, "name": name}

@app.post("/core/docker/start", summary="Run ONE uploaded subdir inside a Docker container")
def docker_start(cfg: DockerStartReq):
    res = _docker_run_for_subdir(cfg)
    return {"ok": True, "container": res}

@app.post("/core/docker/start-both", summary="Run MANY uploaded subdirs inside Docker containers")
def docker_start_many(req: DockerStartManyReq):
    started = {}
    for app_cfg in req.apps:
        res = _docker_run_for_subdir(app_cfg)
        started[app_cfg.subdir] = res
    return {"ok": True, "containers": started}

@app.get("/core/docker/containers")
def docker_containers():
    return {"containers": read_containers()}

# ---- Simple helper to convert port mappings to http://localhost URLs ----
def _ports_to_urls(ports: List[str] | None) -> List[str]:
    urls: List[str] = []
    for m in (ports or []):
        try:
            host, _cont = m.split(":", 1)
            if host.isdigit():
                urls.append(f"http://localhost:{host}")
        except Exception:
            continue
    return urls

@app.get("/core/docker/urls")
def docker_urls():
    """
    Returns subdir -> [http://localhost:<port>, ...] from our recorded -p mappings.
    """
    out = {}
    data = read_containers()
    for rel, rec in (data or {}).items():
        ports = (rec or {}).get("ports") or []
        out[rel] = _ports_to_urls(ports)
    return {"urls": out}

@app.get("/core/docker/ready", summary="Instant single-probe: is localhost:port responding?")
def docker_ready(
    port: int = Query(..., description="Host port to probe"),
):
    """
    Non-blocking single probe — tries to connect to http://127.0.0.1:<port>
    once with a short timeout. Returns {"ready": true/false} immediately.
    The frontend should call this repeatedly on a short interval.
    """
    import http.client

    conn: http.client.HTTPConnection | None = None
    try:
        conn = http.client.HTTPConnection("127.0.0.1", port, timeout=1)
        conn.request("HEAD", "/")
        conn.getresponse()
        return {"ready": True, "port": port}
    except Exception:
        return {"ready": False, "port": port}
    finally:
        if conn:
            try:
                conn.close()
            except Exception:
                pass


@app.post("/core/docker/stop", summary="Stop & remove ONE container by subdir")
def docker_stop(subdir: str = Query(..., description="The subdir key you used when starting")):
    _ensure_docker()
    rel = subdir.strip().strip("/").replace("\\", "/")
    rec = read_containers().get(rel)
    if not rec:
        raise HTTPException(404, detail=f"No container recorded for {rel}")
    cid = rec.get("id")
    if not cid:
        raise HTTPException(404, detail=f"No container id stored for {rel}")
    docker = _docker_exe()
    subprocess.run([docker, "stop", cid], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    subprocess.run([docker, "rm", "-f", cid], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    remove_container(rel)
    return {"ok": True, "stopped": rel, "id": cid}

@app.post("/core/docker/stop-all", summary="Stop & remove ALL recorded containers")
def docker_stop_all():
    _ensure_docker()
    docker = _docker_exe()
    data = read_containers()
    for rel, rec in list(data.items()):
        cid = (rec or {}).get("id")
        if not cid:
            continue
        subprocess.run([docker, "stop", cid], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        subprocess.run([docker, "rm", "-f", cid], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        remove_container(rel)
    return {"ok": True, "message": "All containers stopped/removed."}

# ==============================================================================
# Stop core system (host-mode processes)
# ==============================================================================
@app.post("/core/stop")
def stop_core():
    # Kill multi-PIDs
    pids_file = STORAGE_DIR / "pids.json"
    if pids_file.exists():
        try:
            pids = json.loads(pids_file.read_text(encoding="utf-8"))
        except Exception:
            pids = {}
    else:
        pids = {}

    for key, pid in list(pids.items()):
        try:
            import psutil
            p = psutil.Process(pid)
            p.terminate()
            try:
                p.wait(timeout=8)
            except Exception:
                p.kill()
        except Exception:
            pass
    try:
        pids_file.unlink(missing_ok=True)
    except Exception:
        pass

    # Kill legacy single PID
    pid = read_pid()
    if pid:
        try:
            import psutil
            p = psutil.Process(pid)
            p.terminate()
            try:
                p.wait(timeout=8)
            except Exception:
                p.kill()
        except Exception:
            pass
        finally:
            clear_pid()

    return {"ok": True, "message": "Stopped all host processes."}

# ==============================================================================
# Delete / Reset
# ==============================================================================
@app.delete("/core/file")
def core_delete(
    path: str = Query(..., description="Relative path inside project"),
    recursive: bool = Query(False, description="Allow deleting non-empty folders"),
):
    if not _project_present():
        raise HTTPException(404, detail="No project uploaded")

    target = _safe_join(PROJECT_DIR, path)
    if not target.exists():
        raise HTTPException(404, detail="Path not found")

    if target.is_file():
        target.unlink(missing_ok=True)
        return {"ok": True, "deleted": path, "type": "file"}

    try:
        if recursive:
            shutil.rmtree(target)
        else:
            next(target.iterdir())  # raises StopIteration if empty
            raise HTTPException(400, detail="Directory not empty. Use recursive=true.")
        return {"ok": True, "deleted": path, "type": "dir", "recursive": recursive}
    except StopIteration:
        target.rmdir()
        return {"ok": True, "deleted": path, "type": "dir", "recursive": False}

@app.post("/core/reset")
def core_reset():
    # Stop host processes
    try:
        stop_core()
    except Exception:
        pass

    # Stop all docker containers we tracked
    try:
        docker_stop_all()
    except Exception:
        pass

    # Clear uploaded project
    reset_project_dir()

    # Remove legacy artifacts
    try: JAR_FILE.unlink(missing_ok=True)
    except Exception: pass
    try: META_FILE.unlink(missing_ok=True)
    except Exception: pass
    try: clear_containers()
    except Exception: pass

    return {"ok": True, "message": "Project cleared."}


# ==============================================================================
# call plugins
# ==============================================================================

app.include_router(plugins_router, prefix="/core/plugins", tags=["plugins"])
app.include_router(file_router)

@app.get("/healthz")
def healthz():
    return {"ok": True}