"""Tests for repos discovery summary command."""

from __future__ import annotations

import json
from io import StringIO
from types import SimpleNamespace
from unittest.mock import patch


class _FakeProvider:
    def __init__(self, provider_id: str, rows: list[dict]) -> None:
        self.provider_id = provider_id
        self._rows = rows

    def list_sessions(self, repo, limit, days):
        assert repo == "all"
        return self._rows[:limit]


def test_repos_json_aggregates_by_repository() -> None:
    providers = [
        _FakeProvider(
            "cli",
            [
                {
                    "provider": "cli",
                    "repository": "jshessen/auto-memory",
                    "created_at": "2026-04-22T12:00:00Z",
                },
                {
                    "provider": "cli",
                    "repository": "local:/home/jshessen/.config/squad",
                    "created_at": "2026-04-22T13:00:00Z",
                },
            ],
        ),
        _FakeProvider(
            "vscode",
            [
                {
                    "provider": "vscode",
                    "repository": "jshessen/auto-memory",
                    "created_at": "2026-04-22T14:00:00Z",
                }
            ],
        ),
    ]

    with patch(
        "session_recall.commands.repos.get_active_providers", return_value=providers
    ):
        from session_recall.commands.repos import run

        args = SimpleNamespace(
            json=True, limit=100, days=30, provider="all", include_local=False
        )
        buf = StringIO()
        with patch("sys.stdout", buf):
            code = run(args)

    payload = json.loads(buf.getvalue())
    assert code == 0
    assert payload["count"] == 1
    assert payload["include_local"] is False
    repos = {row["repository"]: row for row in payload["repositories"]}
    assert repos["jshessen/auto-memory"]["session_count"] == 2
    assert repos["jshessen/auto-memory"]["last_seen"] == "2026-04-22T14:00:00Z"
    assert repos["jshessen/auto-memory"]["providers"] == ["cli", "vscode"]


def test_repos_json_include_local_opt_in() -> None:
    providers = [
        _FakeProvider(
            "cli",
            [
                {
                    "provider": "cli",
                    "repository": "local:/home/jshessen/.config/squad",
                    "created_at": "2026-04-22T13:00:00Z",
                }
            ],
        )
    ]

    with patch(
        "session_recall.commands.repos.get_active_providers", return_value=providers
    ):
        from session_recall.commands.repos import run

        args = SimpleNamespace(
            json=True, limit=100, days=30, provider="all", include_local=True
        )
        buf = StringIO()
        with patch("sys.stdout", buf):
            code = run(args)

    payload = json.loads(buf.getvalue())
    assert code == 0
    assert payload["count"] == 1
    assert payload["include_local"] is True
    assert (
        payload["repositories"][0]["repository"] == "local:/home/jshessen/.config/squad"
    )
