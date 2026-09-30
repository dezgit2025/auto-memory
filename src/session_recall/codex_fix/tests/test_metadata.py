"""Read-only, stable-pair metadata inspection tests."""

import hashlib
import sqlite3

from session_recall.codex_fix.contracts import digest
import pytest

from session_recall.codex_metadata import StorageChangingError, inspect

from .conftest import readonly_pair


def _file_digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _expected_profile(profile):
    tables = []
    for name, rows in profile["tables"].items():
        tables.append(
            {
                "name": name,
                "columns": [
                    {
                        "cid": row[0],
                        "name": row[1],
                        "declared_type": row[2],
                        "not_null": bool(row[3]),
                        "default_sql": row[4],
                        "pk_position": row[5],
                    }
                    for row in rows
                ],
            }
        )
    return {
        "filename": profile["db_filename"],
        "migration_ceiling": profile["migration_ceiling"],
        "failed_migrations": profile["failed_migrations"],
        "json1": profile["json1"],
        "tables": tables,
    }


class _InterleavingConnection:
    """Mutate the real state DB between every paired schema capture."""

    def __init__(self, connection, state_path):
        self._connection = connection
        self._state_path = state_path
        self._thread_reads = 0

    def _before_execute(self, sql):
        normalized = str(sql).lower()
        if "table_info" not in normalized or "threads" not in normalized:
            return
        self._thread_reads += 1
        if self._thread_reads % 2:
            return
        marker = self._thread_reads // 2
        writer = sqlite3.connect(self._state_path)
        try:
            writer.execute(
                f"ALTER TABLE threads ADD COLUMN unstable_marker_{marker} TEXT"
            )
            writer.commit()
        finally:
            writer.close()

    def execute(self, sql, *args, **kwargs):
        self._before_execute(sql)
        return self._connection.execute(sql, *args, **kwargs)

    def cursor(self, *args, **kwargs):
        return _InterleavingCursor(self, self._connection.cursor(*args, **kwargs))

    def __getattr__(self, name):
        return getattr(self._connection, name)


class _InterleavingCursor:
    def __init__(self, owner, cursor):
        self._owner = owner
        self._cursor = cursor

    def execute(self, sql, *args, **kwargs):
        self._owner._before_execute(sql)
        return self._cursor.execute(sql, *args, **kwargs)

    def __getattr__(self, name):
        return getattr(self._cursor, name)


def test_inspect_matches_reviewed_projection_and_is_read_only(synthetic_store):
    before = (_file_digest(synthetic_store.state_db), _file_digest(synthetic_store.history_db))
    with readonly_pair(synthetic_store) as connections:
        snapshot = inspect(connections)
    after = (_file_digest(synthetic_store.state_db), _file_digest(synthetic_store.history_db))

    assert before == after
    assert snapshot["storage_family"] == "codex-state-v5-history-v1"
    assert snapshot["state"] == _expected_profile(synthetic_store.oracle["state"])
    assert snapshot["history"] == _expected_profile(synthetic_store.oracle["history"])
    semantic = {
        "storage_family": snapshot["storage_family"],
        "state": snapshot["state"],
        "history": snapshot["history"],
    }
    assert snapshot["schema_fingerprint"] == digest(semantic)


def test_repeated_fresh_readonly_pairs_are_stable(synthetic_store):
    with readonly_pair(synthetic_store) as connections:
        first = inspect(connections)
    with readonly_pair(synthetic_store) as connections:
        second = inspect(connections)
    assert first == second


def test_change_between_internal_captures_is_rejected(synthetic_store):
    state = sqlite3.connect(f"file:{synthetic_store.state_db}?mode=ro", uri=True)
    history = sqlite3.connect(f"file:{synthetic_store.history_db}?mode=ro", uri=True)
    interleaved = _InterleavingConnection(state, synthetic_store.state_db)
    try:
        with pytest.raises(StorageChangingError) as raised:
            inspect((interleaved, history))
    finally:
        state.close()
        history.close()
    assert raised.value.code == "storage_changing"


def test_descriptions_and_unrelated_objects_are_not_semantic(synthetic_store):
    with readonly_pair(synthetic_store) as connections:
        before = inspect(connections)
    connection = sqlite3.connect(synthetic_store.state_db)
    try:
        connection.execute("CREATE TABLE unrelated_diagnostic (value TEXT)")
        connection.execute(
            "UPDATE _sqlx_migrations SET description = ? WHERE version = ?",
            ("changed diagnostic only", synthetic_store.oracle["state"]["migration_ceiling"]),
        )
        connection.commit()
    finally:
        connection.close()
    with readonly_pair(synthetic_store) as connections:
        after = inspect(connections)
    assert after["state"] == before["state"]
    assert after["schema_fingerprint"] == before["schema_fingerprint"]
