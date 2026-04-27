"""Tests for backends/claude_code/index.py."""
import json
import pathlib
import time
import pytest
import session_recall.backends.claude_code.index as idx_mod
from session_recall.backends.claude_code.index import (
    _open, _get_meta, build_index, query_sessions, query_files, query_search, query_show,
)


@pytest.fixture(autouse=True)
def patch_index_path(tmp_path, monkeypatch):
    monkeypatch.setattr(idx_mod, "INDEX_PATH", tmp_path / "test-index.db")
    yield


def _make_session_file(
    tmp_path,
    sid,
    cwd="/repo/proj",
    branch="main",
    user_msg="fix the bug",
    assistant_msg="done",
):
    f = tmp_path / f"{sid}.jsonl"
    records = [
        {
            "type": "user", "sessionId": sid, "timestamp": "2026-01-15T10:00:00Z",
            "cwd": cwd, "gitBranch": branch, "version": "2.0",
            "message": {"role": "user", "content": user_msg},
        },
        {
            "type": "assistant", "sessionId": sid, "timestamp": "2026-01-15T10:00:01Z",
            "cwd": cwd, "gitBranch": branch, "version": "2.0",
            "message": {"role": "assistant", "content": [{"type": "text", "text": assistant_msg}]},
        },
    ]
    f.write_text("\n".join(json.dumps(r) for r in records))
    return f


def test_build_index_basic(tmp_path):
    jf = _make_session_file(tmp_path, "aaa-111")
    from session_recall.backends.claude_code import detect as det
    import unittest.mock as mock

    with mock.patch.object(det, "list_session_files", return_value=[jf]):
        stats = build_index()

    assert stats["indexed"] == 1
    assert stats["skipped"] == 0


def test_query_sessions_after_build(tmp_path):
    jf = _make_session_file(tmp_path, "bbb-222", cwd="/repo/myproject")
    from session_recall.backends.claude_code import detect as det
    import unittest.mock as mock

    with mock.patch.object(det, "list_session_files", return_value=[jf]):
        build_index()

    rows = query_sessions(limit=10, days=3650)
    assert len(rows) == 1
    assert rows[0]["id"] == "bbb-222"


def test_build_index_incremental_skips_old(tmp_path):
    jf = _make_session_file(tmp_path, "ccc-333")
    from session_recall.backends.claude_code import detect as det
    import unittest.mock as mock

    with mock.patch.object(det, "list_session_files", return_value=[jf]):
        s1 = build_index()
        s2 = build_index()  # second run should skip the already-indexed file

    assert s1["indexed"] == 1
    assert s2["skipped"] == 1
    assert s2["indexed"] == 0


def test_build_index_rebuild_clears(tmp_path):
    jf = _make_session_file(tmp_path, "ddd-444")
    from session_recall.backends.claude_code import detect as det
    import unittest.mock as mock

    with mock.patch.object(det, "list_session_files", return_value=[jf]):
        build_index()
        s = build_index(rebuild=True)

    assert s["indexed"] == 1


def test_query_search_finds_text(tmp_path):
    jf = _make_session_file(tmp_path, "eee-555", user_msg="authentication refactor")
    from session_recall.backends.claude_code import detect as det
    import unittest.mock as mock

    with mock.patch.object(det, "list_session_files", return_value=[jf]):
        build_index()

    results = query_search("authentication", days=3650)
    assert len(results) >= 1


def test_query_show_by_prefix(tmp_path):
    jf = _make_session_file(tmp_path, "fff-666-full-id")
    from session_recall.backends.claude_code import detect as det
    import unittest.mock as mock

    with mock.patch.object(det, "list_session_files", return_value=[jf]):
        build_index()

    result = query_show("fff-666")
    assert result is not None
    assert result["id"] == "fff-666-full-id"


def test_query_show_turns_limit(tmp_path):
    jf = _make_session_file(tmp_path, "ggg-777")
    from session_recall.backends.claude_code import detect as det
    import unittest.mock as mock

    with mock.patch.object(det, "list_session_files", return_value=[jf]):
        build_index()

    result = query_show("ggg-777", turns=0)
    assert result is not None
    assert result["turns"] == []


def test_build_index_transaction_rollback_on_bad_session(tmp_path):
    """If parse_session raises, the transaction should roll back cleanly."""
    import unittest.mock as mock
    from session_recall.backends.claude_code import detect as det, reader

    jf = tmp_path / "bad.jsonl"
    jf.write_text("{}")

    with mock.patch.object(det, "list_session_files", return_value=[jf]):
        with mock.patch.object(reader, "parse_session", side_effect=RuntimeError("boom")):
            with pytest.raises(RuntimeError):
                build_index()

    # DB should exist but have 0 sessions (rolled back)
    conn = _open(idx_mod.INDEX_PATH)
    count = conn.execute("SELECT COUNT(*) FROM cc_sessions").fetchone()[0]
    conn.close()
    assert count == 0


def test_query_files_after_build(tmp_path):
    sid = "hhh-888"
    f = tmp_path / f"{sid}.jsonl"
    records = [
        {
            "type": "user", "sessionId": sid, "timestamp": "2026-01-15T10:00:00Z",
            "cwd": "/repo/proj", "gitBranch": "main", "version": "2.0",
            "message": {"role": "user", "content": "edit some files"},
        },
        {
            "type": "assistant", "sessionId": sid, "timestamp": "2026-01-15T10:00:01Z",
            "cwd": "/repo/proj", "gitBranch": "main", "version": "2.0",
            "message": {"role": "assistant", "content": [
                {"type": "tool_use", "name": "Write", "input": {"file_path": "/repo/proj/app.py"}}
            ]},
        },
    ]
    f.write_text("\n".join(json.dumps(r) for r in records))

    from session_recall.backends.claude_code import detect as det
    import unittest.mock as mock

    with mock.patch.object(det, "list_session_files", return_value=[f]):
        build_index()

    rows = query_files(limit=10, days=3650)
    assert len(rows) >= 1
    assert any(r["file_path"] == "/repo/proj/app.py" for r in rows)


def test_query_search_finds_assistant_text(tmp_path):
    jf = _make_session_file(
        tmp_path, "iii-901",
        user_msg="help me",
        assistant_msg="backend abstraction layer using repository pattern",
    )
    from session_recall.backends.claude_code import detect as det
    import unittest.mock as mock

    with mock.patch.object(det, "list_session_files", return_value=[jf]):
        build_index()

    results = query_search("repository pattern", days=3650)
    assert len(results) >= 1


def test_query_show_includes_assistant_summary(tmp_path):
    jf = _make_session_file(tmp_path, "jjj-902", assistant_msg="here is my answer")
    from session_recall.backends.claude_code import detect as det
    import unittest.mock as mock

    with mock.patch.object(det, "list_session_files", return_value=[jf]):
        build_index()

    result = query_show("jjj-902")
    assert result is not None
    turn = result["turns"][0]
    assert "assistant_summary" in turn
    assert len(turn["assistant_summary"]) <= 300


def test_build_index_rebuild_preserves_assistant_summary(tmp_path):
    jf = _make_session_file(
        tmp_path, "kkk-903",
        assistant_msg="backend abstraction layer using repository pattern",
    )
    from session_recall.backends.claude_code import detect as det
    import unittest.mock as mock

    with mock.patch.object(det, "list_session_files", return_value=[jf]):
        build_index()
        build_index(rebuild=True)

    results = query_search("repository pattern", days=3650)
    assert len(results) >= 1
