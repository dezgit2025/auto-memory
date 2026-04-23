"""Tests for the Cursor IDE session backend."""
from __future__ import annotations

import json
import pathlib
import sqlite3
import time

import pytest

import session_recall.backends.cursor as cursor_mod
from session_recall.backends.cursor import CursorBackend, _cursor_base


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_vscdb(db_path: pathlib.Path, tabs: list[dict]) -> None:
    """Create a fake state.vscdb at *db_path* with *tabs* as chat data."""
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(db_path))
    conn.execute("CREATE TABLE IF NOT EXISTS ItemTable (key TEXT PRIMARY KEY, value TEXT)")
    payload = json.dumps({"tabs": tabs})
    conn.execute(
        "INSERT OR REPLACE INTO ItemTable (key, value) VALUES (?, ?)",
        ("workbench.panel.aichat.view.aichat.chatdata", payload),
    )
    conn.commit()
    conn.close()


def _make_tab(
    tab_id: str = "tab-001",
    title: str = "Test chat",
    user_text: str = "How do I fix this bug?",
    ai_text: str = "You should check the stack trace.",
    created_ms: int = 1_700_000_000_000,
    files: list[str] | None = None,
) -> dict:
    """Build a minimal Cursor chat tab dict."""
    bubbles = [
        {"type": "user", "text": user_text, "createdAt": created_ms},
        {"type": "ai",   "text": ai_text,   "createdAt": created_ms + 1000},
    ]
    tab: dict = {
        "tabId": tab_id,
        "chatTitle": title,
        "lastSendTime": created_ms + 1000,
        "createdAt": created_ms,
        "bubbles": bubbles,
    }
    if files:
        # Attach file context to first bubble
        tab["bubbles"][0]["context"] = [{"path": fp} for fp in files]
    return tab


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture(autouse=True)
def reset_index():
    """Reset the global in-memory index before every test."""
    cursor_mod._index._sessions = []
    cursor_mod._index._stamp = 0.0
    yield
    cursor_mod._index._sessions = []
    cursor_mod._index._stamp = 0.0


@pytest.fixture()
def fake_cursor_base(tmp_path, monkeypatch):
    """Redirect _cursor_base() to a tmp directory."""
    ws_storage = tmp_path / "workspaceStorage"
    ws_storage.mkdir()
    monkeypatch.setattr(cursor_mod, "_cursor_base", lambda: ws_storage)
    return ws_storage


# ---------------------------------------------------------------------------
# is_available
# ---------------------------------------------------------------------------

class TestIsAvailable:
    def test_true_when_base_exists(self, fake_cursor_base):
        b = CursorBackend()
        assert b.is_available() is True

    def test_false_when_base_missing(self, tmp_path, monkeypatch):
        missing = tmp_path / "no_such_dir"
        monkeypatch.setattr(cursor_mod, "_cursor_base", lambda: missing)
        b = CursorBackend()
        assert b.is_available() is False


# ---------------------------------------------------------------------------
# list_sessions
# ---------------------------------------------------------------------------

