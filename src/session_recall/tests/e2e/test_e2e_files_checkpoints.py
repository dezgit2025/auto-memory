"""E2E tests for `files` and `checkpoints` CLI commands."""

from .conftest import parse_json, run_cli


def test_files_json_valid_structure(fixture_db):
    result = run_cli("files", "--json", db_path=fixture_db)
    data = parse_json(result)
    assert "files" in data and isinstance(data["files"], list)
    for f in data["files"]:
        assert "file_path" in f and "session_id" in f


def test_files_limit(fixture_db):
    data = parse_json(run_cli("files", "--json", "--limit", "2", db_path=fixture_db))
    assert len(data["files"]) <= 2


def test_files_repo_filter(fixture_db):
    data = parse_json(
        run_cli("files", "--json", "--repo", "acme/myapp", db_path=fixture_db)
    )
    assert len(data["files"]) > 0
    sessions = {f["session_id"] for f in data["files"]}
    # shared-lib session id starts with cccc3333; none should appear
    assert all(not sid.startswith("cccc3333") for sid in sessions)


def test_files_exit_code_zero(fixture_db):
    assert run_cli("files", "--json", db_path=fixture_db).returncode == 0


def test_checkpoints_json_valid(fixture_db):
    data = parse_json(run_cli("checkpoints", "--json", db_path=fixture_db))
    assert "checkpoints" in data and isinstance(data["checkpoints"], list)
    assert len(data["checkpoints"]) == 2
    for cp in data["checkpoints"]:
        assert "title" in cp and "session_id" in cp


def test_checkpoints_limit(fixture_db):
    data = parse_json(
        run_cli("checkpoints", "--json", "--limit", "1", db_path=fixture_db)
    )
    assert len(data["checkpoints"]) == 1


def test_checkpoints_exit_code_zero(fixture_db):
    assert run_cli("checkpoints", "--json", db_path=fixture_db).returncode == 0


def test_files_empty_db(empty_db):
    result = run_cli("files", "--json", db_path=empty_db)
    assert result.returncode == 0
    data = parse_json(result)
    assert data["files"] == [] and data["count"] == 0


def test_checkpoints_empty_db(empty_db):
    result = run_cli("checkpoints", "--json", db_path=empty_db)
    assert result.returncode == 0
    data = parse_json(result)
    assert data["checkpoints"] == [] and data["count"] == 0
