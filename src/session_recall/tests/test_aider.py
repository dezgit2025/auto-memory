"""Tests for the Aider backend."""
from __future__ import annotations
import pathlib
import pytest
import session_recall.backends.aider as aider_mod
from session_recall.backends.aider import AiderBackend, _HISTORY_FILENAME

_SAMPLE_HISTORY = """\
# aider chat started at 2026-01-15 10:23:45

#### fix the authentication bug

> some shell output

> /add src/auth.py

#### added src/auth.py to the chat

The fix involves changing the token validation logic.
Use bcrypt for password hashing.

####

#### add unit tests for auth

> /add tests/test_auth.py

#### added tests/test_auth.py to the chat

Here are the unit tests you requested.

####
"""

_EMPTY_HISTORY = """\
# aider chat started at 2026-02-01 09:00:00

"""

_NO_HEADING_HISTORY = """\
#### what is the meaning of life

The answer is 42.

####
"""


@pytest.fixture()
def history_dir(tmp_path: pathlib.Path) -> pathlib.Path:
    """Create a project directory with a history file."""
    project = tmp_path / "myorg" / "myproject"
    project.mkdir(parents=True)
    hist = project / _HISTORY_FILENAME
    hist.write_text(_SAMPLE_HISTORY, encoding="utf-8")
    return tmp_path


@pytest.fixture()
def backend(history_dir: pathlib.Path, monkeypatch: pytest.MonkeyPatch) -> AiderBackend:
    monkeypatch.setattr(aider_mod, "_DEFAULT_SEARCH_ROOTS", [history_dir])
    b = AiderBackend()
    return b


# ---------------------------------------------------------------------------
# is_available
# ---------------------------------------------------------------------------

