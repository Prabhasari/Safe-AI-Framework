from __future__ import annotations

import logging
import time
from datetime import datetime
from typing import Optional, Dict, Any

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
from models import Base, Plugin, RequestLog, TrustEvent
from auth import save_root_ca_cert, load_root_ca_cert, verify_plugin_cert, issue_jwt, verify_jwt_token, verify_jwt_with_intent
from trust_engine import update_plugin_trust, evaluate_behavior, get_trust_status
from policy_engine import is_allowed, evaluate as policy_evaluate, Decision
from sqlalchemy import func as sa_func, Integer
from fastapi.middleware.cors import CORSMiddleware
from station1_cert_verification import station1
from station2_access_control import station2
import color_logger as clog

# Configure module-level logging so trust/policy engines output to console
logging.basicConfig(level=logging.INFO, format="%(message)s")

app = FastAPI(title="Security Gateway (Auth + Policy + Trust + Proxy)", version="2.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:5173",
        "http://127.0.0.1:5173",
        "http://localhost:5174",
        "http://127.0.0.1:5174",
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


# ============================================================================
# TWO-STATION ARCHITECTURE ENDPOINTS
# ============================================================================

class Station1Request(BaseModel):
    plugin_id: str = Field(..., min_length=3, max_length=120)
    certificate_pem: str
    intent: str = Field(default="read", pattern="^(read|write|execute)$")
    scope: str = Field(default="public", pattern="^(public|protected|private)$")


class Station1Response(BaseModel):
    success: bool
    jwt_token: Optional[str] = None
    trust_score: Optional[float] = None
    expires_in: Optional[int] = None
    next_station: Optional[str] = None
    error: Optional[str] = None
    redirect_to_ca: bool = False


@app.post("/station1/verify-and-issue", response_model=Station1Response)
async def station1_verify_and_issue(req: Station1Request, db: Session = Depends(get_db)):
    """
    Station 1: Certificate Verification & JWT Issuance
    
    Flow:
    1. Plugin provides certificate and declares intent/scope
    2. Verify certificate with CA Service
    3. Calculate trust score based on history
    4. Issue JWT with intent-bound claims
    """
    clog.log_station1_request(req.plugin_id, req.intent, req.scope)
    
    if not req.certificate_pem:
        clog.log_station1_no_cert()
        return Station1Response(
            success=False,
            error="Certificate required. Please obtain certificate from CA first.",
            redirect_to_ca=True
        )
    
    # Process certificate and issue JWT
    success, result, error = await station1.async_process_certificate_and_issue_jwt(
        plugin_id=req.plugin_id,
        certificate_pem=req.certificate_pem,
        intent=req.intent,
        scope=req.scope,
        db=db
    )
    
    if not success:
        clog.log_station1_cert_failed(error)
        return Station1Response(
            success=False,
            error=error,
            redirect_to_ca="Certificate verification failed" in error
        )
    
    clog.log_station1_success(result.get('trust_score'))
    
    return Station1Response(
        success=True,
        jwt_token=result.get("jwt_token"),
        trust_score=result.get("trust_score"),
        expires_in=result.get("expires_in"),
        next_station="/station2/validate-access"
    )


class Station2Request(BaseModel):
    method: str = Field(default="GET")
    path: str = Field(default="/core/")


class Station2Response(BaseModel):
    access_granted: bool
    context: Optional[Dict[str, Any]] = None
    error: Optional[str] = None


@app.post("/station2/validate-access", response_model=Station2Response)
def station2_validate_access(req: Station2Request, request: Request, db: Session = Depends(get_db)):
    """
    Station 2: JWT Validation & Core Access Control
    
    Flow:
    1. Plugin provides JWT from Station 1
    2. Validate JWT signature and claims
    3. Check trust score against scope requirements
    4. Check intent permissions for requested method
    5. Grant or deny core access
    """
    clog.log_station2_request(req.method, req.path)
    
    # Extract JWT from Authorization header
    auth_header = request.headers.get("Authorization", "")
    if not auth_header.startswith("Bearer "):
        clog.log_station2_no_auth()
        return Station2Response(
            access_granted=False,
            error="Missing or invalid Authorization header. Expected: Bearer <jwt_token>"
        )
    
    jwt_token = auth_header.split(" ", 1)[1].strip()
    
    # Validate JWT and check access policy
    access_granted, context, error = station2.validate_jwt_and_check_access(
        jwt_token=jwt_token,
        requested_method=req.method,
        requested_path=req.path,
        db=db
    )
    
    if not access_granted:
        clog.log_station2_denied(error)
        return Station2Response(
            access_granted=False,
            error=error
        )
    
    clog.log_station2_granted(
        context.get('plugin_id'),
        context.get('trust_score'),
        context.get('intent'),
        context.get('scope')
    )
    
    return Station2Response(
        access_granted=True,
        context=context
    )


@app.get("/station1/health")
def station1_health():
    """Health check for Station 1"""
    return {"status": "healthy", "station": "1", "service": "certificate_verification"}


@app.get("/station2/health")
def station2_health():
    """Health check for Station 2"""
    return {"status": "healthy", "station": "2", "service": "access_control"}


@app.post("/auto-enroll")
async def auto_enroll_plugin(
    plugin_id: str,
    intent: str = "execute",
    scope: str = "public",
    db: Session = Depends(get_db)
):
    """
    Automatic enrollment endpoint for testing.
    Simulates the complete flow: CA -> Station 1 -> Station 2
    
    In production, plugins should go through each station manually.
    This is for demonstration and testing purposes.
    """
    try:
        # Step 1: Request certificate from CA Service
        async with httpx.AsyncClient(timeout=10.0) as client:
            ca_response = await client.post(
                f"{CA_SERVICE_URL}/issue-cert",
                json={
                    "plugin_id": plugin_id,
                    "ttl_hours": 24
                }
            )
            
            if ca_response.status_code != 200:
                raise HTTPException(
                    status_code=500,
                    detail=f"CA Service error: {ca_response.text}"
                )
            
            ca_data = ca_response.json()
            certificate_pem = ca_data.get("certificate_pem")
            
            print(f"[AUTO-ENROLL] Step 1 Complete: Certificate issued for {plugin_id}")
        
        # Step 2: Go to Station 1 with certificate
        success, result, error = await station1.async_process_certificate_and_issue_jwt(
            plugin_id=plugin_id,
            certificate_pem=certificate_pem,
            intent=intent,
            scope=scope,
            db=db
        )
        
        if not success:
            raise HTTPException(
                status_code=401,
                detail=f"Station 1 error: {error}"
            )
        
        jwt_token = result.get("jwt_token")
        trust_score = result.get("trust_score")
        
        print(f"[AUTO-ENROLL] Step 2 Complete: JWT issued for {plugin_id}")
        
        # Step 3: Validate JWT at Station 2
        access_granted, context, error = station2.validate_jwt_and_check_access(
            jwt_token=jwt_token,
            requested_method="POST",
            requested_path="/core/plugins/run",
            db=db
        )
        
        if not access_granted:
            raise HTTPException(
                status_code=403,
                detail=f"Station 2 error: {error}"
            )
        
        print(f"[AUTO-ENROLL] Step 3 Complete: JWT validated at Station 2 for {plugin_id}")
        
        return {
            "success": True,
            "message": "Plugin enrolled successfully through two-station flow",
            "plugin_id": plugin_id,
            "jwt_token": jwt_token,
            "trust_score": trust_score,
            "flow_completed": [
                "✓ Step 1: Certificate obtained from CA Service",
                "✓ Step 2: JWT issued by Station 1 (certificate verified)",
                "✓ Step 3: JWT validated by Station 2 (access granted)"
            ],
            "usage": f"Use this JWT in Authorization header: Bearer {jwt_token}",
            "example_request": {
                "method": "POST",
                "url": "/core/plugins/run",
                "headers": {
                    "Authorization": f"Bearer {jwt_token}",
                    "Content-Type": "application/json"
                }
            }
        }
        
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Auto-enrollment failed: {str(e)}"
        )


