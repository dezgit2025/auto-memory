import json, pathlib, sqlite3, time
import pytest
import session_recall.backends.claude_code.index as idx_mod
from session_recall.commands.prune import run

@pytest.fixture(autouse=True)
def patch_index(tmp_path, monkeypatch):
    monkeypatch.setattr(idx_mod, "INDEX_PATH", tmp_path / "test.db")

def _insert_session(tmp_path, sid, last_seen):
    conn = idx_mod._open(idx_mod.INDEX_PATH)
    conn.execute(
        "INSERT OR REPLACE INTO cc_sessions VALUES (?,?,?,?,?,?,?,?,?,?)",
        (sid, "/repo", "r/r", "main", "summary", last_seen, last_seen, 1, 0, "2.0")
    )
    conn.commit(); conn.close()

class _Args:
    days = 30; dry_run = False; json = False

def test_prune_removes_old(tmp_path):
    _insert_session(tmp_path, "old-1", "2020-01-01T00:00:00Z")
    _insert_session(tmp_path, "new-1", "2099-01-01T00:00:00Z")
    run(_Args())
    conn = sqlite3.connect(str(idx_mod.INDEX_PATH))
    ids = [r[0] for r in conn.execute("SELECT id FROM cc_sessions").fetchall()]
    conn.close()
    assert "old-1" not in ids
    assert "new-1" in ids

def test_prune_dry_run_no_delete(tmp_path):
    _insert_session(tmp_path, "old-2", "2020-01-01T00:00:00Z")
    args = _Args(); args.dry_run = True
    run(args)
    conn = sqlite3.connect(str(idx_mod.INDEX_PATH))
    count = conn.execute("SELECT COUNT(*) FROM cc_sessions").fetchone()[0]
    conn.close()
    assert count == 1
