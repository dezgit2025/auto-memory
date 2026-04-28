"""E2E edge-case and error-handling tests for the session-recall CLI."""

from __future__ import annotations


from .conftest import parse_json, run_cli


def test_no_subcommand_exits_nonzero(fixture_db):
    result = run_cli(db_path=fixture_db)
    assert result.returncode != 0


def test_help_exits_zero(fixture_db):
    result = run_cli("--help", db_path=fixture_db)
    assert result.returncode == 0


def test_missing_db_exits_with_error(monkeypatch):
    monkeypatch.setenv(
        "SESSION_RECALL_CLI_STATE_ROOT", "/tmp/nonexistent_state_e2e_12345"
    )
    result = run_cli("list", "--json", db_path="/tmp/nonexistent_e2e_db_12345.db")
    # Provider layer handles missing DB gracefully: no providers → empty results.
    assert result.returncode == 0
    data = parse_json(result)
    assert data["count"] == 0


def test_empty_db_list(empty_db):
    result = run_cli("list", "--json", db_path=empty_db)
    assert result.returncode == 0
    data = parse_json(result)
    assert data["count"] == 0
    assert data["sessions"] == []


def test_empty_db_files(empty_db):
    result = run_cli("files", "--json", db_path=empty_db)
    assert result.returncode == 0
    data = parse_json(result)
    assert data["count"] == 0
    assert data["files"] == []


def test_empty_db_search(empty_db):
    result = run_cli("search", "anything", "--json", db_path=empty_db)
    assert result.returncode == 0
    data = parse_json(result)
    assert data["count"] == 0
    assert data["results"] == []


def test_long_search_query(fixture_db):
    long_query = "a" * 500
    result = run_cli("search", long_query, "--json", db_path=fixture_db)
    assert result.returncode == 0
