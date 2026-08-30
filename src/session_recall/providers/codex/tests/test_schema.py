"""Path resolution and missing-storage diagnosis tests (Phase 1 Step 1).

Schema pre-flight cases are added to this file by a later step.
"""

import hashlib

import pytest

from ..errors import (
    CodexAmbiguousId,
    CodexBusy,
    CodexError,
    CodexNotFound,
    CodexSchemaDrift,
    CodexStorageMissing,
    CodexUsageError,
)
from ..paths import CodexPaths, classify_missing_storage, resolve_paths

# ---------------------------------------------------------------- paths


def test_paths_defaults_resolve_to_codex_home(monkeypatch):
    for var in (
        "SESSION_RECALL_CODEX_STATE_DB",
        "SESSION_RECALL_CODEX_HISTORY_DB",
        "SESSION_RECALL_CODEX_SESSIONS_ROOT",
    ):
        monkeypatch.delenv(var, raising=False)
    paths = resolve_paths()
    assert isinstance(paths, CodexPaths)
    assert paths.state_db.name == "state_5.sqlite"
    assert paths.history_db.name == "thread_history_1.sqlite"
    assert paths.sessions_root.name == "sessions"
    for p in (paths.state_db, paths.history_db, paths.sessions_root):
        assert ".codex" in str(p)
        assert "~" not in str(p)  # expanduser applied


def test_paths_env_overrides_respected(monkeypatch, tmp_path):
    monkeypatch.setenv("SESSION_RECALL_CODEX_STATE_DB", str(tmp_path / "s.sqlite"))
    monkeypatch.setenv("SESSION_RECALL_CODEX_HISTORY_DB", str(tmp_path / "h.sqlite"))
    monkeypatch.setenv("SESSION_RECALL_CODEX_SESSIONS_ROOT", str(tmp_path / "roll"))
    paths = resolve_paths()
    assert paths.state_db == tmp_path / "s.sqlite"
    assert paths.history_db == tmp_path / "h.sqlite"
    assert paths.sessions_root == tmp_path / "roll"


def test_paths_each_override_is_independent(monkeypatch, tmp_path):
    monkeypatch.delenv("SESSION_RECALL_CODEX_HISTORY_DB", raising=False)
    monkeypatch.delenv("SESSION_RECALL_CODEX_SESSIONS_ROOT", raising=False)
    monkeypatch.setenv("SESSION_RECALL_CODEX_STATE_DB", str(tmp_path / "only.sqlite"))
    paths = resolve_paths()
    assert paths.state_db == tmp_path / "only.sqlite"
    assert paths.history_db.name == "thread_history_1.sqlite"


# ------------------------------------------------- missing-storage diagnosis


def test_missing_empty_dir_is_storage_missing(tmp_path):
    code, msg = classify_missing_storage(tmp_path, "state_5.sqlite")
    assert code == "storage_missing"
    assert "is Codex installed?" in msg
    assert "state_5.sqlite" in msg


def test_missing_with_sibling_is_version_changed_and_never_opened(tmp_path):
    sibling = tmp_path / "state_6.sqlite"
    sibling.touch()
    before = (sibling.stat().st_mtime_ns, hashlib.sha256(sibling.read_bytes()).hexdigest())
    code, msg = classify_missing_storage(tmp_path, "state_5.sqlite")
    after = (sibling.stat().st_mtime_ns, hashlib.sha256(sibling.read_bytes()).hexdigest())
    assert code == "storage_version_changed"
    assert "state_6.sqlite" in msg
    assert "schema-check --json" in msg
    assert before == after  # filename-only: sibling untouched


def test_missing_absent_home_dir_is_storage_missing(tmp_path):
    gone = tmp_path / "never_created"
    code, msg = classify_missing_storage(gone, "state_5.sqlite")
    assert code == "storage_missing"
    assert "is Codex installed?" in msg


def test_missing_family_scan_does_not_cross_families(tmp_path):
    (tmp_path / "thread_history_2.sqlite").touch()
    code, _ = classify_missing_storage(tmp_path, "state_5.sqlite")
    assert code == "storage_missing"  # history sibling is not a state sibling
    code2, msg2 = classify_missing_storage(tmp_path, "thread_history_1.sqlite")
    assert code2 == "storage_version_changed"
    assert "thread_history_2.sqlite" in msg2


def test_missing_ignores_non_sqlite_files(tmp_path):
    (tmp_path / "state_backup.txt").touch()
    (tmp_path / "state_5.sqlite-wal").touch()
    code, _ = classify_missing_storage(tmp_path, "state_5.sqlite")
    assert code == "storage_missing"


# ---------------------------------------------------------------- exceptions


def test_exception_exit_codes():
    assert CodexError("x").exit_code == 2
    assert CodexStorageMissing("x").exit_code == 4
    assert CodexStorageMissing("x", code="storage_version_changed").exit_code == 4
    assert CodexBusy("x").exit_code == 3
    assert CodexSchemaDrift("x").exit_code == 2
    assert CodexNotFound("x").exit_code == 1
    assert CodexAmbiguousId("abcd1234", ["a", "b"]).exit_code == 2
    assert CodexUsageError("x").exit_code == 2


def test_storage_missing_carries_code_and_found():
    e = CodexStorageMissing("m", code="storage_version_changed", found=["state_6.sqlite"])
    assert e.code == "storage_version_changed"
    assert e.found == ["state_6.sqlite"]
    assert isinstance(e, CodexError)


