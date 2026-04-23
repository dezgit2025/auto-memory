"""Dim 3: Corpus — session count and project spread."""
from __future__ import annotations
import sqlite3
from .scoring import zone_for_score

NAME = "dim_corpus"


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
            projects = conn.execute(
                "SELECT COUNT(DISTINCT repository) FROM cc_sessions WHERE repository != ''"
            ).fetchone()[0]
        finally:
            conn.close()
        if total > 100:
            score = 10.0
        elif total > 50:
            score = 8.0
        elif total > 10:
            score = 5.0
        elif total > 0:
            score = 2.0
        else:
            score = 0.0
        detail = f"{total} session{'s' if total != 1 else ''} indexed across {projects} project{'s' if projects != 1 else ''}"
        return {"name": NAME, "score": score, "zone": zone_for_score(score), "detail": detail}
    except Exception as e:
        return {"name": NAME, "score": 0.0, "zone": "RED", "detail": f"error: {e}"}
