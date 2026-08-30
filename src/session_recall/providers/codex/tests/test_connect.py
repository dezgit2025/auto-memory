"""Tests for the shared raising connector core and open_codex_ro (§16 Fix 2)."""

import sqlite3

import pytest

from session_recall.db import connect as db_connect
from session_recall.db.connect import (
    DatabaseBusyError,
    connect_ro,
    connect_ro_raising,
)
from session_recall.providers.codex.connect import open_codex_ro
from session_recall.providers.codex.errors import CodexBusy, CodexStorageMissing
from session_recall.providers.codex.paths import CodexPaths


def _make_db(path, table="t"):
    conn = sqlite3.connect(str(path))
    conn.execute(f"CREATE TABLE {table} (a INTEGER)")
    conn.commit()
    conn.close()
    return path


def _paths(tmp_path, state="state_5.sqlite", history="thread_history_1.sqlite"):
    return CodexPaths(
        state_db=tmp_path / state,
        history_db=tmp_path / history,
        sessions_root=tmp_path / "sessions",
    )


def _patch_always_busy(monkeypatch):
    calls = {"n": 0}

    def fake_connect(*a, **kw):
        calls["n"] += 1
        raise sqlite3.OperationalError("database is locked")

    monkeypatch.setattr(db_connect.sqlite3, "connect", fake_connect)
    monkeypatch.setattr(db_connect.time, "sleep", lambda s: None)
    return calls


class TestRaisingCore:
    def test_missing_file_raises_not_exits(self, tmp_path):
        with pytest.raises(FileNotFoundError):
            connect_ro_raising(str(tmp_path / "absent.sqlite"))

    def test_busy_raises_after_bounded_retries(self, tmp_path, monkeypatch):
        db = _make_db(tmp_path / "busy.sqlite")
        calls = _patch_always_busy(monkeypatch)
        with pytest.raises(DatabaseBusyError):
            connect_ro_raising(str(db))
        assert calls["n"] == 1 + len(db_connect.RETRY_DELAYS_MS)

    def test_success_is_read_only(self, tmp_path):
        db = _make_db(tmp_path / "ok.sqlite")
        conn = connect_ro_raising(str(db))
        try:
            with pytest.raises(sqlite3.OperationalError):
                conn.execute("INSERT INTO t VALUES (1)")
        finally:
            conn.close()

    def test_non_lock_operational_error_propagates(self, tmp_path, monkeypatch):
        db = _make_db(tmp_path / "bad.sqlite")

        def fake_connect(*a, **kw):
            raise sqlite3.OperationalError("unable to open database file")

        monkeypatch.setattr(db_connect.sqlite3, "connect", fake_connect)
        with pytest.raises(sqlite3.OperationalError):
            connect_ro_raising(str(db))


class TestWrapperCompatibility:
    def test_missing_file_exits_4_same_stderr(self, tmp_path, capsys):
        target = tmp_path / "absent.sqlite"
        with pytest.raises(SystemExit) as exc:
            connect_ro(str(target))
        assert exc.value.code == 4
        assert (
            f"error: database not found: {target}" in capsys.readouterr().err
        )

    def test_busy_exits_3_same_stderr(self, tmp_path, monkeypatch, capsys):
        db = _make_db(tmp_path / "busy.sqlite")
        _patch_always_busy(monkeypatch)
        with pytest.raises(SystemExit) as exc:
            connect_ro(str(db))
        assert exc.value.code == 3
        assert "error: database is locked" in capsys.readouterr().err

    def test_success_returns_usable_conn(self, tmp_path):
        db = _make_db(tmp_path / "ok.sqlite")
        conn = connect_ro(str(db))
        try:
            assert conn.execute("SELECT COUNT(*) FROM t").fetchone()[0] == 0
        finally:
            conn.close()


class TestOpenCodexRo:
    def test_yields_both_readonly_conns(self, tmp_path):
        paths = _paths(tmp_path)
        _make_db(paths.state_db)
        _make_db(paths.history_db)
        with open_codex_ro(paths) as (state, history):
            for conn in (state, history):
                assert conn.execute("PRAGMA query_only").fetchone()[0] == 1

    def test_missing_state_maps_to_storage_missing(self, tmp_path):
        paths = _paths(tmp_path)
        with pytest.raises(CodexStorageMissing) as exc:
            with open_codex_ro(paths):
                pass
        assert exc.value.code == "storage_missing"
        assert exc.value.exit_code == 4

    def test_missing_state_with_sibling_is_version_changed(self, tmp_path):
        paths = _paths(tmp_path)
        _make_db(tmp_path / "state_6.sqlite")
        with pytest.raises(CodexStorageMissing) as exc:
            with open_codex_ro(paths):
                pass
        assert exc.value.code == "storage_version_changed"
        assert "state_6.sqlite" in exc.value.message

    def test_missing_history_closes_state_conn(self, tmp_path, monkeypatch):
        from session_recall.providers.codex import connect as codex_connect

        paths = _paths(tmp_path)
        _make_db(paths.state_db)
        closed = []

        class TrackedConn:
            def __init__(self, real):
                self._real = real

            def close(self):
                closed.append(id(self))
                self._real.close()

            def __getattr__(self, name):
                return getattr(self._real, name)

        def tracked_connect(db_path):
            return TrackedConn(connect_ro_raising(db_path))

        monkeypatch.setattr(
            codex_connect, "connect_ro_raising", tracked_connect
        )
        with pytest.raises(CodexStorageMissing):
            with open_codex_ro(paths):
                pass
        assert len(closed) == 1  # the state connection was closed

    def test_busy_maps_to_codex_busy(self, tmp_path, monkeypatch):
        paths = _paths(tmp_path)
        _make_db(paths.state_db)
        _make_db(paths.history_db)
        _patch_always_busy(monkeypatch)
        with pytest.raises(CodexBusy) as exc:
            with open_codex_ro(paths):
                pass
        assert exc.value.exit_code == 3

    def test_normal_exit_closes_both(self, tmp_path):
        paths = _paths(tmp_path)
        _make_db(paths.state_db)
        _make_db(paths.history_db)
        with open_codex_ro(paths) as (state, history):
            pass
        for conn in (state, history):
            with pytest.raises(sqlite3.ProgrammingError):
                conn.execute("SELECT 1")
