"""Shared fixtures for E2E tests — realistic session-store.db + CLI runner."""

import json
import os
import sqlite3
import subprocess
import sys
import tempfile
from pathlib import Path

import pytest


def _build_fixture_db(db_path: str) -> None:
    """Populate a session-store.db with realistic multi-session test data."""
    conn = sqlite3.connect(db_path)
    conn.executescript(
        """
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
    )

    # --- Sessions: 3 sessions across 2 repos ---
    sessions = [
        (
            "aaaa1111-0000-0000-0000-000000000001",
            "/home/dev/myapp",
            "acme/myapp",
            "main",
            "Fix authentication bug in login flow",
            "2026-04-27T10:00:00Z",
            "2026-04-27T10:30:00Z",
            "local",
        ),
        (
            "bbbb2222-0000-0000-0000-000000000002",
            "/home/dev/myapp",
            "acme/myapp",
            "feat/dashboard",
            "Add dashboard charts for user analytics",
            "2026-04-26T14:00:00Z",
            "2026-04-26T15:00:00Z",
            "local",
        ),
        (
            "cccc3333-0000-0000-0000-000000000003",
            "/home/dev/lib",
            "acme/shared-lib",
            "main",
            "Refactor logging utilities for structured output",
            "2026-04-25T09:00:00Z",
            "2026-04-25T09:45:00Z",
            "local",
        ),
    ]
    conn.executemany(
        "INSERT INTO sessions VALUES (?,?,?,?,?,?,?,?)", sessions
    )

    # --- Turns ---
    turns = [
        ("aaaa1111-0000-0000-0000-000000000001", 0,
         "Fix the login bug where users get 403",
         "I found the issue in auth_middleware.py line 42.",
         "2026-04-27T10:05:00Z"),
        ("aaaa1111-0000-0000-0000-000000000001", 1,
         "Can you also add a unit test for that fix?",
         "Done — added test_auth_middleware.py with 3 test cases.",
         "2026-04-27T10:15:00Z"),
        ("bbbb2222-0000-0000-0000-000000000002", 0,
         "Create a bar chart component for the dashboard",
         "Created src/components/BarChart.tsx with recharts.",
         "2026-04-26T14:10:00Z"),
        ("cccc3333-0000-0000-0000-000000000003", 0,
         "Refactor the logger to use structured JSON output",
         "Replaced print statements with structlog in 5 files.",
         "2026-04-25T09:10:00Z"),
    ]
    for sid, tidx, umsg, aresp, ts in turns:
        conn.execute(
            "INSERT INTO turns (session_id, turn_index, user_message, "
            "assistant_response, timestamp) VALUES (?,?,?,?,?)",
            (sid, tidx, umsg, aresp, ts),
        )

    # --- FTS index ---
    conn.execute(
        "INSERT INTO turns_fts (rowid, user_message, assistant_response) "
        "SELECT id, user_message, assistant_response FROM turns"
    )

    # --- Search index (used by search command) ---
    conn.execute(
        "INSERT INTO search_index (content, session_id, source_type, source_id) "
        "SELECT user_message || ' ' || assistant_response, session_id, 'turn', "
        "CAST(id AS TEXT) FROM turns"
    )

    # --- Session files ---
    files = [
        ("aaaa1111-0000-0000-0000-000000000001",
         "src/auth_middleware.py", "edit", 0, "2026-04-27T10:06:00Z"),
        ("aaaa1111-0000-0000-0000-000000000001",
         "tests/test_auth_middleware.py", "create", 1, "2026-04-27T10:16:00Z"),
        ("bbbb2222-0000-0000-0000-000000000002",
         "src/components/BarChart.tsx", "create", 0, "2026-04-26T14:11:00Z"),
        ("cccc3333-0000-0000-0000-000000000003",
         "src/logger.py", "edit", 0, "2026-04-25T09:11:00Z"),
    ]
    conn.executemany(
        "INSERT INTO session_files (session_id, file_path, tool_name, "
        "turn_index, first_seen_at) VALUES (?,?,?,?,?)",
        files,
    )

    # --- Checkpoints ---
    checkpoints = [
        ("aaaa1111-0000-0000-0000-000000000001", 1,
         "Auth fix complete", "Fixed 403 bug and added tests",
         "2026-04-27T10:20:00Z"),
        ("bbbb2222-0000-0000-0000-000000000002", 1,
         "Chart component done", "BarChart.tsx renders correctly",
         "2026-04-26T14:30:00Z"),
    ]
    conn.executemany(
        "INSERT INTO checkpoints (session_id, checkpoint_number, title, "
        "overview, created_at) VALUES (?,?,?,?,?)",
        checkpoints,
    )

    # --- Session refs ---
    refs = [
        ("aaaa1111-0000-0000-0000-000000000001",
         "commit", "abc1234", 1, "2026-04-27T10:17:00Z"),
        ("bbbb2222-0000-0000-0000-000000000002",
         "pr", "42", 0, "2026-04-26T14:12:00Z"),
    ]
    conn.executemany(
        "INSERT INTO session_refs (session_id, ref_type, ref_value, "
        "turn_index, created_at) VALUES (?,?,?,?,?)",
        refs,
    )

    conn.commit()
    conn.close()


@pytest.fixture(scope="session")
def fixture_db(tmp_path_factory):
    """Build a realistic fixture DB once per test session."""
    db_dir = tmp_path_factory.mktemp("e2e")
    db_path = str(db_dir / "session-store.db")
    _build_fixture_db(db_path)
    return db_path


@pytest.fixture(scope="session")
def empty_db(tmp_path_factory):
    """DB with correct schema but zero rows."""
    db_dir = tmp_path_factory.mktemp("e2e_empty")
    db_path = str(db_dir / "session-store.db")
    conn = sqlite3.connect(db_path)
    conn.executescript(
        """
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
    )
    conn.close()
    return db_path


def run_cli(*args: str, db_path: str | None = None) -> subprocess.CompletedProcess:
    """Invoke session-recall as a subprocess with optional DB override.

    Runs from /tmp to avoid auto-detection of the current git repo,
    ensuring the fixture DB's repos are visible without --repo filtering.
    """
    env = os.environ.copy()
    if db_path:
        env["SESSION_RECALL_DB"] = db_path
    env.pop("SESSION_RECALL_ENABLE_FILE_BACKENDS", None)
    return subprocess.run(
        [sys.executable, "-m", "session_recall", *args],
        capture_output=True,
        text=True,
        timeout=30,
        env=env,
        cwd="/tmp",
    )


def parse_json(result: subprocess.CompletedProcess) -> dict | list:
    """Parse JSON from CLI stdout, raising on failure."""
    return json.loads(result.stdout)
