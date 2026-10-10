"""Tests for health/dim_freshness.py — WAL-aware mtime freshness check."""
import time
from session_recall.health import dim_freshness


def test_green_when_db_recently_modified(tmp_path, monkeypatch):
    db = tmp_path / "session-store.db"
    db.write_text("")
    monkeypatch.setattr(dim_freshness, "DB_PATH", str(db))
    r = dim_freshness.check()
    assert r["zone"] == "GREEN"


def test_red_when_db_missing(tmp_path, monkeypatch):
    monkeypatch.setattr(dim_freshness, "DB_PATH", str(tmp_path / "missing.db"))
    r = dim_freshness.check()
    assert r["zone"] == "RED"
    assert "not found" in r["detail"]


def test_wal_mtime_used_when_newer_than_db(tmp_path, monkeypatch):
    """WAL file is newer than the main DB — freshness should reflect the WAL."""
    db = tmp_path / "session-store.db"
    wal = tmp_path / "session-store.db-wal"
    db.write_text("")
    wal.write_text("")

    # Make the main DB appear stale (100 hours ago)
    stale_time = time.time() - (100 * 3600)
    import os
    os.utime(str(db), (stale_time, stale_time))

    # WAL is fresh (just now — default mtime from write_text is fine)
    monkeypatch.setattr(dim_freshness, "DB_PATH", str(db))

    r = dim_freshness.check()
    assert r["zone"] == "GREEN", (
        f"Expected GREEN (WAL is fresh) but got {r['zone']}: {r['detail']}"
    )


def test_db_mtime_used_when_no_wal(tmp_path, monkeypatch):
    """No WAL file present — falls back to main DB mtime only."""
    db = tmp_path / "session-store.db"
    db.write_text("")
    monkeypatch.setattr(dim_freshness, "DB_PATH", str(db))
    r = dim_freshness.check()
    assert r["zone"] == "GREEN"


def test_stale_when_both_db_and_wal_are_old(tmp_path, monkeypatch):
    """Both DB and WAL are old — should report RED."""
    import os
    db = tmp_path / "session-store.db"
    wal = tmp_path / "session-store.db-wal"
    db.write_text("")
    wal.write_text("")

    stale_time = time.time() - (100 * 3600)
    os.utime(str(db), (stale_time, stale_time))
    os.utime(str(wal), (stale_time, stale_time))

    monkeypatch.setattr(dim_freshness, "DB_PATH", str(db))
    r = dim_freshness.check()
    assert r["zone"] == "RED"
