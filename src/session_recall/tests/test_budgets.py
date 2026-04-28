"""Token budget and latency regression tests.

Progressive disclosure tiers promise bounded output sizes:
  Tier 1 (list, files): ~50 tokens  (~200 bytes/row, ~2500 bytes for 10 rows)
  Tier 2 (search):      ~200 tokens (~3500 bytes for 5 results)
  Tier 3 (show):        ~500 tokens (uncapped for now)

Budget tests are hard-fail (deterministic).  Latency tests are soft
(warn-only) because CI machines vary.
"""

from __future__ import annotations

import json
import os
import sqlite3
import subprocess
import sys
import time
from pathlib import Path
from statistics import median

import pytest

# ---------------------------------------------------------------------------
# Fixture DB builder — 15 sessions with varied ages + searchable content
# ---------------------------------------------------------------------------

_SCHEMA = """
CREATE TABLE sessions (
    id TEXT PRIMARY KEY, cwd TEXT, repository TEXT, branch TEXT,
    summary TEXT, created_at TEXT, updated_at TEXT, host_type TEXT
);
CREATE TABLE turns (
    id INTEGER PRIMARY KEY AUTOINCREMENT, session_id TEXT,
    turn_index INTEGER, user_message TEXT,
    assistant_response TEXT, timestamp TEXT
);
CREATE TABLE session_files (
    id INTEGER PRIMARY KEY AUTOINCREMENT, session_id TEXT,
    file_path TEXT, tool_name TEXT, turn_index INTEGER,
    first_seen_at TEXT
);
CREATE TABLE session_refs (
    id INTEGER PRIMARY KEY AUTOINCREMENT, session_id TEXT,
    ref_type TEXT, ref_value TEXT, turn_index INTEGER,
    created_at TEXT
);
CREATE TABLE checkpoints (
    id INTEGER PRIMARY KEY AUTOINCREMENT, session_id TEXT,
    checkpoint_number INTEGER, title TEXT, overview TEXT,
    created_at TEXT
);
CREATE VIRTUAL TABLE turns_fts USING fts5(
    user_message, assistant_response, content='turns',
    content_rowid='id'
);
CREATE VIRTUAL TABLE search_index USING fts5(
    content, session_id UNINDEXED, source_type UNINDEXED,
    source_id UNINDEXED
);
"""

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
    "Add search autocomplete component",
    "Fix timezone handling in scheduler",
    "Implement OAuth2 PKCE flow",
    "Add Prometheus metrics endpoint",
    "Refactor error handling across API layer",
]


def _build_budget_db(db_path: str) -> None:
    """Create a realistic DB with 15 sessions for budget testing."""
    conn = sqlite3.connect(db_path)
    conn.executescript(_SCHEMA)

    # 15 sessions spread over time
    for i in range(15):
        sid = f"sess{i:04d}-0000-0000-0000-{i:012d}"
        days_ago = [0, 0, 1, 2, 3, 5, 7, 10, 14, 21, 30, 45, 60, 90, 120][i]
        ts = f"2026-04-{27 - min(days_ago, 26):02d}T{10 + (i % 12):02d}:00:00Z"
        conn.execute(
            "INSERT INTO sessions VALUES (?,?,?,?,?,?,?,?)",
            (
                sid,
                "/home/dev/project",
                "acme/project",
                _BRANCHES[i % len(_BRANCHES)],
                _SUMMARIES[i],
                ts,
                ts,
                "local",
            ),
        )

        # 2 turns per session — include "test" in some for search hits
        for t in range(2):
            user_msg = f"Turn {t} user message for session {i}"
            if i % 3 == 0:
                user_msg += " test coverage and testing patterns"
            asst_msg = f"Turn {t} assistant response for session {i} with details"
            conn.execute(
                "INSERT INTO turns (session_id, turn_index, user_message, "
                "assistant_response, timestamp) VALUES (?,?,?,?,?)",
                (sid, t, user_msg, asst_msg, ts),
            )

        # 1 file per session
        conn.execute(
            "INSERT INTO session_files (session_id, file_path, tool_name, "
            "turn_index, first_seen_at) VALUES (?,?,?,?,?)",
            (sid, f"src/module_{i}.py", "edit", 0, ts),
        )

        # 1 checkpoint per session
        conn.execute(
            "INSERT INTO checkpoints (session_id, checkpoint_number, title, "
            "overview, created_at) VALUES (?,?,?,?,?)",
            (sid, 1, f"Checkpoint for session {i}", f"Overview {i}", ts),
        )

    # Populate FTS indexes
    conn.execute(
        "INSERT INTO turns_fts (rowid, user_message, assistant_response) "
        "SELECT id, user_message, assistant_response FROM turns"
    )
    conn.execute(
        "INSERT INTO search_index (content, session_id, source_type, source_id) "
        "SELECT user_message || ' ' || assistant_response, session_id, 'turn', "
        "CAST(id AS TEXT) FROM turns"
    )

    conn.commit()
    conn.close()


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _run(*args: str, db_path: str) -> subprocess.CompletedProcess:
    """Invoke session-recall as a subprocess with fixture DB."""
    env = os.environ.copy()
    env["SESSION_RECALL_DB"] = db_path
    env.pop("SESSION_RECALL_ENABLE_FILE_BACKENDS", None)
    return subprocess.run(
        [sys.executable, "-m", "session_recall", *args],
        capture_output=True,
        text=True,
        timeout=30,
        env=env,
        cwd="/",
    )


