"""Tests for the ClaudeCodeProvider file-backed session provider."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from session_recall.providers.file.claude_code import ClaudeCodeProvider


@pytest.fixture
def fake_cc_root(tmp_path: Path) -> Path:
    """Build a fake ~/.claude/projects tree with two sessions and a subagent."""
    root = tmp_path / "projects"
    project = root / "C--Users-test-myproject"
    project.mkdir(parents=True)

    # Session 1 — short, 2 turns
    s1 = project / "11111111-aaaa-bbbb-cccc-dddddddddddd.jsonl"
    s1.write_text(
        "\n".join(
            [
                json.dumps({"type": "user", "message": "Hello there", "timestamp": "2026-04-25T10:00:00Z"}),
                json.dumps({"type": "assistant", "message": "Hi! How can I help?", "timestamp": "2026-04-25T10:00:05Z"}),
            ]
        ),
        encoding="utf-8",
    )

    # Session 2 — longer, 4 turns
    s2 = project / "22222222-aaaa-bbbb-cccc-dddddddddddd.jsonl"
    s2.write_text(
        "\n".join(
            [
                json.dumps({"type": "user", "message": "Refactor this code", "timestamp": "2026-04-26T09:00:00Z"}),
                json.dumps({"type": "assistant", "message": "Sure, here's a cleaner version", "timestamp": "2026-04-26T09:00:30Z"}),
                json.dumps({"type": "user", "message": "Add tests", "timestamp": "2026-04-26T09:01:00Z"}),
                json.dumps({"type": "assistant", "message": "Tests added, all passing", "timestamp": "2026-04-26T09:02:00Z"}),
            ]
        ),
        encoding="utf-8",
    )

    # Subagent transcript — should NOT be picked up by the */*.jsonl glob
    subagents = project / "subagents"
    subagents.mkdir()
    (subagents / "agent-deadbeef.jsonl").write_text(
        json.dumps({"type": "user", "message": "subagent stuff"}) + "\n",
        encoding="utf-8",
    )

    return root


def test_provider_id_is_claude_code(fake_cc_root: Path):
    p = ClaudeCodeProvider(root_override=str(fake_cc_root))
    assert p.provider_id == "claude_code"
    assert p.provider_name == "Claude Code"


def test_is_available_true_when_root_exists(fake_cc_root: Path):
    p = ClaudeCodeProvider(root_override=str(fake_cc_root))
    assert p.is_available() is True


def test_is_available_false_when_root_missing(tmp_path: Path):
    nonexistent = tmp_path / "nope"
    p = ClaudeCodeProvider(root_override=str(nonexistent))
    assert p.is_available() is False


def test_list_sessions_finds_both_top_level(fake_cc_root: Path):
    p = ClaudeCodeProvider(root_override=str(fake_cc_root))
    sessions = p.list_sessions(repo=None, limit=10, days=None)
    assert len(sessions) == 2
    # Subagent file (under subagents/) must NOT be included
    paths = [s.get("_path", "") for s in sessions]
    assert all("subagents" not in pp for pp in paths)


def test_list_sessions_counts_turns(fake_cc_root: Path):
    p = ClaudeCodeProvider(root_override=str(fake_cc_root))
    sessions = p.list_sessions(repo=None, limit=10, days=None)
    counts = sorted(s["turns_count"] for s in sessions)
    assert counts == [2, 4]


def test_uses_jsonl_scan_returns_true(fake_cc_root: Path):
    p = ClaudeCodeProvider(root_override=str(fake_cc_root))
    assert p.uses_jsonl_scan() is True


def test_provider_short_code_is_cc(fake_cc_root: Path):
    """Output 'provider' field should be 'cc' (short), not 'claude_code'."""
    p = ClaudeCodeProvider(root_override=str(fake_cc_root))
    sessions = p.list_sessions(repo=None, limit=10, days=None)
    assert all(s["provider"] == "cc" for s in sessions)


def test_recent_files_walks_top_level_only(fake_cc_root: Path):
    p = ClaudeCodeProvider(root_override=str(fake_cc_root))
    files = p.recent_files(repo=None, limit=10, days=None)
    assert len(files) == 2
    assert all("subagents" not in f["file_path"] for f in files)


def test_default_root_is_dot_claude_projects(monkeypatch, tmp_path: Path):
    """Without root_override, the provider points at ~/.claude/projects."""
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv("USERPROFILE", str(tmp_path))  # Windows
    p = ClaudeCodeProvider()
    expected = (Path.home() / ".claude" / "projects").resolve()
    assert any(r.resolve() == expected for r in p._roots)
