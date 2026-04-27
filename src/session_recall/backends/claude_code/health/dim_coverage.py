"""Dim 5: Coverage — fraction of sessions that have non-empty summaries."""
from __future__ import annotations
from .scoring import zone_for_score

NAME = "dim_coverage"


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
            total = conn.execute("SELECT COUNT(*) FROM cc_sessions").fetchone()[0]
            with_summary = conn.execute(
                "SELECT COUNT(*) FROM cc_sessions WHERE summary != '' AND summary IS NOT NULL"
            ).fetchone()[0]
        finally:
            conn.close()
        if total == 0:
            return {
                "name": NAME, "score": 0.0, "zone": "RED",
                "detail": "no sessions indexed — run cc-index to build",
            }
        pct = with_summary / total * 100
        if pct > 90:
            score = 10.0
        elif pct > 70:
            score = 7.0
        elif pct > 40:
            score = 4.0
        else:
            score = 0.0
        detail = f"{pct:.0f}% of sessions have summaries ({with_summary}/{total})"
        return {"name": NAME, "score": score, "zone": zone_for_score(score), "detail": detail}
    except Exception as e:
        return {"name": NAME, "score": 0.0, "zone": "RED", "detail": f"error: {e}"}
