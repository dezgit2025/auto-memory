"""Cursor IDE session backend.

Reads AI chat history from Cursor's SQLite workspace storage databases.
Each workspace has a ``state.vscdb`` file containing key-value pairs;
chat data lives under the key
``workbench.panel.aichat.view.aichat.chatdata``.
"""
from __future__ import annotations

import hashlib
import json
import os
import pathlib
import sqlite3
import sys
import time
from datetime import datetime, timedelta, timezone
from typing import Optional

from .base import SessionBackend


# ---------------------------------------------------------------------------
# Platform helpers
# ---------------------------------------------------------------------------

def _cursor_base() -> pathlib.Path:
    """Return the platform-appropriate workspaceStorage directory."""
    if sys.platform == "win32":
        appdata = os.environ.get("APPDATA", "")
        return pathlib.Path(appdata) / "Cursor" / "User" / "workspaceStorage"
    if sys.platform == "darwin":
        return pathlib.Path.home() / "Library" / "Application Support" / "Cursor" / "User" / "workspaceStorage"
    # Linux / other POSIX
    xdg = os.environ.get("XDG_CONFIG_HOME", "")
    if xdg:
        return pathlib.Path(xdg) / "Cursor" / "User" / "workspaceStorage"
    return pathlib.Path.home() / ".config" / "Cursor" / "User" / "workspaceStorage"


# Alternative keys observed in different Cursor builds
_CHAT_KEY_ALTS = [
    "workbench.panel.aichat.view.aichat.chatdata",
    "workbench.panel.aichat.view.aichat.chatData",
    "aiChat.chatData",
]

_USER_TYPES = ("user", "human")
_AI_TYPES = ("ai", "assistant", "bot")


# ---------------------------------------------------------------------------
# Low-level DB helpers
# ---------------------------------------------------------------------------

def _open_ro(db_path: pathlib.Path) -> Optional[sqlite3.Connection]:
    """Open a SQLite db read-only via URI.  Returns None on any error."""
    try:
        uri = db_path.as_uri() + "?mode=ro"
        conn = sqlite3.connect(uri, uri=True, timeout=2)
        conn.row_factory = sqlite3.Row
        return conn
    except Exception:
        return None


def _read_chat_json(db_path: pathlib.Path) -> Optional[dict]:
    """Return parsed chat JSON from *db_path*, or None."""
    conn = _open_ro(db_path)
    if conn is None:
        return None
    try:
        for key in _CHAT_KEY_ALTS:
            try:
                row = conn.execute(
                    "SELECT value FROM ItemTable WHERE key = ?", (key,)
                ).fetchone()
                if row:
                    return json.loads(row[0])
            except Exception:
                continue
        return None
    except Exception:
        return None
    finally:
        conn.close()


def _iter_workspace_dbs(base: pathlib.Path):
    """Yield (workspace_dir, state.vscdb path) for each workspace with a DB."""
    if not base.exists():
        return
    try:
        for ws_dir in base.iterdir():
            db = ws_dir / "state.vscdb"
            if db.exists():
                yield ws_dir, db
    except Exception:
        return


# ---------------------------------------------------------------------------
# Parsing helpers
# ---------------------------------------------------------------------------