# ============================================================================
# END TWO-STATION ARCHITECTURE
# ============================================================================


@app.middleware("http")
async def security_middleware(request: Request, call_next):
    path = request.url.path

    if path.startswith("/docs") or path.startswith("/openapi"):
        return await call_next(request)

    # Allow station endpoints, onboard, auto-enroll, metrics, and registry endpoints
    if path.startswith("/station1/") or path.startswith("/station2/") or path.startswith("/onboard") or path.startswith("/auto-enroll") or path.startswith("/metrics") or path.startswith("/registry"):
        return await call_next(request)

    # Determine if authentication is needed
    needs_auth = False
    if path.startswith("/plugins/"):
        needs_auth = True
    elif path.startswith("/core/"):
        # Check if this is a request with Authorization header (plugin request)
        # or a frontend request (no Authorization header)
        if STRICT_CORE_AUTH:
            needs_auth = True
        else:
            # Only require auth if Authorization header is present
            # This maintains backward compatibility with frontend while still
            # validating plugin requests that provide JWT
            needs_auth = request.headers.get("Authorization", "").startswith("Bearer ")

    plugin = None
    if needs_auth:
        db = SessionLocal()
        try:
            # Check for Authorization header
            auth_header = request.headers.get("Authorization", "")
            if not auth_header.startswith("Bearer "):
                # For /plugins/ path, require auth
                if path.startswith("/plugins/"):
                    raise HTTPException(
                        status_code=401,
                        detail={
                            "error": "No authentication token provided",
                            "flow": "two_station_required",
                            "steps": [
                                {"step": 1, "action": "Get certificate from CA Service", "endpoint": f"{CA_SERVICE_URL}/issue-cert"},
                                {"step": 2, "action": "Verify certificate and get JWT from Station 1", "endpoint": "/station1/verify-and-issue"},
                                {"step": 3, "action": "Validate JWT at Station 2", "endpoint": "/station2/validate-access"},
                                {"step": 4, "action": "Use validated JWT to access core", "endpoint": path}
                            ],
                            "message": "Please complete the two-station authentication flow before accessing core resources"
                        }
                    )
                # For /core/ paths without auth header, allow through (frontend)
                else:
                    return await call_next(request)
            
            token = auth_header.split(" ", 1)[1].strip()
            
            # Try to validate with intent-bound JWT (two-station flow)
            try:
                payload = verify_jwt_with_intent(token)
                
                # ── Revoked-plugin gate ──────────────────────────────
                plugin_id_early = payload.get("sub")
                if plugin_id_early:
                    _p = db.get(Plugin, plugin_id_early)
                    if _p and _p.status == "revoked":
                        evaluate_behavior(db, plugin_id_early, path, {
                            "method": request.method, "status_code": 403,
                            "latency_ms": 0, "error_flag": True,
                            "cert_valid": True, "auth_failed": True,
                            "policy_violation": True,
                        })
                        # Invalidate cached JWT
                        _plugin_jwt_cache.pop(plugin_id_early, None)
                        raise HTTPException(
                            status_code=403,
                            detail={
                                "error": "Plugin has been revoked due to trust violations",
                                "flow": "revoked",
                                "message": "Trust score fell below revocation threshold. Full re-authentication via Station 1 required.",
                            }
                        )

                # Validate access through Station 2
                method = request.method
                access_granted, context, error = station2.validate_jwt_and_check_access(
                    jwt_token=token,
                    requested_method=method,
                    requested_path=path,
                    db=db
                )
                
                if not access_granted:
                    # Feed denial into trust engine
                    _denied_pid = payload.get("sub")
                    if _denied_pid:
                        evaluate_behavior(db, _denied_pid, path, {
                            "method": request.method, "status_code": 403,
                            "latency_ms": 0, "error_flag": True,
                            "cert_valid": True, "auth_failed": False,
                            "policy_violation": True,
                        })
                    raise HTTPException(
                        status_code=403,
                        detail={
                            "error": error,
                            "flow": "station2_validation_failed",
                            "message": "JWT validation failed at Station 2. You may need to re-authenticate.",
                            "next_step": "Go to Station 1 to get a new JWT with proper intent/scope"
                        }
                    )
                
                # Extract plugin from validated JWT
                plugin_id = payload.get("sub")
                plugin = db.get(Plugin, plugin_id)
                if not plugin:
                    raise HTTPException(status_code=401, detail="Plugin not found in database")
                
                clog.log_middleware_auth(plugin_id, "two-station")
                    
            except ValueError as e:
                # Feed auth failure for the plugin if we can attribute it
                _fail_pid = _safe_extract_plugin_from_jwt(token)
                if _fail_pid:
                    evaluate_behavior(db, _fail_pid, path, {
                        "method": request.method, "status_code": 401,
                        "latency_ms": 0, "error_flag": True,
                        "cert_valid": False, "auth_failed": True,
                        "policy_violation": False,
                    })

                # Try legacy JWT validation for backward compatibility
                try:
                    plugin = _get_plugin_from_token(request, db)
                    if not plugin:
                        raise HTTPException(status_code=401, detail="Missing/invalid JWT")
                    
                    allowed, reason = is_allowed(plugin, path, request.method)
                    if not allowed:
                        evaluate_behavior(db, plugin.plugin_id, path, {
                            "method": request.method, "status_code": 403,
                            "latency_ms": 0, "error_flag": True,
                            "cert_valid": True, "auth_failed": False,
                            "policy_violation": True,
                        })
                        raise HTTPException(status_code=403, detail=reason)
                    
                    clog.log_middleware_legacy(plugin.plugin_id)
                except HTTPException:
                    raise
                except:
                    raise HTTPException(
                        status_code=401,
                        detail={
                            "error": str(e),
                            "flow": "jwt_invalid",
                            "message": "JWT token is invalid or expired",
                            "next_step": "Get a new JWT from Station 1 (provide certificate if needed)"
                        }
                    )
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

                # ── Zero-Trust: evaluate behaviour with full context ──
                # Normal valid requests will NOT reduce trust.
                # Only anomalies / violations trigger penalties.
                evaluate_behavior(db, plugin.plugin_id, path, {
                    "method": request.method,
                    "status_code": status_code,
                    "latency_ms": latency_ms,
                    "error_flag": error_flag,
                    "cert_valid": True,       # cert already verified at station 1
                    "auth_failed": False,     # auth succeeded to reach here
                    "policy_violation": False, # policy was not violated
                })
            finally:
                db.close()

    return response


