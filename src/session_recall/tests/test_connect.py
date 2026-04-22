"""Tests for db/connect.py — backoff and error handling."""
import sqlite3
import tempfile
import os
import pytest
from session_recall.db.connect import connect_ro


def test_connect_success():
    """Normal connection to an existing DB succeeds."""
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
        path = f.name
    try:
        conn = sqlite3.connect(path)
        conn.execute("CREATE TABLE test (id INTEGER)")
        conn.close()
        result = connect_ro(path)
        assert result is not None
        result.close()
    finally:
        os.unlink(path)


def test_connect_missing_db(tmp_path, monkeypatch):
    """Missing DB and no JSONL store exits with code 4."""
    # Mock home directory to avoid JSONL fallback
    fake_home = tmp_path / "home"
    fake_home.mkdir()
    monkeypatch.setenv("HOME", str(fake_home))
    
    with pytest.raises(SystemExit) as exc:
        connect_ro("/nonexistent/path/fake.db")
    assert exc.value.code == 4


def test_connect_readonly():
    """Connection is read-only — writes should fail."""
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
        path = f.name
    try:
        conn = sqlite3.connect(path)
        conn.execute("CREATE TABLE test (id INTEGER)")
        conn.close()
        ro_conn = connect_ro(path)
        with pytest.raises(sqlite3.OperationalError):
            ro_conn.execute("INSERT INTO test VALUES (1)")
        ro_conn.close()
    finally:
        os.unlink(path)
