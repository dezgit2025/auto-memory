"""Tests for Claude Code detect module."""
from __future__ import annotations

import time

import pytest

from session_recall.providers.claude_code.detect import (
    decode_project_path,
    encode_project_path,
    find_project_dir,
    list_projects,
    list_session_files,
)


@pytest.fixture()
def fake_projects(tmp_path, monkeypatch):
    """Create a fake ~/.claude/projects/ tree and patch CC_PROJECTS_DIR."""
    projects = tmp_path / "projects"
    projects.mkdir()
    monkeypatch.setattr(
        "session_recall.providers.claude_code.detect.CC_PROJECTS_DIR",
        projects,
    )
    return projects


# --- decode / encode round-trip ---


def test_decode_unix_path():
    assert decode_project_path("Users-foo-repo") == "/Users/foo/repo"


def test_decode_windows_path():
    assert decode_project_path("C--Users-foo-repo") == "C:\\Users\\foo\\repo"


def test_encode_unix_path():
    assert encode_project_path("/Users/foo/repo") == "Users-foo-repo"


def test_encode_decode_roundtrip_unix():
    original = "/home/user/myproject"
    encoded = encode_project_path(original)
    decoded = decode_project_path(encoded)
    assert decoded == original


# --- list_projects ---


def test_list_projects_with_sessions(fake_projects):
    proj_a = fake_projects / "Users-alice-proj"
    proj_a.mkdir()
    (proj_a / "s1.jsonl").write_text("")
    (proj_a / "s2.jsonl").write_text("")

    proj_b = fake_projects / "Users-bob-proj"
    proj_b.mkdir()
    (proj_b / "s1.jsonl").write_text("")

    result = list_projects()
    assert len(result) == 2
    assert result[0]["session_count"] == 2
    assert result[1]["session_count"] == 1
    assert result[0]["encoded"] == "Users-alice-proj"


def test_list_projects_empty_dir(fake_projects):
    assert list_projects() == []


def test_list_projects_missing_dir(tmp_path, monkeypatch):
    monkeypatch.setattr(
        "session_recall.providers.claude_code.detect.CC_PROJECTS_DIR",
        tmp_path / "nonexistent",
    )
    assert list_projects() == []


def test_list_projects_rejects_symlink_escape(fake_projects, tmp_path):
    outside = tmp_path / "outside"
    outside.mkdir()
    (outside / "evil.jsonl").write_text("")

    link = fake_projects / "symlink-proj"
    link.symlink_to(outside)

    result = list_projects()
    assert all(r["encoded"] != "symlink-proj" for r in result)


# --- list_session_files ---


def test_list_session_files_sorted_by_mtime(fake_projects):
    proj = fake_projects / "Users-test-proj"
    proj.mkdir()

    older = proj / "old.jsonl"
    older.write_text("")
    time.sleep(0.05)
    newer = proj / "new.jsonl"
    newer.write_text("")

    files = list_session_files(proj)
    assert len(files) == 2
    assert files[0].name == "new.jsonl"
    assert files[1].name == "old.jsonl"


def test_list_session_files_all_projects(fake_projects):
    for name in ("proj-a", "proj-b"):
        d = fake_projects / name
        d.mkdir()
        (d / "session.jsonl").write_text("")

    files = list_session_files()
    assert len(files) == 2


def test_list_session_files_missing_dir(tmp_path, monkeypatch):
    monkeypatch.setattr(
        "session_recall.providers.claude_code.detect.CC_PROJECTS_DIR",
        tmp_path / "nonexistent",
    )
    assert list_session_files() == []


def test_list_session_files_rejects_symlink_escape(fake_projects, tmp_path):
    proj = fake_projects / "Users-legit-proj"
    proj.mkdir()
    (proj / "good.jsonl").write_text("")

    outside = tmp_path / "outside"
    outside.mkdir()
    (outside / "evil.jsonl").write_text("")

    evil_link = proj / "bad.jsonl"
    evil_link.symlink_to(outside / "evil.jsonl")

    files = list_session_files(proj)
    names = [f.name for f in files]
    assert "good.jsonl" in names
    assert "bad.jsonl" not in names


# --- find_project_dir ---


def test_find_project_dir_exists(fake_projects):
    proj = fake_projects / "Users-test-myrepo"
    proj.mkdir()
    result = find_project_dir("/Users/test/myrepo")
    assert result is not None
    assert result == proj


def test_find_project_dir_not_found(fake_projects):
    assert find_project_dir("/no/such/path") is None
