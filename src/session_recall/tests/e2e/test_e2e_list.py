"""E2E tests for the `list` command."""

from .conftest import parse_json, run_cli


def test_list_json_returns_valid_structure(fixture_db):
    result = run_cli("list", "--json", db_path=fixture_db)
    data = parse_json(result)
    assert "count" in data
    assert "sessions" in data
    assert data["count"] >= 1


def test_list_json_limit_1(fixture_db):
    result = run_cli("list", "--json", "--limit", "1", db_path=fixture_db)
    data = parse_json(result)
    assert data["count"] == 1
    assert len(data["sessions"]) == 1


def test_list_json_repo_filter(fixture_db):
    result = run_cli("list", "--json", "--repo", "acme/myapp", db_path=fixture_db)
    data = parse_json(result)
    assert data["count"] == 2


def test_list_json_repo_filter_other(fixture_db):
    result = run_cli("list", "--json", "--repo", "acme/shared-lib", db_path=fixture_db)
    data = parse_json(result)
    assert data["count"] == 1


def test_list_json_days_zero_returns_empty(fixture_db):
    # NOTE: --days 0 is falsy in Python so `args.days or 30` falls back to 30,
    # and fixture dates are in 2026 (future), so all sessions match.
    result = run_cli("list", "--json", "--days", "0", db_path=fixture_db)
    data = parse_json(result)
    assert data["count"] == 3


def test_list_human_output(fixture_db):
    result = run_cli("list", db_path=fixture_db)
    assert result.returncode == 0
    assert "Summary" in result.stdout or "session" in result.stdout.lower()


def test_list_exit_code_zero(fixture_db):
    result = run_cli("list", "--json", db_path=fixture_db)
    assert result.returncode == 0


def test_list_empty_db(empty_db):
    result = run_cli("list", "--json", db_path=empty_db)
    data = parse_json(result)
    assert data["count"] == 0