class TestListSessions:
    def test_empty_when_no_dbs(self, fake_cursor_base):
        b = CursorBackend()
        assert b.list_sessions(days=3650) == []

    def test_returns_one_session(self, fake_cursor_base):
        ws_dir = fake_cursor_base / "abc123"
        _make_vscdb(ws_dir / "state.vscdb", [_make_tab()])
        b = CursorBackend()
        sessions = b.list_sessions(days=3650)
        assert len(sessions) == 1

    def test_session_shape(self, fake_cursor_base):
        ws_dir = fake_cursor_base / "abc123"
        _make_vscdb(
            ws_dir / "state.vscdb",
            [_make_tab(title="My awesome chat", user_text="hello")],
        )
        b = CursorBackend()
        s = b.list_sessions(days=3650)[0]
        assert "id_short" in s
        assert "id_full" in s
        assert "repository" in s
        assert "branch" in s
        assert "summary" in s
        assert "date" in s
        assert "created_at" in s
        assert "turns_count" in s
        assert "files_count" in s
        # Internal fields must NOT leak out
        assert "_bubbles" not in s
        assert "_file_set" not in s

    def test_summary_falls_back_to_user_text(self, fake_cursor_base):
        ws_dir = fake_cursor_base / "abc123"
        tab = _make_tab(title="", user_text="Explain recursion to me please")
        _make_vscdb(ws_dir / "state.vscdb", [tab])
        b = CursorBackend()
        s = b.list_sessions(days=3650)[0]
        assert "recursion" in s["summary"].lower()

    def test_limit_respected(self, fake_cursor_base):
        ws_dir = fake_cursor_base / "abc123"
        tabs = [_make_tab(tab_id=f"tab-{i:03d}", title=f"Chat {i}") for i in range(10)]
        _make_vscdb(ws_dir / "state.vscdb", tabs)
        b = CursorBackend()
        assert len(b.list_sessions(days=3650, limit=3)) == 3

    def test_multiple_workspaces(self, fake_cursor_base):
        for i in range(3):
            ws_dir = fake_cursor_base / f"ws{i:04d}"
            _make_vscdb(ws_dir / "state.vscdb", [_make_tab(tab_id=f"tab-{i}")])
        b = CursorBackend()
        sessions = b.list_sessions(days=3650, limit=10)
        assert len(sessions) == 3

    def test_turns_count(self, fake_cursor_base):
        ws_dir = fake_cursor_base / "abc"
        tab = _make_tab()
        # Two user+ai exchanges means turns_count == 1 (one pair)
        _make_vscdb(ws_dir / "state.vscdb", [tab])
        b = CursorBackend()
        s = b.list_sessions(days=3650)[0]
        assert s["turns_count"] == 1

    def test_files_count(self, fake_cursor_base):
        ws_dir = fake_cursor_base / "abc"
        _make_vscdb(
            ws_dir / "state.vscdb",
            [_make_tab(files=["src/app.py", "tests/test_app.py"])],
        )
        b = CursorBackend()
        s = b.list_sessions(days=3650)[0]
        assert s["files_count"] == 2

    def test_days_filter_excludes_old_sessions(self, fake_cursor_base):
        ws_dir = fake_cursor_base / "abc"
        # Use a timestamp from year 2000 — clearly outside any reasonable window
        old_ms = 946_684_800_000  # 2000-01-01T00:00:00Z in ms
        _make_vscdb(ws_dir / "state.vscdb", [_make_tab(created_ms=old_ms)])
        b = CursorBackend()
        assert b.list_sessions(days=30) == []


# ---------------------------------------------------------------------------
# list_files
# ---------------------------------------------------------------------------

class TestListFiles:
    def test_returns_files_from_sessions(self, fake_cursor_base):
        ws_dir = fake_cursor_base / "abc"
        _make_vscdb(
            ws_dir / "state.vscdb",
            [_make_tab(files=["src/main.py", "src/utils.py"])],
        )
        b = CursorBackend()
        files = b.list_files(days=3650)
        paths = [f["file_path"] for f in files]
        assert "src/main.py" in paths
        assert "src/utils.py" in paths

    def test_file_shape(self, fake_cursor_base):
        ws_dir = fake_cursor_base / "abc"
        _make_vscdb(ws_dir / "state.vscdb", [_make_tab(files=["a.py"])])
        b = CursorBackend()
        f = b.list_files(days=3650)[0]
        assert "file_path" in f
        assert "tool_name" in f
        assert "date" in f
        assert "session_id" in f

    def test_no_duplicate_files(self, fake_cursor_base):
        ws_dir = fake_cursor_base / "abc"
        # Two tabs reference the same file
        tabs = [
            _make_tab(tab_id="t1", files=["shared.py"]),
            _make_tab(tab_id="t2", files=["shared.py"]),
        ]
        _make_vscdb(ws_dir / "state.vscdb", tabs)
        b = CursorBackend()
        files = b.list_files(days=3650)
        paths = [f["file_path"] for f in files]
        assert paths.count("shared.py") == 1

    def test_empty_when_no_files(self, fake_cursor_base):
        ws_dir = fake_cursor_base / "abc"
        _make_vscdb(ws_dir / "state.vscdb", [_make_tab(files=None)])
        b = CursorBackend()
        assert b.list_files(days=3650) == []


