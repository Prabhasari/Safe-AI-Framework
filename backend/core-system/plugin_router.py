from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
import requests

from plugin_manager import start_plugin_container, stop_plugin_container, get_plugin_host_port

router = APIRouter()

class StartPayload(BaseModel):
    slug: str
    reuse: bool = True
    instance_id: str | None = None
    mem_limit: str | None = "512m"

@router.post("/start")
def start_plugin(body: StartPayload):
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

        # ✅ if runner fails, return its text/json in detail
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
