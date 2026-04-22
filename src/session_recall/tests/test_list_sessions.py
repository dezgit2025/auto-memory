"""Tests for commands/list_sessions.py — session listing logic."""
import sqlite3
import tempfile
import os
import json
from unittest.mock import patch
from io import StringIO
from types import SimpleNamespace


def _create_test_db() -> str:
    """Create temp DB with test sessions matching real schema."""
    f = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
    path = f.name
    f.close()
    conn = sqlite3.connect(path)
    conn.execute("""CREATE TABLE sessions (
        id TEXT PRIMARY KEY, cwd TEXT, repository TEXT, branch TEXT,
        summary TEXT, created_at TEXT, updated_at TEXT, host_type TEXT)""")
    conn.execute("""CREATE TABLE turns (
        id INTEGER PRIMARY KEY, session_id TEXT, turn_index INTEGER,
        user_message TEXT, assistant_response TEXT, timestamp TEXT)""")
    conn.execute("""CREATE TABLE session_files (
        id INTEGER PRIMARY KEY, session_id TEXT, file_path TEXT,
        tool_name TEXT, turn_index INTEGER, first_seen_at TEXT)""")
    conn.execute("""CREATE TABLE session_refs (
        id INTEGER PRIMARY KEY, session_id TEXT, ref_type TEXT,
        ref_value TEXT, turn_index INTEGER, created_at TEXT)""")
    conn.execute("""CREATE TABLE checkpoints (
        id INTEGER PRIMARY KEY, session_id TEXT, checkpoint_number INTEGER,
        title TEXT, overview TEXT, created_at TEXT)""")
    # Insert test data
    conn.execute("INSERT INTO sessions VALUES ('s1', '/tmp', 'owner/repo', 'main', 'Test session 1', datetime('now'), datetime('now'), 'local')")
    conn.execute("INSERT INTO sessions VALUES ('s2', '/tmp', 'owner/repo', 'main', 'Test session 2', datetime('now', '-1 day'), datetime('now'), 'local')")
    conn.execute("INSERT INTO sessions VALUES ('s3', '/tmp', 'other/repo', 'dev', 'Other repo', datetime('now'), datetime('now'), 'local')")
    conn.execute("INSERT INTO turns VALUES (1, 's1', 0, 'hello', 'hi', datetime('now'))")
    conn.execute("INSERT INTO turns VALUES (2, 's1', 1, 'q2', 'a2', datetime('now'))")
    conn.commit()
    conn.close()
    return path


def test_list_filters_by_repo():
    """List should only return sessions for the specified repo."""
    path = _create_test_db()
    try:
        with patch("session_recall.commands.list_sessions.DB_PATH", path), \
             patch("session_recall.commands.list_sessions.detect_repo", return_value="owner/repo"):
            from session_recall.commands.list_sessions import run
            args = SimpleNamespace(repo=None, limit=10, days=30, json=True)
            buf = StringIO()
            with patch("sys.stdout", buf):
                code = run(args)
            output = json.loads(buf.getvalue())
            assert code == 0
            assert output["count"] == 2  # s1 + s2, not s3
            assert all(s["repository"] == "owner/repo" for s in output["sessions"])
    finally:
        os.unlink(path)


def test_list_respects_limit():
    """List should respect --limit."""
    path = _create_test_db()
    try:
        with patch("session_recall.commands.list_sessions.DB_PATH", path), \
             patch("session_recall.commands.list_sessions.detect_repo", return_value="owner/repo"):
            from session_recall.commands.list_sessions import run
            args = SimpleNamespace(repo=None, limit=1, days=30, json=True)
            buf = StringIO()
            with patch("sys.stdout", buf):
                code = run(args)
            output = json.loads(buf.getvalue())
            assert output["count"] == 1
    finally:
        os.unlink(path)


def test_list_json_shape():
    """JSON output must have repo, count, sessions keys."""
    path = _create_test_db()
    try:
        with patch("session_recall.commands.list_sessions.DB_PATH", path), \
             patch("session_recall.commands.list_sessions.detect_repo", return_value="owner/repo"):
            from session_recall.commands.list_sessions import run
            args = SimpleNamespace(repo="all", limit=10, days=30, json=True)
            buf = StringIO()
            with patch("sys.stdout", buf):
                code = run(args)
            output = json.loads(buf.getvalue())
            assert "repo" in output
            assert "count" in output
            assert "sessions" in output
            # Should include turns_count
            assert "turns_count" in output["sessions"][0]
    finally:
        os.unlink(path)
