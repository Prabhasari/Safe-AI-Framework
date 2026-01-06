from __future__ import annotations

from datetime import datetime, timedelta, timezone
from sqlalchemy import select, func

from config import (
    TRUST_WINDOW_SECONDS,
    TRUST_MIN,
    TRUST_MAX,
    ACTIVE_THRESHOLD,
    RESTRICTED_THRESHOLD,
)
from models import Plugin, RequestLog

UTC = timezone.utc


def _clamp(v: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, v))


def _status_from_score(score: float) -> str:
    if score >= ACTIVE_THRESHOLD:
        return "active"
    if score >= RESTRICTED_THRESHOLD:
        return "restricted"
    return "blocked"


def update_plugin_trust(db, plugin_id: str) -> Plugin | None:
    plugin = db.get(Plugin, plugin_id)
    if not plugin:
        return None

    window_start = datetime.now(UTC) - timedelta(seconds=TRUST_WINDOW_SECONDS)

    total = db.execute(
        select(func.count(RequestLog.id)).where(
            RequestLog.plugin_id == plugin_id,
            RequestLog.created_at >= window_start,
        )
    ).scalar_one()

    if total == 0:
        plugin.status = _status_from_score(plugin.trust_score)
        db.commit()
        return plugin

    errors = db.execute(
        select(func.count(RequestLog.id)).where(
            RequestLog.plugin_id == plugin_id,
            RequestLog.created_at >= window_start,
            RequestLog.error_flag == True,  # noqa
        )
    ).scalar_one()

    avg_latency = db.execute(
        select(func.avg(RequestLog.latency_ms)).where(
            RequestLog.plugin_id == plugin_id,
            RequestLog.created_at >= window_start,
        )
    ).scalar_one() or 0.0

    error_rate = errors / float(total)

    delta = 0.0
    delta -= error_rate * 30.0
    if total > 50:
        delta -= 10.0
    if avg_latency > 500.0:
        delta -= 5.0
    if error_rate == 0.0 and total < 20:
        delta += 2.0

    new_score = _clamp(plugin.trust_score + delta, TRUST_MIN, TRUST_MAX)
    plugin.trust_score = new_score
    plugin.status = _status_from_score(new_score)

    db.commit()
    return plugin