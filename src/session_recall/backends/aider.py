"""Aider backend — reads .aider.chat.history.md files from project directories."""
from __future__ import annotations

import datetime as _dt
import os
import pathlib
import re
import time
from typing import Optional

from .base import SessionBackend

_HISTORY_FILENAME = ".aider.chat.history.md"
_DEFAULT_SEARCH_ROOTS = [pathlib.Path.home() / "Documents", pathlib.Path.home()]
_SEARCH_DEPTHS = range(0, 4)  # root/filename through root/*/*/*/filename

# Regex patterns
_HEADING_RE = re.compile(r"^# aider chat started at (\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2})")
_HUMAN_TURN_RE = re.compile(r"^#### (.+)")
_SYSTEM_TURN_RE = re.compile(r"^####\s*$")
_ADD_FILE_RE = re.compile(r"^> /add (.+)")
_SHELL_OUTPUT_RE = re.compile(r"^> ")
# Aider auto-generated #### messages (not human turns)
_AIDER_AUTO_RE = re.compile(
    r"^#### (?:added|removed|dropped|renamed|created|reset|cleared|"
    r"Here are the|I see you|Tokens:|Cost:|Note:|Warning:|Error:)",
    re.IGNORECASE,
)


def _cutoff_date(days: int) -> str:
    """Return a YYYY-MM-DD cutoff string for ``days`` ago."""
    return (_dt.datetime.now() - _dt.timedelta(days=days)).strftime("%Y-%m-%d")


def _passes_filters(session: dict, *, repo: Optional[str], cutoff: str) -> bool:
    """Return True if ``session`` is within ``cutoff`` and matches ``repo``."""
    if session.get("date", "") < cutoff:
        return False
    if repo and repo != "all" and repo not in session.get("repository", ""):
        return False
    return True