def _safe_extract_plugin_from_jwt(token: str) -> Optional[str]:
    """
    Best-effort extraction of plugin_id from a JWT that may be expired
    or malformed.  Used to attribute auth failures to the correct plugin.
    Returns None when attribution is impossible.
    """
    import jwt as pyjwt
    try:
        payload = pyjwt.decode(token, options={"verify_signature": False, "verify_exp": False})
        return payload.get("sub")
    except Exception:
        return None


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


# Store plugin JWT tokens in memory for session management
_plugin_jwt_cache: dict = {}


async def _ensure_plugin_authenticated(slug: str, db: Session) -> tuple:
    """
    Ensure plugin goes through the two-station authentication flow.
    Returns: (success, jwt_token, error_message)
    
    Flow:
    1. Check if plugin already has a valid JWT in cache
    2. If not, get certificate from CA Service
    3. Go to Station 1 to get JWT
    4. Validate JWT at Station 2
    5. Cache the JWT for future requests
    """
    global _plugin_jwt_cache
    
    # Check if plugin has a cached valid JWT
    if slug in _plugin_jwt_cache:
        cached = _plugin_jwt_cache[slug]
        try:
            # Verify JWT is still valid
            payload = verify_jwt_with_intent(cached["jwt_token"])
            # Check if not expired (with 5 minute buffer)
            import datetime
            if payload.get("exp", 0) > datetime.datetime.now(datetime.timezone.utc).timestamp() + 300:
                clog.log_flow_cached_jwt(slug)
                return True, cached["jwt_token"], None
        except:
            # JWT expired or invalid, remove from cache
            del _plugin_jwt_cache[slug]
    
    clog.log_flow_header(slug)
    
    try:
        # ================================================================
        # STEP 1: Get certificate from CA Service
        # ================================================================
        clog.log_flow_step(1, f"Requesting certificate from CA Service for plugin '{slug}'...")
        
        async with httpx.AsyncClient(timeout=10.0) as client:
            ca_response = await client.post(
                f"{CA_SERVICE_URL}/issue-cert",
                json={
                    "plugin_id": slug,
                    "ttl_hours": 24
                }
            )
            
            if ca_response.status_code != 200:
                error_msg = f"CA Service error: {ca_response.text}"
                clog.log_flow_step_failed(1, error_msg)
                return False, None, error_msg
            
            ca_data = ca_response.json()
            certificate_pem = ca_data.get("certificate_pem")
            serial_number = ca_data.get("serial_number")
            
            clog.log_flow_step_success(1, "Certificate issued", {"Serial": serial_number})
        
        # ================================================================
        # STEP 2: Go to Station 1 with certificate to get JWT
        # ================================================================
        clog.log_flow_step(2, "Station 1 - Verifying certificate and issuing JWT...")
        
        success, result, error = await station1.async_process_certificate_and_issue_jwt(
            plugin_id=slug,
            certificate_pem=certificate_pem,
            intent="execute",  # Plugin containers need execute permission
            scope="public",
            db=db
        )
        
        if not success:
            clog.log_flow_step_failed(2, error)
            return False, None, f"Station 1 error: {error}"
        
        jwt_token = result.get("jwt_token")
        trust_score = result.get("trust_score")
        
        clog.log_flow_step_success(2, "JWT issued", {"Trust Score": trust_score})
        
        # ================================================================
        # STEP 3: Validate JWT at Station 2
        # ================================================================
        clog.log_flow_step(3, "Station 2 - Validating JWT for core access...")
        
        access_granted, context, error = station2.validate_jwt_and_check_access(
            jwt_token=jwt_token,
            requested_method="POST",
            requested_path="/core/plugins/run",
            db=db
        )
        
        if not access_granted:
            clog.log_flow_step_failed(3, error)
            return False, None, f"Station 2 error: {error}"
        
        clog.log_flow_step_success(3, "Access granted to core communication", {
            "Plugin ID": context.get('plugin_id'),
            "Intent": context.get('intent'),
            "Scope": context.get('scope')
        })
        
        # ================================================================
        # STEP 4: Cache JWT for future requests
        # ================================================================
        _plugin_jwt_cache[slug] = {
            "jwt_token": jwt_token,
            "trust_score": trust_score,
            "certificate_serial": serial_number
        }
        
        clog.log_flow_complete(slug)
        
        return True, jwt_token, None
        
    except Exception as e:
        clog.log_flow_error(str(e))
        return False, None, str(e)


