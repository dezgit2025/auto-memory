"""E2E tests for health and schema-check CLI commands."""

import sqlite3

from .conftest import parse_json, run_cli


def test_schema_check_valid_db(fixture_db):
    result = run_cli("schema-check", "--json", db_path=fixture_db)
    data = parse_json(result)
    assert data["ok"] is True
    assert data["problems"] == []


def test_schema_check_corrupted_db(tmp_path):
    db_path = str(tmp_path / "corrupted.db")
    conn = sqlite3.connect(db_path)
    conn.execute("CREATE TABLE sessions (id TEXT PRIMARY KEY)")
    conn.close()

    result = run_cli("schema-check", "--json", db_path=db_path)
    data = parse_json(result)
    assert data["ok"] is False
    assert len(data["problems"]) > 0


def test_schema_check_exit_code(fixture_db):
    result = run_cli("schema-check", "--json", db_path=fixture_db)
    assert result.returncode == 0


def test_health_json_valid(fixture_db):
    result = run_cli("health", "--json", db_path=fixture_db)
    data = parse_json(result)
    assert "overall_score" in data
    assert "dims" in data
    assert isinstance(data["dims"], list)
    assert len(data["dims"]) > 0


def test_health_exit_code(fixture_db):
    result = run_cli("health", "--json", db_path=fixture_db)
    assert result.returncode == 0


def test_schema_check_missing_db():
    result = run_cli("schema-check", "--json", db_path="/tmp/does_not_exist_e2e.db")
    data = parse_json(result)
    # When neither SQLite DB nor session-state exists (e.g., CI),
    # schema-check may return ok=True with 0 providers or 1 provider
    # in session-state-or-sqlite mode (if ~/.copilot/session-state/ exists locally).
    if data.get("providers"):
        assert data["ok"] is True
        assert data["providers"][0]["mode"] == "session-state-or-sqlite"
    else:
        # CI environment: no Copilot CLI installed, no providers discovered
        assert data["ok"] is True
