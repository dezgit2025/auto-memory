"""Tests for the Claude Code CLI entry point."""
from __future__ import annotations

import json

import pytest


ENV_KEY = "SESSION_RECALL_ENABLE_CLAUDE_BACKEND"


# --- env var gate ---


def test_env_gate_exits_2_without_var(monkeypatch):
    monkeypatch.delenv(ENV_KEY, raising=False)
    from session_recall.providers.claude_code.cli import main

    with pytest.raises(SystemExit) as exc_info:
        main([])
    assert exc_info.value.code == 2


def test_env_gate_stderr_contains_url(monkeypatch, capsys):
    monkeypatch.delenv(ENV_KEY, raising=False)
    from session_recall.providers.claude_code.cli import main

    with pytest.raises(SystemExit):
        main([])
    err = capsys.readouterr().err
    assert "SESSION_RECALL_ENABLE_CLAUDE_BACKEND=1" in err
    assert "https://github.com/dezgit2025/auto-memory#claude-code" in err


# --- --help ---


def test_help_works(monkeypatch):
    monkeypatch.setenv(ENV_KEY, "1")
    from session_recall.providers.claude_code.cli import main

    with pytest.raises(SystemExit) as exc_info:
        main(["--help"])
    assert exc_info.value.code == 0


# --- list subcommand ---


def test_list_json_output(monkeypatch, capsys):
    monkeypatch.setenv(ENV_KEY, "1")
    fake_rows = [{"id": "abc123", "summary": "test", "last_seen": "2025-01-01"}]
    monkeypatch.setattr(
        "session_recall.providers.claude_code.provider.ClaudeCodeProvider.list_sessions",
        lambda self, **kw: fake_rows,
    )
    from session_recall.providers.claude_code.cli import main

    with pytest.raises(SystemExit) as exc_info:
        main(["list", "--json"])
    assert exc_info.value.code == 0
    out = json.loads(capsys.readouterr().out)
    assert out["count"] == 1
    assert out["sessions"] == fake_rows


# --- search subcommand ---


def test_search_json_output(monkeypatch, capsys):
    monkeypatch.setenv(ENV_KEY, "1")
    fake_rows = [{"session_id": "abc", "snippet": "hello"}]
    monkeypatch.setattr(
        "session_recall.providers.claude_code.provider.ClaudeCodeProvider.search",
        lambda self, **kw: fake_rows,
    )
    from session_recall.providers.claude_code.cli import main

    with pytest.raises(SystemExit) as exc_info:
        main(["search", "hello", "--json"])
    assert exc_info.value.code == 0
    out = json.loads(capsys.readouterr().out)
    assert out["query"] == "hello"
    assert out["count"] == 1
    assert out["results"] == fake_rows


# --- files subcommand ---


def test_files_json_output(monkeypatch, capsys):
    monkeypatch.setenv(ENV_KEY, "1")
    fake_rows = [{"file_path": "/foo/bar.py", "tool_name": "write"}]
    monkeypatch.setattr(
        "session_recall.providers.claude_code.provider.ClaudeCodeProvider.recent_files",
        lambda self, **kw: fake_rows,
    )
    from session_recall.providers.claude_code.cli import main

    with pytest.raises(SystemExit) as exc_info:
        main(["files", "--json"])
    assert exc_info.value.code == 0
    out = json.loads(capsys.readouterr().out)
    assert out["count"] == 1
    assert out["files"] == fake_rows


# --- health subcommand ---


def test_health_json_output(monkeypatch, capsys, tmp_path):
    monkeypatch.setenv(ENV_KEY, "1")
    idx = tmp_path / "test-index.db"
    monkeypatch.setattr(
        "session_recall.providers.claude_code.index._index_path",
        lambda: idx,
    )
    from session_recall.providers.claude_code.cli import main

    with pytest.raises(SystemExit) as exc_info:
        main(["health", "--json"])
    assert exc_info.value.code == 0
    out = json.loads(capsys.readouterr().out)
    assert out["index_exists"] is False
    assert out["sessions"] == 0


# --- import isolation ---


def test_main_import_isolation():
    import importlib
    import sys

    mods_before = set(sys.modules.keys())
    importlib.import_module("session_recall.__main__")
    mods_after = set(sys.modules.keys())
    new_mods = mods_after - mods_before
    assert not any("claude_code" in m for m in new_mods)
