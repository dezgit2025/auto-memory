"""Reviewer-requested metadata safety regressions."""

from __future__ import annotations

import sqlite3
from dataclasses import replace

import pytest

from session_recall.codex_fix.contracts import ContractError
from session_recall.codex_fix.engine import classify, observe
from session_recall.codex_metadata import StorageChangingError, inspect

from .conftest import readonly_pair


class _RetryInterleavingConnection:
    """Change the real schema between paired captures, never inside product code."""

    def __init__(self, connection, state_path, *, persistent):
        self._connection = connection
        self._state_path = state_path
        self._persistent = persistent
        self.thread_reads = 0
        self.mutations = 0

    def _before_execute(self, sql):
        normalized = str(sql).lower()
        if "table_info" not in normalized or "threads" not in normalized:
            return
        self.thread_reads += 1
        if self.thread_reads % 2 or (self.mutations and not self._persistent):
            return
        self.mutations += 1
        writer = sqlite3.connect(self._state_path)
        try:
            writer.execute(
                f"ALTER TABLE threads ADD COLUMN retry_marker_{self.mutations} TEXT"
            )
            writer.commit()
        finally:
            writer.close()

    def execute(self, sql, *args, **kwargs):
        self._before_execute(sql)
        return self._connection.execute(sql, *args, **kwargs)

    def cursor(self, *args, **kwargs):
        return _RetryInterleavingCursor(
            self, self._connection.cursor(*args, **kwargs)
        )

    def __getattr__(self, name):
        return getattr(self._connection, name)


class _RetryInterleavingCursor:
    def __init__(self, owner, cursor):
        self._owner = owner
        self._cursor = cursor

    def execute(self, sql, *args, **kwargs):
        self._owner._before_execute(sql)
        return self._cursor.execute(sql, *args, **kwargs)

    def __getattr__(self, name):
        return getattr(self._cursor, name)


def _interleaved_pair(store, *, persistent):
    state = sqlite3.connect(f"file:{store.state_db}?mode=ro", uri=True)
    history = sqlite3.connect(f"file:{store.history_db}?mode=ro", uri=True)
    return _RetryInterleavingConnection(
        state, store.state_db, persistent=persistent
    ), state, history


def test_one_time_schema_interleave_stabilizes_on_retry(synthetic_store):
    interleaved, state, history = _interleaved_pair(
        synthetic_store, persistent=False
    )
    try:
        snapshot = inspect((interleaved, history))
    finally:
        state.close()
        history.close()
    columns = snapshot["state"]["tables"][0]["columns"]
    assert columns[-1]["name"] == "retry_marker_1"
    assert interleaved.mutations == 1


def test_persistently_changing_schema_stops_after_two_retries(synthetic_store):
    interleaved, state, history = _interleaved_pair(
        synthetic_store, persistent=True
    )
    try:
        with pytest.raises(StorageChangingError) as raised:
            inspect((interleaved, history))
    finally:
        state.close()
        history.close()
    assert raised.value.code == "storage_changing"
    assert interleaved.mutations == 3


def test_failed_future_migration_does_not_raise_successful_ceiling(synthetic_store):
    connection = sqlite3.connect(synthetic_store.state_db)
    try:
        connection.execute(
            "INSERT INTO _sqlx_migrations "
            "(version, description, installed_on, success, checksum, execution_time) "
            "VALUES (56, 'failed future', '2026-09-20 00:00:00', 0, ?, 0)",
            (b"",),
        )
        connection.commit()
    finally:
        connection.close()
    with readonly_pair(synthetic_store) as connections:
        snapshot = inspect(connections)
    assert snapshot["state"]["migration_ceiling"] == 55
    assert snapshot["state"]["failed_migrations"] == 1


@pytest.mark.parametrize(
    ("database", "table"),
    [("state", "threads"), ("history", "thread_turns")],
)
def test_missing_used_table_is_never_assistance_eligible(
    synthetic_store, engine_case_factory, database, table
):
    path = synthetic_store.state_db if database == "state" else synthetic_store.history_db
    connection = sqlite3.connect(path)
    try:
        connection.execute(f'DROP TABLE "{table}"')
        connection.commit()
    finally:
        connection.close()

    try:
        with readonly_pair(synthetic_store) as connections:
            snapshot = inspect(connections)
    except (ContractError, sqlite3.DatabaseError):
        return
    case = engine_case_factory()
    observation = observe(snapshot, case.context)
    context = replace(case.context, current_observation=observation)
    result = classify(observation, context)
    assert result["status"] == "invalid"
    assert result["status"] != "assistance_eligible"
