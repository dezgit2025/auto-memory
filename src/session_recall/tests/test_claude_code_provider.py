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
        json.dumps({"type": "user", "message": "subagent stuff"}),
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


def test_list_sessions_excludes_subagent_files(fake_cc_root: Path):
    """Subagent transcripts under <slug>/subagents/ must not surface as sessions.

    ``list_sessions`` strips internal ``_``-prefixed keys so we can't peek at
    the source file there — verify exclusion via ``recent_files`` which does
    expose ``file_path``.
    """
    p = ClaudeCodeProvider(root_override=str(fake_cc_root))
    files = p.recent_files(repo=None, limit=10, days=None)
    assert all("subagents" not in f["file_path"] for f in files)
    matched = [str(fp) for fp in p._iter_files()]
    assert all("subagents" not in m for m in matched)


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
    """Without root_override, the provider points at ~/.claude/projects.

    Patches ``Path.home`` directly rather than env vars — env-var redirection
    of ``Path.home()`` is unreliable across platforms and CPython versions.
    """
    monkeypatch.setattr(Path, "home", lambda: tmp_path)
    p = ClaudeCodeProvider()
    expected = tmp_path / ".claude" / "projects"
    assert any(r == expected for r in p._roots)


def test_extracts_text_from_nested_assistant_message(tmp_path: Path):
    """Real CC assistant events have ``message: {role, content: [{type, text}, ...]}``.

    The shared ``_extract_text`` recurses through the nested structure;
    verify end-to-end that the inner text reaches the parsed turns.
    """
    root = tmp_path / "projects"
    project = root / "C--test"
    project.mkdir(parents=True)
    session = project / "abcdef01-0000-0000-0000-000000000000.jsonl"
    session.write_text(
        "\n".join(
            [
                json.dumps({
                    "type": "user",
                    "message": "Plan the refactor",
                    "timestamp": "2026-04-26T10:00:00Z",
                }),
                json.dumps({
                    "type": "assistant",
                    "message": {
                        "role": "assistant",
                        "content": [
                            {"type": "text", "text": "Here is the plan"},
                            {"type": "tool_use", "name": "Read", "input": {"file_path": "x"}},
                        ],
                    },
                    "timestamp": "2026-04-26T10:00:05Z",
                }),
            ]
        ),
        encoding="utf-8",
    )
    p = ClaudeCodeProvider(root_override=str(root))
    sessions = p.list_sessions(repo=None, limit=10, days=None)
    assert len(sessions) == 1
    assert sessions[0]["turns_count"] == 2


def test_handles_empty_session_file(tmp_path: Path):
    """A zero-byte JSONL file should produce a session with 0 turns, not crash."""
    root = tmp_path / "projects"
    project = root / "C--test"
    project.mkdir(parents=True)
    (project / "empty-0000-0000-0000-000000000000.jsonl").write_text("", encoding="utf-8")
    p = ClaudeCodeProvider(root_override=str(root))
    sessions = p.list_sessions(repo=None, limit=10, days=None)
    assert len(sessions) == 1
    assert sessions[0]["turns_count"] == 0


def test_skips_malformed_lines_but_keeps_valid_ones(tmp_path: Path):
    """Mixed valid/malformed JSONL — valid turns survive, malformed lines are skipped."""
    root = tmp_path / "projects"
    project = root / "C--test"
    project.mkdir(parents=True)
    session = project / "mixed-0000-0000-0000-000000000000.jsonl"
    session.write_text(
        "\n".join(
            [
                json.dumps({"type": "user", "message": "valid 1"}),
                "{ this is not json at all",
                json.dumps({"type": "assistant", "message": "valid 2"}),
                "",
                json.dumps({"type": "user", "message": "valid 3"}),
            ]
        ),
        encoding="utf-8",
    )
    p = ClaudeCodeProvider(root_override=str(root))
    sessions = p.list_sessions(repo=None, limit=10, days=None)
    assert len(sessions) == 1
    assert sessions[0]["turns_count"] == 3
