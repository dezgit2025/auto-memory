"""Tests for provider-aware health and schema-check commands."""

from __future__ import annotations

import argparse
import json


class _FakeProvider:
    def __init__(
        self,
        provider_id: str,
        provider_name: str,
        problems: list[str],
        session_count: int,
    ) -> None:
        self.provider_id = provider_id
        self.provider_name = provider_name
        self._problems = problems
        self._session_count = session_count

    def schema_problems(self) -> list[str]:
        return self._problems

    def list_sessions(
        self, repo: str | None, limit: int, days: int | None
    ) -> list[dict]:
        return [{"id": f"s{i}"} for i in range(min(self._session_count, limit))]


def test_schema_check_provider_ok_json(monkeypatch, capsys):
    from session_recall.commands import schema_check_cmd

    providers = [_FakeProvider("cli", "Copilot CLI", [], 1)]
    monkeypatch.setattr(
        schema_check_cmd, "get_active_providers", lambda selected, db_path: providers
    )

    args = argparse.Namespace(json=True, provider="all")
    rc = schema_check_cmd.run(args)

    assert rc == 0
    out = json.loads(capsys.readouterr().out)
    assert out["ok"] is True
    assert out["providers"][0]["provider"] == "cli"


def test_schema_check_provider_failure_json(monkeypatch, capsys):
    from session_recall.commands import schema_check_cmd

    providers = [_FakeProvider("cli", "Copilot CLI", ["MISSING TABLE: sessions"], 0)]
    monkeypatch.setattr(
        schema_check_cmd, "get_active_providers", lambda selected, db_path: providers
    )

    args = argparse.Namespace(json=True, provider="all")
    rc = schema_check_cmd.run(args)

    assert rc == 2
    out = json.loads(capsys.readouterr().out)
    assert out["ok"] is False
    assert any("MISSING TABLE" in p for p in out["problems"])


def test_health_provider_fallback_mode_json(monkeypatch, capsys):
    from session_recall.commands import health

    providers = [_FakeProvider("vscode", "VS Code", [], 3)]
    monkeypatch.setattr(
        health, "get_active_providers", lambda selected, db_path: providers
    )
    monkeypatch.setattr(health, "DB_PATH", "/tmp/definitely-missing-auto-memory.db")

    args = argparse.Namespace(json=True, provider="all")
    rc = health.run(args)

    assert rc == 0
    out = json.loads(capsys.readouterr().out)
    assert out["storage_mode"] == "provider-fallback"
    names = [d["name"] for d in out["dims"]]
    assert "SQLite Health Core" in names
    assert "Provider:vscode" in names


# ── helpers for integration tests ────────────────────────────────────


def _create_test_db(path: str) -> None:
    """Create a minimal SQLite DB with expected schema and sample data."""
    import sqlite3

    from session_recall.db.schema_check import EXPECTED_SCHEMA

    conn = sqlite3.connect(path)
    for table, cols in EXPECTED_SCHEMA.items():
        col_defs = ", ".join(f"{c} TEXT" for c in cols)
        conn.execute(f"CREATE TABLE {table} ({col_defs})")
    conn.execute(
        "INSERT INTO sessions (id, repository, branch, summary, created_at, updated_at) "
        "VALUES ('test-1', 'test/repo', 'main', 'Test session', "
        "datetime('now'), datetime('now'))"
    )
    conn.execute(
        "INSERT INTO turns (session_id, turn_index, user_message, "
        "assistant_response, timestamp) "
        "VALUES ('test-1', '0', 'hello', 'world', datetime('now'))"
    )
    conn.commit()
    conn.close()


def _patch_all_db_paths(monkeypatch, db_path: str) -> None:
    """Monkeypatch DB_PATH in health and all dim modules that import it."""
    from session_recall.commands import health
    from session_recall.health import (
        dim_corpus,
        dim_e2e,
        dim_freshness,
        dim_latency,
        dim_repo_coverage,
        dim_schema,
        dim_summary_coverage,
    )

    for mod in (
        health,
        dim_freshness,
        dim_schema,
        dim_latency,
        dim_corpus,
        dim_summary_coverage,
        dim_repo_coverage,
        dim_e2e,
    ):
        monkeypatch.setattr(mod, "DB_PATH", db_path)


# ── integration tests ────────────────────────────────────────────────


def test_health_provider_cli_only(monkeypatch, capsys, tmp_path):
    from session_recall.commands import health
    from session_recall.providers.copilot_cli import CopilotCliProvider

    db_path = str(tmp_path / "test.db")
    _create_test_db(db_path)
    _patch_all_db_paths(monkeypatch, db_path)

    provider = CopilotCliProvider(
        db_path=db_path, state_root=str(tmp_path / "state")
    )
    monkeypatch.setattr(
        health, "get_active_providers", lambda selected, db_path: [provider]
    )

    args = argparse.Namespace(provider="cli", json=True)
    exit_code = health.run(args)

    assert exit_code == 0
    out = json.loads(capsys.readouterr().out)
    # 9 SQLite dims + 4 provider sub-dims + 1 Provider:cli summary = 14
    assert len(out["dims"]) >= 13


