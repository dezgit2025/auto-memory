"""Token budget tests for the Claude Code provider.

Tier 1 progressive disclosure limits:
  list   output < 7000 bytes  (10 sessions)
  files  output < 3000 bytes  (10 files)

These are hard-fail (deterministic) — same methodology as the main
budget tests in session_recall/tests/test_budgets.py.
"""
from __future__ import annotations

import json
import pathlib

import pytest

from session_recall.providers.claude_code.provider import ClaudeCodeProvider

# ---------------------------------------------------------------------------
# Fixture data
# ---------------------------------------------------------------------------

_BRANCHES = ["main", "feat/ui", "fix/auth", "feat/api", "dev"]
_SUMMARIES = [
    "Fix authentication bug in login flow",
    "Add dashboard charts for user analytics",
    "Refactor logging utilities for structured output",
    "Update CI pipeline to run integration tests",
    "Migrate database schema to v3 format",
    "Implement rate limiting middleware",
    "Add CSV export endpoint for reports",
    "Fix memory leak in websocket handler",
    "Create test fixtures for payment module",
    "Upgrade React to v19 with new hooks",
]


def _build_cc_index(db_path: str) -> None:
    """Create a realistic CC FTS5 index with 10 sessions."""
    from session_recall.providers.claude_code.index import _open

    conn = _open(pathlib.Path(db_path))
    for i in range(10):
        sid = f"cc-sess{i:04d}-0000-0000-0000-{i:012d}"
        days_ago = [0, 0, 1, 2, 3, 5, 7, 10, 14, 21][i]
        ts = f"2026-04-{27 - min(days_ago, 26):02d}T{10 + (i % 12):02d}:00:00Z"
        summary = _SUMMARIES[i]

        conn.execute(
            "INSERT INTO cc_sessions VALUES(?,?,?,?,?,?,?,?,?,?)",
            (
                sid,
                "/home/dev/project",
                "acme/project",
                _BRANCHES[i % len(_BRANCHES)],
                summary,
                ts,
                ts,
                2,
                1,
                "1.0",
            ),
        )

        for t in range(2):
            user_msg = f"Turn {t} user message for session {i}"
            asst_msg = f"Turn {t} assistant response for session {i} with details"
            asst_sum = f"Summary of turn {t}"
            conn.execute(
                "INSERT OR REPLACE INTO cc_turns VALUES(?,?,?,?,?,?)",
                (sid, t, user_msg, asst_msg, ts, asst_sum),
            )
            conn.execute(
                "INSERT INTO cc_search(session_id, user_msg, assistant_msg,"
                " summary, assistant_summary) VALUES(?,?,?,?,?)",
                (sid, user_msg, asst_msg, summary, asst_sum),
            )

        conn.execute(
            "INSERT OR IGNORE INTO cc_files VALUES(?,?,?)",
            (sid, f"src/module_{i}.py", "edit"),
        )

    conn.commit()
    conn.close()


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture(scope="module")
def cc_budget_db(tmp_path_factory):
    """Build a 10-session CC index once per module."""
    db_dir = tmp_path_factory.mktemp("cc_budget")
    db_path = str(db_dir / "sr-index.db")
    _build_cc_index(db_path)
    return db_path


# ---------------------------------------------------------------------------
# Token budget tests (hard fail — deterministic)
# ---------------------------------------------------------------------------


class TestCCTokenBudgets:
    """Claude Code output size must stay within progressive disclosure tiers."""

    @staticmethod
    def _patch(monkeypatch, cc_budget_db: str) -> None:
        idx = pathlib.Path(cc_budget_db)
        monkeypatch.setattr(
            "session_recall.providers.claude_code.index._index_path",
            lambda: idx,
        )
        monkeypatch.setattr(
            "session_recall.providers.claude_code.provider._index_path",
            lambda: idx,
        )
        monkeypatch.setattr(
            "session_recall.providers.claude_code.provider.build_index",
            lambda **kw: {"indexed": 0, "skipped": 0, "errors": 0, "total": 0},
        )

    def test_cc_list_output_under_7000_bytes(self, cc_budget_db, monkeypatch):
        self._patch(monkeypatch, cc_budget_db)
        rows = ClaudeCodeProvider().list_sessions(repo=None, limit=10, days=30)
        output = json.dumps({"count": len(rows), "sessions": rows}, default=str)
        size = len(output)
        assert size < 7000, (
            f"CC list --limit 10 output is {size} bytes, exceeds 7000 byte budget"
        )

    def test_cc_files_output_under_3000_bytes(self, cc_budget_db, monkeypatch):
        self._patch(monkeypatch, cc_budget_db)
        rows = ClaudeCodeProvider().recent_files(repo=None, limit=10, days=30)
        output = json.dumps({"count": len(rows), "files": rows}, default=str)
        size = len(output)
        assert size < 3000, (
            f"CC files --limit 10 output is {size} bytes, exceeds 3000 byte budget"
        )
