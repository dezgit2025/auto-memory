"""Dim 2: Freshness — how recently the index was last updated."""
from __future__ import annotations
import time
from .scoring import zone_for_score

NAME = "dim_freshness"

_ONE_HOUR = 3600
_ONE_DAY = 86400
_ONE_WEEK = 7 * _ONE_DAY
_ONE_MONTH = 30 * _ONE_DAY


def check() -> dict:
    try:
        from .. import index as _idx
        if not _idx.INDEX_PATH.exists():
            return {
                "name": NAME, "score": 0.0, "zone": "RED",
                "detail": "index missing — run cc-index to build",
            }
        conn = _idx._open()
        try:
            last_run = _idx._get_meta(conn, "last_run_epoch")
        finally:
            conn.close()
        if not last_run:
            return {
                "name": NAME, "score": 0.0, "zone": "RED",
                "detail": "no last_run_epoch — run cc-index to build",
            }
        age_s = time.time() - float(last_run)
        if age_s < _ONE_HOUR:
            score = 10.0
            mins = int(age_s / 60)
            detail = f"indexed {mins} minute{'s' if mins != 1 else ''} ago"
        elif age_s < _ONE_DAY:
            score = 8.0
            hrs = int(age_s / _ONE_HOUR)
            detail = f"indexed {hrs} hour{'s' if hrs != 1 else ''} ago"
        elif age_s < _ONE_WEEK:
            score = 5.0
            days = int(age_s / _ONE_DAY)
            detail = f"indexed {days} day{'s' if days != 1 else ''} ago"
        elif age_s < _ONE_MONTH:
            score = 2.0
            weeks = int(age_s / _ONE_WEEK)
            detail = f"indexed {weeks} week{'s' if weeks != 1 else ''} ago"
        else:
            score = 0.0
            months = int(age_s / _ONE_MONTH)
            detail = f"indexed {months} month{'s' if months != 1 else ''} ago — stale"
        return {"name": NAME, "score": score, "zone": zone_for_score(score), "detail": detail}
    except Exception as e:
        return {"name": NAME, "score": 0.0, "zone": "RED", "detail": f"error: {e}"}