# ---------------------------------------------------------------------------
# search
# ---------------------------------------------------------------------------

class TestSearch:
    def test_finds_match_in_summary(self, fake_cursor_base):
        ws_dir = fake_cursor_base / "abc"
        _make_vscdb(
            ws_dir / "state.vscdb",
            [_make_tab(title="Authentication refactor")],
        )
        b = CursorBackend()
        results = b.search("authentication", days=3650)
        assert len(results) >= 1

    def test_finds_match_in_bubble_text(self, fake_cursor_base):
        ws_dir = fake_cursor_base / "abc"
        _make_vscdb(
            ws_dir / "state.vscdb",
            [_make_tab(title="", user_text="How do I implement OAuth2 login?")],
        )
        b = CursorBackend()
        results = b.search("OAuth2", days=3650)
        assert len(results) >= 1
        assert results[0]["excerpt"]

    def test_no_results_for_missing_term(self, fake_cursor_base):
        ws_dir = fake_cursor_base / "abc"
        _make_vscdb(ws_dir / "state.vscdb", [_make_tab(title="Unrelated chat")])
        b = CursorBackend()
        results = b.search("xyzzy_nonexistent_term", days=3650)
        assert results == []

    def test_search_result_shape(self, fake_cursor_base):
        ws_dir = fake_cursor_base / "abc"
        _make_vscdb(
            ws_dir / "state.vscdb",
            [_make_tab(title="Fix the login bug")],
        )
        b = CursorBackend()
        r = b.search("login", days=3650)[0]
        assert "session_id" in r
        assert "session_id_full" in r
        assert "source_type" in r
        assert "summary" in r
        assert "date" in r
        assert "excerpt" in r

    def test_search_limit(self, fake_cursor_base):
        ws_dir = fake_cursor_base / "abc"
        tabs = [
            _make_tab(tab_id=f"t{i}", title=f"Bugfix session {i}", user_text="bugfix")
            for i in range(10)
        ]
        _make_vscdb(ws_dir / "state.vscdb", tabs)
        b = CursorBackend()
        results = b.search("bugfix", days=3650, limit=3)
        assert len(results) <= 3


# ---------------------------------------------------------------------------
# show_session
# ---------------------------------------------------------------------------

class TestShowSession:
    def test_returns_none_for_unknown_id(self, fake_cursor_base):
        ws_dir = fake_cursor_base / "abc"
        _make_vscdb(ws_dir / "state.vscdb", [_make_tab()])
        b = CursorBackend()
        b.list_sessions(days=3650)  # warm index
        assert b.show_session("nonexistent-id-0000") is None

    def test_returns_session_by_full_id(self, fake_cursor_base):
        ws_dir = fake_cursor_base / "abc"
        _make_vscdb(ws_dir / "state.vscdb", [_make_tab(tab_id="mytab-001")])
        b = CursorBackend()
        sessions = b.list_sessions(days=3650)
        full_id = sessions[0]["id_full"]
        detail = b.show_session(full_id)
        assert detail is not None
        assert detail["id"] == full_id

    def test_show_session_shape(self, fake_cursor_base):
        ws_dir = fake_cursor_base / "abc"
        _make_vscdb(ws_dir / "state.vscdb", [_make_tab()])
        b = CursorBackend()
        sessions = b.list_sessions(days=3650)
        detail = b.show_session(sessions[0]["id_full"])
        assert "id" in detail
        assert "summary" in detail
        assert "turns" in detail
        assert "files" in detail
        assert isinstance(detail["turns"], list)

    def test_turns_limit(self, fake_cursor_base):
        ws_dir = fake_cursor_base / "abc"
        # 3 user+ai exchanges
        bubbles = []
        for i in range(3):
            bubbles.append({"type": "user", "text": f"Q{i}", "createdAt": 1_700_000_000_000 + i * 2000})
            bubbles.append({"type": "ai",   "text": f"A{i}", "createdAt": 1_700_000_000_000 + i * 2000 + 1000})
        tab = {
            "tabId": "multi-turn",
            "chatTitle": "Multi-turn chat",
            "lastSendTime": 1_700_000_005_000,
            "createdAt": 1_700_000_000_000,
            "bubbles": bubbles,
        }
        _make_vscdb(ws_dir / "state.vscdb", [tab])
        b = CursorBackend()
        sessions = b.list_sessions(days=3650)
        detail = b.show_session(sessions[0]["id_full"], turns=2)
        assert len(detail["turns"]) == 2


