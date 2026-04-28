"""E2E tests for the `show` command."""

from .conftest import parse_json, run_cli

SID_AAAA = "aaaa1111-0000-0000-0000-000000000001"


def test_show_json_full_session(fixture_db):
    r = run_cli("show", SID_AAAA, "--json", db_path=fixture_db)
    assert r.returncode == 0
    data = parse_json(r)
    assert data["id"] == SID_AAAA
    assert data["repository"] == "acme/myapp"
    assert data["branch"] == "main"
    assert "turns" in data


def test_show_json_has_turns(fixture_db):
    r = run_cli("show", SID_AAAA, "--json", db_path=fixture_db)
    data = parse_json(r)
    assert len(data["turns"]) == 2
    assert data["turns"][0]["user"]
    assert data["turns"][1]["assistant"]


def test_show_turns_limit(fixture_db):
    r = run_cli("show", SID_AAAA, "--json", "--turns", "1", db_path=fixture_db)
    assert r.returncode == 0
    data = parse_json(r)
    assert len(data["turns"]) == 1


def test_show_prefix_match(fixture_db):
    r = run_cli("show", "aaaa1111", "--json", db_path=fixture_db)
    assert r.returncode == 0
    data = parse_json(r)
    assert data["id"] == SID_AAAA


def test_show_invalid_session_id(fixture_db):
    r = run_cli("show", "zzzz-nonexistent", "--json", db_path=fixture_db)
    assert r.returncode != 0


def test_show_human_output(fixture_db):
    r = run_cli("show", "aaaa1111", db_path=fixture_db)
    assert r.returncode == 0
    out = r.stdout
    assert "aaaa1111" in out
    assert "acme/myapp" in out or "main" in out


def test_show_exit_code_zero(fixture_db):
    r = run_cli("show", SID_AAAA, db_path=fixture_db)
    assert r.returncode == 0
