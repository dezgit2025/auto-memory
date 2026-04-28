"""Shared base class for file-backed providers."""

from __future__ import annotations

import hashlib
import time
from pathlib import Path

from ..base import StorageProvider
from ..common import is_within_days, short_id, utc_iso_from_ts
from ._parse_helpers import _best_summary, parse_turns
from ._trust import wrap_untrusted
from ._path_safety import is_under_root


class _FileSessionProvider(StorageProvider):
    provider_name = "File Sessions"
    _MAX_PARSE_LINES = 5000
    _MAX_LINE_CHARS = 500_000
    _PROVIDER_SHORT: dict[str, str] = {"vscode": "vsc", "jetbrains": "jb", "neovim": "nv"}

    def __init__(
        self, provider_id: str, roots: list[Path], patterns: list[str]
    ) -> None:
        self.provider_id = provider_id
        self._output_id = self._PROVIDER_SHORT.get(provider_id, provider_id)
        self._roots = roots
        self._patterns = patterns

    def uses_jsonl_scan(self) -> bool:
        return True

    def is_available(self) -> bool:
        return any(root.exists() for root in self._roots)

    def _iter_files(self, days: int | None = None) -> list[Path]:
        files: list[Path] = []
        seen: set[Path] = set()
        cutoff = (time.time() - days * 86400) if days else None
        for root in self._roots:
            if not root.exists():
                continue
            for pattern in self._patterns:
                for file_path in root.glob(pattern):
                    if not file_path.is_file():
                        continue
                    resolved = file_path.resolve()
                    if not is_under_root(resolved, root):
                        continue  # symlink escape — skip
                    if resolved in seen:
                        continue
                    seen.add(resolved)
                    # mtime prefilter — skip stale files before opening
                    if cutoff is not None:
                        try:
                            if file_path.stat().st_mtime < cutoff:
                                continue
                        except OSError:
                            continue
                    files.append(resolved)
        files.sort(key=lambda p: p.stat().st_mtime, reverse=True)
        return files

    def _session_id(self, file_path: Path) -> str:
        digest = hashlib.sha1(str(file_path).encode("utf-8")).hexdigest()
        return f"{self.provider_id}:{digest}"

    def _session_from_file(self, file_path: Path) -> dict:
        sid = self._session_id(file_path)
        mtime = file_path.stat().st_mtime
        created = utc_iso_from_ts(mtime)
        turns = self._parse_turns(file_path)
        summary = _best_summary(turns, fallback=file_path.name)
        return {
            "provider": self._output_id,
            "id_short": short_id(sid),
            "id_full": sid,
            "repository": "unknown",
            "branch": "unknown",
            "summary": wrap_untrusted(summary),
            "date": created[:10],
            "created_at": created,
            "turns_count": len(turns),
            "files_count": 1,
            "_trust_level": "untrusted_third_party",
            "_path": str(file_path),
            "_turns": turns,
        }

    def _parse_turns(self, file_path: Path) -> list[dict]:
        return parse_turns(file_path, self._MAX_PARSE_LINES, self._MAX_LINE_CHARS)

    def list_sessions(
        self, repo: str | None, limit: int, days: int | None
    ) -> list[dict]:
        sessions: list[dict] = []
        for fp in self._iter_files(days=days):
            sess = self._session_from_file(fp)
            if not is_within_days(sess.get("created_at"), days):
                continue
            record = {k: v for k, v in sess.items() if not k.startswith("_")}
            record["_trust_level"] = "untrusted_third_party"
            sessions.append(record)
            if len(sessions) >= limit:
                break
        return sessions

    def recent_files(
        self, repo: str | None, limit: int, days: int | None
    ) -> list[dict]:
        rows: list[dict] = []
        for fp in self._iter_files(days=days):
            created = utc_iso_from_ts(fp.stat().st_mtime)
            if not is_within_days(created, days):
                continue
            sid = self._session_id(fp)
            rows.append(
                {
                    "provider": self._output_id,
                    "file_path": str(fp),
                    "tool_name": "json-log",
                    "date": created[:10],
                    "session_id": short_id(sid),
                    "session_summary": wrap_untrusted(fp.name),
                    "_trust_level": "untrusted_third_party",
                }
            )
            if len(rows) >= limit:
                break
        return rows

    def list_checkpoints(
        self, repo: str | None, limit: int, days: int | None
    ) -> list[dict]:
        return []

    def search(
        self, query: str, repo: str | None, limit: int, days: int | None
    ) -> list[dict]:
        q = query.strip().lower()
        if not q:
            return []
        matches: list[dict] = []
        for fp in self._iter_files(days=days):
            sess = self._session_from_file(fp)
            if not is_within_days(sess.get("created_at"), days):
                continue
            for turn in sess.get("_turns", []):
                blob = f"{turn.get('user', '')}\n{turn.get('assistant', '')}".lower()
                if q not in blob:
                    continue
                matches.append(
                    {
                        "provider": self._output_id,
                        "session_id": short_id(sess["id_full"]),
                        "session_id_full": sess["id_full"],
                        "source_type": "turn",
                        "summary": sess["summary"],
                        "repository": sess["repository"],
                        "date": sess["date"],
                        "excerpt": wrap_untrusted(
                            blob[:250] + ("..." if len(blob) > 250 else "")
                        ),
                        "_trust_level": "untrusted_third_party",
                    }
                )
                if len(matches) >= limit:
                    return matches
        return matches

    def get_session(
        self, session_id: str, turns: int | None, full: bool
    ) -> dict | None:
        sid = session_id.strip().lower()
        for fp in self._iter_files():
            sess = self._session_from_file(fp)
            full_id = sess["id_full"].lower()
            if not (full_id == sid or full_id.startswith(sid)):
                continue
            turn_rows = sess.get("_turns", [])
            if turns is not None:
                turn_rows = turn_rows[:turns]
            if not full:
                turn_rows = [
                    {
                        "idx": t["idx"],
                        "user": (t.get("user") or "")[:500],
                        "assistant": (t.get("assistant") or "")[:500],
                        "timestamp": t.get("timestamp"),
                    }
                    for t in turn_rows
                ]
            return {
                "provider": self._output_id,
                "id": sess["id_full"],
                "repository": sess["repository"],
                "branch": sess["branch"],
                "summary": sess["summary"],
                "created_at": sess["created_at"],
                "turns_count": len(turn_rows),
                "turns": turn_rows,
                "files": [
                    {
                        "file_path": sess["_path"],
                        "tool_name": "json-log",
                        "turn_index": 0,
                    }
                ],
                "refs": [],
                "checkpoints": [],
                "_trust_level": "untrusted_third_party",
            }
        return None


# Re-export for backward compatibility
from ._parse_helpers import _extract_role, _extract_text  # noqa: F401, E402

__all__ = ["_FileSessionProvider", "_extract_role", "_extract_text", "_best_summary"]
