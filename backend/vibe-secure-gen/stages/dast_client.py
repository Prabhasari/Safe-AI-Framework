# backend/vibe-secure-gen/stages/dast_client.py

"""
Thin HTTP client that calls the DAST microservice (port 7095).

TIMEOUT BUDGET (worst case):
  - Pattern scan:           ~1s
  - Java sandbox timeout:   90s  (compile + JVM start + run)
  - LLM fix attempt:       120s
  - Serialization/network:  ~5s
  ──────────────────────────────
  Total worst case:        ~216s

  _TIMEOUT is set to 240s as a safe ceiling.
  Override with DAST_TIMEOUT env var if needed.
"""

from __future__ import annotations

import os
import time
from typing import Any, Dict

import requests

DAST_SERVICE_URL = os.getenv("DAST_SERVICE_URL", "http://localhost:7095")
_ANALYZE_URL     = f"{DAST_SERVICE_URL}/dast/analyze"
_HEALTH_URL      = f"{DAST_SERVICE_URL}/dast/health"

# 240s covers: Java sandbox (90s) + LLM fix (120s) + overhead (30s)
_TIMEOUT = int(os.getenv("DAST_TIMEOUT", "240"))


def _empty_result(reason: str) -> Dict[str, Any]:
    return {
        "ok":                  False,
        "error":               reason,
        "docker_available":    False,
        "findings":            [],
        "pattern_findings":    [],
        "runtime_findings":    [],
        "execution_results":   [],
        "proof_of_executions": [],
        "languages":           [],
        "fix_result": {
            "attempted": False, "fixed": False, "fixed_code": None,
            "fixes_applied": 0, "unfixable": [], "error": reason,
        },
        "summary": {
            "total":            0,
            "critical":         0,
            "high":             0,
            "medium":           0,
            "low":              0,
            "docker_executed":  False,
            "owasp_coverage":   [],
            "fix_attempted":    False,
            "fixes_applied":    0,
            "unfixable_count":  0,
        },
    }


def call_dast_service(code_blob: str, language_hint: str = "") -> Dict[str, Any]:
    """
    Send code_blob to the DAST microservice and return the result.
    Falls back gracefully if the service is not running or times out.
    """
    blob_size = len(code_blob)
    print(f"  📡 DAST: sending {blob_size:,} chars to :7095 (timeout={_TIMEOUT}s)...")
    t0 = time.monotonic()

    try:
        response = requests.post(
            _ANALYZE_URL,
            json={"code_blob": code_blob, "language": language_hint},
            timeout=_TIMEOUT,
        )
        response.raise_for_status()
        elapsed = time.monotonic() - t0
        print(f"  ✔ DAST: response received in {elapsed:.1f}s")
        return response.json()

    except requests.exceptions.ConnectionError:
        print("  ⚠️  DAST service not reachable at port 7095 — skipping DAST stage")
        print("     → Start it with: cd backend/dast-service && python start.py")
        return _empty_result("DAST service not running (connection refused on port 7095)")

    except requests.exceptions.Timeout:
        elapsed = time.monotonic() - t0
        print(f"  ⚠️  DAST service timed out after {elapsed:.0f}s (limit={_TIMEOUT}s)")
        print(f"     → Set DAST_TIMEOUT=300 env var to increase")
        return _empty_result(
            f"DAST service timed out after {elapsed:.0f}s "
            f"(blob={blob_size:,} chars). Set DAST_TIMEOUT=300."
        )

    except Exception as exc:
        print(f"  ⚠️  DAST service error: {exc}")
        return _empty_result(f"DAST service error: {str(exc)}")


def dast_service_healthy() -> bool:
    try:
        r = requests.get(_HEALTH_URL, timeout=3)
        return r.ok
    except Exception:
        return False