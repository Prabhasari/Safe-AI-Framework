"""
Trust Engine — Zero Trust Architecture
=======================================

Responsible for trust **scoring only**.  Policy decisions live in policy_engine.

Trust Model (weighted formula):
  T = αR + βC + γH   (scaled to 0–100)

  R = Reputation score  — success ratio from request logs
  C = Context score     — behavioural quality of the current request
  H = Historical trust  — plugin's previous trust score (normalised)

  Weights: α = 0.4, β = 0.3, γ = 0.3

  Status thresholds:
    active   : score ≥ 70
    restricted : 40 ≤ score < 70
    blocked  : 20 ≤ score < 40
    revoked  : score < 20  — requires full re-auth via Station 1
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Dict, Any, Optional, List

from sqlalchemy import select, func
from sqlalchemy.orm import Session

from config import (
    TRUST_MIN,
    TRUST_MAX,
    ACTIVE_THRESHOLD,
    RESTRICTED_THRESHOLD,
    REVOKED_THRESHOLD,
)
from models import Plugin, RequestLog, TrustEvent

UTC = timezone.utc
log = logging.getLogger("trust_engine")

# ──────────────────────────────────────────────────────────────────────────── #
#  Weighted trust model constants                                              #
# ──────────────────────────────────────────────────────────────────────────── #

ALPHA = 0.4   # reputation weight
BETA  = 0.3   # context weight
GAMMA = 0.3   # history weight


# ──────────────────────────────────────────────────────────────────────────── #
#  Internal helpers                                                            #
# ──────────────────────────────────────────────────────────────────────────── #

def _clamp(value: float, lo: float = TRUST_MIN, hi: float = TRUST_MAX) -> float:
    """Clamp *value* between *lo* and *hi*."""
    return max(lo, min(hi, value))


def _status_from_score(score: float) -> str:
    """
    Derive the plugin status string from a numeric trust score.

    Status ladder (highest → lowest):
      active   : score ≥ 70
      restricted : 40 ≤ score < 70
      blocked  : 20 ≤ score < 40
      revoked  : score < 20  — requires full re-auth via Station 1
    """
    if score >= ACTIVE_THRESHOLD:
        return "active"
    if score >= RESTRICTED_THRESHOLD:
        return "restricted"
    if score >= REVOKED_THRESHOLD:
        return "blocked"
    return "revoked"


# ──────────────────────────────────────────────────────────────────────────── #
#  Trust event audit helper                                                    #
# ──────────────────────────────────────────────────────────────────────────── #

def _record_trust_event(
    db: Session,
    plugin_id: str,
    event_type: str,
    delta: float,
    score_before: float,
    score_after: float,
    detail: str = "",
) -> None:
    """Persist an immutable trust-score change record for auditing."""
    db.add(TrustEvent(
        plugin_id=plugin_id,
        event_type=event_type,
        delta=round(delta, 4),
        score_before=round(score_before, 4),
        score_after=round(score_after, 4),
        detail=detail[:500],
    ))


# ──────────────────────────────────────────────────────────────────────────── #
#  Weighted trust model components                                             #
# ──────────────────────────────────────────────────────────────────────────── #

def _compute_reputation(db: Session, plugin_id: str) -> float:
    """
    Reputation score (R) — ratio of successful requests to total requests.

    A request is successful when status_code < 400 AND error_flag is False.
    Returns 1.0 when no request history exists (benefit of the doubt).
    """
    total = db.scalar(
        select(func.count()).where(RequestLog.plugin_id == plugin_id)
    )
    if not total:
        return 1.0

    successful = db.scalar(
        select(func.count()).where(
            RequestLog.plugin_id == plugin_id,
            RequestLog.status_code < 400,
            RequestLog.error_flag == False,  # noqa: E712
        )
    )
    return successful / total


def _compute_context(request_metadata: Dict[str, Any]) -> float:
    """
    Context score (C) — behavioural quality of the *current* request.

    Evaluates only the request outcome, NOT the route risk level.
    Route risk is handled by the policy engine.
    """
    if request_metadata.get("error_flag"):
        return 0.2

    status_code = request_metadata.get("status_code", 200)
    if status_code >= 500:
        return 0.2
    if status_code >= 400:
        return 0.3

    return 1.0


def _compute_historical(plugin: Plugin) -> float:
    """
    Historical trust (H) — plugin's previous trust score normalised to 0–1.
    """
    return plugin.trust_score / TRUST_MAX


# ──────────────────────────────────────────────────────────────────────────── #
#  JWT-cache invalidation hook (called when plugin is revoked)                 #
# ──────────────────────────────────────────────────────────────────────────── #

def _invalidate_jwt_cache(plugin_id: str) -> None:
    """
    Remove a plugin's cached JWT so that it must re-authenticate
    through Station 1.  Imported lazily to avoid circular imports.
    """
    try:
        # app.py maintains _plugin_jwt_cache at module level
        from app import _plugin_jwt_cache
        if plugin_id in _plugin_jwt_cache:
            del _plugin_jwt_cache[plugin_id]
            log.info("[TRUST] Invalidated cached JWT for revoked plugin=%s", plugin_id)
    except (ImportError, AttributeError):
        pass  # defensive: app module may not be loaded in tests


# ──────────────────────────────────────────────────────────────────────────── #
#  PUBLIC API — evaluate_behavior                                              #
# ──────────────────────────────────────────────────────────────────────────── #

def evaluate_behavior(
    db: Session,
    plugin_id: str,
    route: str,
    request_metadata: Dict[str, Any],
) -> Dict[str, Any]:
    """
    Central behavioural evaluation — called on every proxied request.

    Computes trust using the weighted formula:
        T = αR + βC + γH   (scaled to 0–100)

    Parameters
    ----------
    db : Session
        Active SQLAlchemy session.
    plugin_id : str
        The plugin whose behaviour is being evaluated.
    route : str
        The request path (e.g. ``/core/plugins/run``).
    request_metadata : dict
        Keys consumed:
        - ``status_code``      (int)  — response status code
        - ``error_flag``       (bool) — True when the request failed

    Returns
    -------
    dict with ``trust_score``, ``status``, ``anomaly``, ``detail``.
    """
    plugin = db.get(Plugin, plugin_id)
    if plugin is None:
        log.warning("[TRUST] evaluate_behavior called for unknown plugin=%s", plugin_id)
        return {
            "trust_score": 0.0,
            "status": "blocked",
            "anomaly": True,
            "detail": "Unknown plugin",
        }

    now = datetime.now(UTC)
    score_before = plugin.trust_score
    details: List[str] = []

    # ── 1. Book-keeping ──────────────────────────────────────────────── #
    plugin.last_request_at = now
    plugin.request_frequency = (plugin.request_frequency or 0) + 1

    # ── 2. Compute weighted trust components ─────────────────────────── #
    R = _compute_reputation(db, plugin_id)
    C = _compute_context(request_metadata)
    H = _compute_historical(plugin)

    trust = (ALPHA * R) + (BETA * C) + (GAMMA * H)
    new_score = _clamp(trust * 100)

    details.append(f"R={R:.4f} C={C:.4f} H={H:.4f}")
    details.append(f"T = {ALPHA}*{R:.4f} + {BETA}*{C:.4f} + {GAMMA}*{H:.4f} = {new_score:.2f}")

    # ── 3. Record trust event if score changed ───────────────────────── #
    delta = new_score - score_before
    if delta != 0.0:
        event_type = "weighted_update"
        _record_trust_event(
            db, plugin_id, event_type, delta,
            score_before, new_score,
            "; ".join(details),
        )

    plugin.trust_score = new_score

    # ── 4. Update anomaly flag based on context ──────────────────────── #
    if C < 1.0:
        plugin.anomaly_flag = True
        plugin.last_anomaly_at = now
    else:
        plugin.anomaly_flag = False

    # ── 5. Derive status (including revoked at <20) ──────────────────── #
    new_status = _status_from_score(plugin.trust_score)
    old_status = plugin.status
    plugin.status = new_status

    # ── 6. If newly revoked → invalidate JWT cache ───────────────────── #
    if new_status == "revoked" and old_status != "revoked":
        _invalidate_jwt_cache(plugin_id)
        details.append("Plugin REVOKED — cached JWT invalidated, re-auth required")
        log.warning("[TRUST] plugin=%s REVOKED (score=%.1f)", plugin_id, plugin.trust_score)

    db.commit()

    # ── Terminal output: clear formula-based breakdown ────────────────── #
    log.info("")
    log.info("╔══════════════════════════════════════════════════════════════╗")
    log.info("║            TRUST SCORE CALCULATION  (T = αR + βC + γH)     ║")
    log.info("╠══════════════════════════════════════════════════════════════╣")
    log.info("║  Plugin : %-48s ║", plugin_id)
    log.info("╠══════════════════════════════════════════════════════════════╣")
    log.info("║  Component        Weight   Value    Weighted               ║")
    log.info("║  ─────────────────────────────────────────────             ║")
    log.info("║  R (Reputation)   α=%.1f    %.4f   %.4f × %.1f = %.4f     ║",
             ALPHA, R, R, ALPHA, ALPHA * R)
    log.info("║  C (Context)      β=%.1f    %.4f   %.4f × %.1f = %.4f     ║",
             BETA, C, C, BETA, BETA * C)
    log.info("║  H (Historical)   γ=%.1f    %.4f   %.4f × %.1f = %.4f     ║",
             GAMMA, H, H, GAMMA, GAMMA * H)
    log.info("╠══════════════════════════════════════════════════════════════╣")
    log.info("║  T = (%.1f × %.4f) + (%.1f × %.4f) + (%.1f × %.4f)",
             ALPHA, R, BETA, C, GAMMA, H)
    log.info("║    = %.4f + %.4f + %.4f",
             ALPHA * R, BETA * C, GAMMA * H)
    log.info("║    = %.4f", trust)
    log.info("║  Trust Score = %.4f × 100 = %.2f", trust, new_score)
    log.info("╠══════════════════════════════════════════════════════════════╣")
    log.info("║  Score  : %.1f → %.1f  (Δ %+.1f)", score_before, new_score, delta)
    log.info("║  Status : %-12s  Anomaly: %-5s", plugin.status, str(plugin.anomaly_flag))
    log.info("╚══════════════════════════════════════════════════════════════╝")
    log.info("")

    return {
        "trust_score": plugin.trust_score,
        "status": plugin.status,
        "anomaly": plugin.anomaly_flag,
        "detail": "; ".join(details),
    }


# ──────────────────────────────────────────────────────────────────────────── #
#  Station 1 helper — lightweight scoring for JWT issuance                     #
# ──────────────────────────────────────────────────────────────────────────── #

def calculate_trust_score(db: Session, plugin_id: str, current_score: float) -> float:
    """
    Lightweight trust calculation used by Station 1 during JWT issuance.

    Computes trust using the weighted formula with a neutral context
    (C = 1.0) since no active request is being evaluated.
    """
    plugin = db.get(Plugin, plugin_id)
    if plugin is None:
        return current_score

    R = _compute_reputation(db, plugin_id)
    C = 1.0  # no active request context — assume normal
    H = _compute_historical(plugin)

    trust = (ALPHA * R) + (BETA * C) + (GAMMA * H)
    return _clamp(trust * 100)


# ──────────────────────────────────────────────────────────────────────────── #
#  Legacy-compatible wrapper                                                   #
# ──────────────────────────────────────────────────────────────────────────── #

def update_plugin_trust(db: Session, plugin_id: str) -> Optional[Plugin]:
    """
    Backward-compatible entry point called after proxy requests in app.py.

    Recalculates trust using the weighted formula with neutral context.
    Callers should migrate to ``evaluate_behavior()`` for full scoring.
    """
    plugin = db.get(Plugin, plugin_id)
    if plugin is None:
        return None

    R = _compute_reputation(db, plugin_id)
    C = 1.0  # no active request context — assume normal
    H = _compute_historical(plugin)

    trust = (ALPHA * R) + (BETA * C) + (GAMMA * H)
    new_score = _clamp(trust * 100)

    if new_score != plugin.trust_score:
        _record_trust_event(
            db, plugin_id, "weighted_update",
            new_score - plugin.trust_score,
            plugin.trust_score, new_score,
            f"Periodic recalc: R={R:.4f} C={C:.4f} H={H:.4f}",
        )
        plugin.trust_score = new_score

    plugin.status = _status_from_score(plugin.trust_score)
    db.commit()
    return plugin


# ──────────────────────────────────────────────────────────────────────────── #
#  Read-only status query                                                      #
# ──────────────────────────────────────────────────────────────────────────── #

def get_trust_status(db: Session, plugin_id: str) -> Dict[str, Any]:
    """Return current trust state for a plugin (read-only query)."""
    plugin = db.get(Plugin, plugin_id)
    if plugin is None:
        return {"error": "Plugin not found"}
    return {
        "plugin_id": plugin_id,
        "trust_score": plugin.trust_score,
        "status": plugin.status,
        "anomaly_flag": plugin.anomaly_flag,
        "last_request_at": (
            plugin.last_request_at.isoformat() if plugin.last_request_at else None
        ),
        "last_anomaly_at": (
            plugin.last_anomaly_at.isoformat() if plugin.last_anomaly_at else None
        ),
        "request_frequency": plugin.request_frequency,
    }