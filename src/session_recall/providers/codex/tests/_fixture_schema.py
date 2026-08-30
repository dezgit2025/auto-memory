"""Build empty synthetic Codex DBs from the machine-captured schema profiles.

The captured JSON (verifications/captured-profiles.json) is the single source
of truth — CREATE TABLE statements are generated from its table_info rows,
never hand-typed.
"""

import json
import sqlite3
from pathlib import Path

_PROFILES_PATH = (
    Path(__file__).resolve().parent.parent / "verifications" / "captured-profiles.json"
)

# Deterministic timestamp for migration rows (never CURRENT_TIMESTAMP).
MIGRATION_INSTALLED_ON = "2026-08-01 00:00:00"


def load_profiles() -> dict:
    """Load the captured schema profiles JSON."""
    with open(_PROFILES_PATH, encoding="utf-8") as f:
        return json.load(f)


def create_table_sql(table_name: str, table_info: list) -> str:
    """Generate CREATE TABLE from captured PRAGMA table_info rows.

    Rows are [cid, name, type, notnull, dflt_value, pk]; pk > 0 gives the
    1-based position in a (possibly composite) primary key.
    """
    cols = []
    pk_cols = [r for r in table_info if r[5] > 0]
    single_pk = len(pk_cols) == 1
    for _cid, name, ctype, notnull, dflt, pk in table_info:
        part = f'"{name}" {ctype}'
        if single_pk and pk:
            part += " PRIMARY KEY"
        if notnull:
            part += " NOT NULL"
        if dflt is not None:
            part += f" DEFAULT {dflt}"
        cols.append(part)
    if not single_pk and pk_cols:
        ordered = sorted(pk_cols, key=lambda r: r[5])
        names = ", ".join(f'"{r[1]}"' for r in ordered)
        cols.append(f"PRIMARY KEY ({names})")
    return f'CREATE TABLE "{table_name}" ({", ".join(cols)})'


def insert_migrations(conn: sqlite3.Connection, ceiling: int, top_desc: str) -> None:
    """Insert success=1 migration rows for versions 1..ceiling."""
    for version in range(1, ceiling + 1):
        desc = top_desc if version == ceiling else f"migration {version:03d}"
        conn.execute(
            "INSERT INTO _sqlx_migrations "
            "(version, description, installed_on, success, checksum, execution_time) "
            "VALUES (?, ?, ?, 1, ?, 0)",
            (version, desc, MIGRATION_INSTALLED_ON, b""),
        )


def build_empty_db(db_path: Path, db_key: str) -> None:
    """Create a synthetic DB (state or history) with exact captured schema."""
    profiles = load_profiles()
    entry = profiles[db_key]
    conn = sqlite3.connect(db_path)
    try:
        for table_name, table_info in entry["tables"].items():
            conn.execute(create_table_sql(table_name, table_info))
        insert_migrations(
            conn, entry["migration_ceiling"], entry["migration_description"]
        )
        conn.commit()
    finally:
        conn.close()


def column_names(db_key: str, table: str) -> list:
    """Ordered column names for a captured table."""
    return [row[1] for row in load_profiles()[db_key]["tables"][table]]
