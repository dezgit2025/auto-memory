"""Tests for the trial session-recall-codex CLI entry point."""

from __future__ import annotations

import json

import pytest

from session_recall.providers.codex.cli import main

from ._fixture_drift import make_drifted


def _run(capsys, argv):
    with pytest.raises(SystemExit) as exc_info:
        main(argv)
    out = capsys.readouterr()
    return exc_info.value.code, out.out, out.err


# --- version / help ---


def test_version_exits_0(capsys):
    code, out, _ = _run(capsys, ["--version"])
    assert code == 0
    from session_recall import __version__

    assert out.strip() == __version__


def test_help_contains_trial_note(capsys):
    code, out, _ = _run(capsys, ["--help"])
    assert code == 0
    assert "Trial build" in out


def test_no_command_prints_help_exit_1(capsys):
    code, out, _ = _run(capsys, [])
    assert code == 1
    assert "session-recall-codex" in out


def test_unknown_command_search_exits_2(capsys):
    code, _, err = _run(capsys, ["search", "anything"])
    assert code == 2
    assert "invalid choice" in err


# --- schema-check ---


def test_schema_check_ok_json(codex_env, capsys):
    code, out, _ = _run(capsys, ["schema-check", "--json"])
    assert code == 0
    data = json.loads(out)
    assert data["ok"] is True
    assert data["profiles"]["state"] == "codex-state-v5-migration-51"
    assert data["profiles"]["history"] == "codex-thread-history-v1-migration-6"


def test_schema_check_drift_exit_2(codex_env, codex_store, tmp_path, monkeypatch, capsys):
    drifted = make_drifted(
        codex_store.state_db, codex_store.history_db, tmp_path / "drift", "drop_preview"
    )
    monkeypatch.setenv("SESSION_RECALL_CODEX_STATE_DB", str(drifted["state"]))
    monkeypatch.setenv("SESSION_RECALL_CODEX_HISTORY_DB", str(drifted["history"]))
    code, out, _ = _run(capsys, ["schema-check", "--json"])
    assert code == 2
    data = json.loads(out)
    assert data == {
        "ok": False,
        "error": "schema_drift",
        "query_executed": False,
        "expected_profiles": data["expected_profiles"],
        "differences": data["differences"],
        "action": data["action"],
    }
    assert any("preview" in d for d in data["differences"])


def test_missing_store_exit_4_storage_missing(tmp_path, monkeypatch, capsys):
    monkeypatch.setenv(
        "SESSION_RECALL_CODEX_STATE_DB", str(tmp_path / "empty" / "state_5.sqlite")
    )
    monkeypatch.setenv(
        "SESSION_RECALL_CODEX_HISTORY_DB",
        str(tmp_path / "empty" / "thread_history_1.sqlite"),
    )
    code, out, _ = _run(capsys, ["schema-check", "--json"])
    assert code == 4
    data = json.loads(out)
    assert data["error"] == "storage_missing"
    assert data["query_executed"] is False


def test_state6_sibling_exit_4_version_changed(tmp_path, monkeypatch, capsys):
    home = tmp_path / "codexhome"
    home.mkdir()
    (home / "state_6.sqlite").touch()
    monkeypatch.setenv("SESSION_RECALL_CODEX_STATE_DB", str(home / "state_5.sqlite"))
    monkeypatch.setenv(
        "SESSION_RECALL_CODEX_HISTORY_DB", str(home / "thread_history_1.sqlite")
    )
    code, out, _ = _run(capsys, ["schema-check", "--json"])
    assert code == 4
    data = json.loads(out)
    assert data["error"] == "storage_version_changed"
    assert "state_6.sqlite" in data["message"]


# --- list ---


def test_list_json_default_rows(codex_env, capsys):
    code, out, _ = _run(capsys, ["list", "--json"])
    assert code == 0
    rows = json.loads(out)
    assert len(rows) == 5
    assert list(rows[0].keys())[:3] == ["id_full", "id_short", "summary"]
    assert all(r["_trust_level"] == "codex_local_first_party" for r in rows)


def test_list_human_mode(codex_env, capsys):
    code, out, _ = _run(capsys, ["list"])
    assert code == 0
    assert "ID" in out and "Summary" in out
    assert "\x1b[" not in out


def test_list_include_archived(codex_env, capsys):
    code, out, _ = _run(capsys, ["list", "--json", "--include-archived"])
    assert code == 0
    assert len(json.loads(out)) == 6


def test_list_drift_exit_2_no_query(codex_env, codex_store, tmp_path, monkeypatch, capsys):
    drifted = make_drifted(
        codex_store.state_db, codex_store.history_db, tmp_path / "d2", "migration_52"
    )
    monkeypatch.setenv("SESSION_RECALL_CODEX_STATE_DB", str(drifted["state"]))
    monkeypatch.setenv("SESSION_RECALL_CODEX_HISTORY_DB", str(drifted["history"]))
    code, out, err = _run(capsys, ["list", "--json"])
    assert code == 2
    data = json.loads(out)
    assert data["error"] == "schema_drift"
    assert data["query_executed"] is False


# --- repos ---


def test_repos_json(codex_env, capsys):
    code, out, _ = _run(capsys, ["repos", "--json"])
    assert code == 0
    data = json.loads(out)
    assert data["count"] >= 1
    assert all(not r["repository"].startswith("local:") for r in data["repos"])


def test_repos_include_local(codex_env, capsys):
    code, out, _ = _run(capsys, ["repos", "--json", "--include-local"])
    assert code == 0
    data = json.loads(out)
    assert any(r["repository"].startswith("local:") for r in data["repos"])


# --- isolation ---


def test_main_cli_does_not_import_codex():
    import subprocess
    import sys

    probe = (
        "import sys; import session_recall.__main__; "
        "bad = [m for m in sys.modules if 'providers.codex' in m]; "
        "assert not bad, bad; print('CLEAN')"
    )
    r = subprocess.run(
        [sys.executable, "-c", probe], capture_output=True, text=True, timeout=30
    )
    assert r.returncode == 0, r.stderr
    assert "CLEAN" in r.stdout


class TestSqliteErrorMapping:
    def _args(self, json_mode=False):
        import argparse
        return argparse.Namespace(json=json_mode)

    def test_operational_error_maps_to_exit_3(self, capsys):
        import sqlite3

        from session_recall.providers.codex.cli import _handle

        def boom(_args):
            raise sqlite3.OperationalError("database disk image is malformed")

        rc = _handle(self._args(), boom)
        assert rc == 3
        err = capsys.readouterr().err
        assert "mid-query" in err and "malformed" in err

    def test_operational_error_json_shape(self, capsys):
        import json as jsonlib
        import sqlite3

        from session_recall.providers.codex.cli import _handle

        def boom(_args):
            raise sqlite3.DatabaseError("locked")

        rc = _handle(self._args(json_mode=True), boom)
        assert rc == 3
        obj = jsonlib.loads(capsys.readouterr().out)
        assert obj["ok"] is False
        assert obj["error"] == "sqlite_error"
        assert obj["query_executed"] is False