@app.post("/core/plugins/start")
async def proxy_plugins_start(request: Request, db: Session = Depends(get_db)):
    """
    Proxy to core system for plugin start.
    ENFORCES TWO-STATION FLOW: CA -> Station 1 -> Station 2 -> Core
    """
    payload = await request.json()
    slug = payload.get("slug", "unknown")

    _ensure_plugin_row(db, slug)
    
    # ================================================================
    # ENFORCE TWO-STATION AUTHENTICATION FLOW
    # ================================================================
    success, jwt_token, error = await _ensure_plugin_authenticated(slug, db)
    if not success:
        raise HTTPException(
            status_code=401,
            detail={
                "error": error,
                "message": "Plugin failed two-station authentication flow",
                "plugin_id": slug
            }
        )

    start = time.perf_counter()
    resp = await _proxy_request(request, CORE_SYSTEM_URL, "/core/plugins/start")
    latency_ms = (time.perf_counter() - start) * 1000.0

    error_flag = resp.status_code >= 400
    db.add(RequestLog(
        plugin_id=slug,
        path="/core/plugins/start",
        method="POST",
        status_code=resp.status_code,
        latency_ms=latency_ms,
        error_flag=error_flag,
    ))
    db.commit()

    # Zero-Trust: evaluate behaviour — normal requests will NOT reduce trust
    evaluate_behavior(db, slug, "/core/plugins/start", {
        "method": "POST",
        "status_code": resp.status_code,
        "latency_ms": latency_ms,
        "error_flag": error_flag,
        "cert_valid": True,
        "auth_failed": False,
        "policy_violation": False,
    })
    return resp


