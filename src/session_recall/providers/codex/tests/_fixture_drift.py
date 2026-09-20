"""Drift-fixture factory: mutated copies of the synthetic store (plan §10.3).

Every mutation operates on a COPY — sources are never altered.
"""

import shutil
import sqlite3
from pathlib import Path

from ._fixture_schema import MIGRATION_INSTALLED_ON

# mutation name -> (which db, sql statements)
STATE_MUTATIONS = {
    "drop_preview": ["ALTER TABLE threads DROP COLUMN preview"],
    "rename_history_mode":
        ["ALTER TABLE threads RENAME COLUMN history_mode TO history_mode_x"],
    "extra_threads_column":
        ["ALTER TABLE threads ADD COLUMN example_column TEXT"],
    "migration_54": [
        "DELETE FROM _sqlx_migrations WHERE version = 55",
    ],
    "migration_56": [
        "INSERT INTO _sqlx_migrations (version, description, installed_on, "
        f"success, checksum, execution_time) VALUES (56, 'synthetic future', "
        f"'{MIGRATION_INSTALLED_ON}', 1, x'', 0)"
    ],
    "failed_migration":
        ["UPDATE _sqlx_migrations SET success = 0 WHERE version = 55"],
    "extra_unrelated_table":
        ["CREATE TABLE totally_unrelated (x INTEGER)"],  # must PASS w/ diagnostic
}

HISTORY_MUTATIONS = {
    "item_json_type_changed": [
        "ALTER TABLE thread_items RENAME TO thread_items_old",
        "CREATE TABLE thread_items ("
        '"thread_id" TEXT NOT NULL, "turn_id" TEXT NOT NULL, '
        '"item_id" TEXT NOT NULL, "rollout_ordinal" INTEGER NOT NULL, '
        '"created_at_ms" INTEGER NOT NULL, "item_json" BLOB NOT NULL, '
        "\"item_type\" TEXT NOT NULL DEFAULT '', "
        '"updated_at_ordinal" INTEGER NOT NULL DEFAULT 0, '
        'PRIMARY KEY ("thread_id", "turn_id", "item_id"))',
        "INSERT INTO thread_items SELECT * FROM thread_items_old",
        "DROP TABLE thread_items_old",
    ],
    "missing_thread_turns": ["DROP TABLE thread_turns"],
    "migration_5": [
        "DELETE FROM _sqlx_migrations WHERE version = 6",
    ],
    "migration_7": [
        "INSERT INTO _sqlx_migrations (version, description, installed_on, "
        f"success, checksum, execution_time) VALUES (7, 'synthetic future', "
        f"'{MIGRATION_INSTALLED_ON}', 1, x'', 0)"
    ],
}

ALL_MUTATIONS = sorted(STATE_MUTATIONS) + sorted(HISTORY_MUTATIONS)


def make_drifted(state_db: Path, history_db: Path, dst_dir: Path,
                 mutation: str) -> dict:
    """Copy both DBs into dst_dir and apply one named mutation to the copy."""
    dst_dir.mkdir(parents=True, exist_ok=True)
    dst_state = dst_dir / "state_5.sqlite"
    dst_history = dst_dir / "thread_history_1.sqlite"
    shutil.copy(state_db, dst_state)
    shutil.copy(history_db, dst_history)
    if mutation in STATE_MUTATIONS:
        target, statements = dst_state, STATE_MUTATIONS[mutation]
    elif mutation in HISTORY_MUTATIONS:
        target, statements = dst_history, HISTORY_MUTATIONS[mutation]
    else:
        raise ValueError(f"unknown mutation: {mutation}")
    conn = sqlite3.connect(target)
    try:
        for sql in statements:
            conn.execute(sql)
        conn.commit()
    finally:
        conn.close()
    return {"state": dst_state, "history": dst_history, "mutation": mutation}
