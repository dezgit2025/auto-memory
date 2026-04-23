"""Claude Code session backend."""
from __future__ import annotations
from typing import Optional
from ..base import SessionBackend
from .detect import CC_PROJECTS_DIR
from . import index as _idx


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
        from .detect import list_projects
        projects = list_projects()
        total_sessions = sum(p["session_count"] for p in projects)
        index_exists = _idx.INDEX_PATH.exists()
        score = 8.0 if (index_exists and total_sessions > 5) else (4.0 if total_sessions > 0 else 0.0)
        return {
            "score": score,
            "zone": "GREEN" if score >= 8 else ("AMBER" if score >= 5 else "RED"),
            "dimensions": [
                {"name": "index_exists", "score": 10.0 if index_exists else 0.0,
                 "detail": str(_idx.INDEX_PATH) if index_exists else "run cc-index to build"},
                {"name": "project_count", "score": min(10.0, total_sessions / 10),
                 "detail": f"{len(projects)} projects, {total_sessions} sessions"},
            ]
        }
