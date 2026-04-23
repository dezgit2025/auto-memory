"""Aider backend — reads .aider.chat.history.md files from project directories."""
from __future__ import annotations
import os
import pathlib
import re
import sys
import time
from typing import Optional
from .base import SessionBackend

_HISTORY_FILENAME = ".aider.chat.history.md"
_DEFAULT_SEARCH_ROOTS = [pathlib.Path.home() / "Documents", pathlib.Path.home()]

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
        try:
            roots = self._get_search_roots()
            for root in roots:
                if not root.exists():
                    continue
                # Search up to depth 3: root/*/filename, root/*/*/filename, root/*/*/*/filename
                for depth in range(0, 4):
                    pattern = "/".join(["*"] * depth) + ("/" if depth > 0 else "") + _HISTORY_FILENAME
                    for p in root.glob(pattern):
                        if p not in results:
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

    def _parse_file(self, path: pathlib.Path) -> dict:
        """Parse one .aider.chat.history.md file into a session dict."""
        try:
            text = path.read_text(encoding="utf-8", errors="replace")
        except Exception:
            return {}

        lines = text.splitlines()
        created_at = ""
        date = ""

        # Parse the file heading for creation time
        for line in lines:
            m = _HEADING_RE.match(line)
            if m:
                dt_str = m.group(1)
                created_at = dt_str.replace(" ", "T")
                date = dt_str[:10]
                break

        # Fall back to file mtime
        if not created_at:
            try:
                mtime = path.stat().st_mtime
                import datetime
                dt = datetime.datetime.fromtimestamp(mtime)
                created_at = dt.strftime("%Y-%m-%dT%H:%M:%S")
                date = dt.strftime("%Y-%m-%d")
            except Exception:
                pass

        # Parse turns and file references
        turns: list[dict] = []
        files_added: list[str] = []
        seen_files: set[str] = set()

        current_user: str | None = None
        current_assistant_lines: list[str] = []

        def _flush_turn() -> None:
            nonlocal current_user, current_assistant_lines
            if current_user is not None:
                assistant_text = "\n".join(current_assistant_lines).strip()
                turns.append({
                    "user": current_user,
                    "assistant": assistant_text,
                    "timestamp": "",
                })
            current_user = None
            current_assistant_lines = []

        for line in lines:
            # Check for system turn / separator (#### alone)
            if _SYSTEM_TURN_RE.match(line):
                _flush_turn()
                continue

            # Check for human turn (#### followed by text)
            m_human = _HUMAN_TURN_RE.match(line)
            if m_human:
                # Skip aider auto-generated #### messages (e.g. "added X to the chat")
                if _AIDER_AUTO_RE.match(line):
                    # Treat as assistant continuation if we're in a turn, else skip
                    if current_user is not None:
                        current_assistant_lines.append(m_human.group(1).strip())
                    continue
                _flush_turn()
                current_user = m_human.group(1).strip()
                continue

            # Check for /add file references
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

            # Accumulate assistant response lines (when we're inside a human turn)
            if current_user is not None:
                current_assistant_lines.append(line)

        # Flush any remaining turn
        _flush_turn()

        summary = ""
        if turns:
            summary = turns[0]["user"][:120]

        parent_name = path.parent.name
        grandparent_name = path.parent.parent.name
        repository = f"{grandparent_name}/{parent_name}"

        file_records = [
            {"file_path": fp, "tool_name": "aider/add"}
            for fp in files_added
        ]

        return {
            "id": str(path),
            "id_short": parent_name[:8],
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
                pass
        return sessions

    def list_sessions(self, *, repo: Optional[str] = None, limit: int = 10, days: int = 30) -> list[dict]:
        try:
            import datetime
            cutoff = (datetime.datetime.now() - datetime.timedelta(days=days)).strftime("%Y-%m-%d")
            sessions = self._all_sessions()
            results = []
            for s in sessions:
                if s.get("date", "") < cutoff:
                    continue
                if repo and repo != "all":
                    if repo not in s.get("repository", ""):
                        continue
                # Return session summary (without full turns/files to keep it compact)
                results.append({
                    "id": s["id"],
                    "id_short": s["id_short"],
                    "id_full": s["id_full"],
                    "repository": s["repository"],
                    "branch": s["branch"],
                    "summary": s["summary"],
                    "created_at": s["created_at"],
                    "date": s["date"],
                    "turns_count": s["turns_count"],
                    "files_count": s["files_count"],
                })
            results.sort(key=lambda x: x.get("created_at") or x.get("date") or "", reverse=True)
            return results[:limit]
        except Exception:
            return []

    def list_files(self, *, repo: Optional[str] = None, limit: int = 20, days: int = 30) -> list[dict]:
        try:
            import datetime
            cutoff = (datetime.datetime.now() - datetime.timedelta(days=days)).strftime("%Y-%m-%d")
            sessions = self._all_sessions()
            seen: set[str] = set()
            results = []
            for s in sessions:
                if s.get("date", "") < cutoff:
                    continue
                if repo and repo != "all":
                    if repo not in s.get("repository", ""):
                        continue
                for f in s.get("files", []):
                    fp = f.get("file_path", "")
                    if fp not in seen:
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
            import datetime
            cutoff = (datetime.datetime.now() - datetime.timedelta(days=days)).strftime("%Y-%m-%d")
            q_lower = query.lower()
            sessions = self._all_sessions()
            results = []
            for s in sessions:
                if s.get("date", "") < cutoff:
                    continue
                if repo and repo != "all":
                    if repo not in s.get("repository", ""):
                        continue
                for turn in s.get("turns", []):
                    user_text = turn.get("user", "")
                    asst_text = turn.get("assistant", "")
                    combined = f"{user_text}\n{asst_text}"
                    if q_lower in combined.lower():
                        # Find the matching excerpt
                        idx = combined.lower().find(q_lower)
                        start = max(0, idx - 50)
                        end = min(len(combined), idx + len(query) + 100)
                        excerpt = combined[start:end]
                        results.append({
                            "session_id": s.get("id_short", ""),
                            "session_id_full": s.get("id_full", ""),
                            "source_type": "turn",
                            "summary": s.get("summary", ""),
                            "date": s.get("date", ""),
                            "excerpt": excerpt[:200],
                        })
                        break  # one result per session
            return results[:limit]
        except Exception:
            return []

    def show_session(self, session_id: str, *, turns: Optional[int] = None) -> Optional[dict]:
        try:
            sessions = self._all_sessions()
            for s in sessions:
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
            sessions = self._all_sessions()
            n = len(sessions)
            files_found = self._find_history_files()
            score = min(10.0, round(5.0 + (n / max(1, len(files_found))) * 5.0, 1)) if files_found else 0.0
            if not files_found:
                zone = "RED"
            elif n == 0:
                zone = "AMBER"
            else:
                zone = "GREEN"
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
                    "zone": "GREEN" if n >= 3 else ("AMBER" if n >= 1 else "RED"),
                    "detail": f"{n} session(s) parsed",
                },
            ]
            return {"score": score, "zone": zone, "dimensions": dimensions}
        except Exception:
            return {"score": 0.0, "zone": "RED", "dimensions": []}
