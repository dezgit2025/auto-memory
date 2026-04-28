"""Tests for repo-scope fallback in list/search commands."""

from __future__ import annotations

import json
from io import StringIO
from types import SimpleNamespace
from unittest.mock import patch


class _FakeProvider:
    provider_id = "cli"

    def __init__(
        self,
        scoped_sessions=None,
        all_sessions=None,
        scoped_results=None,
        all_results=None,
    ):
        self._scoped_sessions = scoped_sessions or []
        self._all_sessions = all_sessions or []
        self._scoped_results = scoped_results or []
        self._all_results = all_results or []

    def schema_problems(self):
        return []

    def list_sessions(self, repo, limit, days):
        rows = self._all_sessions if repo == "all" else self._scoped_sessions
        return rows[:limit]

    def recent_files(self, repo, limit, days):
        return []

    def search(self, query, repo, limit, days):
        rows = self._all_results if repo == "all" else self._scoped_results
        return rows[:limit]


def test_list_falls_back_to_all_scope_when_scoped_is_empty():
    cli_provider = _FakeProvider(
        scoped_sessions=[],
        all_sessions=[
            {
                "provider": "fake",
                "id_short": "abc12345",
                "id_full": "abc12345-0000-0000-0000-000000000000",
                "repository": "unknown",
                "branch": "unknown",
                "summary": "skills fix session",
                "date": "2026-04-22",
                "created_at": "2026-04-22T17:00:00Z",
                "turns_count": 3,
                "files_count": 0,
            }
        ],
    )

    class _OtherProvider:
        provider_id = "vscode"

        def schema_problems(self):
            return []

        def list_sessions(self, repo, limit, days):
            return []

        def recent_files(self, repo, limit, days):
            return []

    providers = [cli_provider, _OtherProvider()]

    args = SimpleNamespace(repo=None, limit=10, days=5, json=True, provider="all")
    with (
        patch(
            "session_recall.commands.list_sessions.detect_repo",
            return_value="owner/repo",
        ),
        patch(
            "session_recall.commands.list_sessions.get_active_providers",
            return_value=providers,
        ),
    ):
        from session_recall.commands.list_sessions import run

        buf = StringIO()
        with patch("sys.stdout", buf):
            code = run(args)

    payload = json.loads(buf.getvalue())
    assert code == 0
    assert payload["repo"] == "all"
    assert payload["count"] == 1


def test_search_falls_back_to_all_scope_when_scoped_is_empty():
    provider = _FakeProvider(
        scoped_results=[],
        all_results=[
            {
                "provider": "fake",
                "session_id": "abc12345",
                "session_id_full": "abc12345-0000-0000-0000-000000000000",
                "source_type": "turn",
                "summary": "can you fix the broken skills?",
                "repository": "unknown",
                "date": "2026-04-22",
                "excerpt": "can you fix the broken skills?",
            }
        ],
    )

    args = SimpleNamespace(
        query="broken skills", repo=None, limit=10, days=5, json=True, provider="all"
    )
    with (
        patch("session_recall.commands.search.detect_repo", return_value="owner/repo"),
        patch(
            "session_recall.commands.search.get_active_providers",
            return_value=[provider],
        ),
    ):
        from session_recall.commands.search import run

        buf = StringIO()
        with patch("sys.stdout", buf):
            code = run(args)

    payload = json.loads(buf.getvalue())
    assert code == 0
    assert payload["repo"] == "all"
    assert payload["count"] == 1
