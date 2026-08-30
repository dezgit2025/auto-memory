"""Codex StorageProvider — Phase 2 scope: list_sessions / list_repos.

Every data path runs inside one ``open_codex_ro`` context and calls
``preflight`` before any session query (plan §5.2, §16 Fix 2). Repo
filtering happens in Python on the derived label, after which counts are
computed only for rows that survive the filter.
"""

from __future__ import annotations

from ..base import StorageProvider
from .connect import open_codex_ro
from .normalize import (
    normalize_thread_row,
    repo_label,
    repo_matches,
    thread_timestamp,
)
from .paths import CodexPaths, resolve_paths
from .schema import preflight
from .state_queries import count_files, count_turns, select_threads


class CodexProvider(StorageProvider):
    """Read-only provider over ~/.codex state/history storage."""

    provider_id = "codex"
    provider_name = "Codex CLI"

    def __init__(self, paths: CodexPaths | None = None):
        self.paths = paths or resolve_paths()

    def is_available(self) -> bool:
        """Both databases exist as files (no connections opened)."""
        return self.paths.state_db.is_file() and self.paths.history_db.is_file()

    # -- Phase 2 commands ---------------------------------------------------

    def list_sessions(
        self,
        repo: str | None = None,
        limit: int = 10,
        days: int | None = 30,
        *,
        include_archived: bool = False,
    ) -> list[dict]:
        days = 30 if days is None else days
        with open_codex_ro(self.paths) as (state, history):
            preflight(state, history)
            rows = select_threads(
                state,
                repo=repo,
                limit=limit,
                days=days,
                include_archived=include_archived,
            )
            out: list[dict] = []
            for row in rows:
                label = repo_label(row["git_origin_url"], row["cwd"])
                if not repo_matches(label, repo):
                    continue
                out.append(self._normalize_with_counts(row, history))
                if len(out) >= limit:
                    break
            return out

    def list_repos(
        self, limit: int = 10, days: int | None = 30, include_local: bool = False
    ) -> list[dict]:
        """Aggregate repositories from the lookback window.

        Output rows mirror the main CLI's ``repos`` shape (repository,
        session_count, last_seen); ``local:`` labels are excluded unless
        ``include_local`` (same convention as commands/repos.py).
        """
        days = 30 if days is None else days
        with open_codex_ro(self.paths) as (state, history):
            preflight(state, history)
            # repo sentinel disables LIMIT pushdown: aggregation needs all rows.
            rows = select_threads(state, repo="all", limit=0, days=days)
            buckets: dict[str, dict] = {}
            for row in rows:
                label = repo_label(row["git_origin_url"], row["cwd"])
                created = thread_timestamp(row)
                entry = buckets.setdefault(
                    label,
                    {"repository": label, "session_count": 0, "last_seen": created},
                )
                entry["session_count"] += 1
                if created > entry["last_seen"]:
                    entry["last_seen"] = created
        out = list(buckets.values())
        if not include_local:
            out = [r for r in out if not r["repository"].startswith("local:")]
        out.sort(key=lambda r: (-r["session_count"], r["last_seen"]))
        return out[:limit]

    def list_checkpoints(
        self, repo: str | None = None, limit: int = 10, days: int | None = 30
    ) -> list[dict]:
        """Always empty: Codex storage has no checkpoint records.

        Plan §4.1 — validated empirically (§15.1): no checkpoints table
        exists in any Codex database; ``memories_1.sqlite`` and
        ``thread_artifacts`` were both empty on the reviewed machine and
        are not session-recall sources.
        """
        return []

    # -- Phase 3 scope (deliberate stubs, plan §8 sequencing) ---------------

    def recent_files(self, repo=None, limit=10, days=30) -> list[dict]:
        raise NotImplementedError("codex recent_files lands in Phase 3")

    def search(self, query, repo=None, limit=5, days=30) -> list[dict]:
        raise NotImplementedError("codex search lands in Phase 3")

    def get_session(self, session_id, turns=None, full=False) -> dict | None:
        raise NotImplementedError("codex get_session lands in Phase 3")

    # -- helpers ------------------------------------------------------------

    def _normalize_with_counts(self, row, history) -> dict:
        """Normalize one thread row, attaching counts for paginated threads.

        Legacy threads pass None counts (rendered as null in JSON) until the
        Phase 4 rollout reader supplies real numbers.  TODO(plan §8 Phase 4).
        """
        if row["history_mode"] == "paginated":
            tc = count_turns(history, row["id"])
            fc = count_files(history, row["id"])
        else:
            tc = fc = None
        return normalize_thread_row(row, turns_count=tc, files_count=fc)
