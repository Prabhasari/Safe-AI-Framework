from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict

import jwt
from cryptography import x509
from cryptography.hazmat.primitives.asymmetric import padding
from cryptography.hazmat.primitives import hashes

from config import JWT_SECRET, JWT_ALG, JWT_TTL_SECONDS

UTC = timezone.utc


def save_root_ca_cert(path: Path, pem: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(pem, encoding="utf-8")


def load_root_ca_cert(path: Path) -> x509.Certificate:
    pem = path.read_text(encoding="utf-8")
    return x509.load_pem_x509_certificate(pem.encode("utf-8"))


def verify_plugin_cert(cert_pem: str, root_ca_cert: x509.Certificate, expected_plugin_id: str) -> None:
    cert = x509.load_pem_x509_certificate(cert_pem.encode("utf-8"))

    cn = cert.subject.get_attributes_for_oid(x509.oid.NameOID.COMMON_NAME)[0].value
    if cn != expected_plugin_id:
        raise ValueError(f"Certificate CN mismatch: expected '{expected_plugin_id}', got '{cn}'")

    now = datetime.now(UTC)
    if now < cert.not_valid_before.replace(tzinfo=UTC) or now > cert.not_valid_after.replace(tzinfo=UTC):
        raise ValueError("Certificate is expired or not yet valid")

    if cert.issuer != root_ca_cert.subject:
        raise ValueError("Certificate issuer is not Root CA")

    root_public_key = root_ca_cert.public_key()
    root_public_key.verify(
        cert.signature,
        cert.tbs_certificate_bytes,
        padding.PKCS1v15(),
        cert.signature_hash_algorithm,
    )


def issue_jwt(plugin_id: str, role: str, declared_intent: str, trust_score: float) -> str:
    now = int(datetime.now(UTC).timestamp())
    payload = {
        "sub": plugin_id,
        "role": role,
        "declared_intent": declared_intent,
        "trust_score": trust_score,
        "iat": now,
        "exp": now + JWT_TTL_SECONDS,
    }
    return jwt.encode(payload, JWT_SECRET, algorithm=JWT_ALG)


def verify_jwt_token(token: str) -> Dict[str, Any]:
    return jwt.decode(token, JWT_SECRET, algorithms=[JWT_ALG])