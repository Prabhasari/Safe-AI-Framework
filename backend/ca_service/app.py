from __future__ import annotations

from pathlib import Path
from datetime import datetime, timezone
from fastapi import FastAPI, HTTPException, Depends, Request
from pydantic import BaseModel, Field
from typing import Optional, List
from sqlalchemy.orm import Session

from crypto_utils import (
    load_or_create_root_ca, 
    issue_plugin_cert, 
    verify_certificate,
)
from database import (
    engine, get_db, init_db, Base,
    IssuedCertificate, CertificateAuditLog, RevokedCertificate
)
import color_logger as clog

UTC = timezone.utc
BASE_DIR = Path(__file__).resolve().parent
KEYS_DIR = BASE_DIR / "keys"

app = FastAPI(title="CA Service (Internal PKI)", version="2.0")

# Initialize database on startup
@app.on_event("startup")
def startup_event():
    init_db()
    clog.log_startup()

root_ca = load_or_create_root_ca(KEYS_DIR)


class IssueCertRequest(BaseModel):
    plugin_id: str = Field(..., min_length=3, max_length=100)
    ttl_hours: int = Field(3, ge=1, le=168)
    persistent: bool = Field(False, description="If true, certificate is long-lived (100 years) for creation-time issuance")


class IssueCertResponse(BaseModel):
    plugin_private_key_pem: str
    certificate_pem: str
    expires_at: str
    serial_number: str


class VerifyCertRequest(BaseModel):
    certificate_pem: str
    plugin_id: Optional[str] = None


class VerifyCertResponse(BaseModel):
    valid: bool
    plugin_id: Optional[str] = None
    serial_number: Optional[str] = None
    error: Optional[str] = None


class RevokeCertRequest(BaseModel):
    serial_number: str
    reason: Optional[str] = "unspecified"


def _log_audit(db: Session, operation: str, plugin_id: str = None, serial_number: str = None, 
               success: bool = True, details: str = None, ip_address: str = None):
    """Log certificate operation to audit log"""
    audit_entry = CertificateAuditLog(
        operation=operation,
        plugin_id=plugin_id,
        serial_number=serial_number,
        success=success,
        details=details,
        ip_address=ip_address
    )
    db.add(audit_entry)
    db.commit()


@app.get("/root-ca")
def get_root_ca():
    return {"root_ca_pem": root_ca.cert_pem}


