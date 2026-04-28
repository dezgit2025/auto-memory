"""E2E tests for the `search` command."""

from .conftest import parse_json, run_cli


def test_search_json_finds_known_term(fixture_db):
    r = run_cli("search", "login", "--json", db_path=fixture_db)
    assert r.returncode == 0
    data = parse_json(r)
    assert data["count"] >= 1
    hit = data["results"][0]
    assert "session_id" in hit
    assert "excerpt" in hit
    assert "login" in hit["excerpt"].lower()


def test_search_json_no_results(fixture_db):
    r = run_cli("search", "xyznonexistent", "--json", db_path=fixture_db)
    assert r.returncode == 0
    data = parse_json(r)
    assert data["count"] == 0
    assert data["results"] == []


def test_search_limit(fixture_db):
    r = run_cli("search", "auth", "--json", "--limit", "1", db_path=fixture_db)
    assert r.returncode == 0
    data = parse_json(r)
    assert len(data["results"]) <= 1


def test_search_repo_filter(fixture_db):
    r = run_cli("search", "Refactor", "--json", "--repo", "acme/shared-lib", db_path=fixture_db)
    assert r.returncode == 0
    data = parse_json(r)
    assert data["count"] >= 1
    assert data["repo"] == "acme/shared-lib"
    for hit in data["results"]:
        assert hit["repository"] == "acme/shared-lib"


def test_search_special_chars_safe(fixture_db):
    r = run_cli("search", "(foo) [bar] {baz}", "--json", db_path=fixture_db)
    assert r.returncode == 0
    data = parse_json(r)
    assert isinstance(data["results"], list)


def test_search_human_output(fixture_db):
    r = run_cli("search", "dashboard", db_path=fixture_db)
    assert r.returncode == 0
    assert "dashboard" in r.stdout.lower()
    assert "bbbb2222" in r.stdout


def test_search_exit_code_zero(fixture_db):
    r = run_cli("search", "login", db_path=fixture_db)
    assert r.returncode == 0


def test_search_empty_db(empty_db):
    r = run_cli("search", "login", "--json", db_path=empty_db)
    assert r.returncode == 0
    data = parse_json(r)
    assert data["count"] == 0
    assert data["results"] == []