@pytest.fixture(scope="module")
def budget_db(tmp_path_factory):
    """Build a 15-session fixture DB once per module."""
    db_dir = tmp_path_factory.mktemp("budget")
    db_path = str(db_dir / "session-store.db")
    _build_budget_db(db_path)
    return db_path


# ===================================================================
# Token budget tests (hard fail — deterministic)
# ===================================================================


class TestTokenBudgets:
    """Output size must stay within progressive disclosure tiers."""

    def test_list_output_under_7000_bytes(self, budget_db):
        # list returns sessions (10) + recent_files (10) — both contribute.
        # Budget: ~300 bytes/session × 10 + ~200 bytes/file × 10 + envelope ≈ 5000.
        # Allow 7000 to avoid flakes while still catching bloat.
        result = _run("list", "--json", "--limit", "10", db_path=budget_db)
        assert result.returncode == 0, f"stderr: {result.stderr}"
        size = len(result.stdout)
        assert size < 7000, (
            f"list --limit 10 output is {size} bytes, exceeds 7000 byte budget"
        )

    def test_files_output_under_3000_bytes(self, budget_db):
        result = _run("files", "--json", "--limit", "10", db_path=budget_db)
        assert result.returncode == 0, f"stderr: {result.stderr}"
        size = len(result.stdout)
        assert size < 3000, (
            f"files --limit 10 output is {size} bytes, exceeds 3000 byte budget"
        )

    def test_search_output_under_5000_bytes(self, budget_db):
        result = _run("search", "test", "--json", "--limit", "5", db_path=budget_db)
        assert result.returncode == 0, f"stderr: {result.stderr}"
        size = len(result.stdout)
        assert size < 5000, (
            f"search --limit 5 output is {size} bytes, exceeds 5000 byte budget"
        )

    def test_search_uses_excerpt_not_content(self, budget_db):
        result = _run("search", "test", "--json", "--limit", "5", db_path=budget_db)
        assert result.returncode == 0
        data = json.loads(result.stdout)
        for item in data.get("results", []):
            assert "excerpt" in item, (
                f"Search result missing 'excerpt' field: {list(item.keys())}"
            )
            assert "content" not in item, (
                "Search result leaks raw 'content' — should use 'excerpt' only"
            )

    def test_search_excerpt_max_253_chars(self, budget_db):
        result = _run("search", "test", "--json", "--limit", "5", db_path=budget_db)
        assert result.returncode == 0
        data = json.loads(result.stdout)
        for item in data.get("results", []):
            excerpt = item.get("excerpt", "")
            assert len(excerpt) <= 253, (
                f"Excerpt is {len(excerpt)} chars, exceeds 253 (250 + '...')"
            )

    def test_list_default_limit_is_10(self, budget_db):
        result = _run("list", "--json", db_path=budget_db)
        assert result.returncode == 0
        data = json.loads(result.stdout)
        assert data["count"] <= 10, (
            f"Default list returned {data['count']} sessions, expected ≤10"
        )


# ===================================================================
# Latency budget tests (soft — warn only, never fail)
# ===================================================================


class TestLatencyBudgets:
    """Performance sanity checks — log warnings, never fail CI."""

    @staticmethod
    def _median_ms(cmd: list[str], db_path: str, runs: int = 3) -> float:
        """Return median wall-clock ms over *runs* invocations."""
        times = []
        for _ in range(runs):
            t0 = time.perf_counter()
            _run(*cmd, db_path=db_path)
            times.append((time.perf_counter() - t0) * 1000)
        return median(times)

    def test_list_latency_warn(self, budget_db):
        ms = self._median_ms(["list", "--json", "--limit", "10"], budget_db)
        if ms > 500:
            import warnings
            warnings.warn(
                f"list --limit 10 median latency {ms:.0f}ms exceeds 500ms target",
                stacklevel=1,
            )
        # Always passes — this is informational only
        assert True, f"list median latency: {ms:.0f}ms"

    def test_search_latency_warn(self, budget_db):
        ms = self._median_ms(["search", "test", "--json", "--limit", "5"], budget_db)
        if ms > 500:
            import warnings
            warnings.warn(
                f"search --limit 5 median latency {ms:.0f}ms exceeds 500ms target",
                stacklevel=1,
            )
        # Always passes — this is informational only
        assert True, f"search median latency: {ms:.0f}ms"
