"""Tests for backends/claude_code/reader.py."""
import json
import pathlib
import pytest
from session_recall.backends.claude_code.reader import iter_records, parse_session, _extract_text


def _write_jsonl(path, records):
    path.write_text("\n".join(json.dumps(r) for r in records), encoding="utf-8")


def test_iter_records_basic(tmp_path):
    f = tmp_path / "s.jsonl"
    _write_jsonl(f, [{"type": "user", "msg": "hello"}, {"type": "assistant"}])
    records = list(iter_records(f))
    assert len(records) == 2


def test_iter_records_skips_bad_json(tmp_path):
    f = tmp_path / "s.jsonl"
    f.write_text('{"ok": 1}\nnot json\n{"ok": 2}\n')
    records = list(iter_records(f))
    assert len(records) == 2


def test_iter_records_oserror_propagates(tmp_path):
    missing = tmp_path / "missing.jsonl"
    with pytest.raises(OSError):
        list(iter_records(missing))


def test_parse_session_empty_file(tmp_path):
    f = tmp_path / "abc123.jsonl"
    f.write_text("")
    assert parse_session(f) is None


def test_parse_session_basic_turn(tmp_path):
    sid = "test-session-id-1234"
    f = tmp_path / f"{sid}.jsonl"
    records = [
        {
            "type": "user", "sessionId": sid, "timestamp": "2026-01-01T10:00:00Z",
            "cwd": "/home/user/myproject", "gitBranch": "main", "version": "2.0",
            "message": {"role": "user", "content": "hello world"},
        },
        {
            "type": "assistant", "sessionId": sid, "timestamp": "2026-01-01T10:00:01Z",
            "cwd": "/home/user/myproject", "gitBranch": "main", "version": "2.0",
            "message": {"role": "assistant", "content": [{"type": "text", "text": "hi there"}]},
        },
    ]
    _write_jsonl(f, records)
    result = parse_session(f)
    assert result is not None
    assert result["id"] == sid
    assert result["branch"] == "main"
    assert len(result["turns"]) == 1
    assert result["turns"][0]["user"] == "hello world"
    assert "hi there" in result["turns"][0]["assistant"]


def test_parse_session_extracts_tool_files(tmp_path):
    sid = "file-test-session-5678"
    f = tmp_path / f"{sid}.jsonl"
    records = [
        {
            "type": "user", "sessionId": sid, "timestamp": "2026-01-01T10:00:00Z",
            "cwd": "/repo", "gitBranch": "main", "version": "2.0",
            "message": {"role": "user", "content": "edit the file"},
        },
        {
            "type": "assistant", "sessionId": sid, "timestamp": "2026-01-01T10:00:01Z",
            "cwd": "/repo", "gitBranch": "main", "version": "2.0",
            "message": {"role": "assistant", "content": [
                {"type": "tool_use", "name": "Edit", "input": {"file_path": "/repo/main.py"}}
            ]},
        },
    ]
    _write_jsonl(f, records)
    result = parse_session(f)
    assert result is not None
    files = result["files"]
    assert any(fi["file_path"] == "/repo/main.py" for fi in files)
    assert any(fi["tool_name"] == "Edit" for fi in files)


def test_parse_session_sets_summary_from_first_user(tmp_path):
    sid = "summary-test-9999"
    f = tmp_path / f"{sid}.jsonl"
    records = [
        {
            "type": "user", "sessionId": sid, "timestamp": "2026-01-01T10:00:00Z",
            "cwd": "/repo", "gitBranch": "main", "version": "2.0",
            "message": {"role": "user", "content": "initial request"},
        },
        {
            "type": "assistant", "sessionId": sid, "timestamp": "2026-01-01T10:00:01Z",
            "cwd": "/repo", "gitBranch": "main", "version": "2.0",
            "message": {"role": "assistant", "content": [{"type": "text", "text": "response"}]},
        },
    ]
    _write_jsonl(f, records)
    result = parse_session(f)
    assert result is not None
    assert "initial request" in result["summary"]


def test_extract_text_string():
    assert _extract_text("hello") == "hello"


def test_extract_text_list():
    content = [{"type": "text", "text": "hi"}, {"type": "tool_use", "name": "Bash"}]
    result = _extract_text(content)
    assert "hi" in result
    assert "[Bash]" in result


def test_extract_text_empty():
    assert _extract_text([]) == ""
    assert _extract_text(None) == ""


def test_parse_session_turn_has_assistant_summary(tmp_path):
    sid = "asummary-long-0001"
    f = tmp_path / f"{sid}.jsonl"
    long_text = "x" * 400
    records = [
        {
            "type": "user", "sessionId": sid, "timestamp": "2026-01-01T10:00:00Z",
            "cwd": "/repo", "gitBranch": "main", "version": "2.0",
            "message": {"role": "user", "content": "question"},
        },
        {
            "type": "assistant", "sessionId": sid, "timestamp": "2026-01-01T10:00:01Z",
            "cwd": "/repo", "gitBranch": "main", "version": "2.0",
            "message": {"role": "assistant", "content": [{"type": "text", "text": long_text}]},
        },
    ]
    _write_jsonl(f, records)
    result = parse_session(f)
    assert result is not None
    turn = result["turns"][0]
    assert "assistant_summary" in turn
    assert len(turn["assistant_summary"]) <= 300


def test_parse_session_assistant_summary_short_text(tmp_path):
    sid = "asummary-short-0002"
    f = tmp_path / f"{sid}.jsonl"
    short_text = "short answer"
    records = [
        {
            "type": "user", "sessionId": sid, "timestamp": "2026-01-01T10:00:00Z",
            "cwd": "/repo", "gitBranch": "main", "version": "2.0",
            "message": {"role": "user", "content": "question"},
        },
        {
            "type": "assistant", "sessionId": sid, "timestamp": "2026-01-01T10:00:01Z",
            "cwd": "/repo", "gitBranch": "main", "version": "2.0",
            "message": {"role": "assistant", "content": [{"type": "text", "text": short_text}]},
        },
    ]
    _write_jsonl(f, records)
    result = parse_session(f)
    assert result is not None
    turn = result["turns"][0]
    assert turn["assistant_summary"] == turn["assistant"]