def test_ambiguous_id_message_and_candidates():
    e = CodexAmbiguousId("01a04f9b", ["01a04f9b-aaaa", "01a04f9b-bbbb"])
    assert "01a04f9b" in str(e)
    assert len(e.candidates) == 2
    with pytest.raises(CodexError):
        raise e


# ---------------------------------------------------------------- schema (Phase 1 Step 3)

import sqlite3  # noqa: E402

from .. import schema  # noqa: E402
from ._fixture_drift import make_drifted  # noqa: E402


def _open_pair(store):
    return (sqlite3.connect(store.state_db), sqlite3.connect(store.history_db))


def _check(state_db, history_db):
    s, h = sqlite3.connect(state_db), sqlite3.connect(history_db)
    try:
        return schema.check_schema(s, h)
    finally:
        s.close()
        h.close()


def test_schema_exact_fixture_passes(codex_store):
    report = _check(codex_store.state_db, codex_store.history_db)
    assert report.ok and report.differences == []
    assert report.expected_profiles == {
        "state": schema.STATE_PROFILE_NAME,
        "history": schema.HISTORY_PROFILE_NAME,
    }
    assert report.found["state"]["migration"] == 51
    assert report.found["history"]["migration"] == 6


def test_unrelated_table_is_diagnostic_only(codex_store, tmp_path):
    d = make_drifted(codex_store.state_db, codex_store.history_db,
                     tmp_path / "drift", "extra_unrelated_table")
    report = _check(d["state"], d["history"])
    assert report.ok
    assert any("totally_unrelated" in x for x in report.diagnostics)


_FAILING = {
    "drop_preview": "preview",
    "rename_history_mode": "history_mode",
    "extra_threads_column": "example_column",
    "migration_52": "ceiling 52",
    "failed_migration": "failed migration",
    "item_json_type_changed": "item_json",
    "missing_thread_turns": "thread_turns",
    "migration_7": "ceiling 7",
}


@pytest.mark.parametrize("mutation,needle", sorted(_FAILING.items()))
def test_each_mutation_fails_with_specific_difference(
        codex_store, tmp_path, mutation, needle):
    d = make_drifted(codex_store.state_db, codex_store.history_db,
                     tmp_path / "drift", mutation)
    report = _check(d["state"], d["history"])
    assert not report.ok
    assert any(needle in diff for diff in report.differences), report.differences


def test_lower_ceiling_fails(codex_store):
    conn = sqlite3.connect(codex_store.state_db)
    conn.execute("DELETE FROM _sqlx_migrations WHERE version = 51")
    conn.commit()
    conn.close()
    report = _check(codex_store.state_db, codex_store.history_db)
    assert not report.ok
    assert any("ceiling 50" in d for d in report.differences)


def test_drift_json_exact_shape(codex_store, tmp_path):
    d = make_drifted(codex_store.state_db, codex_store.history_db,
                     tmp_path / "drift", "drop_preview")
    report = _check(d["state"], d["history"])
    obj = schema.drift_json(report)
    assert set(obj) == {"ok", "error", "query_executed",
                        "expected_profiles", "differences", "action"}
    assert obj["ok"] is False
    assert obj["error"] == "schema_drift"
    assert obj["query_executed"] is False
    assert obj["expected_profiles"] == {
        "state": schema.STATE_PROFILE_NAME,
        "history": schema.HISTORY_PROFILE_NAME,
    }
    assert obj["differences"]


def test_success_json_shape(codex_store):
    report = _check(codex_store.state_db, codex_store.history_db)
    obj = schema.success_json(report)
    assert obj["ok"] is True
    assert obj["profiles"] == {
        "state": schema.STATE_PROFILE_NAME,
        "history": schema.HISTORY_PROFILE_NAME,
    }
    assert isinstance(obj["diagnostics"], list)


def test_format_drift_human_contents(codex_store, tmp_path):
    d = make_drifted(codex_store.state_db, codex_store.history_db,
                     tmp_path / "drift", "extra_threads_column")
    report = _check(d["state"], d["history"])
    text = schema.format_drift_human(report)
    assert "session data was not queried" in text
    assert "expected: " in text and "found:    " in text
    assert "difference: " in text and "example_column" in text
    assert "session-recall-codex schema-check --json" in text
    assert "reviewed and updated" in text


def test_preflight_raises_with_report(codex_store, tmp_path):
    d = make_drifted(codex_store.state_db, codex_store.history_db,
                     tmp_path / "drift", "migration_52")
    s, h = sqlite3.connect(d["state"]), sqlite3.connect(d["history"])
    try:
        with pytest.raises(CodexSchemaDrift) as ei:
            schema.preflight(s, h)
        assert ei.value.exit_code == 2
        assert ei.value.report.ok is False
        assert ei.value.differences
    finally:
        s.close()
        h.close()


def test_preflight_passes_on_exact(codex_store):
    s, h = _open_pair(codex_store)
    try:
        assert schema.preflight(s, h).ok
    finally:
        s.close()
        h.close()


def test_check_schema_opens_no_connections(codex_store, monkeypatch):
    s, h = _open_pair(codex_store)
    try:
        def boom(*a, **k):
            raise AssertionError("check_schema must not open connections")
        monkeypatch.setattr(sqlite3, "connect", boom)
        report = schema.check_schema(s, h)
        assert report.ok
        assert s.execute("SELECT 1").fetchone()[0] == 1
        assert h.execute("SELECT 1").fetchone()[0] == 1
    finally:
        s.close()
        h.close()
