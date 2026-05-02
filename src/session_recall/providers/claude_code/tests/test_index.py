"""Tests for Claude Code FTS5 index."""
from __future__ import annotations

import datetime
import json
import os
import time
from pathlib import Path

import pytest

from session_recall.providers.claude_code import index


def _now_iso() -> str:
    return datetime.datetime.now(tz=datetime.timezone.utc).isoformat().replace("+00:00", "Z")


@pytest.fixture()
def cc_env(tmp_path, monkeypatch):
    """Mock CC projects dir and index path for isolation."""
    projects_dir = tmp_path / "projects"
    projects_dir.mkdir()
    db_path = tmp_path / "test-index.db"
    monkeypatch.setenv("SESSION_RECALL_CC_INDEX_PATH", str(db_path))
    monkeypatch.setattr(
        "session_recall.providers.claude_code.detect.CC_PROJECTS_DIR",
        projects_dir,
    )
    monkeypatch.setattr(
        "session_recall.providers.claude_code.reader._CLAUDE_PROJECTS_ROOT",
        projects_dir,
    )
    monkeypatch.setenv("SESSION_RECALL_JSONL_DAYS", "999")
    monkeypatch.setenv("SESSION_RECALL_CC_PRUNE_DAYS", "999")
    return {"projects_dir": projects_dir, "db_path": db_path}


def _write_session(
    projects_dir: Path,
    project: str,
    session_id: str,
    user_msg: str = "hello",
    ts: str | None = None,
    *,
    tool_files: list[dict] | None = None,
) -> Path:
    if ts is None:
        ts = _now_iso()
    proj_dir = projects_dir / project
    proj_dir.mkdir(exist_ok=True)
    path = proj_dir / f"{session_id}.jsonl"
    assistant_content: list[dict] = [
        {"type": "text", "text": f"response to {user_msg}"},
    ]
    if tool_files:
        for f in tool_files:
            assistant_content.append({
                "type": "tool_use",
                "name": f.get("tool", "Read"),
                "input": {"file_path": f["path"]},
            })
    lines = [
        json.dumps({
            "type": "user",
            "message": {"content": user_msg},
            "timestamp": ts,
            "cwd": f"/projects/{project}",
        }),
        json.dumps({
            "type": "assistant",
            "message": {"content": assistant_content},
            "timestamp": ts,
        }),
    ]
    path.write_text("\n".join(lines) + "\n")
    return path


# --- _open / WAL ---

def test_open_creates_db_with_wal(cc_env):
    conn = index._open(cc_env["db_path"])
    try:
        mode = conn.execute("PRAGMA journal_mode").fetchone()[0]
        assert mode == "wal"
    finally:
        conn.close()


# --- build_index basic ---

def test_build_index_basic(cc_env):
    _write_session(cc_env["projects_dir"], "proj", "s1", "test message")
    stats = index.build_index()
    assert stats["indexed"] == 1
    assert stats["errors"] == 0


# --- FTS5 sanitization ---

def test_fts5_injection_sanitized(cc_env):
    _write_session(cc_env["projects_dir"], "proj", "s1", "important data")
    index.build_index()
    results = index.query_search("* OR *", days=365)
    assert isinstance(results, list)
    results = index.query_search('" DROP TABLE cc_sessions; --', days=365)
    assert isinstance(results, list)


# --- incremental indexing ---

def test_incremental_indexing(cc_env):
    _write_session(cc_env["projects_dir"], "proj", "s1", "first session")
    stats1 = index.build_index()
    assert stats1["indexed"] == 1

    stats2 = index.build_index()
    assert stats2["indexed"] == 0
    assert stats2["skipped"] >= 1

    time.sleep(0.05)
    _write_session(cc_env["projects_dir"], "proj", "s2", "second session")
    stats3 = index.build_index()
    assert stats3["indexed"] == 1


# --- auto-prune ---

def test_auto_prune(cc_env, monkeypatch):
    monkeypatch.setenv("SESSION_RECALL_CC_PRUNE_DAYS", "1")
    _write_session(
        cc_env["projects_dir"], "proj", "old-sess", "old msg",
        ts="2020-01-01T00:00:00Z",
    )
    index.build_index()
    sessions = index.query_sessions(days=36500)
    assert len(sessions) == 0


# --- query_sessions ---

def test_query_sessions(cc_env):
    _write_session(cc_env["projects_dir"], "proj", "s1", "hello world")
    index.build_index()
    sessions = index.query_sessions(days=365)
    assert len(sessions) == 1
    assert sessions[0]["_trust_level"] == "claude_code_jsonl"
    assert sessions[0]["id"] == "s1"


# --- query_search with snippet ---

def test_query_search(cc_env):
    _write_session(
        cc_env["projects_dir"], "proj", "s1", "unique searchterm xyz",
    )
    index.build_index()
    results = index.query_search("searchterm", days=365)
    assert len(results) >= 1
    assert "snippet" in results[0]
    assert results[0]["_trust_level"] == "claude_code_jsonl"


# --- query_files ---

def test_query_files(cc_env):
    _write_session(
        cc_env["projects_dir"], "proj", "s1", "edit files",
        tool_files=[{"path": "/src/main.py", "tool": "Write"}],
    )
    index.build_index()
    files = index.query_files(days=365)
    assert len(files) >= 1
    assert files[0]["file_path"] == "/src/main.py"
    assert files[0]["_trust_level"] == "claude_code_jsonl"


# --- bm25 weighting ---

def test_bm25_user_msg_weighted_higher(cc_env):
    ts = _now_iso()
    _write_session(
        cc_env["projects_dir"], "proj", "user-match",
        "tell me about quantum physics", ts=ts,
    )
    proj_dir = cc_env["projects_dir"] / "proj"
    s2 = proj_dir / "assist-match.jsonl"
    s2.write_text(
        json.dumps({
            "type": "user",
            "message": {"content": "hello there"},
            "timestamp": ts,
            "cwd": "/projects/proj",
        })
        + "\n"
        + json.dumps({
            "type": "assistant",
            "message": {"content": [
                {"type": "text", "text": "quantum physics is fascinating"},
            ]},
            "timestamp": ts,
        })
        + "\n"
    )
    index.build_index()
    results = index.query_search("quantum", days=365)
    assert len(results) >= 2
    assert results[0]["session_id"] == "user-match"


# --- symlink rejection ---

def test_symlink_rejection(cc_env):
    _write_session(cc_env["projects_dir"], "proj", "real-sess", "real content")
    proj_dir = cc_env["projects_dir"] / "proj"
    real_path = proj_dir / "real-sess.jsonl"
    sym = proj_dir / "symlinked.jsonl"
    sym.symlink_to(real_path)

    index.build_index()
    sessions = index.query_sessions(days=365)
    session_ids = [s["id"] for s in sessions]
    assert "real-sess" in session_ids
    assert "symlinked" not in session_ids
