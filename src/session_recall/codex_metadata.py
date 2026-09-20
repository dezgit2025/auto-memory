"""Stable read-only projection of Codex storage metadata used by recall."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from .codex_fix.contracts import ContractError, digest, validate


class StorageChangingError(RuntimeError):
    """The used schema changed during a dual metadata capture."""

    code = "storage_changing"


_TABLES = {
    "state": ("threads", "_sqlx_migrations"),
    "history": ("thread_items", "thread_turns", "_sqlx_migrations"),
}


def _filename(connection: Any) -> str:
    rows = connection.execute("PRAGMA database_list").fetchall()
    for row in rows:
        if row[1] == "main":
            return Path(row[2]).name or ":memory:"
    return ":memory:"


def _columns(connection: Any, table_name: str) -> list[dict[str, Any]]:
    # Names are selected exclusively from the closed _TABLES allowlist.
    rows = connection.execute(f'PRAGMA table_info("{table_name}")').fetchall()
    return [
        {
            "cid": row[0],
            "name": row[1],
            "declared_type": row[2],
            "not_null": bool(row[3]),
            "default_sql": row[4],
            "pk_position": row[5],
        }
        for row in rows
    ]


def _profile(connection: Any, family: str) -> dict[str, Any]:
    migration = connection.execute(
        'SELECT COALESCE(MAX(CASE WHEN "success" = 1 THEN "version" END), 0), '
        'COALESCE(SUM(CASE WHEN "success" = 1 THEN 0 ELSE 1 END), 0) '
        'FROM "_sqlx_migrations"'
    ).fetchone()
    try:
        json1 = bool(connection.execute("SELECT json_valid('null')").fetchone()[0])
    except Exception:  # sqlite builds without JSON1 reject the capability probe.
        json1 = False
    tables = [
        {"name": name, "columns": _columns(connection, name)}
        for name in _TABLES[family]
    ]
    if any(not table["columns"] for table in tables):
        raise ContractError("storage_invalid", f"{family} used table is missing")
    return {
        "filename": _filename(connection),
        "migration_ceiling": migration[0],
        "failed_migrations": migration[1],
        "json1": json1,
        "tables": tables,
    }


def _capture(state_conn: Any, history_conn: Any) -> dict[str, Any]:
    semantic = {
        "storage_family": "codex-state-v5-history-v1",
        "state": _profile(state_conn, "state"),
        "history": _profile(history_conn, "history"),
    }
    return {
        "format_version": 1,
        **semantic,
        "schema_fingerprint": digest(semantic),
        "diagnostics": [],
    }


def inspect(connections: tuple[Any, Any]) -> dict[str, Any]:
    """Capture the used state/history metadata twice and reject instability."""
    if not isinstance(connections, tuple) or len(connections) != 2:
        raise TypeError("inspect expects a (state_conn, history_conn) pair")
    state_conn, history_conn = connections
    for _attempt in range(3):
        first = _capture(state_conn, history_conn)
        second = _capture(state_conn, history_conn)
        if first == second:
            return validate(second, "SchemaSnapshot")
    raise StorageChangingError("Codex metadata changed during inspection")
