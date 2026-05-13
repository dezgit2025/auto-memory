"""Tests for Claude Code JSONL reader."""
from __future__ import annotations

import json
import pathlib

import pytest

from session_recall.providers.claude_code.reader import (
    _cwd_to_repo,
    _extract_text,
    parse_session,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

def _write_jsonl(path: pathlib.Path, records: list[dict]) -> None:
    with open(path, "w", encoding="utf-8") as f:
        for rec in records:
            f.write(json.dumps(rec) + "\n")


@pytest.fixture()
def session_dir(tmp_path: pathlib.Path) -> pathlib.Path:
    d = tmp_path / "projects" / "test"
    d.mkdir(parents=True)
    return d


BASIC_RECORDS = [
    {"type": "user", "timestamp": "2025-01-01T00:00:00Z",
     "cwd": "/home/u/proj", "gitBranch": "main", "version": "1.0",
     "message": {"content": "hello world"}},
    {"type": "assistant", "timestamp": "2025-01-01T00:00:01Z",
     "message": {"content": [{"type": "text", "text": "hi there"}]}},
]


# ---------------------------------------------------------------------------
# parse_session — happy path
# ---------------------------------------------------------------------------

class TestParseSession:
    def test_normal_jsonl(self, session_dir: pathlib.Path) -> None:
        fp = session_dir / "abc123.jsonl"
        _write_jsonl(fp, BASIC_RECORDS)
        result = parse_session(fp, root=session_dir.parent)
        assert result is not None
        assert result["id"] == "abc123"
        assert result["cwd"] == "/home/u/proj"
        assert result["branch"] == "main"
        assert result["turns_count"] == 1
        assert result["turns"][0]["user"] == "hello world"
        assert "hi there" in result["turns"][0]["assistant"]

    def test_empty_session_returns_none(self, session_dir: pathlib.Path) -> None:
        fp = session_dir / "empty.jsonl"
        fp.write_text("")
        result = parse_session(fp, root=session_dir.parent)
        assert result is None

    def test_last_prompt_used_as_summary(self, session_dir: pathlib.Path) -> None:
        records = BASIC_RECORDS + [
            {"type": "last-prompt", "lastPrompt": "summarize this"},
        ]
        fp = session_dir / "lp.jsonl"
        _write_jsonl(fp, records)
        result = parse_session(fp, root=session_dir.parent)
        assert result is not None
        assert result["summary"] == "summarize this"

    def test_tool_files_collected(self, session_dir: pathlib.Path) -> None:
        records = [
            {"type": "user", "timestamp": "t1", "cwd": "/x",
             "message": {"content": "do it"}},
            {"type": "assistant", "timestamp": "t2",
             "message": {"content": [
                 {"type": "tool_use", "name": "Read",
                  "input": {"file_path": "/x/foo.py"}},
             ]}},
        ]
        fp = session_dir / "tools.jsonl"
        _write_jsonl(fp, records)
        result = parse_session(fp, root=session_dir.parent)
        assert result is not None
        assert result["files_count"] == 1
        assert result["files"][0]["file_path"] == "/x/foo.py"


# ---------------------------------------------------------------------------
# Bounded read — oversized lines are skipped
# ---------------------------------------------------------------------------

class TestBoundedRead:
    def test_oversized_line_skipped(self, session_dir: pathlib.Path) -> None:
        fp = session_dir / "big.jsonl"
        with open(fp, "w") as f:
            f.write(json.dumps(BASIC_RECORDS[0]) + "\n")
            # >1MB line
            f.write('{"type":"user","big":"' + "x" * 1_100_000 + '"}\n')
            f.write(json.dumps(BASIC_RECORDS[1]) + "\n")
        result = parse_session(fp, root=session_dir.parent)
        assert result is not None
        assert result["turns_count"] == 1


# ---------------------------------------------------------------------------
# Symlink rejection (S6)
# ---------------------------------------------------------------------------

class TestSymlinkRejection:
    def test_symlink_outside_root_rejected(self, tmp_path: pathlib.Path) -> None:
        root = tmp_path / "allowed"
        root.mkdir()
        outside = tmp_path / "outside"
        outside.mkdir()
        real_file = outside / "session.jsonl"
        _write_jsonl(real_file, BASIC_RECORDS)
        link = root / "session.jsonl"
        link.symlink_to(real_file)
        result = parse_session(link, root=root)
        assert result is None

    def test_file_inside_root_accepted(self, session_dir: pathlib.Path) -> None:
        fp = session_dir / "ok.jsonl"
        _write_jsonl(fp, BASIC_RECORDS)
        result = parse_session(fp, root=session_dir.parent)
        assert result is not None

    def test_nonexistent_file_returns_none(self, session_dir: pathlib.Path) -> None:
        fp = session_dir / "nope.jsonl"
        result = parse_session(fp, root=session_dir.parent)
        assert result is None


# ---------------------------------------------------------------------------
# Malformed JSON handling
# ---------------------------------------------------------------------------

class TestMalformedJson:
    def test_malformed_lines_skipped(self, session_dir: pathlib.Path) -> None:
        fp = session_dir / "bad.jsonl"
        with open(fp, "w") as f:
            f.write("NOT JSON\n")
            f.write("{bad json}\n")
            f.write(json.dumps(BASIC_RECORDS[0]) + "\n")
            f.write(json.dumps(BASIC_RECORDS[1]) + "\n")
        result = parse_session(fp, root=session_dir.parent)
        assert result is not None
        assert result["turns_count"] == 1


# ---------------------------------------------------------------------------
# _extract_text
# ---------------------------------------------------------------------------

class TestExtractText:
    def test_string_input(self) -> None:
        assert _extract_text("hello") == "hello"

    def test_string_truncated_at_500(self) -> None:
        assert len(_extract_text("a" * 600)) == 500

    def test_list_with_text_block(self) -> None:
        blocks = [{"type": "text", "text": "foo"}]
        assert _extract_text(blocks) == "foo"

    def test_list_with_tool_use(self) -> None:
        blocks = [{"type": "tool_use", "name": "Read"}]
        assert _extract_text(blocks) == "[Read]"

    def test_list_with_tool_result(self) -> None:
        blocks = [{"type": "tool_result", "content": "output"}]
        assert _extract_text(blocks) == "output"

    def test_non_dict_block_ignored(self) -> None:
        assert _extract_text([42, "string"]) == ""

    def test_none_returns_empty(self) -> None:
        assert _extract_text(None) == ""

    def test_int_returns_empty(self) -> None:
        assert _extract_text(123) == ""


# ---------------------------------------------------------------------------
# _cwd_to_repo
# ---------------------------------------------------------------------------

class TestCwdToRepo:
    def test_two_segments(self) -> None:
        assert _cwd_to_repo("/home/user/my-project") == "user/my-project"

    def test_deep_path(self) -> None:
        assert _cwd_to_repo("/a/b/c/owner/repo") == "owner/repo"

    def test_single_segment(self) -> None:
        assert _cwd_to_repo("repo") == "repo"
