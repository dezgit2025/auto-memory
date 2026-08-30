"""CodexProvider tests — Phase 2 scope (list_sessions / list_repos)."""

import pytest

from .. import state_queries
from ..errors import CodexSchemaDrift
from ..paths import CodexPaths
from ..provider import CodexProvider
from ._fixture_drift import make_drifted
from ._fixture_state import REF_NOW_MS

EXPECTED_KEYS = [
    "id_full", "id_short", "summary", "created_at", "date",
    "branch", "repository", "turns_count", "files_count", "_trust_level",
]


def _paths(store) -> CodexPaths:
    return CodexPaths(
        state_db=store.state_db,
        history_db=store.history_db,
        sessions_root=store.sessions_root,
    )


@pytest.fixture()
def frozen_now(monkeypatch):
    """Pin state_queries' wall clock to the fixtures' REF_NOW (no time bombs)."""
    monkeypatch.setattr(state_queries.time, "time", lambda: REF_NOW_MS / 1000)


@pytest.fixture()
def provider(codex_store, frozen_now):
    return CodexProvider(_paths(codex_store))


class TestListSessions:
    def test_default_five_rows_newest_first(self, provider):
        rows = provider.list_sessions()
        assert len(rows) == 5
        dates = [r["created_at"] for r in rows]
        assert dates == sorted(dates, reverse=True)
        summaries = " | ".join(r["summary"] for r in rows)
        for absent in ("guardian", "subagent", "archived"):
            assert absent not in summaries
        for r in rows:
            assert list(r.keys()) == EXPECTED_KEYS
            assert r["_trust_level"] == "codex_local_first_party"

    def test_counts_paginated_int_legacy_none(self, provider):
        rows = provider.list_sessions()
        legacy = [r for r in rows if "legacy" in r["summary"]]
        paginated = [r for r in rows if "legacy" not in r["summary"]]
        assert legacy and legacy[0]["turns_count"] is None
        assert legacy[0]["files_count"] is None
        assert all(isinstance(r["turns_count"], int) for r in paginated)
        assert all(isinstance(r["files_count"], int) for r in paginated)

    def test_repo_filter_exact(self, provider):
        rows = provider.list_sessions(repo="acme/widget")
        assert len(rows) == 4
        assert all(r["repository"] == "acme/widget" for r in rows)

    def test_repo_filter_all_and_local(self, provider):
        assert len(provider.list_sessions(repo="all")) == 5
        local = provider.list_sessions(repo="local:/Users/synthetic/scratch")
        assert len(local) == 1
        assert local[0]["repository"].startswith("local:")

    def test_repo_substring_rejected(self, provider):
        assert provider.list_sessions(repo="acme") == []

    def test_limit_after_repo_filter(self, provider):
        rows = provider.list_sessions(repo="acme/widget", limit=2)
        assert len(rows) == 2
        assert all(r["repository"] == "acme/widget" for r in rows)

    def test_include_archived(self, provider):
        rows = provider.list_sessions(include_archived=True)
        assert len(rows) == 6  # guardian trap still excluded
        assert any("archived" in r["summary"] for r in rows)

    def test_days_band(self, provider):
        week = provider.list_sessions(days=7)
        assert len(week) == 4  # oldband (20d) drops out
        assert len(provider.list_sessions(days=30)) == 5


class TestPreflightGate:
    def test_drift_blocks_before_any_query(
        self, codex_store, tmp_path, frozen_now, monkeypatch
    ):
        drifted = make_drifted(
            codex_store.state_db, codex_store.history_db,
            tmp_path / "drift", "drop_preview",
        )
        paths = CodexPaths(
            state_db=drifted["state"], history_db=drifted["history"],
            sessions_root=codex_store.sessions_root,
        )

        def _no_query(*a, **k):  # pragma: no cover - must not run
            raise AssertionError("thread query executed despite schema drift")

        monkeypatch.setattr(
            "session_recall.providers.codex.provider.select_threads", _no_query
        )
        with pytest.raises(CodexSchemaDrift) as exc:
            CodexProvider(paths).list_sessions()
        assert exc.value.exit_code == 2


class TestOtherMethods:
    def test_list_repos_shape_and_local_exclusion(self, provider):
        rows = provider.list_repos()
        assert [r["repository"] for r in rows] == ["acme/widget"]
        assert rows[0]["session_count"] == 4
        assert rows[0]["last_seen"][:4] == "2026"
        both = provider.list_repos(include_local=True)
        assert {r["repository"] for r in both} == {
            "acme/widget", "local:/Users/synthetic/scratch",
        }

    def test_checkpoints_empty_because_codex_has_none(self, provider):
        # Plan §4.1 / §15.1: no checkpoint storage exists in any Codex DB —
        # empty list is the documented, deliberate contract.
        assert provider.list_checkpoints() == []
        assert provider.list_checkpoints(repo="acme/widget", limit=1) == []

    def test_phase3_stubs_raise(self, provider):
        for call in (
            lambda: provider.recent_files(),
            lambda: provider.search("x"),
            lambda: provider.get_session("a" * 12),
        ):
            with pytest.raises(NotImplementedError, match="Phase 3"):
                call()

    def test_is_available(self, codex_store, tmp_path):
        assert CodexProvider(_paths(codex_store)).is_available() is True
        empty = CodexPaths(
            state_db=tmp_path / "nope.sqlite",
            history_db=tmp_path / "nope2.sqlite",
            sessions_root=tmp_path,
        )
        assert CodexProvider(empty).is_available() is False


class TestReposTieBreak:
    def test_equal_counts_sort_newest_first(self, monkeypatch):
        from session_recall.providers.codex.provider import CodexProvider

        rows = [
            {"git_origin_url": "https://github.com/acme/old.git", "cwd": None,
             "created_at_ms": 1_700_000_000_000, "created_at": None},
            {"git_origin_url": "https://github.com/acme/new.git", "cwd": None,
             "created_at_ms": 1_800_000_000_000, "created_at": None},
        ]
        p = CodexProvider.__new__(CodexProvider)

        import contextlib

        @contextlib.contextmanager
        def fake_open(_paths):
            yield None, None

        monkeypatch.setattr(
            "session_recall.providers.codex.provider.open_codex_ro", fake_open)
        monkeypatch.setattr(
            "session_recall.providers.codex.provider.preflight",
            lambda s, h: None)
        monkeypatch.setattr(
            "session_recall.providers.codex.provider.select_threads",
            lambda *a, **k: rows)
        p.paths = None
        out = p.list_repos()
        assert [r["repository"] for r in out] == ["acme/new", "acme/old"]
