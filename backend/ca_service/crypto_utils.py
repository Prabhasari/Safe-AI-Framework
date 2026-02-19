from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Tuple

from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.x509.oid import NameOID, ExtendedKeyUsageOID

UTC = timezone.utc


@dataclass
class RootCA:
    key_pem: str
    cert_pem: str


def _write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def _read_text(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def load_or_create_root_ca(keys_dir: Path) -> RootCA:
    key_path = keys_dir / "root_ca_key.pem"
    cert_path = keys_dir / "root_ca_cert.pem"

    if key_path.exists() and cert_path.exists():
        return RootCA(key_pem=_read_text(key_path), cert_pem=_read_text(cert_path))

    root_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)

    subject = issuer = x509.Name(
        [
            x509.NameAttribute(NameOID.COUNTRY_NAME, "LK"),
            x509.NameAttribute(NameOID.ORGANIZATION_NAME, "Vibe Secure AI Framework"),
            x509.NameAttribute(NameOID.COMMON_NAME, "Vibe Root CA"),
        ]
    )

    now = datetime.now(UTC)
    root_cert = (
        x509.CertificateBuilder()
        .subject_name(subject)
        .issuer_name(issuer)
        .public_key(root_key.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(now - timedelta(minutes=1))
        .not_valid_after(now + timedelta(days=365 * 5))
        .add_extension(x509.BasicConstraints(ca=True, path_length=None), critical=True)
        .add_extension(
            x509.KeyUsage(
                digital_signature=False,
                content_commitment=False,
                key_encipherment=False,
                data_encipherment=False,
                key_agreement=False,
                key_cert_sign=True,
                crl_sign=True,
                encipher_only=False,
                decipher_only=False,
            ),
            critical=True,
        )
        .sign(private_key=root_key, algorithm=hashes.SHA256())
    )

    key_pem = root_key.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.TraditionalOpenSSL,
        encryption_algorithm=serialization.NoEncryption(),
    ).decode("utf-8")

    cert_pem = root_cert.public_bytes(serialization.Encoding.PEM).decode("utf-8")

    _write_text(key_path, key_pem)
    _write_text(cert_path, cert_pem)

    return RootCA(key_pem=key_pem, cert_pem=cert_pem)


def issue_plugin_cert(
    root_key_pem: str,
    root_cert_pem: str,
    plugin_id: str,
    ttl_hours: int = 3,
) -> Tuple[str, str, str]:
    root_key = serialization.load_pem_private_key(root_key_pem.encode("utf-8"), password=None)
    root_cert = x509.load_pem_x509_certificate(root_cert_pem.encode("utf-8"))

    plugin_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)

    subject = x509.Name(
        [
            x509.NameAttribute(NameOID.ORGANIZATION_NAME, "Vibe Secure AI Framework"),
            x509.NameAttribute(NameOID.COMMON_NAME, plugin_id),
        ]
    )

    now = datetime.now(UTC)
    expires = now + timedelta(hours=ttl_hours)

    plugin_cert = (
        x509.CertificateBuilder()
        .subject_name(subject)
        .issuer_name(root_cert.subject)
        .public_key(plugin_key.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(now - timedelta(minutes=1))
        .not_valid_after(expires)
        .add_extension(x509.BasicConstraints(ca=False, path_length=None), critical=True)
        .add_extension(x509.SubjectAlternativeName([x509.DNSName(plugin_id)]), critical=False)
        .add_extension(x509.ExtendedKeyUsage([ExtendedKeyUsageOID.CLIENT_AUTH]), critical=False)
        .add_extension(
            x509.KeyUsage(
                digital_signature=True,
                content_commitment=False,
                key_encipherment=True,
                data_encipherment=False,
                key_agreement=False,
                key_cert_sign=False,
                crl_sign=False,
                encipher_only=False,
                decipher_only=False,
            ),
            critical=True,
        )
        .sign(private_key=root_key, algorithm=hashes.SHA256())
    )

    plugin_key_pem = plugin_key.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.TraditionalOpenSSL,
        encryption_algorithm=serialization.NoEncryption(),
    ).decode("utf-8")

    plugin_cert_pem = plugin_cert.public_bytes(serialization.Encoding.PEM).decode("utf-8")

    return plugin_key_pem, plugin_cert_pem, expires.isoformat()