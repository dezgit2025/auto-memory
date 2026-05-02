"""Tests for Claude Code provider."""
from __future__ import annotations

import time

import pytest

from session_recall.providers.claude_code.provider import ClaudeCodeProvider


@pytest.fixture()
def fake_projects(tmp_path, monkeypatch):
    projects = tmp_path / "projects"
    projects.mkdir()
    monkeypatch.setattr(
        "session_recall.providers.claude_code.detect.CC_PROJECTS_DIR",
        projects,
    )
    monkeypatch.setattr(
        "session_recall.providers.claude_code.provider.CC_PROJECTS_DIR",
        projects,
    )
    return projects


@pytest.fixture()
def fake_index(tmp_path, monkeypatch):
    idx = tmp_path / "test-index.db"
    monkeypatch.setattr(
        "session_recall.providers.claude_code.provider._index_path",
        lambda: idx,
    )
    monkeypatch.setattr(
        "session_recall.providers.claude_code.index._index_path",
        lambda: idx,
    )
    return idx


# --- is_available ---


def test_is_available_true(fake_projects):
    proj = fake_projects / "Users-test-proj"
    proj.mkdir()
    (proj / "session.jsonl").write_text("")

    p = ClaudeCodeProvider()
    assert p.is_available() is True


def test_is_available_false_missing_dir(tmp_path, monkeypatch):
    monkeypatch.setattr(
        "session_recall.providers.claude_code.provider.CC_PROJECTS_DIR",
        tmp_path / "nonexistent",
    )
    p = ClaudeCodeProvider()
    assert p.is_available() is False


def test_is_available_false_no_jsonl(fake_projects):
    proj = fake_projects / "Users-test-proj"
    proj.mkdir()
    # directory exists but no .jsonl files
    p = ClaudeCodeProvider()
    assert p.is_available() is False


# --- list_checkpoints ---


def test_list_checkpoints_returns_empty():
    p = ClaudeCodeProvider()
    assert p.list_checkpoints(repo=None, limit=10, days=None) == []


# --- uses_jsonl_scan ---


def test_uses_jsonl_scan():
    p = ClaudeCodeProvider()
    assert p.uses_jsonl_scan() is True


# --- schema_problems ---


def test_schema_problems_empty():
    p = ClaudeCodeProvider()
    assert p.schema_problems() == []


# --- _ensure_index ---


def test_ensure_index_builds_when_missing(fake_projects, fake_index, monkeypatch):
    calls = []
    monkeypatch.setattr(
        "session_recall.providers.claude_code.provider.build_index",
        lambda **kw: calls.append("build") or {"indexed": 0, "skipped": 0, "errors": 0, "total": 0},
    )
    p = ClaudeCodeProvider()
    p._ensure_index()
    assert calls == ["build"]


def test_ensure_index_skips_when_fresh(fake_projects, fake_index, monkeypatch):
    # Create the index file and make it fresh
    fake_index.write_text("")

    calls = []
    monkeypatch.setattr(
        "session_recall.providers.claude_code.provider.build_index",
        lambda **kw: calls.append("build") or {"indexed": 0, "skipped": 0, "errors": 0, "total": 0},
    )
    p = ClaudeCodeProvider()
    p._ensure_index()
    assert calls == []


def test_ensure_index_rebuilds_when_stale(fake_projects, fake_index, monkeypatch):
    import os

    # Create the index file and backdate it
    fake_index.write_text("")
    old_time = time.time() - 120
    os.utime(str(fake_index), (old_time, old_time))

    calls = []
    monkeypatch.setattr(
        "session_recall.providers.claude_code.provider.build_index",
        lambda **kw: calls.append("build") or {"indexed": 0, "skipped": 0, "errors": 0, "total": 0},
    )
    p = ClaudeCodeProvider()
    p._ensure_index()
    assert calls == ["build"]


# --- list_sessions ---


def test_list_sessions_returns_results(fake_projects, fake_index, monkeypatch):
    fake_rows = [{"id": "abc123", "summary": "test session", "last_seen": "2025-01-01"}]
    monkeypatch.setattr(
        "session_recall.providers.claude_code.provider.build_index",
        lambda **kw: {"indexed": 0, "skipped": 0, "errors": 0, "total": 0},
    )
    monkeypatch.setattr(
        "session_recall.providers.claude_code.provider.query_sessions",
        lambda **kw: fake_rows,
    )
    p = ClaudeCodeProvider()
    result = p.list_sessions(repo=None, limit=10, days=30)
    assert len(result) == 1
    assert result[0]["provider"] == "claude_code"
    assert result[0]["_trust_level"] == "claude_code_jsonl"
    assert result[0]["id"] == "abc123"


# --- search ---


def test_search_returns_results(fake_projects, fake_index, monkeypatch):
    fake_rows = [{"session_id": "abc", "snippet": "hello world", "_trust_level": "claude_code_jsonl"}]
    monkeypatch.setattr(
        "session_recall.providers.claude_code.provider.build_index",
        lambda **kw: {"indexed": 0, "skipped": 0, "errors": 0, "total": 0},
    )
    monkeypatch.setattr(
        "session_recall.providers.claude_code.provider.query_search",
        lambda q, **kw: fake_rows,
    )
    p = ClaudeCodeProvider()
    result = p.search(query="hello", repo=None, limit=10, days=30)
    assert len(result) == 1
    assert result[0]["provider"] == "claude_code"
    assert result[0]["_trust_level"] == "claude_code_jsonl"


# --- get_session ---


def test_get_session_returns_result(fake_projects, fake_index, monkeypatch):
    fake_session = {"id": "abc123", "turns": [], "files": []}
    monkeypatch.setattr(
        "session_recall.providers.claude_code.provider.build_index",
        lambda **kw: {"indexed": 0, "skipped": 0, "errors": 0, "total": 0},
    )
    monkeypatch.setattr(
        "session_recall.providers.claude_code.provider.query_show",
        lambda sid, **kw: fake_session,
    )
    p = ClaudeCodeProvider()
    result = p.get_session(session_id="abc123", turns=None, full=False)
    assert result is not None
    assert result["_trust_level"] == "claude_code_jsonl"
    assert result["id"] == "abc123"


def test_get_session_returns_none(fake_projects, fake_index, monkeypatch):
    monkeypatch.setattr(
        "session_recall.providers.claude_code.provider.build_index",
        lambda **kw: {"indexed": 0, "skipped": 0, "errors": 0, "total": 0},
    )
    monkeypatch.setattr(
        "session_recall.providers.claude_code.provider.query_show",
        lambda sid, **kw: None,
    )
    p = ClaudeCodeProvider()
    result = p.get_session(session_id="nonexistent", turns=None, full=False)
    assert result is None