@app.post("/core/plugins/run")
async def proxy_plugins_run(request: Request, db: Session = Depends(get_db)):
    """
    Proxy to core system for plugin run.
    ENFORCES TWO-STATION FLOW: CA -> Station 1 -> Station 2 -> Core
    """
    payload = await request.json()
    slug = payload.get("slug", "unknown")

    plugin = _ensure_plugin_row(db, slug)

    # ── Policy Engine: evaluate access before proxying ──────────────
    policy_result = policy_evaluate(
        plugin, "/core/plugins/run", "POST",
        cert_valid=True,
        anomaly_flag=plugin.anomaly_flag,
    )
    if policy_result.decision in (Decision.TEMPORARY_BLOCK, Decision.HARD_BLOCK):
        # Record the policy violation in the trust engine
        evaluate_behavior(db, slug, "/core/plugins/run", {
            "method": "POST", "status_code": 403, "latency_ms": 0,
            "error_flag": True, "cert_valid": True,
            "auth_failed": False, "policy_violation": True,
        })
        raise HTTPException(
            status_code=403,
            detail={
                "error": policy_result.reason,
                "decision": policy_result.decision.value,
                "trust_score": policy_result.trust_score,
                "risk_level": policy_result.risk_level.value,
            }
        )

    # ================================================================
    # ENFORCE TWO-STATION AUTHENTICATION FLOW
    # ================================================================
    success, jwt_token, error = await _ensure_plugin_authenticated(slug, db)
    if not success:
        raise HTTPException(
            status_code=401,
            detail={
                "error": error,
                "message": "Plugin failed two-station authentication flow",
                "plugin_id": slug
            }
        )

    start = time.perf_counter()
    resp = await _proxy_request(request, CORE_SYSTEM_URL, "/core/plugins/run")
    latency_ms = (time.perf_counter() - start) * 1000.0

    error_flag = resp.status_code >= 400
    db.add(RequestLog(
        plugin_id=slug,
        path="/core/plugins/run",
        method="POST",
        status_code=resp.status_code,
        latency_ms=latency_ms,
        error_flag=error_flag,
    ))
    db.commit()

    # Zero-Trust: evaluate behaviour — normal requests will NOT reduce trust
    evaluate_behavior(db, slug, "/core/plugins/run", {
        "method": "POST",
        "status_code": resp.status_code,
        "latency_ms": latency_ms,
        "error_flag": error_flag,
        "cert_valid": True,
        "auth_failed": False,
        "policy_violation": False,
    })
    return resp


