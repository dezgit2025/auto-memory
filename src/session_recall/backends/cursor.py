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
from datetime import datetime, timezone
from typing import Optional


# ---------------------------------------------------------------------------
# Platform helpers
# ---------------------------------------------------------------------------

def _cursor_base() -> pathlib.Path:
    """Return the platform-appropriate workspaceStorage directory."""
    if sys.platform == "win32":
        appdata = os.environ.get("APPDATA", "")
        return pathlib.Path(appdata) / "Cursor" / "User" / "workspaceStorage"
    elif sys.platform == "darwin":
        return pathlib.Path.home() / "Library" / "Application Support" / "Cursor" / "User" / "workspaceStorage"
    else:
        # Linux / other POSIX
        xdg = os.environ.get("XDG_CONFIG_HOME", "")
        if xdg:
            return pathlib.Path(xdg) / "Cursor" / "User" / "workspaceStorage"
        return pathlib.Path.home() / ".config" / "Cursor" / "User" / "workspaceStorage"


_CHAT_KEY = "workbench.panel.aichat.view.aichat.chatdata"

# Alternative keys observed in different Cursor builds
_CHAT_KEY_ALTS = [
    _CHAT_KEY,
    "workbench.panel.aichat.view.aichat.chatData",
    "aiChat.chatData",
]


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

        # Summary: use chatTitle, or first user bubble text (truncated)
        summary = (tab.get("chatTitle") or "").strip()
        if not summary:
            for b in bubbles:
                if b.get("type") == "user":
                    summary = _extract_text(b)[:120]
                    break
        if not summary:
            summary = f"Cursor chat {tab_id[:8]}"

        # Count turns (user+ai pairs)
        user_bubbles = [b for b in bubbles if b.get("type") in ("user", "human")]
        ai_bubbles = [b for b in bubbles if b.get("type") in ("ai", "assistant", "bot")]
        turns_count = max(len(user_bubbles), len(ai_bubbles))

        # Files mentioned (Cursor attaches file context in some versions)
        file_set: set[str] = set()
        for b in bubbles:
            for ctx in b.get("context") or []:
                if isinstance(ctx, dict):
                    fp = ctx.get("path") or ctx.get("relativeWorkspacePath") or ""
                    if fp:
                        file_set.add(fp)
            # Also check selections / attachments
            for sel in b.get("selections") or []:
                if isinstance(sel, dict):
                    fp = (sel.get("uri") or {}).get("path") or ""
                    if fp:
                        file_set.add(fp)

        files_count = len(file_set)

        return {
            "id_short": id_short,
            "id_full": id_full,
            "repository": "",        # Cursor doesn't expose git info per-tab
            "branch": "",
            "summary": summary,
            "date": date_str,
            "created_at": created_iso,
            "turns_count": turns_count,
            "files_count": files_count,
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
        base = _cursor_base()
        if not base.exists():
            return 0.0
        total = 0.0
        try:
            for d in base.iterdir():
                db = d / "state.vscdb"
                if db.exists():
                    total += db.stat().st_mtime
        except Exception:
            pass
        return total

    def _build(self) -> None:
        base = _cursor_base()
        sessions: list[dict] = []
        if not base.exists():
            self._sessions = sessions
            self._stamp = 0.0
            return
        try:
            for ws_dir in base.iterdir():
                db = ws_dir / "state.vscdb"
                if not db.exists():
                    continue
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
        except Exception:
            pass

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

from .base import SessionBackend  # noqa: E402


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
        from datetime import timedelta
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
                if fp not in seen:
                    seen.add(fp)
                    files.append({
                        "file_path": fp,
                        "tool_name": "cursor",
                        "date": s.get("date") or "",
                        "session_id": s.get("id_short") or "",
                    })
                if len(files) >= limit:
                    break
            if len(files) >= limit:
                break
        return files

    def search(self, query: str, *, repo: Optional[str] = None, limit: int = 10, days: int = 30) -> list[dict]:
        sessions = self._sessions_in_window(repo=repo, days=days)
        q = query.lower()
        results: list[dict] = []
        for s in sessions:
            # Search summary
            summary = (s.get("summary") or "").lower()
            snippet = ""
            if q in summary:
                snippet = s.get("summary") or ""
            else:
                # Search bubble texts
                for b in s.get("_bubbles") or []:
                    text = _extract_text(b).lower()
                    if q in text:
                        idx = text.find(q)
                        start = max(0, idx - 60)
                        snippet = _extract_text(b)[start:start + 200]
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
            if s.get("id_full", "").lower() == sid:
                match = s
                break
            if s.get("id_short", "").lower() == sid:
                match = s
                break
            if s.get("id_full", "").lower().startswith(sid):
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
            if btype in ("user", "human"):
                user_buf = text
            elif btype in ("ai", "assistant", "bot"):
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
        base = _cursor_base()

        # Dimension: workspace count
        ws_count = 0
        chat_count = 0
        try:
            if base.exists():
                for d in base.iterdir():
                    db = d / "state.vscdb"
                    if db.exists():
                        ws_count += 1
                        if _read_chat_json(db) is not None:
                            chat_count += 1
        except Exception:
            pass

        # Dimension: index freshness (seconds since last build)
        import time
        stamp_age = time.time() - _index._stamp if _index._stamp else float("inf")
        fresh = stamp_age < 300  # < 5 min

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
            "detail": "fresh" if fresh else ("never built" if stamp_age == float("inf") else f"stale ({int(stamp_age)}s old)"),
        }
        dim_sessions = {
            "name": "cursor_sessions",
            "label": "Indexed sessions",
            "value": len(_index.sessions),
            "zone": "GREEN" if _index.sessions else "AMBER",
            "detail": f"{len(_index.sessions)} session(s) indexed",
        }

        dims = [dim_workspaces, dim_freshness, dim_sessions]
        zones = [d["zone"] for d in dims]
        zone = "RED" if "RED" in zones else ("AMBER" if "AMBER" in zones else "GREEN")

        # Score: 10 if all green, 6 if any amber, 2 if any red
        if zone == "GREEN":
            score = 10.0
        elif zone == "AMBER":
            score = 6.0
        else:
            score = 2.0

        return {"score": score, "zone": zone, "dimensions": dims}
