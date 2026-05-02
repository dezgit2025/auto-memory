"""Claude Code storage provider backed by an FTS5 index over JSONL files."""
from __future__ import annotations

import time

from ..base import StorageProvider
from .detect import CC_PROJECTS_DIR
from .index import _index_path, build_index, query_files, query_search, query_sessions, query_show

_STALE_SECONDS = 60
_TRUST_LEVEL = "claude_code_jsonl"


class ClaudeCodeProvider(StorageProvider):
    provider_id = "claude_code"
    provider_name = "Claude Code"

    def is_available(self) -> bool:
        if not CC_PROJECTS_DIR.exists():
            return False
        return any(
            d.is_dir() and any(d.glob("*.jsonl"))
            for d in CC_PROJECTS_DIR.iterdir()
        )

    def _ensure_index(self) -> None:
        idx = _index_path()
        if not idx.exists():
            build_index()
            return
        try:
            age = time.time() - idx.stat().st_mtime
        except OSError:
            age = _STALE_SECONDS + 1
        if age > _STALE_SECONDS:
            build_index()

    def list_sessions(
        self, repo: str | None, limit: int, days: int | None
    ) -> list[dict]:
        self._ensure_index()
        rows = query_sessions(repo=repo, limit=limit, days=days or 30)
        return [
            {**r, "provider": self.provider_id, "_trust_level": _TRUST_LEVEL}
            for r in rows
        ]

    def recent_files(
        self, repo: str | None, limit: int, days: int | None
    ) -> list[dict]:
        self._ensure_index()
        rows = query_files(repo=repo, limit=limit, days=days or 30)
        return [
            {**r, "_trust_level": _TRUST_LEVEL}
            for r in rows
        ]

    def list_checkpoints(
        self, repo: str | None, limit: int, days: int | None
    ) -> list[dict]:
        return []

    def search(
        self, query: str, repo: str | None, limit: int, days: int | None
    ) -> list[dict]:
        self._ensure_index()
        rows = query_search(query, repo=repo, limit=limit, days=days or 30)
        return [
            {**r, "provider": self.provider_id, "_trust_level": _TRUST_LEVEL}
            for r in rows
        ]

    def get_session(
        self, session_id: str, turns: int | None, full: bool
    ) -> dict | None:
        self._ensure_index()
        result = query_show(session_id, turns=turns)
        if result is not None:
            result["_trust_level"] = _TRUST_LEVEL
        return result

    def uses_jsonl_scan(self) -> bool:
        return True

    def schema_problems(self) -> list[str]:
        return []
