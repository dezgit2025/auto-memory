"""Claude Code session backend."""
from __future__ import annotations
from typing import Optional
from ..base import SessionBackend
from .detect import CC_PROJECTS_DIR
from . import index as _idx


def _worst_zone(zones: list[str]) -> str:
    """Return the worst zone across dimensions (RED > AMBER > GREEN)."""
    if "RED" in zones:
        return "RED"
    if "AMBER" in zones:
        return "AMBER"
    return "GREEN"


class ClaudeCodeBackend(SessionBackend):
    @property
    def name(self) -> str:
        return "claude"

    def is_available(self) -> bool:
        return CC_PROJECTS_DIR.exists()

    def _ensure_index(self) -> None:
        if not _idx.INDEX_PATH.exists():
            _idx.build_index()
            return
        # File exists but may be empty from a previously failed build — check for sentinel
        conn = _idx._open()
        try:
            last_run = _idx._get_meta(conn, "last_run_epoch")
        finally:
            conn.close()
        if not last_run:
            _idx.build_index()

    def list_sessions(self, *, repo=None, limit=10, days=30) -> list[dict]:
        self._ensure_index()
        rows = _idx.query_sessions(repo=repo, limit=limit, days=days)
        return [
            {
                "id_short": r["id"][:8], "id_full": r["id"],
                "repository": r["repository"], "branch": r["branch"],
                "summary": r["summary"],
                "date": (r["last_seen"] or "")[:10],
                "created_at": r["first_seen"],
                "turns_count": r["turns_count"],
                "files_count": r["files_count"],
            }
            for r in rows
        ]

    def list_files(self, *, repo=None, limit=20, days=30) -> list[dict]:
        self._ensure_index()
        rows = _idx.query_files(repo=repo, limit=limit, days=days)
        return [
            {
                "file_path": r["file_path"],
                "tool_name": r["tool_name"] or "unknown",
                "date": (r["last_seen"] or "")[:10],
                "session_id": r["session_id"][:8],
            }
            for r in rows
        ]

    def search(self, query: str, *, repo=None, limit=10, days=30) -> list[dict]:
        self._ensure_index()
        return _idx.query_search(query, repo=repo, limit=limit, days=days)

    def show_session(self, session_id: str, *, turns=None) -> Optional[dict]:
        self._ensure_index()
        return _idx.query_show(session_id, turns=turns)

    def health(self) -> dict:
        from .health import (dim_index, dim_freshness, dim_corpus,
                             dim_latency, dim_coverage, dim_surfaces)
        from .health.scoring import overall_score
        dims = [dim_index, dim_freshness, dim_corpus, dim_latency, dim_coverage, dim_surfaces]
        results = [d.check() for d in dims]
        zones = [r.get("zone", "GREEN") for r in results]
        return {
            "score": overall_score(results),
            "zone": _worst_zone(zones),
            "dimensions": results,
        }
