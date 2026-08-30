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