@app.post("/core/plugins/stop")
async def proxy_plugins_stop(request: Request, db: Session = Depends(get_db)):
    """
    Proxy to core system for plugin stop.
    ENFORCES TWO-STATION FLOW: CA -> Station 1 -> Station 2 -> Core
    """
    payload = await request.json()
    slug = payload.get("slug", "unknown")

    _ensure_plugin_row(db, slug)
    
    # ================================================================
    # ENFORCE TWO-STATION AUTHENTICATION FLOW
    # ================================================================
    success, jwt_token, error = await _ensure_plugin_authenticated(slug, db)
    if not success:
        raise HTTPException(
            status_code=401,
            detail={
                "error": error,
                "message": "Plugin failed two-station authentication flow",
                "plugin_id": slug
            }
        )

    start = time.perf_counter()
    resp = await _proxy_request(request, CORE_SYSTEM_URL, "/core/plugins/stop")
    latency_ms = (time.perf_counter() - start) * 1000.0

    error_flag = resp.status_code >= 400
    db.add(RequestLog(
        plugin_id=slug,
        path="/core/plugins/stop",
        method="POST",
        status_code=resp.status_code,
        latency_ms=latency_ms,
        error_flag=error_flag,
    ))
    db.commit()

    # Zero-Trust: evaluate behaviour — normal requests will NOT reduce trust
    evaluate_behavior(db, slug, "/core/plugins/stop", {
        "method": "POST",
        "status_code": resp.status_code,
        "latency_ms": latency_ms,
        "error_flag": error_flag,
        "cert_valid": True,
        "auth_failed": False,
        "policy_violation": False,
    })
    return resp


