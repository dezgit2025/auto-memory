"""Copilot CLI SQLite provider."""

from __future__ import annotations

import re
from pathlib import Path

from ...db.connect import connect_ro
from ...db.schema_check import schema_check
from ..base import StorageProvider
from ._sql import (
    sql_list_checkpoints,
    sql_list_sessions,
    sql_recent_files,
    sql_search,
)
from ._sql_session import sql_get_session
from ._state_fallback import state_get_session, state_list_sessions, state_search
from ..file._path_safety import is_under_root

_SID_RE = re.compile(r"^[0-9a-fA-F-]{4,}$")


class CopilotCliProvider(StorageProvider):
    provider_id = "cli"
    provider_name = "Copilot CLI"

    def __init__(self, db_path: str, state_root: str) -> None:
        self.db_path = db_path
        self.state_root = Path(state_root)

    def _has_db(self) -> bool:
        return Path(self.db_path).exists()

    def _state_files(self) -> list[Path]:
        if not self.state_root.exists():
            return []
        files = [
            f for f in self.state_root.glob("*/events.jsonl")
            if is_under_root(f, self.state_root)
        ]
        files.sort(key=lambda p: p.stat().st_mtime, reverse=True)
        return files

    def uses_jsonl_scan(self) -> bool:
        return not self._has_db()

    def is_available(self) -> bool:
        return self._has_db() or bool(self._state_files())

    def schema_problems(self) -> list[str]:
        if not self._has_db():
            return []
        conn = connect_ro(self.db_path)
        try:
            return schema_check(conn)
        finally:
            conn.close()

    def list_sessions(
        self, repo: str | None, limit: int, days: int | None
    ) -> list[dict]:
        if not self._has_db():
            return state_list_sessions(
                self.provider_id, self._state_files(), repo, limit, days
            )
        conn = connect_ro(self.db_path)
        try:
            return sql_list_sessions(conn, self.provider_id, repo, limit, days)
        finally:
            conn.close()

    def recent_files(
        self, repo: str | None, limit: int, days: int | None
    ) -> list[dict]:
        if not self._has_db():
            return []
        conn = connect_ro(self.db_path)
        try:
            return sql_recent_files(conn, self.provider_id, repo, limit, days)
        finally:
            conn.close()

    def list_checkpoints(
        self, repo: str | None, limit: int, days: int | None
    ) -> list[dict]:
        if not self._has_db():
            return []
        conn = connect_ro(self.db_path)
        try:
            return sql_list_checkpoints(conn, self.provider_id, repo, limit, days)
        finally:
            conn.close()

    def search(
        self, query: str, repo: str | None, limit: int, days: int | None
    ) -> list[dict]:
        if not self._has_db():
            return state_search(
                self.provider_id, self._state_files(), query, repo, limit, days
            )
        from ...commands.search import sanitize_fts5_query

        fts_query = sanitize_fts5_query(query)
        if fts_query is None:
            return []
        conn = connect_ro(self.db_path)
        try:
            return sql_search(conn, self.provider_id, fts_query, repo, limit, days)
        finally:
            conn.close()

    def get_session(
        self, session_id: str, turns: int | None, full: bool
    ) -> dict | None:
        if not self._has_db():
            return state_get_session(
                self.provider_id, self._state_files(), session_id, turns, full
            )
        if not _SID_RE.match(session_id) or not session_id.replace("-", ""):
            return None
        conn = connect_ro(self.db_path)
        try:
            return sql_get_session(conn, self.provider_id, session_id, turns, full)
        finally:
            conn.close()