def _ms_to_iso(ms: object) -> str:
    """Convert millisecond epoch to ISO-8601 UTC string, best-effort."""
    try:
        ts = int(ms) / 1000.0
        return datetime.fromtimestamp(ts, tz=timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    except Exception:
        return ""


def _extract_text(bubble: dict) -> str:
    """Pull readable text from a bubble dict (user or AI)."""
    text = bubble.get("text") or bubble.get("richText") or ""
    if isinstance(text, list):
        # Some builds store content as a list of blocks
        parts = []
        for block in text:
            if isinstance(block, dict):
                parts.append(block.get("text") or block.get("content") or "")
            elif isinstance(block, str):
                parts.append(block)
        text = " ".join(p for p in parts if p)
    return str(text).strip()


def _collect_files(bubbles: list) -> set[str]:
    """Return the set of file paths referenced across bubbles."""
    files: set[str] = set()
    for b in bubbles:
        for ctx in b.get("context") or []:
            if isinstance(ctx, dict):
                fp = ctx.get("path") or ctx.get("relativeWorkspacePath") or ""
                if fp:
                    files.add(fp)
        for sel in b.get("selections") or []:
            if isinstance(sel, dict):
                fp = (sel.get("uri") or {}).get("path") or ""
                if fp:
                    files.add(fp)
    return files


def _tab_to_session(tab: dict, workspace_hash: str) -> Optional[dict]:
    """Convert a single Cursor chat *tab* dict to a normalised session dict."""
    try:
        tab_id = tab.get("tabId") or tab.get("id") or ""
        if not tab_id:
            return None

        bubbles = tab.get("bubbles") or tab.get("messages") or []
        if not isinstance(bubbles, list):
            bubbles = []

        # Build a unique full id that encodes workspace + tab
        id_full = f"cursor-{workspace_hash[:8]}-{tab_id}"
        id_short = hashlib.sha1(id_full.encode()).hexdigest()[:8]

        # Timestamps
        last_send_ms = tab.get("lastSendTime") or tab.get("updatedAt") or 0
        created_ms = tab.get("createdAt") or last_send_ms
        created_iso = _ms_to_iso(created_ms) if created_ms else ""
        date_str = created_iso[:10]

        # Summary: chatTitle, else first user bubble text (truncated), else fallback
        summary = (tab.get("chatTitle") or "").strip()
        if not summary:
            for b in bubbles:
                if b.get("type") == "user":
                    summary = _extract_text(b)[:120]
                    break
        if not summary:
            summary = f"Cursor chat {tab_id[:8]}"

        # Count turns (user+ai pairs)
        user_count = sum(1 for b in bubbles if b.get("type") in _USER_TYPES)
        ai_count = sum(1 for b in bubbles if b.get("type") in _AI_TYPES)
        turns_count = max(user_count, ai_count)

        file_set = _collect_files(bubbles)

        return {
            "id_short": id_short,
            "id_full": id_full,
            "repository": "",        # Cursor doesn't expose git info per-tab
            "branch": "",
            "summary": summary,
            "date": date_str,
            "created_at": created_iso,
            "turns_count": turns_count,
            "files_count": len(file_set),
            # Store raw data for show_session / search
            "_bubbles": bubbles,
            "_file_set": sorted(file_set),
        }
    except Exception:
        return None


# ---------------------------------------------------------------------------
# In-memory index
# ---------------------------------------------------------------------------

class _Index:
    """Lazily built, mtime-invalidated in-memory session index."""

    def __init__(self) -> None:
        self._sessions: list[dict] = []
        self._stamp: float = 0.0  # mtime sum when last built

    def _current_stamp(self) -> float:
        total = 0.0
        for _ws_dir, db in _iter_workspace_dbs(_cursor_base()):
            try:
                total += db.stat().st_mtime
            except Exception:
                continue
        return total

    def _build(self) -> None:
        sessions: list[dict] = []
        for ws_dir, db in _iter_workspace_dbs(_cursor_base()):
            data = _read_chat_json(db)
            if not data:
                continue
            tabs = data.get("tabs") or data.get("sessions") or []
            if not isinstance(tabs, list):
                continue
            for tab in tabs:
                if not isinstance(tab, dict):
                    continue
                sess = _tab_to_session(tab, ws_dir.name)
                if sess:
                    sessions.append(sess)

        # Sort newest first
        sessions.sort(
            key=lambda s: s.get("created_at") or s.get("date") or "",
            reverse=True,
        )
        self._sessions = sessions
        self._stamp = self._current_stamp()

    def ensure(self) -> None:
        stamp = self._current_stamp()
        if not self._sessions or stamp != self._stamp:
            self._build()

    @property
    def sessions(self) -> list[dict]:
        return self._sessions


_index = _Index()


def _public(s: dict) -> dict:
    """Strip internal fields from a session dict."""
    return {k: v for k, v in s.items() if not k.startswith("_")}


# ---------------------------------------------------------------------------
# Backend
# ---------------------------------------------------------------------------

class CursorBackend(SessionBackend):
    """Session backend for Cursor IDE chat history."""

    @property
    def name(self) -> str:
        return "cursor"

    def is_available(self) -> bool:
        return _cursor_base().exists()

    # ------------------------------------------------------------------
    # Core query helpers
    # ------------------------------------------------------------------

    def _sessions_in_window(self, *, repo: Optional[str], days: int) -> list[dict]:
        _index.ensure()
        cutoff = (
            datetime.now(tz=timezone.utc) - timedelta(days=days)
        ).strftime("%Y-%m-%dT%H:%M:%SZ")
        result = []
        for s in _index.sessions:
            if repo and repo != "all" and s.get("repository", "") != repo:
                continue
            created = s.get("created_at") or ""
            if created and created < cutoff:
                continue
            result.append(s)
        return result

    # ------------------------------------------------------------------
    # SessionBackend interface
    # ------------------------------------------------------------------

    def list_sessions(self, *, repo: Optional[str] = None, limit: int = 10, days: int = 30) -> list[dict]:
        sessions = self._sessions_in_window(repo=repo, days=days)
        return [_public(s) for s in sessions[:limit]]

    def list_files(self, *, repo: Optional[str] = None, limit: int = 20, days: int = 30) -> list[dict]:
        sessions = self._sessions_in_window(repo=repo, days=days)
        seen: set[str] = set()
        files: list[dict] = []
        for s in sessions:
            for fp in s.get("_file_set") or []:
                if len(files) >= limit:
                    return files
                if fp in seen:
                    continue
                seen.add(fp)
                files.append({
                    "file_path": fp,
                    "tool_name": "cursor",
                    "date": s.get("date") or "",
                    "session_id": s.get("id_short") or "",
                })
        return files

    def search(self, query: str, *, repo: Optional[str] = None, limit: int = 10, days: int = 30) -> list[dict]:
        sessions = self._sessions_in_window(repo=repo, days=days)
        q = query.lower()
        results: list[dict] = []
        for s in sessions:
            summary = s.get("summary") or ""
            snippet = ""
            if q in summary.lower():
                snippet = summary
            else:
                # Search bubble texts
                for b in s.get("_bubbles") or []:
                    text = _extract_text(b)
                    idx = text.lower().find(q)
                    if idx >= 0:
                        start = max(0, idx - 60)
                        snippet = text[start:start + 200]
                        break
            if snippet:
                results.append({
                    "session_id": s.get("id_short") or "",
                    "session_id_full": s.get("id_full") or "",
                    "source_type": "chat",
                    "summary": s.get("summary") or "",
                    "date": s.get("date") or "",
                    "excerpt": snippet[:200],
                })
            if len(results) >= limit:
                break
        return results

    def show_session(self, session_id: str, *, turns: Optional[int] = None) -> Optional[dict]:
        _index.ensure()
        sid = session_id.strip().lower()
        match = None
        for s in _index.sessions:
            id_full = s.get("id_full", "").lower()
            id_short = s.get("id_short", "").lower()
            if id_full == sid or id_short == sid or id_full.startswith(sid):
                match = s
                break
        if match is None:
            return None

        bubbles = match.get("_bubbles") or []

        # Build turn pairs
        turn_list: list[dict] = []
        user_buf: Optional[str] = None
        idx = 0
        for b in bubbles:
            btype = b.get("type", "")
            text = _extract_text(b)
            if btype in _USER_TYPES:
                user_buf = text
            elif btype in _AI_TYPES:
                if turns is not None and idx >= turns:
                    break
                turn_list.append({
                    "idx": idx,
                    "user": user_buf or "",
                    "assistant": text[:500],
                    "timestamp": _ms_to_iso(b.get("createdAt") or 0),
                })
                user_buf = None
                idx += 1

        files = [
            {"file_path": fp, "tool_name": "cursor", "turn_index": None}
            for fp in (match.get("_file_set") or [])
        ]

        return {
            "id": match.get("id_full") or "",
            "repository": match.get("repository") or "",
            "branch": match.get("branch") or "",
            "summary": match.get("summary") or "",
            "created_at": match.get("created_at") or "",
            "turns_count": len(turn_list),
            "turns": turn_list,
            "files": files,
            "refs": [],
            "checkpoints": [],
        }

    def health(self) -> dict:
        _index.ensure()

        # Dimension: workspace count
        ws_count = 0
        chat_count = 0
        for _ws_dir, db in _iter_workspace_dbs(_cursor_base()):
            ws_count += 1
            if _read_chat_json(db) is not None:
                chat_count += 1

        # Dimension: index freshness (seconds since last build)
        stamp_age = time.time() - _index._stamp if _index._stamp else float("inf")
        fresh = stamp_age < 300  # < 5 min

        if stamp_age == float("inf"):
            freshness_detail = "never built"
        elif fresh:
            freshness_detail = "fresh"
        else:
            freshness_detail = f"stale ({int(stamp_age)}s old)"

        dim_workspaces = {
            "name": "cursor_workspaces",
            "label": "Cursor workspace count",
            "value": ws_count,
            "zone": "GREEN" if ws_count > 0 else "AMBER",
            "detail": f"{ws_count} workspace(s), {chat_count} with chat data",
        }
        dim_freshness = {
            "name": "cursor_index_freshness",
            "label": "Index freshness",
            "value": round(stamp_age, 1),
            "zone": "GREEN" if fresh else "AMBER",
            "detail": freshness_detail,
        }
        dim_sessions = {
            "name": "cursor_sessions",
            "label": "Indexed sessions",
            "value": len(_index.sessions),
            "zone": "GREEN" if _index.sessions else "AMBER",
            "detail": f"{len(_index.sessions)} session(s) indexed",
        }

        dims = [dim_workspaces, dim_freshness, dim_sessions]
        zones = {d["zone"] for d in dims}
        if "RED" in zones:
            zone = "RED"
            score = 2.0
        elif "AMBER" in zones:
            zone = "AMBER"
            score = 6.0
        else:
            zone = "GREEN"
            score = 10.0

        return {"score": score, "zone": zone, "dimensions": dims}