# ============================================================================
# REGISTRY ENDPOINT  (Public plugin listing for frontend)
# ============================================================================

def _human_time_ago(dt: Optional[datetime]) -> str:
    """Convert a datetime to a human-readable '… ago' string."""
    if dt is None:
        return "never"
    from datetime import timezone as _tz
    now = datetime.now(_tz.utc)
    # Ensure dt is offset-aware
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=_tz.utc)
    delta = now - dt
    seconds = int(delta.total_seconds())
    if seconds < 0:
        return "just now"
    if seconds < 60:
        return f"{seconds}s ago"
    minutes = seconds // 60
    if minutes < 60:
        return f"{minutes}m ago"
    hours = minutes // 60
    if hours < 24:
        return f"{hours}h ago"
    days = hours // 24
    return f"{days}d ago"


_STATUS_MAP = {
    "active": "trusted",
    "restricted": "restricted",
    "blocked": "blocked",
    "revoked": "blocked",
}


@app.get("/registry/plugins")
async def registry_plugins(db: Session = Depends(get_db)):
    """
    Public listing of all registered plugins with safe fields only.
    Returns frontend-compatible JSON (no secrets, tokens, or certs).
    """
    plugins = db.query(Plugin).all()
    result = []
    for p in plugins:
        result.append({
            "id": p.plugin_id,
            "role": p.role or "Plugin",
            "intent": p.declared_intent or "—",
            "trustScore": round(p.trust_score, 1),
            "status": _STATUS_MAP.get(p.status, "blocked"),
            "anomalyFlag": p.anomaly_flag,
            "lastActive": _human_time_ago(p.last_request_at),
            "reqRate": f"{p.request_frequency} req/min",
        })
    return result


# ============================================================================
# METRICS ENDPOINTS  (Zero-Trust Observability)
# ============================================================================

@app.get("/metrics/trust")
async def metrics_trust(db: Session = Depends(get_db)):
    """
    Aggregate trust-score statistics across all registered plugins.

    Returns counts per status tier (active / restricted / blocked / revoked),
    the overall average trust score, and a per-plugin breakdown.
    """
    plugins = db.query(Plugin).all()
    total = len(plugins)

    active = sum(1 for p in plugins if p.status == "active")
    restricted = sum(1 for p in plugins if p.status == "restricted")
    blocked = sum(1 for p in plugins if p.status == "blocked")
    revoked = sum(1 for p in plugins if p.status == "revoked")
    avg_trust = round(sum(p.trust_score for p in plugins) / total, 2) if total else 0.0

    breakdown = [
        {
            "plugin_id": p.plugin_id,
            "trust_score": round(p.trust_score, 2),
            "status": p.status,
            "anomaly_flag": p.anomaly_flag,
        }
        for p in plugins
    ]

    return {
        "total_plugins": total,
        "average_trust_score": avg_trust,
        "active_count": active,
        "restricted_count": restricted,
        "blocked_count": blocked,
        "revoked_count": revoked,
        "plugins": breakdown,
    }


