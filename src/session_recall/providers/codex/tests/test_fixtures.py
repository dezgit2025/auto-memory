"""Self-tests for the synthetic fixture layer (Phase 0 Step 4 P1-A)."""

import sqlite3

from ._fixture_drift import ALL_MUTATIONS, make_drifted
from ._fixture_schema import build_empty_db, load_profiles
from ._fixture_state import SEARCH_TOKEN, _base_row, insert_threads, make_uuid7
from .conftest import build_small_store


def _table_info(db_path, table):
    conn = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
    try:
        rows = conn.execute(f'PRAGMA table_info("{table}")').fetchall()
    finally:
        conn.close()
    return [list(r) for r in rows]


def test_schemas_match_captured_profiles(codex_store):
    profiles = load_profiles()
    for db_key, db_path in (("state", codex_store.state_db),
                            ("history", codex_store.history_db)):
        for table, expected in profiles[db_key]["tables"].items():
            assert _table_info(db_path, table) == expected, (db_key, table)


def test_migration_ceilings(codex_store):
    for db_path, ceiling, desc in (
        (codex_store.state_db, 55, "thread attachments"),
        (codex_store.history_db, 6, "thread turn ends"),
    ):
        conn = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
        try:
            version, d = conn.execute(
                "SELECT version, description FROM _sqlx_migrations "
                "WHERE success = 1 ORDER BY version DESC LIMIT 1"
            ).fetchone()
            failed = conn.execute(
                "SELECT COUNT(*) FROM _sqlx_migrations WHERE success = 0"
            ).fetchone()[0]
        finally:
            conn.close()
        assert (version, d, failed) == (ceiling, desc, 0)


def test_thread_inventory(codex_store):
    t = codex_store.threads
    assert len(t) == 8
    by_title = {r["title"]: r for r in t}
    assert by_title["archived experiment"]["archived"] == 1
    assert by_title["guardian trap"]["agent_path"] is None
    assert "subagent" in by_title["guardian trap"]["source"]
    assert by_title["explicit subagent"]["agent_path"]
    assert by_title["legacy-recent session"]["history_mode"] == "legacy"
    assert SEARCH_TOKEN in by_title["oldband alpha work"]["first_user_message"]
    assert by_title["recent-c local scratch"]["git_origin_url"] is None


def test_originator_and_daybreak_nullable_values_round_trip(tmp_path):
    state_db = tmp_path / "state_5.sqlite"
    build_empty_db(state_db, "state")
    ts = 1_787_486_400_000
    null_row = _base_row(make_uuid7(ts, 101), ts)
    value_row = _base_row(make_uuid7(ts + 1, 102), ts + 1)
    assert null_row["originator"] is None
    assert null_row["daybreak_enabled"] is None
    value_row.update(originator="synthetic-test", daybreak_enabled=1)

    conn = sqlite3.connect(state_db)
    try:
        insert_threads(conn, [null_row, value_row])
        rows = conn.execute(
            "SELECT originator, daybreak_enabled FROM threads ORDER BY created_at_ms"
        ).fetchall()
    finally:
        conn.close()
    assert rows == [(None, None), ("synthetic-test", 1)]


def test_collision_pair_shares_8_char_prefix(codex_store):
    ids = [r["id"] for r in codex_store.threads
           if r["title"].startswith(("recent-a", "recent-b"))]
    assert len(ids) == 2
    assert ids[0][:8] == ids[1][:8]
    assert ids[0] != ids[1]


def test_history_items_present(codex_store):
    conn = sqlite3.connect(f"file:{codex_store.history_db}?mode=ro", uri=True)
    try:
        types = dict(conn.execute(
            "SELECT item_type, COUNT(*) FROM thread_items GROUP BY item_type"
        ).fetchall())
        turns = conn.execute("SELECT COUNT(*) FROM thread_turns").fetchone()[0]
    finally:
        conn.close()
    paginated = sum(1 for r in codex_store.threads
                    if r["history_mode"] == "paginated")
    assert types["userMessage"] == paginated
    assert types["agentMessage"] == paginated
    assert types["reasoning"] == paginated
    assert types["commandExecution"] == paginated
    assert types["fileChange"] == 1  # only the oldband thread
    assert turns == paginated


def test_rollout_files(codex_store):
    r = codex_store.rollouts
    assert r["good"].exists() and r["drifted"].exists()
    assert r["malformed"].exists()
    assert r["oversized"].stat().st_size > 1_000_000
    assert r["escape"].is_symlink()
    resolved = r["escape"].resolve()
    assert not str(resolved).startswith(str(codex_store.sessions_root.resolve()))


def test_drift_factory_all_mutations(codex_store, tmp_path):
    assert len(ALL_MUTATIONS) == 11
    for mutation in ALL_MUTATIONS:
        out = make_drifted(codex_store.state_db, codex_store.history_db,
                           tmp_path / mutation, mutation)
        conn = sqlite3.connect(f"file:{out['state']}?mode=ro", uri=True)
        hconn = sqlite3.connect(f"file:{out['history']}?mode=ro", uri=True)
        try:
            state_cols = [r[1] for r in conn.execute(
                "PRAGMA table_info(threads)").fetchall()]
            if mutation == "drop_preview":
                assert "preview" not in state_cols
            elif mutation == "rename_history_mode":
                assert "history_mode_x" in state_cols
            elif mutation == "extra_threads_column":
                assert "example_column" in state_cols
            elif mutation == "migration_54":
                assert conn.execute("SELECT MAX(version) FROM _sqlx_migrations"
                                    ).fetchone()[0] == 54
            elif mutation == "migration_56":
                assert conn.execute("SELECT MAX(version) FROM _sqlx_migrations"
                                    ).fetchone()[0] == 56
            elif mutation == "failed_migration":
                assert conn.execute("SELECT COUNT(*) FROM _sqlx_migrations "
                                    "WHERE success = 0").fetchone()[0] == 1
            elif mutation == "extra_unrelated_table":
                assert conn.execute("SELECT name FROM sqlite_master WHERE "
                                    "name='totally_unrelated'").fetchone()
            elif mutation == "item_json_type_changed":
                info = hconn.execute("PRAGMA table_info(thread_items)").fetchall()
                assert dict((r[1], r[2]) for r in info)["item_json"] == "BLOB"
            elif mutation == "missing_thread_turns":
                assert not hconn.execute("SELECT name FROM sqlite_master WHERE "
                                         "name='thread_turns'").fetchone()
            elif mutation == "migration_5":
                assert hconn.execute("SELECT MAX(version) FROM _sqlx_migrations"
                                     ).fetchone()[0] == 5
            elif mutation == "migration_7":
                assert hconn.execute("SELECT MAX(version) FROM _sqlx_migrations"
                                     ).fetchone()[0] == 7
        finally:
            conn.close()
            hconn.close()


def test_deterministic_rebuild(tmp_path):
    a = build_small_store(tmp_path / "a")
    b = build_small_store(tmp_path / "b")
    assert [r["id"] for r in a.threads] == [r["id"] for r in b.threads]
    assert [r["created_at_ms"] for r in a.threads] == \
           [r["created_at_ms"] for r in b.threads]
