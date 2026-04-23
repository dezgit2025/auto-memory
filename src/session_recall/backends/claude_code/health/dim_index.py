"""Dim 1: Index existence + sentinel check."""
from __future__ import annotations
from .scoring import zone_for_score

NAME = "dim_index"


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
            score = 5.0
            detail = f"index exists at {_idx.INDEX_PATH} but no sentinel — rerun cc-index"
        else:
            score = 10.0
            detail = f"index ready at {_idx.INDEX_PATH}"
        return {"name": NAME, "score": score, "zone": zone_for_score(score), "detail": detail}
    except Exception as e:
        return {"name": NAME, "score": 0.0, "zone": "RED", "detail": f"error: {e}"}
