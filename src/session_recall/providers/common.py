"""Shared helpers for provider implementations."""

from __future__ import annotations

import datetime as _dt


def utc_iso_from_ts(ts: float) -> str:
    """Convert POSIX timestamp to UTC ISO8601."""
    return _dt.datetime.fromtimestamp(ts, tz=_dt.timezone.utc).isoformat()


def is_within_days(iso_ts: str | None, days: int | None) -> bool:
    """Check if timestamp string falls inside the requested day window."""
    if days is None:
        return True
    if not iso_ts:
        return False
    try:
        parsed = _dt.datetime.fromisoformat(iso_ts.replace("Z", "+00:00"))
    except ValueError:
        return False
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=_dt.timezone.utc)
    cutoff = _dt.datetime.now(tz=_dt.timezone.utc) - _dt.timedelta(days=days)
    return parsed >= cutoff


def short_id(sid: str) -> str:
    """Consistent short id representation."""
    return sid[:8]