def test_health_provider_vscode_only(monkeypatch, capsys, tmp_path):
    from session_recall.commands import health
    from session_recall.providers.file import VSCodeProvider

    ws_dir = tmp_path / "ws" / "abc" / "chatSessions"
    ws_dir.mkdir(parents=True)
    (ws_dir / "test.jsonl").write_text('{"role":"user","content":"hello"}\n')
    vsc = VSCodeProvider(root_override=str(tmp_path / "ws"))

    monkeypatch.setattr(
        health, "get_active_providers", lambda selected, db_path: [vsc]
    )
    monkeypatch.setattr(health, "DB_PATH", str(tmp_path / "nonexistent.db"))
    monkeypatch.setattr(health, "ENABLE_FILE_BACKENDS", True)

    args = argparse.Namespace(provider="vscode", json=True)
    exit_code = health.run(args)

    assert exit_code == 0
    out = json.loads(capsys.readouterr().out)
    dim_names = [d["name"] for d in out["dims"]]
    sqlite_dims = {
        "DB Freshness", "Schema Integrity", "Query Latency",
        "Corpus Size", "Summary Coverage", "Repo Coverage",
        "Concurrency", "E2E Probe", "Progressive Disclosure",
    }
    assert not sqlite_dims.intersection(dim_names)
    provider_dims = {"Path Discovery", "File Inventory", "Recent Activity", "Trust Model"}
    assert provider_dims.issubset(set(dim_names))


def test_health_provider_all_shows_grouped(monkeypatch, capsys, tmp_path):
    from session_recall.commands import health
    from session_recall.providers.copilot_cli import CopilotCliProvider
    from session_recall.providers.file import VSCodeProvider

    db_path = str(tmp_path / "test.db")
    _create_test_db(db_path)
    _patch_all_db_paths(monkeypatch, db_path)

    provider_cli = CopilotCliProvider(
        db_path=db_path, state_root=str(tmp_path / "state")
    )
    ws_dir = tmp_path / "ws" / "abc" / "chatSessions"
    ws_dir.mkdir(parents=True)
    (ws_dir / "test.jsonl").write_text('{"role":"user","content":"hello"}\n')
    provider_vsc = VSCodeProvider(root_override=str(tmp_path / "ws"))

    monkeypatch.setattr(
        health,
        "get_active_providers",
        lambda selected, db_path: [provider_cli, provider_vsc],
    )
    monkeypatch.setattr(health, "ENABLE_FILE_BACKENDS", True)

    args = argparse.Namespace(provider="all", json=True)
    exit_code = health.run(args)

    assert exit_code == 0
    out = json.loads(capsys.readouterr().out)
    dim_names = [d["name"] for d in out["dims"]]
    assert "Provider:cli" in dim_names
    assert "Provider:vscode" in dim_names


def test_health_provider_disabled_error_message(monkeypatch, capsys):
    from session_recall.commands import health

    monkeypatch.setattr(health, "ENABLE_FILE_BACKENDS", False)
    args = argparse.Namespace(provider="vscode", json=False)
    exit_code = health.run(args)

    assert exit_code == 2
    captured = capsys.readouterr()
    assert "not enabled" in captured.err
    assert "SESSION_RECALL_ENABLE_FILE_BACKENDS" in captured.err


def test_health_provider_typo_error_message(tmp_path, monkeypatch):
    import pytest

    from session_recall.providers import discovery

    monkeypatch.setattr(discovery, "ENABLE_FILE_BACKENDS", False)
    monkeypatch.setattr(
        discovery, "CLI_SESSION_STATE_ROOT", str(tmp_path / "nostate")
    )

    with pytest.raises(ValueError, match="vscde"):
        discovery.get_active_providers("vscde", str(tmp_path / "nonexistent.db"))


def test_health_provider_json_schema(monkeypatch, capsys, tmp_path):
    from session_recall.commands import health
    from session_recall.providers.file import VSCodeProvider

    ws_dir = tmp_path / "ws" / "abc" / "chatSessions"
    ws_dir.mkdir(parents=True)
    (ws_dir / "test.jsonl").write_text('{"role":"user","content":"hello"}\n')
    vsc = VSCodeProvider(root_override=str(tmp_path / "ws"))

    monkeypatch.setattr(
        health, "get_active_providers", lambda selected, db_path: [vsc]
    )
    monkeypatch.setattr(health, "DB_PATH", str(tmp_path / "nonexistent.db"))
    monkeypatch.setattr(health, "ENABLE_FILE_BACKENDS", True)

    args = argparse.Namespace(provider="vscode", json=True)
    exit_code = health.run(args)

    assert exit_code == 0
    out = json.loads(capsys.readouterr().out)
    assert "dims" in out
    assert "dimensions" in out
    assert "providers" in out
    assert "overall_score" in out


def test_health_provider_backward_compat(monkeypatch, capsys, tmp_path):
    from session_recall.commands import health
    from session_recall.providers.copilot_cli import CopilotCliProvider

    db_path = str(tmp_path / "test.db")
    _create_test_db(db_path)
    _patch_all_db_paths(monkeypatch, db_path)

    provider = CopilotCliProvider(
        db_path=db_path, state_root=str(tmp_path / "state")
    )
    monkeypatch.setattr(
        health, "get_active_providers", lambda selected, db_path: [provider]
    )

    args = argparse.Namespace(provider="cli", json=True)
    exit_code = health.run(args)

    assert exit_code == 0
    out = json.loads(capsys.readouterr().out)
    assert "dims" in out
    assert "providers" in out
    assert "cli" in out["providers"]
