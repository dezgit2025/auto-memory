"""File-backed providers for IDE/session JSON logs."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

from .base import StorageProvider
from .common import is_within_days, short_id, utc_iso_from_ts


class _FileSessionProvider(StorageProvider):
    provider_name = "File Sessions"
    _MAX_PARSE_LINES = 5000
    _MAX_LINE_CHARS = 500_000

    def __init__(
        self, provider_id: str, roots: list[Path], patterns: list[str]
    ) -> None:
        self.provider_id = provider_id
        self._roots = roots
        self._patterns = patterns

    def is_available(self) -> bool:
        return any(root.exists() for root in self._roots)

    def _iter_files(self) -> list[Path]:
        files: list[Path] = []
        seen: set[Path] = set()
        for root in self._roots:
            if not root.exists():
                continue
            for pattern in self._patterns:
                for file_path in root.glob(pattern):
                    if not file_path.is_file():
                        continue
                    resolved = file_path.resolve()
                    if resolved in seen:
                        continue
                    seen.add(resolved)
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
            "provider": self.provider_id,
            "id_short": short_id(sid),
            "id_full": sid,
            "repository": "unknown",
            "branch": "unknown",
            "summary": summary,
            "date": created[:10],
            "created_at": created,
            "turns_count": len(turns),
            "files_count": 1,
            "_path": str(file_path),
            "_turns": turns,
        }

    def _parse_turns(self, file_path: Path) -> list[dict]:
        turns: list[dict] = []
        last_text = None
        try:
            with file_path.open("r", encoding="utf-8", errors="replace") as f:
                for idx, line in enumerate(f):
                    if idx >= self._MAX_PARSE_LINES:
                        break
                    line = line.strip()
                    if not line:
                        continue
                    if len(line) > self._MAX_LINE_CHARS:
                        # Skip pathological lines to keep recall responsive.
                        continue
                    try:
                        obj = json.loads(line)
                    except (
                        json.JSONDecodeError,
                        RecursionError,
                        TypeError,
                        ValueError,
                    ):
                        continue
                    text = _extract_text(obj)
                    if not text:
                        continue
                    text = text.strip()
                    if not text or text == last_text:
                        continue
                    last_text = text
                    role = _extract_role(obj)
                    turns.append(
                        {
                            "idx": idx,
                            "user": text if role == "user" else "",
                            "assistant": text if role != "user" else "",
                            "timestamp": (
                                obj.get("timestamp") if isinstance(obj, dict) else None
                            ),
                        }
                    )
        except OSError:
            return []
        return turns

    def list_sessions(
        self, repo: str | None, limit: int, days: int | None
    ) -> list[dict]:
        sessions: list[dict] = []
        for fp in self._iter_files():
            sess = self._session_from_file(fp)
            if not is_within_days(sess.get("created_at"), days):
                continue
            sessions.append({k: v for k, v in sess.items() if not k.startswith("_")})
            if len(sessions) >= limit:
                break
        return sessions

    def recent_files(
        self, repo: str | None, limit: int, days: int | None
    ) -> list[dict]:
        rows: list[dict] = []
        for fp in self._iter_files():
            created = utc_iso_from_ts(fp.stat().st_mtime)
            if not is_within_days(created, days):
                continue
            sid = self._session_id(fp)
            rows.append(
                {
                    "provider": self.provider_id,
                    "file_path": str(fp),
                    "tool_name": "json-log",
                    "date": created[:10],
                    "session_id": short_id(sid),
                    "session_summary": fp.name,
                }
            )
            if len(rows) >= limit:
                break
        return rows

    def list_checkpoints(
        self, repo: str | None, limit: int, days: int | None
    ) -> list[dict]:
        # File-backed providers typically don't expose checkpoints as first-class records.
        return []

    def search(
        self, query: str, repo: str | None, limit: int, days: int | None
    ) -> list[dict]:
        q = query.strip().lower()
        if not q:
            return []
        matches: list[dict] = []
        for fp in self._iter_files():
            sess = self._session_from_file(fp)
            if not is_within_days(sess.get("created_at"), days):
                continue
            for turn in sess.get("_turns", []):
                blob = f"{turn.get('user', '')}\n{turn.get('assistant', '')}".lower()
                if q not in blob:
                    continue
                matches.append(
                    {
                        "provider": self.provider_id,
                        "session_id": short_id(sess["id_full"]),
                        "session_id_full": sess["id_full"],
                        "source_type": "turn",
                        "summary": sess["summary"],
                        "repository": sess["repository"],
                        "date": sess["date"],
                        "content": blob[:500],
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
                "provider": self.provider_id,
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
            }
        return None


class VSCodeProvider(_FileSessionProvider):
    provider_name = "VS Code"

    def __init__(self, root_override: str | None = None) -> None:
        home = Path.home()
        if root_override:
            roots = [Path(root_override).expanduser()]
        else:
            roots = [
                home / ".config" / "Code" / "User" / "workspaceStorage",
                home
                / ".var"
                / "app"
                / "com.visualstudio.code"
                / "config"
                / "Code"
                / "User"
                / "workspaceStorage",
                home
                / "snap"
                / "code"
                / "current"
                / ".config"
                / "Code"
                / "User"
                / "workspaceStorage",
            ]
        super().__init__("vscode", roots, ["**/chatSessions/*.jsonl"])


class JetBrainsProvider(_FileSessionProvider):
    provider_name = "JetBrains"

    def __init__(self, root_override: str | None = None) -> None:
        home = Path.home()
        roots = (
            [Path(root_override).expanduser()]
            if root_override
            else [home / ".config" / "github-copilot"]
        )
        super().__init__(
            "jetbrains",
            roots,
            ["chat-sessions/*", "chat-agent-sessions/*", "chat-edit-sessions/*"],
        )


class NeovimProvider(_FileSessionProvider):
    provider_name = "Neovim"

    def __init__(self, root_override: str | None = None) -> None:
        home = Path.home()
        if root_override:
            roots = [Path(root_override).expanduser()]
        else:
            roots = [
                home / ".config" / "github-copilot",
                home / ".local" / "share" / "nvim",
            ]
        super().__init__("neovim", roots, ["**/*chat*.json", "**/*chat*.jsonl"])


def _extract_role(obj: object) -> str:
    if not isinstance(obj, dict):
        return "assistant"
    # VS Code chatSessions uses kind/k/v records for state diffs.
    if obj.get("kind") == 1:
        k = obj.get("k")
        if (
            isinstance(k, list)
            and len(k) >= 2
            and k[0] == "inputState"
            and k[1] == "inputText"
        ):
            return "user"
    role = obj.get("role")
    if isinstance(role, str):
        return role.lower()
    kind = obj.get("type")
    if isinstance(kind, str):
        return "user" if "user" in kind.lower() else "assistant"
    return "assistant"


def _extract_text(obj: object) -> str:
    if isinstance(obj, str):
        return obj
    if isinstance(obj, list):
        return " ".join(x for x in (_extract_text(i) for i in obj) if x)
    if not isinstance(obj, dict):
        return ""

    # VS Code chatSessions incremental state update format.
    if obj.get("kind") == 1:
        k = obj.get("k")
        v = obj.get("v")
        if (
            isinstance(k, list)
            and len(k) >= 2
            and k[0] == "inputState"
            and k[1] == "inputText"
        ):
            return v if isinstance(v, str) else ""

    # Some chatSessions have requests payload with user message text.
    if obj.get("kind") == 2 and isinstance(obj.get("v"), list):
        for item in obj.get("v"):
            if not isinstance(item, dict):
                continue
            message = item.get("message")
            if isinstance(message, str) and message.strip():
                return message

    candidates = [
        obj.get("text"),
        obj.get("content"),
        obj.get("message"),
        obj.get("value"),
    ]
    for c in candidates:
        t = _extract_text(c)
        if t:
            return t

    for key in ("messages", "parts", "items", "payload"):
        if key in obj:
            t = _extract_text(obj[key])
            if t:
                return t
    return ""


def _best_summary(turns: list[dict], fallback: str) -> str:
    """Pick the first meaningful user/assistant line for list summaries."""
    for turn in turns:
        for key in ("user", "assistant"):
            raw = str(turn.get(key) or "").strip()
            if not raw:
                continue
            first_line = raw.splitlines()[0].strip()
            if len(first_line) < 4:
                continue
            # Skip low-signal markdown/mention noise.
            if first_line in {"@", "```", "---"}:
                continue
            return first_line[:120]
    return fallback