class AiderBackend(SessionBackend):
    """Backend that reads .aider.chat.history.md files."""

    def __init__(self) -> None:
        self._cache: list[pathlib.Path] | None = None
        self._cache_time: float = 0.0
        self._cache_ttl: float = 60.0

    @property
    def name(self) -> str:
        return "aider"

    def _get_search_roots(self) -> list[pathlib.Path]:
        env_root = os.environ.get("AIDER_SEARCH_ROOT")
        if env_root:
            return [pathlib.Path(env_root)]
        return _DEFAULT_SEARCH_ROOTS

    def _find_history_files(self) -> list[pathlib.Path]:
        now = time.time()
        if self._cache is not None and (now - self._cache_time) < self._cache_ttl:
            return self._cache

        results: list[pathlib.Path] = []
        seen: set[pathlib.Path] = set()
        try:
            for root in self._get_search_roots():
                if not root.exists():
                    continue
                for depth in _SEARCH_DEPTHS:
                    prefix = "/".join(["*"] * depth) + ("/" if depth > 0 else "")
                    for p in root.glob(prefix + _HISTORY_FILENAME):
                        if p not in seen:
                            seen.add(p)
                            results.append(p)
        except Exception:
            pass

        self._cache = results
        self._cache_time = now
        return results

    def is_available(self) -> bool:
        try:
            return bool(self._find_history_files())
        except Exception:
            return False

    def _parse_header(self, lines: list[str], path: pathlib.Path) -> tuple[str, str]:
        """Return (created_at, date) from the file heading, or mtime fallback."""
        for line in lines:
            m = _HEADING_RE.match(line)
            if m:
                dt_str = m.group(1)
                return dt_str.replace(" ", "T"), dt_str[:10]

        try:
            dt = _dt.datetime.fromtimestamp(path.stat().st_mtime)
            return dt.strftime("%Y-%m-%dT%H:%M:%S"), dt.strftime("%Y-%m-%d")
        except Exception:
            return "", ""

    def _parse_file(self, path: pathlib.Path) -> dict:
        """Parse one .aider.chat.history.md file into a session dict."""
        try:
            text = path.read_text(encoding="utf-8", errors="replace")
        except Exception:
            return {}

        lines = text.splitlines()
        created_at, date = self._parse_header(lines, path)

        turns: list[dict] = []
        files_added: list[str] = []
        seen_files: set[str] = set()

        current_user: str | None = None
        current_assistant_lines: list[str] = []

        def _flush_turn() -> None:
            nonlocal current_user, current_assistant_lines
            if current_user is not None:
                turns.append({
                    "user": current_user,
                    "assistant": "\n".join(current_assistant_lines).strip(),
                    "timestamp": "",
                })
            current_user = None
            current_assistant_lines = []

        for line in lines:
            # System turn / separator (#### alone)
            if _SYSTEM_TURN_RE.match(line):
                _flush_turn()
                continue

            # Human turn (#### followed by text)
            m_human = _HUMAN_TURN_RE.match(line)
            if m_human:
                # Aider auto-generated messages are not true human turns
                if _AIDER_AUTO_RE.match(line):
                    if current_user is not None:
                        current_assistant_lines.append(m_human.group(1).strip())
                    continue
                _flush_turn()
                current_user = m_human.group(1).strip()
                continue

            # /add file references
            m_add = _ADD_FILE_RE.match(line)
            if m_add:
                fpath = m_add.group(1).strip()
                if fpath not in seen_files:
                    seen_files.add(fpath)
                    files_added.append(fpath)
                continue

            # Skip other > lines (shell output etc.)
            if _SHELL_OUTPUT_RE.match(line):
                continue

            # Accumulate assistant response lines (when inside a human turn)
            if current_user is not None:
                current_assistant_lines.append(line)

        _flush_turn()

        summary = turns[0]["user"][:120] if turns else ""
        repository = f"{path.parent.parent.name}/{path.parent.name}"
        file_records = [
            {"file_path": fp, "tool_name": "aider/add"} for fp in files_added
        ]

        return {
            "id": str(path),
            "id_short": path.parent.name[:8],
            "id_full": str(path),
            "repository": repository,
            "branch": "",
            "summary": summary,
            "created_at": created_at,
            "date": date,
            "turns_count": len(turns),
            "files_count": len(files_added),
            "turns": turns,
            "files": file_records,
        }

    def _all_sessions(self) -> list[dict]:
        """Return all parsed sessions."""
        sessions = []
        for path in self._find_history_files():
            try:
                s = self._parse_file(path)
                if s:
                    sessions.append(s)
            except Exception:
                continue
        return sessions

    def list_sessions(self, *, repo: Optional[str] = None, limit: int = 10, days: int = 30) -> list[dict]:
        try:
            cutoff = _cutoff_date(days)
            summary_fields = (
                "id", "id_short", "id_full", "repository", "branch",
                "summary", "created_at", "date", "turns_count", "files_count",
            )
            results = [
                {k: s[k] for k in summary_fields}
                for s in self._all_sessions()
                if _passes_filters(s, repo=repo, cutoff=cutoff)
            ]
            results.sort(
                key=lambda x: x.get("created_at") or x.get("date") or "",
                reverse=True,
            )
            return results[:limit]
        except Exception:
            return []

    def list_files(self, *, repo: Optional[str] = None, limit: int = 20, days: int = 30) -> list[dict]:
        try:
            cutoff = _cutoff_date(days)
            seen: set[str] = set()
            results: list[dict] = []
            for s in self._all_sessions():
                if not _passes_filters(s, repo=repo, cutoff=cutoff):
                    continue
                for f in s.get("files", []):
                    fp = f.get("file_path", "")
                    if not fp or fp in seen:
                        continue
                    seen.add(fp)
                    results.append({
                        "file_path": fp,
                        "tool_name": f.get("tool_name", "aider/add"),
                        "date": s.get("date", ""),
                        "session_id": s.get("id_short", ""),
                        "session_summary": s.get("summary", ""),
                    })
            return results[:limit]
        except Exception:
            return []

    def search(self, query: str, *, repo: Optional[str] = None, limit: int = 10, days: int = 30) -> list[dict]:
        try:
            cutoff = _cutoff_date(days)
            q_lower = query.lower()
            results: list[dict] = []
            for s in self._all_sessions():
                if not _passes_filters(s, repo=repo, cutoff=cutoff):
                    continue
                for turn in s.get("turns", []):
                    combined = f"{turn.get('user', '')}\n{turn.get('assistant', '')}"
                    idx = combined.lower().find(q_lower)
                    if idx < 0:
                        continue
                    start = max(0, idx - 50)
                    end = min(len(combined), idx + len(query) + 100)
                    results.append({
                        "session_id": s.get("id_short", ""),
                        "session_id_full": s.get("id_full", ""),
                        "source_type": "turn",
                        "summary": s.get("summary", ""),
                        "date": s.get("date", ""),
                        "excerpt": combined[start:end][:200],
                    })
                    break  # one result per session
            return results[:limit]
        except Exception:
            return []

    def show_session(self, session_id: str, *, turns: Optional[int] = None) -> Optional[dict]:
        try:
            for s in self._all_sessions():
                if s.get("id_full") == session_id or s.get("id") == session_id:
                    result = dict(s)
                    if turns is not None:
                        result["turns"] = result["turns"][:turns]
                    return result
            return None
        except Exception:
            return None

    def health(self) -> dict:
        try:
            files_found = self._find_history_files()
            sessions = self._all_sessions()
            n = len(sessions)

            if not files_found:
                zone = "RED"
            elif n == 0:
                zone = "AMBER"
            else:
                zone = "GREEN"

            score = (
                min(10.0, round(5.0 + (n / max(1, len(files_found))) * 5.0, 1))
                if files_found
                else 0.0
            )

            if n >= 3:
                sessions_zone = "GREEN"
            elif n >= 1:
                sessions_zone = "AMBER"
            else:
                sessions_zone = "RED"

            dimensions = [
                {
                    "name": "availability",
                    "score": 10.0 if files_found else 0.0,
                    "zone": "GREEN" if files_found else "RED",
                    "detail": f"{len(files_found)} history file(s) found",
                },
                {
                    "name": "sessions",
                    "score": min(10.0, round(n * 2.0, 1)),
                    "zone": sessions_zone,
                    "detail": f"{n} session(s) parsed",
                },
            ]
            return {"score": score, "zone": zone, "dimensions": dimensions}
        except Exception:
            return {"score": 0.0, "zone": "RED", "dimensions": []}
