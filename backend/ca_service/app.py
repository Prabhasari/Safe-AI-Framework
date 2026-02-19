from __future__ import annotations

from pathlib import Path
from fastapi import FastAPI
from pydantic import BaseModel, Field

from crypto_utils import load_or_create_root_ca, issue_plugin_cert

BASE_DIR = Path(__file__).resolve().parent
KEYS_DIR = BASE_DIR / "keys"

app = FastAPI(title="CA Service (Internal PKI)", version="1.0")

root_ca = load_or_create_root_ca(KEYS_DIR)


class IssueCertRequest(BaseModel):
    plugin_id: str = Field(..., min_length=3, max_length=100)
    ttl_hours: int = Field(3, ge=1, le=168)


class IssueCertResponse(BaseModel):
    plugin_private_key_pem: str
    certificate_pem: str
    expires_at: str


@app.get("/root-ca")
def get_root_ca():
    return {"root_ca_pem": root_ca.cert_pem}


@app.post("/issue-cert", response_model=IssueCertResponse)
def issue_cert(req: IssueCertRequest):
    plugin_key_pem, plugin_cert_pem, expires_at = issue_plugin_cert(
        root_key_pem=root_ca.key_pem,
        root_cert_pem=root_ca.cert_pem,
        plugin_id=req.plugin_id,
        ttl_hours=req.ttl_hours,
    )
    return IssueCertResponse(
        plugin_private_key_pem=plugin_key_pem,
        certificate_pem=plugin_cert_pem,
        expires_at=expires_at,
    )