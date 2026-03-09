# backend/vibe-secure-gen/stages/dast_client.py

"""
Thin HTTP client that calls the DAST microservice (port 7095).
This lives inside vibe-secure-gen/stages/ and is called from pipeline.py.

If the DAST service is unreachable, it falls back gracefully
(returns empty findings, no crash).
"""

from __future__ import annotations

import os
from typing import Any, Dict

import requests

DAST_SERVICE_URL = os.getenv("DAST_SERVICE_URL", "http://localhost:7095")
_ANALYZE_URL     = f"{DAST_SERVICE_URL}/dast/analyze"
_HEALTH_URL      = f"{DAST_SERVICE_URL}/dast/health"

_TIMEOUT = 60   # seconds — sandbox execution can take up to 15s per language


def _empty_result(reason: str) -> Dict[str, Any]:
    """Return a safe empty result when the service is unavailable."""
    return {
        "ok":                False,
        "error":             reason,
        "docker_available":  False,
        "findings":          [],
        "pattern_findings":  [],
        "runtime_findings":  [],
        "execution_results": [],
        "languages":         [],
        "summary": {
            "total":           0,
            "critical":        0,
            "high":            0,
            "medium":          0,
            "low":             0,
            "docker_executed": False,
            "owasp_coverage":  [],
        },
    }


def call_dast_service(code_blob: str, language_hint: str = "") -> Dict[str, Any]:
    """
    Send code_blob to the DAST microservice and return the result.

    Falls back gracefully if the service is not running.
    """
    try:
        response = requests.post(
            _ANALYZE_URL,
            json={
                "code_blob": code_blob,
                "language":  language_hint,
            },
            timeout=_TIMEOUT,
        )
        response.raise_for_status()
        return response.json()

    except requests.exceptions.ConnectionError:
        print("  ⚠️  DAST service not reachable at port 7095 — skipping DAST stage")
        print("     → Start it with: cd backend/dast-service && python start.py")
        return _empty_result("DAST service not running (connection refused on port 7095)")

    except requests.exceptions.Timeout:
        print("  ⚠️  DAST service timed out")
        return _empty_result("DAST service request timed out")

    except Exception as exc:
        print(f"  ⚠️  DAST service error: {exc}")
        return _empty_result(f"DAST service error: {str(exc)}")


def dast_service_healthy() -> bool:
    """Quick health-check ping."""
    try:
        r = requests.get(_HEALTH_URL, timeout=3)
        return r.ok
    except Exception:
        return False