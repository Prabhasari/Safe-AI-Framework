from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
import json
import requests

from plugin_manager import start_plugin_container, stop_plugin_container, get_plugin_host_port, delete_plugin, list_running_plugins, PLUGINS_ROOT
from interface_enforcer import enforce_interface

router = APIRouter()

# ---------------------------------------------------------------------------
# Plugin certificate retrieval
# ---------------------------------------------------------------------------
@router.get("/{slug}/cert")
def get_plugin_cert(slug: str):
    """
    Return the stored persistent certificate for a plugin.
    Used by the Secure Gateway to load the cert at run time
    instead of requesting a fresh one from the CA.

    ALL three files (cert.pem, key.pem, meta.json) must be present.
    If any file is missing the plugin is considered unauthorized.
    """
    plugin_dir = (PLUGINS_ROOT / slug).resolve()

    # Path-traversal guard
    if PLUGINS_ROOT.resolve() not in plugin_dir.parents:
        raise HTTPException(status_code=400, detail="Invalid slug")
    if not plugin_dir.exists():
        raise HTTPException(status_code=404, detail=f"Plugin '{slug}' not found")

    cert_file = plugin_dir / "cert" / "cert.pem"
    key_file  = plugin_dir / "cert" / "key.pem"
    meta_file = plugin_dir / "cert" / "meta.json"

    # --- All three cert artefacts are required ---
    missing = []
    if not cert_file.exists():
        missing.append("cert.pem")
    if not key_file.exists():
        missing.append("key.pem")
    if not meta_file.exists():
        missing.append("meta.json")

    if missing:
        raise HTTPException(
            status_code=404,
            detail=(
                f"Plugin '{slug}' is missing certificate files: {', '.join(missing)}. "
                "Certificates are only issued at plugin-creation time. "
                "Please re-create the plugin."
            )
        )

    # --- Load and validate meta.json identity ---
    try:
        meta = json.loads(meta_file.read_text(encoding="utf-8"))
    except Exception as exc:
        raise HTTPException(
            status_code=500,
            detail=f"Failed to parse meta.json for plugin '{slug}': {exc}"
        )

    meta_plugin_id = meta.get("plugin_id")
    if meta_plugin_id and meta_plugin_id != slug:
        raise HTTPException(
            status_code=400,
            detail=(
                f"Certificate identity mismatch for plugin '{slug}': "
                f"meta.json plugin_id is '{meta_plugin_id}'"
            )
        )

    return {
        "cert_pem": cert_file.read_text(encoding="utf-8"),
        "key_pem": key_file.read_text(encoding="utf-8"),
        "meta": meta,
    }

class StartPayload(BaseModel):
    slug: str
    reuse: bool = True
    instance_id: str | None = None
    mem_limit: str | None = "512m"

@router.post("/start")
def start_plugin(body: StartPayload):
    # --- Guard: plugin folder must exist before enforcement ---
    plugin_path = PLUGINS_ROOT / body.slug
    if not plugin_path.exists():
        raise HTTPException(
            status_code=404,
            detail=f"Plugin '{body.slug}' not found in {PLUGINS_ROOT}"
        )
    # --- Interface Enforcement ---
    plugin_path = PLUGINS_ROOT / body.slug
    try:
        enforce_interface(plugin_path)
    except ValueError as ve:
        raise HTTPException(status_code=400, detail=f"Interface validation failed: {ve}")

    try:
        c = start_plugin_container(
            slug=body.slug,
            reuse=body.reuse,
            instance_id=body.instance_id,
            mem_limit=body.mem_limit or "512m",
        )
        host_port = get_plugin_host_port(c)
        return {
            "ok": True,
            "slug": body.slug,
            "host_port": host_port,
            "base_url": f"http://127.0.0.1:{host_port}"
        }
    except FileNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


class RunPayload(BaseModel):
    slug: str
    input: dict | None = None
    metadata: dict | None = None
    reuse: bool = True
    instance_id: str | None = None
    mem_limit: str | None = "512m"

@router.post("/run")
def run_plugin(body: RunPayload):
    # --- Interface Enforcement ---
    plugin_path = PLUGINS_ROOT / body.slug

    # --- Guard: plugin folder must exist before enforcement ---
    if not plugin_path.exists():
        raise HTTPException(
            status_code=404,
            detail=f"Plugin '{body.slug}' not found in {PLUGINS_ROOT}"
        )
    
    try:
        enforce_interface(plugin_path)
    except ValueError as ve:
        raise HTTPException(status_code=400, detail=f"Interface validation failed: {ve}")

    try:
        c = start_plugin_container(
            slug=body.slug,
            reuse=body.reuse,
            instance_id=body.instance_id,
            mem_limit=body.mem_limit or "512m",
        )
        host_port = get_plugin_host_port(c)
        url = f"http://127.0.0.1:{host_port}/run"

        r = requests.post(
            url,
            json={"input": body.input or {}, "metadata": body.metadata or {}},
            timeout=30
        )

        # if runner fails, return its text/json in detail
        if r.status_code >= 400:
            raise HTTPException(
                status_code=500,
                detail=f"Runner error {r.status_code}: {r.text}"
            )

        data = r.json()
        if not data.get("ok"):
            raise HTTPException(status_code=500, detail=data.get("error", "plugin error"))

        return {"ok": True, "slug": body.slug, "result": data.get("result")}

    except HTTPException:
        raise
    except FileNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


class StopPayload(BaseModel):
    slug: str
    instance_id: str | None = None

@router.post("/stop")
def stop_plugin(body: StopPayload):
    try:
        return {"ok": True, "stopped": stop_plugin_container(body.slug, body.instance_id)}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/running")
def get_running_plugins():
    """
    Returns the list of currently running plugin containers with their slug and base URL.
    Used by the frontend to restore the running-plugins list after navigation/reload.
    """
    return {"running": list_running_plugins()}


SECURE_GATEWAY_URL = "http://127.0.0.1:8012"


@router.delete("/{slug}")
def delete_plugin_route(slug: str):
    """
    Stops the plugin container (if running), then permanently deletes the plugin
    folder (manifest.json, entry.js, and all contents) from ai_plugins.
    Path traversal is prevented by plugin_manager.delete_plugin.
    After deleting the folder, removes the plugin record from the Secure Gateway database.
    """
    # Stop the container first — safe to call even if not running
    try:
        stop_plugin_container(slug)
    except Exception as stop_err:
        # Not a fatal error — log and continue with deletion
        print(f"[WARN] Could not stop container for '{slug}' before delete: {stop_err}")

    try:
        delete_plugin(slug)
    except FileNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

    # Best-effort: remove the plugin record from the Secure Gateway database.
    # A 404 means the plugin was never registered there, which is not an error.
    try:
        gw_resp = requests.delete(
            f"{SECURE_GATEWAY_URL}/gateway/plugins/{slug}",
            timeout=5,
        )
        if gw_resp.status_code not in (200, 404):
            # Log but do not fail — the folder is already gone
            print(f"[WARN] Gateway cleanup returned {gw_resp.status_code}: {gw_resp.text}")
    except Exception as gw_err:
        print(f"[WARN] Could not reach Secure Gateway for cleanup: {gw_err}")

    return {"ok": True, "deleted": slug}
