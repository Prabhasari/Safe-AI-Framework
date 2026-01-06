from __future__ import annotations

import time
from typing import Optional

import httpx
from fastapi import FastAPI, Depends, HTTPException, Request, Body
from fastapi.responses import Response
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from config import (
    CA_SERVICE_URL,
    CORE_SYSTEM_URL,
    ROOT_CA_CACHE_PATH,
    INITIAL_TRUST_SCORE,
    STRICT_CORE_AUTH,
)
from database import engine, get_db, SessionLocal
from models import Base, Plugin, RequestLog
from auth import save_root_ca_cert, load_root_ca_cert, verify_plugin_cert, issue_jwt, verify_jwt_token
from trust_engine import update_plugin_trust
from policy_engine import is_allowed
from fastapi.middleware.cors import CORSMiddleware

app = FastAPI(title="Security Gateway (Auth + Policy + Trust + Proxy)", version="1.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:5173",
        "http://127.0.0.1:5173",
        "http://localhost:5000",
        "http://127.0.0.1:5000",
        "http://localhost:3000",
        "http://127.0.0.1:3000",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

Base.metadata.create_all(bind=engine)

ROOT_CA_CERT = None


class OnboardRequest(BaseModel):
    plugin_id: str = Field(..., min_length=3, max_length=120)
    plugin_name: str = ""
    role: str = "plugin"
    declared_intent: str = "general"
    certificate_pem: str
    service_base_url: str = ""


class OnboardResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    trust_score: float
    status: str


@app.on_event("startup")
async def startup_load_root_ca():
    global ROOT_CA_CERT

    if ROOT_CA_CACHE_PATH.exists():
        ROOT_CA_CERT = load_root_ca_cert(ROOT_CA_CACHE_PATH)
        return

    async with httpx.AsyncClient() as client:
        r = await client.get(f"{CA_SERVICE_URL}/root-ca")
        r.raise_for_status()
        pem = r.json()["root_ca_pem"]

    save_root_ca_cert(ROOT_CA_CACHE_PATH, pem)
    ROOT_CA_CERT = load_root_ca_cert(ROOT_CA_CACHE_PATH)


def _get_plugin_from_token(request: Request, db: Session) -> Optional[Plugin]:
    auth_header = request.headers.get("Authorization", "")
    if not auth_header.startswith("Bearer "):
        return None

    token = auth_header.split(" ", 1)[1].strip()
    payload = verify_jwt_token(token)
    plugin_id = payload.get("sub")
    if not plugin_id:
        return None

    plugin = db.get(Plugin, plugin_id)
    if not plugin:
        raise HTTPException(status_code=401, detail="Unknown plugin_id")
    return plugin


@app.post("/onboard", response_model=OnboardResponse)
def onboard(req: OnboardRequest, db: Session = Depends(get_db)):
    if ROOT_CA_CERT is None:
        raise HTTPException(status_code=500, detail="Root CA not loaded")

    try:
        verify_plugin_cert(req.certificate_pem, ROOT_CA_CERT, req.plugin_id)
    except Exception as e:
        raise HTTPException(status_code=401, detail=f"Certificate verification failed: {e}")

    plugin = db.get(Plugin, req.plugin_id)
    if not plugin:
        plugin = Plugin(
            plugin_id=req.plugin_id,
            name=req.plugin_name,
            role=req.role,
            declared_intent=req.declared_intent,
            trust_score=INITIAL_TRUST_SCORE,
            status="active",
            service_base_url=req.service_base_url or "",
        )
        db.add(plugin)
        db.commit()
        db.refresh(plugin)
    else:
        plugin.name = req.plugin_name or plugin.name
        plugin.role = req.role or plugin.role
        plugin.declared_intent = req.declared_intent or plugin.declared_intent
        if req.service_base_url:
            plugin.service_base_url = req.service_base_url
        db.commit()
        db.refresh(plugin)

    token = issue_jwt(plugin.plugin_id, plugin.role, plugin.declared_intent, plugin.trust_score)

    return OnboardResponse(
        access_token=token,
        trust_score=plugin.trust_score,
        status=plugin.status,
    )


@app.middleware("http")
async def security_middleware(request: Request, call_next):
    path = request.url.path

    if path.startswith("/docs") or path.startswith("/openapi"):
        return await call_next(request)

    needs_auth = False
    if path.startswith("/plugins/"):
        needs_auth = True
    elif path.startswith("/core/"):
        if STRICT_CORE_AUTH:
            needs_auth = True
        else:
            needs_auth = request.headers.get("Authorization", "").startswith("Bearer ")

    plugin = None
    if needs_auth:
        db = SessionLocal()
        try:
            plugin = _get_plugin_from_token(request, db)
            if not plugin:
                raise HTTPException(status_code=401, detail="Missing/invalid JWT")

            allowed, reason = is_allowed(plugin, path, request.method)
            if not allowed:
                raise HTTPException(status_code=403, detail=reason)
        finally:
            db.close()

    start = time.perf_counter()
    status_code = 500
    error_flag = False

    try:
        response = await call_next(request)
        status_code = response.status_code
        if status_code >= 400:
            error_flag = True
    except Exception:
        error_flag = True
        raise
    finally:
        if plugin and (path.startswith("/core/") or path.startswith("/plugins/")):
            latency_ms = (time.perf_counter() - start) * 1000.0
            db = SessionLocal()
            try:
                db.add(
                    RequestLog(
                        plugin_id=plugin.plugin_id,
                        path=path,
                        method=request.method,
                        status_code=status_code,
                        latency_ms=latency_ms,
                        error_flag=error_flag,
                    )
                )
                db.commit()
                update_plugin_trust(db, plugin.plugin_id)
            finally:
                db.close()

    return response


async def _proxy_request(request: Request, target_base: str, target_path: str) -> Response:
    method = request.method
    body = await request.body()

    headers = dict(request.headers)
    headers.pop("host", None)

    url = f"{target_base}{target_path}"
    if request.url.query:
        url = f"{url}?{request.url.query}"

    async with httpx.AsyncClient(timeout=30.0) as client:
        resp = await client.request(method, url, content=body, headers=headers)

    content_type = resp.headers.get("content-type", "application/json")
    return Response(content=resp.content, status_code=resp.status_code, media_type=content_type)


def _ensure_plugin_row(db: Session, slug: str):
    plugin = db.get(Plugin, slug)
    if not plugin:
        plugin = Plugin(
            plugin_id=slug,                 # use slug as plugin_id for tracking
            name=slug,
            role="runtime_plugin",
            declared_intent="run",
            trust_score=INITIAL_TRUST_SCORE,
            status="active",
            service_base_url=""
        )
        db.add(plugin)
        db.commit()
        db.refresh(plugin)
    return plugin


@app.post("/core/plugins/start")
async def proxy_plugins_start(request: Request, db: Session = Depends(get_db)):
    payload = await request.json()
    slug = payload.get("slug", "unknown")

    _ensure_plugin_row(db, slug)

    start = time.perf_counter()
    resp = await _proxy_request(request, CORE_SYSTEM_URL, "/core/plugins/start")
    latency_ms = (time.perf_counter() - start) * 1000.0

    db.add(RequestLog(
        plugin_id=slug,
        path="/core/plugins/start",
        method="POST",
        status_code=resp.status_code,
        latency_ms=latency_ms,
        error_flag=resp.status_code >= 400,
    ))
    db.commit()

    update_plugin_trust(db, slug)
    return resp


@app.post("/core/plugins/run")
async def proxy_plugins_run(request: Request, db: Session = Depends(get_db)):
    payload = await request.json()
    slug = payload.get("slug", "unknown")

    plugin = _ensure_plugin_row(db, slug)

    # Optional enforcement (only if you want):
    if plugin.status == "blocked":
        raise HTTPException(status_code=403, detail="Plugin blocked by trust policy")

    start = time.perf_counter()
    resp = await _proxy_request(request, CORE_SYSTEM_URL, "/core/plugins/run")
    latency_ms = (time.perf_counter() - start) * 1000.0

    db.add(RequestLog(
        plugin_id=slug,
        path="/core/plugins/run",
        method="POST",
        status_code=resp.status_code,
        latency_ms=latency_ms,
        error_flag=resp.status_code >= 400,
    ))
    db.commit()

    update_plugin_trust(db, slug)
    return resp


@app.post("/core/plugins/stop")
async def proxy_plugins_stop(request: Request, db: Session = Depends(get_db)):
    payload = await request.json()
    slug = payload.get("slug", "unknown")

    _ensure_plugin_row(db, slug)

    start = time.perf_counter()
    resp = await _proxy_request(request, CORE_SYSTEM_URL, "/core/plugins/stop")
    latency_ms = (time.perf_counter() - start) * 1000.0

    db.add(RequestLog(
        plugin_id=slug,
        path="/core/plugins/stop",
        method="POST",
        status_code=resp.status_code,
        latency_ms=latency_ms,
        error_flag=resp.status_code >= 400,
    ))
    db.commit()

    update_plugin_trust(db, slug)
    return resp


@app.api_route("/core/{path:path}", methods=["GET", "POST", "PUT", "PATCH", "DELETE"])
async def core_proxy(path: str, request: Request):
    return await _proxy_request(request, CORE_SYSTEM_URL, f"/core/{path}")