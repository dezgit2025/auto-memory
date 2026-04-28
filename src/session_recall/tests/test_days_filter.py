"""Tests for --days filter across list, files, checkpoints, search commands."""
import sqlite3
import tempfile
import os
import json
import pytest
from unittest.mock import patch
from io import StringIO
from types import SimpleNamespace


def _create_db_with_aged_data() -> str:
    """Create temp DB with sessions/files/checkpoints at various ages."""
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
        title TEXT, overview TEXT, history TEXT, work_done TEXT,
        technical_details TEXT, important_files TEXT, next_steps TEXT,
        created_at TEXT)""")
    conn.execute("""CREATE VIRTUAL TABLE search_index USING fts5(
        content, session_id UNINDEXED, source_type UNINDEXED, source_id UNINDEXED)""")

    # 4 sessions: today, 3 days ago, 10 days ago, 60 days ago
    ages = [("s_now", "0 days"), ("s_3d", "-3 days"), ("s_10d", "-10 days"), ("s_60d", "-60 days")]
    for sid, age in ages:
        conn.execute(
            "INSERT INTO sessions VALUES (?, '/tmp', 'owner/repo', 'main', ?, datetime('now', ?), datetime('now', ?), 'local')",
            (sid, f"Session {sid}", age, age))
        conn.execute(
            "INSERT INTO session_files VALUES (NULL, ?, ?, 'edit', 0, datetime('now', ?))",
            (sid, f"/tmp/file-{sid}.md", age))
        conn.execute(
            "INSERT INTO checkpoints VALUES (NULL, ?, 1, ?, 'overview', '', '', '', '', '', datetime('now', ?))",
            (sid, f"Checkpoint {sid}", age))
        conn.execute(
            "INSERT INTO search_index (content, session_id, source_type, source_id) VALUES (?, ?, 'turn', '1')",
            (f"content about mcp and other things for {sid}", sid))
    conn.commit()
    conn.close()
    return path


@pytest.fixture
def db_path():
    path = _create_db_with_aged_data()
    yield path
    os.unlink(path)


def _run_cmd(module_path, run_fn, args, db_path):
    """Helper to invoke a command's run() function with patched DB."""
    with patch(f"{module_path}.DB_PATH", db_path), \
         patch(f"{module_path}.detect_repo", return_value="owner/repo"):
        buf = StringIO()
        with patch("sys.stdout", buf):
            code = run_fn(args)
    return code, json.loads(buf.getvalue())


# -------- LIST --------

def test_list_days_1_returns_only_today(db_path):
    from session_recall.commands.list_sessions import run
    args = SimpleNamespace(repo=None, limit=100, days=1, json=True)
    code, out = _run_cmd("session_recall.commands.list_sessions", run, args, db_path)
    assert code == 0
    assert out["count"] == 1
    assert out["sessions"][0]["id_full"] == "s_now"


def test_list_days_7_includes_3d_excludes_10d(db_path):
    from session_recall.commands.list_sessions import run
    args = SimpleNamespace(repo=None, limit=100, days=7, json=True)
    code, out = _run_cmd("session_recall.commands.list_sessions", run, args, db_path)
    ids = {s["id_full"] for s in out["sessions"]}
    assert "s_now" in ids
    assert "s_3d" in ids
    assert "s_10d" not in ids
    assert "s_60d" not in ids


def test_list_days_30_excludes_60d(db_path):
    from session_recall.commands.list_sessions import run
    args = SimpleNamespace(repo=None, limit=100, days=30, json=True)
    code, out = _run_cmd("session_recall.commands.list_sessions", run, args, db_path)
    ids = {s["id_full"] for s in out["sessions"]}
    assert "s_60d" not in ids
    assert len(ids) == 3


def test_list_days_default_30(db_path):
    """days=None should use default 30 days (excludes 60d old)."""
    from session_recall.commands.list_sessions import run
    args = SimpleNamespace(repo=None, limit=100, days=None, json=True)
    code, out = _run_cmd("session_recall.commands.list_sessions", run, args, db_path)
    ids = {s["id_full"] for s in out["sessions"]}
    assert "s_60d" not in ids


# -------- FILES --------