@app.post("/issue-cert", response_model=IssueCertResponse)
def issue_cert(req: IssueCertRequest, request: Request, db: Session = Depends(get_db)):
    client_ip = request.client.host if request.client else "unknown"
    
    # For persistent (creation-time) certs, use 100-year validity
    effective_ttl = 100 * 365 * 24 if req.persistent else req.ttl_hours
    
    clog.log_cert_request(req.plugin_id, effective_ttl, client_ip)
    
    try:
        plugin_key_pem, plugin_cert_pem, expires_at, serial_number = issue_plugin_cert(
            root_key_pem=root_ca.key_pem,
            root_cert_pem=root_ca.cert_pem,
            plugin_id=req.plugin_id,
            ttl_hours=effective_ttl,
        )
        
        # Store certificate in database
        cert_record = IssuedCertificate(
            serial_number=serial_number,
            plugin_id=req.plugin_id,
            status="active",
            expires_at=datetime.fromisoformat(expires_at.replace("+00:00", "")),
            cert_pem=plugin_cert_pem
        )
        db.add(cert_record)
        db.commit()
        
        # Log audit entry
        cert_type = "persistent" if req.persistent else "ephemeral"
        _log_audit(
            db=db,
            operation="ISSUE",
            plugin_id=req.plugin_id,
            serial_number=serial_number,
            success=True,
            details=f"Certificate issued ({cert_type}) with TTL {effective_ttl} hours",
            ip_address=client_ip
        )
        
        clog.log_cert_issued(serial_number, expires_at)
        
        return IssueCertResponse(
            plugin_private_key_pem=plugin_key_pem,
            certificate_pem=plugin_cert_pem,
            expires_at=expires_at,
            serial_number=serial_number,
        )
    except Exception as e:
        _log_audit(
            db=db,
            operation="ISSUE",
            plugin_id=req.plugin_id,
            success=False,
            details=str(e),
            ip_address=client_ip
        )
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/verify-cert", response_model=VerifyCertResponse, deprecated=True)
def verify_cert(req: VerifyCertRequest, request: Request, db: Session = Depends(get_db)):
    """
    [DEPRECATED] Verify certificate validity against CA
    
    NOTE: This endpoint is deprecated. Certificate verification should be done 
    LOCALLY at the Secure Gateway using the CA's public key from /root-ca.
    
    The Secure Gateway should:
    1. Verify certificate signature locally using CA's public key
    2. Only call /check-revocation/{serial_number} to check revocation status
    
    This follows proper PKI architecture where verification is distributed.
    """
    client_ip = request.client.host if request.client else "unknown"
    
    clog.log_cert_verify_request(req.plugin_id, client_ip)
    
    try:
        is_valid, result = verify_certificate(
            cert_pem=req.certificate_pem,
            root_ca_cert_pem=root_ca.cert_pem,
            expected_plugin_id=req.plugin_id
        )
        
        if not is_valid:
            clog.log_cert_verify_failed(result)
            _log_audit(
                db=db,
                operation="VERIFY",
                plugin_id=req.plugin_id,
                success=False,
                details=result,
                ip_address=client_ip
            )
            return VerifyCertResponse(valid=False, error=result)
        
        serial_number = result.get('serial_number')
        plugin_id = result.get('plugin_id')
        
        # Check if certificate is revoked
        revoked = db.query(RevokedCertificate).filter(
            RevokedCertificate.serial_number == serial_number
        ).first()
        
        if revoked:
            clog.log_cert_revoked_check(revoked.reason)
            _log_audit(
                db=db,
                operation="VERIFY",
                plugin_id=plugin_id,
                serial_number=serial_number,
                success=False,
                details=f"Certificate revoked: {revoked.reason}",
                ip_address=client_ip
            )
            return VerifyCertResponse(valid=False, error=f"Certificate revoked: {revoked.reason}")
        
        clog.log_cert_verify_success(plugin_id, serial_number)
        
        _log_audit(
            db=db,
            operation="VERIFY",
            plugin_id=plugin_id,
            serial_number=serial_number,
            success=True,
            details="Certificate verified successfully",
            ip_address=client_ip
        )
        
        return VerifyCertResponse(
            valid=True,
            plugin_id=plugin_id,
            serial_number=serial_number
        )
    except Exception as e:
        clog.log_cert_verify_failed(str(e))
        _log_audit(
            db=db,
            operation="VERIFY",
            plugin_id=req.plugin_id,
            success=False,
            details=str(e),
            ip_address=client_ip
        )
        return VerifyCertResponse(valid=False, error=str(e))


@app.post("/revoke-cert")
def revoke_cert(req: RevokeCertRequest, request: Request, db: Session = Depends(get_db)):
    """Revoke a certificate by serial number"""
    client_ip = request.client.host if request.client else "unknown"
    
    clog.log_revoke_request(req.serial_number, req.reason)
    
    try:
        # Check if already revoked
        existing = db.query(RevokedCertificate).filter(
            RevokedCertificate.serial_number == req.serial_number
        ).first()
        
        if existing:
            raise HTTPException(status_code=400, detail="Certificate already revoked")
        
        # Find the certificate
        cert = db.query(IssuedCertificate).filter(
            IssuedCertificate.serial_number == req.serial_number
        ).first()
        
        plugin_id = cert.plugin_id if cert else "unknown"
        
        # Add to revocation list
        revocation = RevokedCertificate(
            serial_number=req.serial_number,
            plugin_id=plugin_id,
            reason=req.reason
        )
        db.add(revocation)
        
        # Update certificate status
        if cert:
            cert.status = "revoked"
            cert.revoked_at = datetime.now(UTC)
            cert.revocation_reason = req.reason
        
        db.commit()
        
        _log_audit(
            db=db,
            operation="REVOKE",
            plugin_id=plugin_id,
            serial_number=req.serial_number,
            success=True,
            details=f"Certificate revoked: {req.reason}",
            ip_address=client_ip
        )
        
        clog.log_revoke_success(plugin_id)
        
        return {"message": "Certificate revoked successfully", "serial_number": req.serial_number}
        
    except HTTPException:
        raise
    except Exception as e:
        _log_audit(
            db=db,
            operation="REVOKE",
            serial_number=req.serial_number,
            success=False,
            details=str(e),
            ip_address=client_ip
        )
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/check-revocation/{serial_number}")
def check_revocation(serial_number: str, db: Session = Depends(get_db)):
    """
    Check if a certificate is revoked.
    
    This endpoint is designed to be called by Secure Gateway Station 1
    after it has verified the certificate locally.
    
    Returns:
    - revoked: bool
    - reason: str (only if revoked)
    """
    revoked = db.query(RevokedCertificate).filter(
        RevokedCertificate.serial_number == serial_number
    ).first()
    
    if revoked:
        clog.log_revocation_check(serial_number, True)
        return {
            "serial_number": serial_number,
            "revoked": True,
            "reason": revoked.reason,
            "revoked_at": revoked.revoked_at.isoformat() if revoked.revoked_at else None
        }
    
    clog.log_revocation_check(serial_number, False)
    return {
        "serial_number": serial_number,
        "revoked": False
    }


