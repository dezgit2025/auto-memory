"""Tests for state_queries: filters, ordering, id resolution, counts."""

import sqlite3

import pytest

from ..errors import CodexAmbiguousId, CodexNotFound, CodexUsageError
from ..state_queries import (
    count_files,
    count_turns,
    resolve_thread_id,
    select_threads,
)
from ._fixture_state import OLDBAND_FILE, REF_NOW_MS


def _ro(path):
    conn = sqlite3.connect(f"file:{path}?mode=ro", uri=True)
    conn.row_factory = sqlite3.Row
    return conn


@pytest.fixture()
def state(codex_store):
    conn = _ro(codex_store.state_db)
    yield conn
    conn.close()


@pytest.fixture()
def history(codex_store):
    conn = _ro(codex_store.history_db)
    yield conn
    conn.close()


def _titles(rows):
    return [r["title"] for r in rows]


def test_default_select_excludes_traps_and_archived(state):
    rows = select_threads(state, limit=10, days=30, now_ms=REF_NOW_MS)
    titles = _titles(rows)
    assert len(rows) == 5
    assert "guardian trap" not in titles
    assert "explicit subagent" not in titles
    assert "archived experiment" not in titles


def test_default_select_newest_first(state):
    rows = select_threads(state, limit=10, days=30, now_ms=REF_NOW_MS)
    assert _titles(rows) == [
        "recent-b widget tests",
        "recent-a widget refactor",
        "legacy-recent session",
        "recent-c local scratch",
        "oldband alpha work",
    ]


def test_include_archived_adds_archived_row(state):
    rows = select_threads(
        state, limit=10, days=30, include_archived=True, now_ms=REF_NOW_MS
    )
    assert len(rows) == 6
    assert "archived experiment" in _titles(rows)
    # Sub-agent exclusions are unconditional (§19.3).
    assert "guardian trap" not in _titles(rows)


def test_days_band(state):
    week = select_threads(state, limit=10, days=7, now_ms=REF_NOW_MS)
    assert "oldband alpha work" not in _titles(week)
    assert len(week) == 4
    month = select_threads(state, limit=10, days=30, now_ms=REF_NOW_MS)
    assert "oldband alpha work" in _titles(month)


def test_limit_pushdown_without_repo(state):
    rows = select_threads(state, limit=2, days=30, now_ms=REF_NOW_MS)
    assert _titles(rows) == ["recent-b widget tests", "recent-a widget refactor"]


def test_no_limit_pushdown_with_repo(state):
    rows = select_threads(
        state, repo="github.com/acme/widget", limit=2, days=30, now_ms=REF_NOW_MS
    )
    assert len(rows) == 5  # caller filters + limits after normalization


def test_resolve_short_prefix_rejected(state):
    with pytest.raises(CodexUsageError, match="UUIDv7"):
        resolve_thread_id(state, "01a0")


def test_resolve_collision_prefix_ambiguous(state, codex_store):
    prefix = codex_store.threads[0]["id"][:8]
    assert codex_store.threads[1]["id"].startswith(prefix)  # designed pair
    with pytest.raises(CodexAmbiguousId) as exc:
        resolve_thread_id(state, prefix)
    ids = [c[0] for c in exc.value.candidates]
    assert codex_store.threads[0]["id"] in ids
    assert codex_store.threads[1]["id"] in ids


def test_resolve_unique_longer_prefix(state, codex_store):
    legacy = next(t for t in codex_store.threads if t["history_mode"] == "legacy")
    prefix13 = legacy["id"][:13]  # 12 hex chars + dash
    assert resolve_thread_id(state, prefix13) == legacy["id"]


def test_resolve_full_exact_id(state, codex_store):
    tid = codex_store.threads[3]["id"]
    assert resolve_thread_id(state, tid) == tid


def test_resolve_unknown_prefix_not_found(state):
    with pytest.raises(CodexNotFound):
        resolve_thread_id(state, "ffffffff")


def test_resolve_case_insensitive(state, codex_store):
    tid = codex_store.threads[0]["id"]
    assert resolve_thread_id(state, tid.upper()) == tid


def test_resolve_injection_is_literal(state):
    with pytest.raises(CodexNotFound):
        resolve_thread_id(state, "'; DROP TABLE threads;--")
    assert state.execute("SELECT COUNT(*) FROM threads").fetchone()[0] == 8


def test_counts_per_fixture(history, codex_store):
    oldband = next(t for t in codex_store.threads if "oldband" in t["title"])
    recent = next(t for t in codex_store.threads if "recent-a" in t["title"])
    assert count_turns(history, oldband["id"]) == 1
    assert count_files(history, oldband["id"]) == 1
    assert count_files(history, recent["id"]) == 0
    # File path really is the designed one (sanity on the JSON path query).
    row = history.execute(
        "SELECT json_extract(je.value, '$.path') FROM thread_items, "
        "json_each(thread_items.item_json, '$.changes') je "
        "WHERE thread_id = ? AND item_type = 'fileChange'",
        (oldband["id"],),
    ).fetchone()
    assert row[0] == OLDBAND_FILE
