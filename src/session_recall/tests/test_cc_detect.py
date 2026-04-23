"""Tests for backends/claude_code/detect.py."""
import pathlib
import sys
import time
import pytest
from session_recall.backends.claude_code.detect import (
    encode_project_path, decode_project_path, _safe_mtime, list_session_files
)


def test_encode_windows_path():
    # On Windows the function uses drive-letter encoding; on other platforms it treats
    # the string as a plain path. Document both behaviours.
    result = encode_project_path("C:\\Users\\foo\\my-project")
    if sys.platform == "win32":
        assert result == "C--Users-foo-my-project"
    else:
        # On non-Windows os.name != 'nt', so backslashes are treated as path separators
        # that get replaced with hyphens (no drive-letter prefix).
        assert "C" in result and "Users" in result and "my-project" in result


def test_encode_unix_path():
    result = encode_project_path("/home/user/my-project")
    assert result == "home-user-my-project"


def test_decode_windows_path():
    # decode_project_path always applies its logic regardless of platform
    result = decode_project_path("C--Users-foo-bar")
    # On any platform, decode_project_path returns Windows-style path for C-- prefix
    assert result.startswith("C:\\") or result.startswith("C:/")
    assert "foo" in result


def test_decode_unix_path():
    result = decode_project_path("home-user-my-project")
    # Unix path: starts with / and hyphens become slashes
    assert result.startswith("/")
    assert "home" in result


def test_safe_mtime_nonexistent(tmp_path):
    missing = tmp_path / "nonexistent.jsonl"
    assert _safe_mtime(missing) == 0.0


def test_safe_mtime_existing(tmp_path):
    f = tmp_path / "test.jsonl"
    f.write_text("{}")
    assert _safe_mtime(f) > 0.0


def test_list_session_files_empty_dir(tmp_path):
    result = list_session_files(project_dir=tmp_path)
    assert result == []


def test_list_session_files_returns_jsonl_only(tmp_path):
    (tmp_path / "session1.jsonl").write_text("{}")
    (tmp_path / "session2.jsonl").write_text("{}")
    (tmp_path / "other.txt").write_text("ignored")
    result = list_session_files(project_dir=tmp_path)
    assert len(result) == 2
    assert all(p.suffix == ".jsonl" for p in result)


def test_list_session_files_sorted_by_mtime(tmp_path):
    a = tmp_path / "old.jsonl"
    a.write_text("{}")
    time.sleep(0.05)
    b = tmp_path / "new.jsonl"
    b.write_text("{}")
    result = list_session_files(project_dir=tmp_path)
    assert result[0].name == "new.jsonl"
