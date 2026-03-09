import time
import re
import uuid
import shutil
from pathlib import Path
import docker

docker_client = docker.from_env()

PLUGINS_ROOT = (Path(__file__).resolve().parents[1] / "storage" / "core_project" / "ai_plugins").resolve()
SLUG_RE = re.compile(r"^[A-Za-z0-9._-]+$")


def _sanitize_slug(slug: str) -> str:
    if not SLUG_RE.match(slug or ""):
        raise ValueError(f"Invalid plugin slug: {slug!r}")
    return slug


def _plugin_folder(slug: str) -> Path:
    p = (PLUGINS_ROOT / slug).resolve()
    if not p.exists() or not (p / "entry.js").exists():
        raise FileNotFoundError(f"Plugin folder not found or missing entry.js: {p}")
    if PLUGINS_ROOT not in p.parents:
        raise ValueError(f"Path traversal detected: {p}")
    return p


def _find_existing_container(name: str):
    lst = docker_client.containers.list(all=True, filters={"name": name})
    return lst[0] if lst else None

# ---------------------------------------------------------------------------
# NEW: wait until the container has bound its port
# ---------------------------------------------------------------------------
def _wait_for_port(container, inner_port: str = "9000/tcp", timeout: int = 15) -> str:
    """
    Poll the container's port bindings until the host port appears or timeout.
    Returns the host port string.
    Raises RuntimeError if the container never binds the port in time.
    """
    deadline = time.time() + timeout
    while time.time() < deadline:
        container.reload()                          # refresh attrs from Docker daemon
        state = container.attrs.get("State", {})

        # If container exited/crashed stop waiting immediately
        if state.get("Status") in ("exited", "dead"):
            logs = container.logs(tail=30).decode("utf-8", errors="replace")
            raise RuntimeError(
                f"Container '{container.name}' stopped unexpectedly.\n"
                f"Last logs:\n{logs}"
            )

        ports = container.attrs.get("NetworkSettings", {}).get("Ports", {})
        bindings = ports.get(inner_port)
        if bindings:
            host_port = bindings[0].get("HostPort")
            if host_port:
                return host_port

        time.sleep(0.4)

    # Timed out — collect logs to help debug
    try:
        logs = container.logs(tail=30).decode("utf-8", errors="replace")
    except Exception:
        logs = "<unavailable>"
    raise RuntimeError(
        f"Container '{container.name}' did not bind port {inner_port} "
        f"within {timeout}s.\nLast logs:\n{logs}"
    )

def start_plugin_container(
    slug: str,
    reuse: bool = True,
    instance_id: str | None = None,
    mem_limit: str = "512m"
):
    """
    reuse=True  -> one long-lived container per slug
    reuse=False -> new container each call
    """
    slug = _sanitize_slug(slug)
    folder = _plugin_folder(slug)

    base_name = f"plugin_{slug}"
    name = base_name if reuse else f"{base_name}_{instance_id or uuid.uuid4().hex[:8]}"

    if reuse:
        existing = _find_existing_container(name)
        if existing:
            existing.reload()
            if existing.attrs["State"]["Status"] != "running":
                existing.start()
            _wait_for_port(existing)
            return existing


    volumes = {
        str(folder): {"bind": "/plugin", "mode": "ro"}
    }

    # publish container 9000 to a random host port
    ports = {"9000/tcp": None}

    container = docker_client.containers.run(
        image="ai-plugin-runner:1",
        name=name,
        detach=True,
        environment={"PLUGIN_DIR": "/plugin", "ENTRY": "entry.js", "TIMEOUT_MS": "8000"},
        volumes=volumes,
        ports=ports,
        mem_limit=mem_limit
    )

    _wait_for_port(container)
    return container


def stop_plugin_container(slug: str, instance_id: str | None = None) -> bool:
    slug = _sanitize_slug(slug)
    base_name = f"plugin_{slug}"
    name = base_name if instance_id is None else f"{base_name}_{instance_id}"
    existing = _find_existing_container(name)
    if not existing:
        return False
    existing.stop()
    existing.remove()
    return True


def get_plugin_host_port(container) -> str:
    """
    Read the host port from an already-started (and port-bound) container.
    Raises RuntimeError if the port mapping is missing.
    """
    container.reload()
    ports = container.attrs.get("NetworkSettings", {}).get("Ports", {})
    bindings = ports.get("9000/tcp")
    if not bindings:
        raise RuntimeError(
            f"Container '{container.name}' has no port binding for 9000/tcp. "
            f"Full ports dict: {ports}"
        )
    host_port = bindings[0].get("HostPort")
    if not host_port:
        raise RuntimeError(
            f"Container '{container.name}' port binding exists but HostPort is empty."
        )
    return host_port


def delete_plugin(slug: str) -> Path:
    """
    Deletes the plugin directory for the given slug recursively.
    Returns the path that was deleted.
    Raises FileNotFoundError if the plugin does not exist.
    Raises ValueError on invalid slug or path traversal attempt.
    """
    slug = _sanitize_slug(slug)
    p = (PLUGINS_ROOT / slug).resolve()
    # Prevent path traversal: p must be a direct child of PLUGINS_ROOT
    if PLUGINS_ROOT not in p.parents:
        raise ValueError(f"Path traversal detected: {p}")
    if not p.exists():
        raise FileNotFoundError(f"Plugin '{slug}' not found.")
    shutil.rmtree(p)
    return p


def list_running_plugins() -> list[dict]:
    """
    Returns a list of currently running plugin containers.
    Each entry: { "slug": str, "host_port": str, "base_url": str, "name": str }
    """
    results = []
    try:
        containers = docker_client.containers.list(
            filters={"name": "plugin_", "status": "running"}
        )
        for c in containers:
            # Container names start with "plugin_<slug>" (Docker prepends "/")
            raw_name = c.name.lstrip("/")
            if not raw_name.startswith("plugin_"):
                continue
            # Extract slug: strip the "plugin_" prefix; for reuse=False names like
            # "plugin_<slug>_<hex>" we still want the slug portion.
            remainder = raw_name[len("plugin_"):]
            # The slug cannot contain "_" only by the SLUG_RE (it CAN contain "_").
            # The safest heuristic: use the full remainder as slug (reuse=True containers
            # have name == "plugin_<slug>" exactly). For ephemeral ones we surface the
            # full remainder, which is fine for display/stop purposes.
            slug = remainder

            ports = c.attrs.get("NetworkSettings", {}).get("Ports", {})
            bindings = ports.get("9000/tcp")
            if not bindings:
                continue
            host_port = bindings[0].get("HostPort")
            if not host_port:
                continue

            results.append({
                "slug": slug,
                "host_port": host_port,
                "base_url": f"http://127.0.0.1:{host_port}",
                "name": raw_name,
            })
    except Exception:
        pass
    return results
