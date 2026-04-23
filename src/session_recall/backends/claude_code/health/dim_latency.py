"""Dim 4: Query latency — time a simple SELECT against cc_sessions."""
from __future__ import annotations
import time
from .scoring import zone_for_score

NAME = "dim_latency"


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
            t0 = time.monotonic()
            conn.execute(
                "SELECT id, summary FROM cc_sessions ORDER BY last_seen DESC LIMIT 10"
            ).fetchall()
            elapsed_ms = (time.monotonic() - t0) * 1000
        finally:
            conn.close()
        if elapsed_ms < 5:
            score = 10.0
        elif elapsed_ms < 20:
            score = 8.0
        elif elapsed_ms < 100:
            score = 5.0
        else:
            score = 0.0
        detail = f"query latency {elapsed_ms:.1f}ms"
        return {"name": NAME, "score": score, "zone": zone_for_score(score), "detail": detail}
    except Exception as e:
        return {"name": NAME, "score": 0.0, "zone": "RED", "detail": f"error: {e}"}