# ============================================================================
# ADMIN/QUERY ENDPOINTS
# ============================================================================

@app.get("/certificates")
def list_certificates(
    status: Optional[str] = None,
    plugin_id: Optional[str] = None,
    db: Session = Depends(get_db)
):
    """List all issued certificates with optional filters"""
    query = db.query(IssuedCertificate)
    
    if status:
        query = query.filter(IssuedCertificate.status == status)
    if plugin_id:
        query = query.filter(IssuedCertificate.plugin_id == plugin_id)
    
    certs = query.order_by(IssuedCertificate.issued_at.desc()).all()
    return {"certificates": [cert.to_dict() for cert in certs]}


@app.get("/certificates/{serial_number}")
def get_certificate(serial_number: str, db: Session = Depends(get_db)):
    """Get certificate details by serial number"""
    cert = db.query(IssuedCertificate).filter(
        IssuedCertificate.serial_number == serial_number
    ).first()
    
    if not cert:
        raise HTTPException(status_code=404, detail="Certificate not found")
    
    return cert.to_dict()


@app.get("/audit-log")
def get_audit_log(
    operation: Optional[str] = None,
    plugin_id: Optional[str] = None,
    limit: int = 100,
    db: Session = Depends(get_db)
):
    """Get certificate audit log"""
    query = db.query(CertificateAuditLog)
    
    if operation:
        query = query.filter(CertificateAuditLog.operation == operation)
    if plugin_id:
        query = query.filter(CertificateAuditLog.plugin_id == plugin_id)
    
    logs = query.order_by(CertificateAuditLog.timestamp.desc()).limit(limit).all()
    return {"audit_log": [log.to_dict() for log in logs]}


@app.get("/revoked")
def list_revoked_certificates(db: Session = Depends(get_db)):
    """List all revoked certificates (CRL)"""
    revoked = db.query(RevokedCertificate).order_by(RevokedCertificate.revoked_at.desc()).all()
    return {
        "revoked_certificates": [
            {
                "serial_number": r.serial_number,
                "plugin_id": r.plugin_id,
                "revoked_at": r.revoked_at.isoformat() if r.revoked_at else None,
                "reason": r.reason
            }
            for r in revoked
        ]
    }


@app.get("/stats")
def get_ca_stats(db: Session = Depends(get_db)):
    """Get CA service statistics"""
    total_issued = db.query(IssuedCertificate).count()
    active_certs = db.query(IssuedCertificate).filter(IssuedCertificate.status == "active").count()
    revoked_certs = db.query(RevokedCertificate).count()
    total_verifications = db.query(CertificateAuditLog).filter(CertificateAuditLog.operation == "VERIFY").count()
    
    return {
        "total_issued": total_issued,
        "active_certificates": active_certs,
        "revoked_certificates": revoked_certs,
        "total_verifications": total_verifications
    }


@app.delete("/ca/plugins/{plugin_id}")
def delete_plugin_records(plugin_id: str, db: Session = Depends(get_db)):
    """
    Removes all CA records for a plugin from ca_service.db.
    Called by the Core System (via Secure Gateway) when a plugin is deleted.
    """
    issued_deleted = db.query(IssuedCertificate).filter(IssuedCertificate.plugin_id == plugin_id).delete()
    audit_deleted = db.query(CertificateAuditLog).filter(CertificateAuditLog.plugin_id == plugin_id).delete()
    revoked_deleted = db.query(RevokedCertificate).filter(RevokedCertificate.plugin_id == plugin_id).delete()
    db.commit()

    return {
        "ok": True,
        "deleted": plugin_id,
        "issued_certificates_removed": issued_deleted,
        "audit_log_entries_removed": audit_deleted,
        "revoked_certificates_removed": revoked_deleted,
    }