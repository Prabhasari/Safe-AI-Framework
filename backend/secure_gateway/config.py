from __future__ import annotations
from pathlib import Path

# ═══════════════════════════════════════════════════════════════════════════════
# Service URLs
# ═══════════════════════════════════════════════════════════════════════════════
CA_SERVICE_URL = "http://127.0.0.1:8011"
CORE_SYSTEM_URL = "http://127.0.0.1:8010"

# ═══════════════════════════════════════════════════════════════════════════════
# JWT Settings
# ═══════════════════════════════════════════════════════════════════════════════
JWT_SECRET = "CHANGE_ME_IN_PROD__use_env_var"
JWT_ALG = "HS256"
JWT_TTL_SECONDS = 3 * 60 * 60  # 3 hours

# ═══════════════════════════════════════════════════════════════════════════════
# Trust Engine — Zero Trust Configuration
# ═══════════════════════════════════════════════════════════════════════════════
INITIAL_TRUST_SCORE = 100.0          # Every plugin starts fully trusted
TRUST_WINDOW_SECONDS = 5 * 60       # Sliding window for request counting
TRUST_MIN = 0.0
TRUST_MAX = 100.0

ACTIVE_THRESHOLD = 70.0              # score ≥ 70  → active
RESTRICTED_THRESHOLD = 40.0          # score 40–69 → restricted
REVOKED_THRESHOLD = 20.0             # score < 20  → revoked (hard deny, JWT invalidated)
#                                      score 20–39 → blocked

# ── Trust penalties (applied ONLY on verified anomalies) ────────────────────
TRUST_PENALTY_POLICY_VIOLATION = 15.0
TRUST_PENALTY_RATE_ANOMALY = 10.0
TRUST_PENALTY_INVALID_CERT = 25.0
TRUST_PENALTY_SENSITIVE_ROUTE = 10.0
TRUST_PENALTY_AUTH_FAILURE = 20.0

# ── Trust passive recovery ──────────────────────────────────────────────────
TRUST_RECOVERY_INTERVAL_SECONDS = 30  # +1 point every 30 s of clean behaviour
TRUST_RECOVERY_AMOUNT = 1.0

# ── Rate-based anomaly detection ────────────────────────────────────────────
RATE_LIMIT_MAX_REQUESTS = 50          # Max requests within the window
RATE_LIMIT_WINDOW_SECONDS = 60        # 1-minute sliding window

# ═══════════════════════════════════════════════════════════════════════════════
# Policy Engine — Route Risk Classification
# ═══════════════════════════════════════════════════════════════════════════════

# HIGH risk — admin / core-mutation routes
ROUTE_RISK_HIGH_PREFIXES = (
    "/core/upload-folder",
    "/core/save",
    "/core/delete",
    "/core/reset",
    "/core/stop",
    "/core/start",
    "/core/docker",
)

# MEDIUM risk — normal operational API routes
ROUTE_RISK_MEDIUM_PREFIXES = (
    "/core/plugins/",
    "/core/config",
    "/core/project",
)

# Sensitive routes used by the trust engine for abuse detection
SENSITIVE_ROUTE_PREFIXES = (
    "/core/upload-folder",
    "/core/save",
    "/core/delete",
    "/core/reset",
    "/core/docker",
)

# ═══════════════════════════════════════════════════════════════════════════════
# General Gateway Settings
# ═══════════════════════════════════════════════════════════════════════════════
STRICT_CORE_AUTH = False

BASE_DIR = Path(__file__).resolve().parent
ROOT_CA_CACHE_PATH = BASE_DIR / "root_ca_cert.pem"
DB_PATH = BASE_DIR / "gateway.db"

# Station 2 Access Control Settings
TRUST_MIN_SCORE_FOR_ACCESS = 40.0

# Intent-based permissions (what HTTP methods each intent allows)
INTENT_PERMISSIONS = {
    "read": ["GET"],
    "write": ["GET", "POST", "PUT", "PATCH"],
    "execute": ["GET", "POST", "PUT", "PATCH", "DELETE"],
}

# Scope-based minimum trust scores
SCOPE_MIN_TRUST = {
    "public": 40.0,
    "protected": 60.0,
    "private": 80.0,
}