@app.get("/metrics/anomalies")
async def metrics_anomalies(db: Session = Depends(get_db)):
    """
    Anomaly and trust-event summary for observability dashboards.
    """
    anomaly_flagged = db.query(sa_func.count()).select_from(Plugin).filter(
        Plugin.anomaly_flag == True  # noqa: E712
    ).scalar() or 0

    total_trust_events = db.query(sa_func.count()).select_from(TrustEvent).scalar() or 0

    penalty_events = db.query(sa_func.count()).select_from(TrustEvent).filter(
        TrustEvent.event_type == "penalty"
    ).scalar() or 0

    recovery_events = db.query(sa_func.count()).select_from(TrustEvent).filter(
        TrustEvent.event_type == "recovery"
    ).scalar() or 0

    # Recent penalties (last 100)
    recent = (
        db.query(TrustEvent)
        .filter(TrustEvent.event_type == "penalty")
        .order_by(TrustEvent.created_at.desc())
        .limit(100)
        .all()
    )
    recent_list = [
        {
            "plugin_id": e.plugin_id,
            "delta": e.delta,
            "score_before": round(e.score_before, 2),
            "score_after": round(e.score_after, 2),
            "detail": e.detail,
            "created_at": e.created_at.isoformat() if e.created_at else None,
        }
        for e in recent
    ]

    return {
        "anomaly_flagged_plugins": anomaly_flagged,
        "total_trust_events": total_trust_events,
        "penalty_events": penalty_events,
        "recovery_events": recovery_events,
        "recent_penalties": recent_list,
    }


@app.get("/metrics/performance")
async def metrics_performance(db: Session = Depends(get_db)):
    """
    Request-level performance metrics from the request_logs table.
    """
    total_requests = db.query(sa_func.count()).select_from(RequestLog).scalar() or 0

    avg_latency = db.query(sa_func.avg(RequestLog.latency_ms)).scalar()
    avg_latency = round(avg_latency, 2) if avg_latency else 0.0

    error_count = db.query(sa_func.count()).select_from(RequestLog).filter(
        RequestLog.error_flag == True  # noqa: E712
    ).scalar() or 0

    error_rate = round(error_count / total_requests * 100, 2) if total_requests else 0.0

    # Per-path breakdown (top 20 by request count)
    path_stats = (
        db.query(
            RequestLog.path,
            sa_func.count().label("count"),
            sa_func.avg(RequestLog.latency_ms).label("avg_latency"),
            sa_func.sum(
                sa_func.cast(RequestLog.error_flag, Integer)
            ).label("errors"),
        )
        .group_by(RequestLog.path)
        .order_by(sa_func.count().desc())
        .limit(20)
        .all()
    )
    per_path = [
        {
            "path": row.path,
            "request_count": row.count,
            "avg_latency_ms": round(row.avg_latency, 2) if row.avg_latency else 0.0,
            "error_count": int(row.errors or 0),
        }
        for row in path_stats
    ]

    return {
        "total_requests": total_requests,
        "average_latency_ms": avg_latency,
        "error_count": error_count,
        "error_rate_percent": error_rate,
        "per_path": per_path,
    }


@app.api_route("/core/{path:path}", methods=["GET", "POST", "PUT", "PATCH", "DELETE"])
async def core_proxy(path: str, request: Request):
    return await _proxy_request(request, CORE_SYSTEM_URL, f"/core/{path}")