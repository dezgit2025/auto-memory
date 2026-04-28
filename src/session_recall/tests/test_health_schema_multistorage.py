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
