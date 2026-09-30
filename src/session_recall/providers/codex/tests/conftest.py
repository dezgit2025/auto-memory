"""Pytest fixtures for the Codex provider test suite.

Everything is synthetic and hermetic: DBs are generated from the captured
schema profiles, rollouts are written fresh per test session, and env
overrides point all three Codex paths at the temp store.
"""

import sqlite3
from types import SimpleNamespace

import pytest

from .. import state_queries
from ._fixture_history import populate_history
from ._fixture_rollouts import build_all as build_rollouts
from ._fixture_schema import build_empty_db
from ._fixture_state import (
    REF_NOW_MS,
    insert_threads,
    make_uuid7,
    small_store_threads,
)


def build_small_store(root):
    """Create the standard small store under `root`; returns a namespace."""
    root.mkdir(parents=True, exist_ok=True)
    sessions_root = root / "sessions"
    state_db = root / "state_5.sqlite"
    history_db = root / "thread_history_1.sqlite"
    build_empty_db(state_db, "state")
    build_empty_db(history_db, "history")
    rollouts = build_rollouts(sessions_root, root / "outside")
    threads = small_store_threads(sessions_root)
    conn = sqlite3.connect(state_db)
    try:
        insert_threads(conn, threads)
    finally:
        conn.close()
    hconn = sqlite3.connect(history_db)
    try:
        populate_history(hconn, threads)
    finally:
        hconn.close()
    return SimpleNamespace(
        root=root, state_db=state_db, history_db=history_db,
        sessions_root=sessions_root, rollouts=rollouts,
        threads=threads, ref_now_ms=REF_NOW_MS,
    )


@pytest.fixture()
def codex_store(tmp_path):
    """Fresh small store per test."""
    return build_small_store(tmp_path / "codex")


@pytest.fixture()
def codex_env(codex_store, monkeypatch):
    """Point the three Codex env overrides at the temp store."""
    monkeypatch.setattr(
        state_queries,
        "time",
        SimpleNamespace(time=lambda: REF_NOW_MS / 1000),
    )
    monkeypatch.setenv("SESSION_RECALL_CODEX_STATE_DB", str(codex_store.state_db))
    monkeypatch.setenv(
        "SESSION_RECALL_CODEX_HISTORY_DB", str(codex_store.history_db)
    )
    monkeypatch.setenv(
        "SESSION_RECALL_CODEX_SESSIONS_ROOT", str(codex_store.sessions_root)
    )
    return codex_store


def build_scaled_store(root, n_threads: int):
    """Scaled store for budget tests: n paginated threads, deterministic."""
    from ._fixture_state import _base_row, insert_threads as _ins

    root.mkdir(parents=True, exist_ok=True)
    state_db = root / "state_5.sqlite"
    history_db = root / "thread_history_1.sqlite"
    build_empty_db(state_db, "state")
    build_empty_db(history_db, "history")
    rows = []
    for i in range(n_threads):
        ts = REF_NOW_MS - (i % 30) * 86_400_000 - i * 1000
        row = _base_row(make_uuid7(ts, 1000 + i), ts)
        row.update(title=f"scaled thread {i:04d}")
        rows.append(row)
    conn = sqlite3.connect(state_db)
    try:
        _ins(conn, rows)
    finally:
        conn.close()
    hconn = sqlite3.connect(history_db)
    try:
        populate_history(hconn, rows)
    finally:
        hconn.close()
    return SimpleNamespace(root=root, state_db=state_db, history_db=history_db,
                           threads=rows)


@pytest.fixture(scope="session")
def scaled_store_factory(tmp_path_factory):
    """Lazy session-scoped factory: scaled_store_factory(500)."""
    cache = {}

    def factory(n_threads: int = 500):
        if n_threads not in cache:
            root = tmp_path_factory.mktemp(f"codex-scaled-{n_threads}")
            cache[n_threads] = build_scaled_store(root, n_threads)
        return cache[n_threads]

    return factory