# ---------------------------------------------------------------------------
# health
# ---------------------------------------------------------------------------

class TestHealth:
    def test_health_shape(self, fake_cursor_base):
        b = CursorBackend()
        h = b.health()
        assert "score" in h
        assert "zone" in h
        assert "dimensions" in h
        assert isinstance(h["dimensions"], list)

    def test_health_zone_amber_when_no_dbs(self, fake_cursor_base):
        b = CursorBackend()
        h = b.health()
        # No workspaces → at least AMBER
        assert h["zone"] in ("AMBER", "RED")

    def test_health_green_with_data(self, fake_cursor_base):
        ws_dir = fake_cursor_base / "abc"
        _make_vscdb(ws_dir / "state.vscdb", [_make_tab()])
        b = CursorBackend()
        b.list_sessions(days=3650)  # warm index
        h = b.health()
        assert h["score"] > 0
        assert isinstance(h["zone"], str)

    def test_health_dimensions_have_required_keys(self, fake_cursor_base):
        ws_dir = fake_cursor_base / "abc"
        _make_vscdb(ws_dir / "state.vscdb", [_make_tab()])
        b = CursorBackend()
        h = b.health()
        for dim in h["dimensions"]:
            assert "name" in dim
            assert "zone" in dim


# ---------------------------------------------------------------------------
# Robustness / edge cases
# ---------------------------------------------------------------------------

class TestRobustness:
    def test_malformed_json_in_db(self, fake_cursor_base):
        ws_dir = fake_cursor_base / "bad_ws"
        ws_dir.mkdir()
        db_path = ws_dir / "state.vscdb"
        conn = sqlite3.connect(str(db_path))
        conn.execute("CREATE TABLE ItemTable (key TEXT PRIMARY KEY, value TEXT)")
        conn.execute(
            "INSERT INTO ItemTable (key, value) VALUES (?, ?)",
            ("workbench.panel.aichat.view.aichat.chatdata", "NOT VALID JSON {{{"),
        )
        conn.commit()
        conn.close()
        b = CursorBackend()
        # Must not raise
        sessions = b.list_sessions(days=3650)
        assert isinstance(sessions, list)

    def test_empty_db(self, fake_cursor_base):
        ws_dir = fake_cursor_base / "empty_ws"
        ws_dir.mkdir()
        db_path = ws_dir / "state.vscdb"
        conn = sqlite3.connect(str(db_path))
        conn.execute("CREATE TABLE ItemTable (key TEXT PRIMARY KEY, value TEXT)")
        conn.commit()
        conn.close()
        b = CursorBackend()
        assert b.list_sessions(days=3650) == []

    def test_db_with_no_chat_key(self, fake_cursor_base):
        ws_dir = fake_cursor_base / "no_chat"
        ws_dir.mkdir()
        db_path = ws_dir / "state.vscdb"
        conn = sqlite3.connect(str(db_path))
        conn.execute("CREATE TABLE ItemTable (key TEXT PRIMARY KEY, value TEXT)")
        conn.execute(
            "INSERT INTO ItemTable (key, value) VALUES (?, ?)",
            ("some.other.key", '{"data": "irrelevant"}'),
        )
        conn.commit()
        conn.close()
        b = CursorBackend()
        assert b.list_sessions(days=3650) == []

    def test_backend_available_false_returns_empty(self, tmp_path, monkeypatch):
        missing = tmp_path / "no_cursor_here"
        monkeypatch.setattr(cursor_mod, "_cursor_base", lambda: missing)
        b = CursorBackend()
        assert not b.is_available()
        assert b.list_sessions(days=3650) == []
        assert b.list_files(days=3650) == []
        assert b.search("anything", days=3650) == []
        assert b.show_session("fakeid") is None
