import re
import uuid
from pathlib import Path
import docker

docker_client = docker.from_env()

PLUGINS_ROOT = (Path(__file__).resolve().parents[1] / "storage" / "core_project" / "ai_plugins").resolve()
SLUG_RE = re.compile(r"^[A-Za-z0-9._-]+$")


def _sanitize_slug(slug: str) -> str:
    if not SLUG_RE.match(slug or ""):
        raise ValueError("invalid slug")
    return slug


def _plugin_folder(slug: str) -> Path:
    p = (PLUGINS_ROOT / slug).resolve()
    if not p.exists() or not (p / "entry.js").exists():
        raise FileNotFoundError(f"Plugin '{slug}' not found or missing entry.js")
    if PLUGINS_ROOT not in p.parents:
        raise ValueError("bad path")
    return p


def _find_existing_container(name: str):
    lst = docker_client.containers.list(all=True, filters={"name": name})
    return lst[0] if lst else None


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
        existing = _find_existing_container(base_name)
        if existing:
            existing.reload()
            if existing.status != "running":
                existing.start()
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

    return container


def stop_plugin_container(slug: str, instance_id: str | None = None) -> bool:
    base = f"plugin_{_sanitize_slug(slug)}"
    name = base if not instance_id else f"{base}_{instance_id}"
    c = _find_existing_container(name)
    if not c:
        return False
    try:
        c.stop()
    except Exception:
        pass
    try:
        c.remove(force=True)
    except Exception:
        pass
    return True


def get_plugin_host_port(container) -> str:
    container.reload()
    ports = container.attrs.get("NetworkSettings", {}).get("Ports", {})
    mapping = ports.get("9000/tcp")
    if not mapping or not mapping[0].get("HostPort"):
        raise RuntimeError("no port mapping for 9000/tcp")
    return mapping[0]["HostPort"]