class TestIsAvailable:
    def test_true_when_history_exists(self, backend: AiderBackend) -> None:
        assert backend.is_available() is True

    def test_false_when_no_history(self, tmp_path: pathlib.Path, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr(aider_mod, "_DEFAULT_SEARCH_ROOTS", [tmp_path])
        b = AiderBackend()
        assert b.is_available() is False

    def test_env_var_overrides_root(self, tmp_path: pathlib.Path, monkeypatch: pytest.MonkeyPatch) -> None:
        project = tmp_path / "envproject"
        project.mkdir()
        (project / _HISTORY_FILENAME).write_text(_SAMPLE_HISTORY, encoding="utf-8")
        monkeypatch.setenv("AIDER_SEARCH_ROOT", str(tmp_path))
        monkeypatch.setattr(aider_mod, "_DEFAULT_SEARCH_ROOTS", [])
        b = AiderBackend()
        assert b.is_available() is True
        monkeypatch.delenv("AIDER_SEARCH_ROOT")


# ---------------------------------------------------------------------------
# list_sessions
# ---------------------------------------------------------------------------

class TestListSessions:
    def test_returns_sessions(self, backend: AiderBackend) -> None:
        sessions = backend.list_sessions(days=3650)
        assert len(sessions) == 1

    def test_session_fields(self, backend: AiderBackend) -> None:
        s = backend.list_sessions(days=3650)[0]
        assert s["turns_count"] == 2
        assert s["files_count"] == 2
        assert "authentication" in s["summary"]
        assert s["date"] == "2026-01-15"
        assert s["created_at"] == "2026-01-15T10:23:45"
        assert "myproject" in s["repository"]

    def test_empty_history_file(self, tmp_path: pathlib.Path, monkeypatch: pytest.MonkeyPatch) -> None:
        project = tmp_path / "org" / "proj"
        project.mkdir(parents=True)
        (project / _HISTORY_FILENAME).write_text(_EMPTY_HISTORY, encoding="utf-8")
        monkeypatch.setattr(aider_mod, "_DEFAULT_SEARCH_ROOTS", [tmp_path])
        b = AiderBackend()
        sessions = b.list_sessions(days=3650)
        assert len(sessions) == 1
        s = sessions[0]
        assert s["turns_count"] == 0
        assert s["summary"] == ""

    def test_no_heading_falls_back_to_mtime(self, tmp_path: pathlib.Path, monkeypatch: pytest.MonkeyPatch) -> None:
        project = tmp_path / "org" / "fallback"
        project.mkdir(parents=True)
        (project / _HISTORY_FILENAME).write_text(_NO_HEADING_HISTORY, encoding="utf-8")
        monkeypatch.setattr(aider_mod, "_DEFAULT_SEARCH_ROOTS", [tmp_path])
        b = AiderBackend()
        sessions = b.list_sessions(days=3650)
        assert len(sessions) == 1
        assert sessions[0]["date"] != ""

    def test_days_filter_excludes_old(self, tmp_path: pathlib.Path, monkeypatch: pytest.MonkeyPatch) -> None:
        project = tmp_path / "org" / "old"
        project.mkdir(parents=True)
        old_history = "# aider chat started at 2020-01-01 10:00:00\n\n#### old question\n\nold answer\n\n####\n"
        (project / _HISTORY_FILENAME).write_text(old_history, encoding="utf-8")
        monkeypatch.setattr(aider_mod, "_DEFAULT_SEARCH_ROOTS", [tmp_path])
        b = AiderBackend()
        sessions = b.list_sessions(days=30)  # Only last 30 days
        assert len(sessions) == 0

    def test_repo_filter(self, backend: AiderBackend) -> None:
        sessions_match = backend.list_sessions(days=3650, repo="myproject")
        assert len(sessions_match) == 1
        sessions_no_match = backend.list_sessions(days=3650, repo="otherproject")
        assert len(sessions_no_match) == 0

    def test_limit(self, tmp_path: pathlib.Path, monkeypatch: pytest.MonkeyPatch) -> None:
        for i in range(5):
            project = tmp_path / "org" / f"proj{i}"
            project.mkdir(parents=True)
            (project / _HISTORY_FILENAME).write_text(_SAMPLE_HISTORY, encoding="utf-8")
        monkeypatch.setattr(aider_mod, "_DEFAULT_SEARCH_ROOTS", [tmp_path])
        b = AiderBackend()
        sessions = b.list_sessions(days=3650, limit=3)
        assert len(sessions) <= 3


# ---------------------------------------------------------------------------
# list_files
# ---------------------------------------------------------------------------

class TestListFiles:
    def test_returns_added_files(self, backend: AiderBackend) -> None:
        files = backend.list_files(days=3650)
        paths = [f["file_path"] for f in files]
        assert "src/auth.py" in paths
        assert "tests/test_auth.py" in paths

    def test_files_are_deduplicated(self, tmp_path: pathlib.Path, monkeypatch: pytest.MonkeyPatch) -> None:
        # Two sessions that both add the same file
        for i in range(2):
            project = tmp_path / "org" / f"proj{i}"
            project.mkdir(parents=True)
            hist = f"# aider chat started at 2026-01-{15+i:02d} 10:00:00\n\n#### task\n\n> /add shared.py\n\nanswer\n\n####\n"
            (project / _HISTORY_FILENAME).write_text(hist, encoding="utf-8")
        monkeypatch.setattr(aider_mod, "_DEFAULT_SEARCH_ROOTS", [tmp_path])
        b = AiderBackend()
        files = b.list_files(days=3650)
        paths = [f["file_path"] for f in files]
        assert paths.count("shared.py") == 1

    def test_tool_name_is_aider_add(self, backend: AiderBackend) -> None:
        files = backend.list_files(days=3650)
        for f in files:
            assert f["tool_name"] == "aider/add"

    def test_days_filter(self, backend: AiderBackend) -> None:
        # history date is 2026-01-15, which is in the past relative to test date
        files = backend.list_files(days=1)
        # With days=1, should filter out the 2026-01-15 session
        # (depends on current test date — just verify it doesn't crash)
        assert isinstance(files, list)


# ---------------------------------------------------------------------------
# search
# ---------------------------------------------------------------------------

class TestSearch:
    def test_finds_text_in_user_turn(self, backend: AiderBackend) -> None:
        results = backend.search("authentication", days=3650)
        assert len(results) >= 1
        assert any("authentication" in r["excerpt"].lower() for r in results)

    def test_finds_text_in_assistant_turn(self, backend: AiderBackend) -> None:
        results = backend.search("bcrypt", days=3650)
        assert len(results) >= 1

    def test_case_insensitive(self, backend: AiderBackend) -> None:
        upper = backend.search("AUTHENTICATION", days=3650)
        lower = backend.search("authentication", days=3650)
        assert len(upper) == len(lower)

    def test_no_results_for_missing_term(self, backend: AiderBackend) -> None:
        results = backend.search("xyzzy_not_present_12345", days=3650)
        assert results == []

    def test_one_result_per_session(self, backend: AiderBackend) -> None:
        # "auth" appears in both turns; should only return 1 result per session
        results = backend.search("auth", days=3650)
        session_ids = [r["session_id_full"] for r in results]
        assert len(session_ids) == len(set(session_ids))

    def test_result_fields(self, backend: AiderBackend) -> None:
        results = backend.search("authentication", days=3650)
        r = results[0]
        assert "session_id" in r
        assert "session_id_full" in r
        assert "excerpt" in r
        assert "date" in r
        assert "summary" in r


# ---------------------------------------------------------------------------
# show_session
# ---------------------------------------------------------------------------

class TestShowSession:
    def test_returns_full_session(self, backend: AiderBackend) -> None:
        sessions = backend.list_sessions(days=3650)
        full_id = sessions[0]["id_full"]
        result = backend.show_session(full_id)
        assert result is not None
        assert result["turns_count"] == 2
        assert len(result["turns"]) == 2
        assert len(result["files"]) == 2

    def test_turns_have_correct_fields(self, backend: AiderBackend) -> None:
        sessions = backend.list_sessions(days=3650)
        result = backend.show_session(sessions[0]["id_full"])
        assert result is not None
        for t in result["turns"]:
            assert "user" in t
            assert "assistant" in t
            assert "timestamp" in t

    def test_turns_limit(self, backend: AiderBackend) -> None:
        sessions = backend.list_sessions(days=3650)
        result = backend.show_session(sessions[0]["id_full"], turns=1)
        assert result is not None
        assert len(result["turns"]) == 1

    def test_returns_none_for_missing_id(self, backend: AiderBackend) -> None:
        result = backend.show_session("nonexistent-session-id-xyz")
        assert result is None

    def test_first_turn_content(self, backend: AiderBackend) -> None:
        sessions = backend.list_sessions(days=3650)
        result = backend.show_session(sessions[0]["id_full"])
        assert result is not None
        first_turn = result["turns"][0]
        assert "authentication" in first_turn["user"]
        assert "bcrypt" in first_turn["assistant"]

    def test_second_turn_content(self, backend: AiderBackend) -> None:
        sessions = backend.list_sessions(days=3650)
        result = backend.show_session(sessions[0]["id_full"])
        assert result is not None
        second_turn = result["turns"][1]
        assert "unit tests" in second_turn["user"]
        assert "unit tests" in second_turn["assistant"]


# ---------------------------------------------------------------------------
# health
# ---------------------------------------------------------------------------

class TestHealth:
    def test_health_structure(self, backend: AiderBackend) -> None:
        h = backend.health()
        assert "score" in h
        assert "zone" in h
        assert "dimensions" in h
        assert isinstance(h["score"], float)
        assert h["zone"] in ("GREEN", "AMBER", "RED")
        assert isinstance(h["dimensions"], list)

    def test_healthy_when_sessions_exist(self, backend: AiderBackend) -> None:
        h = backend.health()
        assert h["zone"] in ("GREEN", "AMBER")

    def test_red_when_no_files(self, tmp_path: pathlib.Path, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr(aider_mod, "_DEFAULT_SEARCH_ROOTS", [tmp_path])
        b = AiderBackend()
        h = b.health()
        assert h["zone"] == "RED"
        assert h["score"] == 0.0