def test_files_days_1(db_path):
    from session_recall.commands.files import run
    args = SimpleNamespace(repo=None, limit=100, days=1, json=True)
    code, out = _run_cmd("session_recall.commands.files", run, args, db_path)
    assert code == 0
    assert out["count"] == 1


def test_files_days_7(db_path):
    from session_recall.commands.files import run
    args = SimpleNamespace(repo=None, limit=100, days=7, json=True)
    code, out = _run_cmd("session_recall.commands.files", run, args, db_path)
    assert out["count"] == 2


def test_files_no_days_returns_all(db_path):
    from session_recall.commands.files import run
    args = SimpleNamespace(repo=None, limit=100, days=None, json=True)
    code, out = _run_cmd("session_recall.commands.files", run, args, db_path)
    assert out["count"] == 4  # all 4 including 60d old


def test_files_days_with_repo_all(db_path):
    from session_recall.commands.files import run
    args = SimpleNamespace(repo="all", limit=100, days=7, json=True)
    code, out = _run_cmd("session_recall.commands.files", run, args, db_path)
    assert out["count"] == 2


# -------- CHECKPOINTS --------

def test_checkpoints_days_1(db_path):
    from session_recall.commands.checkpoints import run
    args = SimpleNamespace(repo=None, limit=100, days=1, json=True)
    code, out = _run_cmd("session_recall.commands.checkpoints", run, args, db_path)
    assert code == 0
    assert out["count"] == 1


def test_checkpoints_days_15(db_path):
    from session_recall.commands.checkpoints import run
    args = SimpleNamespace(repo=None, limit=100, days=15, json=True)
    code, out = _run_cmd("session_recall.commands.checkpoints", run, args, db_path)
    assert out["count"] == 3  # now, 3d, 10d — not 60d


def test_checkpoints_no_days_returns_all(db_path):
    from session_recall.commands.checkpoints import run
    args = SimpleNamespace(repo=None, limit=100, days=None, json=True)
    code, out = _run_cmd("session_recall.commands.checkpoints", run, args, db_path)
    assert out["count"] == 4


# -------- SEARCH --------

def test_search_days_1(db_path):
    from session_recall.commands.search import run
    args = SimpleNamespace(query="mcp", repo=None, limit=100, days=1, json=True)
    code, out = _run_cmd("session_recall.commands.search", run, args, db_path)
    assert code == 0
    assert out["count"] == 1


def test_search_days_7(db_path):
    from session_recall.commands.search import run
    args = SimpleNamespace(query="mcp", repo=None, limit=100, days=7, json=True)
    code, out = _run_cmd("session_recall.commands.search", run, args, db_path)
    assert out["count"] == 2


def test_search_no_days_returns_all_matches(db_path):
    from session_recall.commands.search import run
    args = SimpleNamespace(query="mcp", repo=None, limit=100, days=None, json=True)
    code, out = _run_cmd("session_recall.commands.search", run, args, db_path)
    assert out["count"] == 3  # days=None defaults to 30; 60-day-old session excluded


def test_search_days_with_repo_filter(db_path):
    from session_recall.commands.search import run
    args = SimpleNamespace(query="mcp", repo="owner/repo", limit=100, days=7, json=True)
    code, out = _run_cmd("session_recall.commands.search", run, args, db_path)
    assert out["count"] == 2


# -------- EDGE CASES --------

def test_list_days_zero_excludes_everything(db_path):
    """days=0 should return nothing (datetime('now', '-0 days') == now)."""
    from session_recall.commands.list_sessions import run
    args = SimpleNamespace(repo=None, limit=100, days=0, json=True)
    code, out = _run_cmd("session_recall.commands.list_sessions", run, args, db_path)
    # days=0 falsy → default 30 applied (expected: returns 3, excludes 60d)
    assert out["count"] == 3


def test_search_empty_query_with_days(db_path):
    from session_recall.commands.search import run
    args = SimpleNamespace(query="   ", repo=None, limit=100, days=7, json=True)
    code, out = _run_cmd("session_recall.commands.search", run, args, db_path)
    assert code == 0
    assert out["count"] == 0
    assert "warning" in out


def test_list_days_large_number(db_path):
    from session_recall.commands.list_sessions import run
    args = SimpleNamespace(repo=None, limit=100, days=3650, json=True)
    code, out = _run_cmd("session_recall.commands.list_sessions", run, args, db_path)
    assert out["count"] == 4
