"""Copilot CLI SQLite provider."""

from __future__ import annotations

import re
import json
from pathlib import Path

from ..db.connect import connect_ro
from ..db.schema_check import schema_check
from ..util.detect_repo import detect_repo_for_cwd
from .base import StorageProvider
from .common import is_within_days, short_id, utc_iso_from_ts

_SID_RE = re.compile(r"^[0-9a-fA-F-]{4,}$")


class CopilotCliProvider(StorageProvider):
    provider_id = "cli"
    provider_name = "Copilot CLI"

    def __init__(self, db_path: str, state_root: str) -> None:
        self.db_path = db_path
        self.state_root = Path(state_root)

    def _has_db(self) -> bool:
        return Path(self.db_path).exists()

    def _state_files(self) -> list[Path]:
        if not self.state_root.exists():
            return []
        files = list(self.state_root.glob("*/events.jsonl"))
        files.sort(key=lambda p: p.stat().st_mtime, reverse=True)
        return files

    def is_available(self) -> bool:
        return self._has_db() or bool(self._state_files())

    def schema_problems(self) -> list[str]:
        if not self._has_db():
            return []
        conn = connect_ro(self.db_path)
        try:
            return schema_check(conn)
        finally:
            conn.close()

    def list_sessions(
        self, repo: str | None, limit: int, days: int | None
    ) -> list[dict]:
        if not self._has_db():
            return self._state_list_sessions(repo=repo, limit=limit, days=days)
        conn = connect_ro(self.db_path)
        try:
            days_arg = f"-{days or 30} days"
            if repo and repo != "all":
                rows = conn.execute(
                    """
                    SELECT s.id, s.repository, s.branch, s.summary, s.created_at, s.updated_at,
                           (SELECT COUNT(*) FROM turns t WHERE t.session_id = s.id) as turns_count,
                           (SELECT COUNT(*) FROM session_files f WHERE f.session_id = s.id) as files_count
                    FROM sessions s WHERE s.repository = ? AND s.created_at >= datetime('now', ?)
                    ORDER BY s.created_at DESC LIMIT ?
                    """,
                    (repo, days_arg, limit),
                ).fetchall()
            else:
                rows = conn.execute(
                    """
                    SELECT s.id, s.repository, s.branch, s.summary, s.created_at, s.updated_at,
                           (SELECT COUNT(*) FROM turns t WHERE t.session_id = s.id) as turns_count,
                           (SELECT COUNT(*) FROM session_files f WHERE f.session_id = s.id) as files_count
                    FROM sessions s WHERE s.created_at >= datetime('now', ?)
                    ORDER BY s.created_at DESC LIMIT ?
                    """,
                    (days_arg, limit),
                ).fetchall()
            return [
                {
                    "provider": self.provider_id,
                    "id_short": short_id(r["id"]),
                    "id_full": r["id"],
                    "repository": r["repository"],
                    "branch": r["branch"],
                    "summary": r["summary"],
                    "date": r["created_at"][:10] if r["created_at"] else None,
                    "created_at": r["created_at"],
                    "turns_count": r["turns_count"],
                    "files_count": r["files_count"],
                }
                for r in rows
            ]
        finally:
            conn.close()

    def recent_files(
        self, repo: str | None, limit: int, days: int | None
    ) -> list[dict]:
        if not self._has_db():
            return []
        conn = connect_ro(self.db_path)
        try:
            date_filter = " AND sf.first_seen_at >= datetime('now', ?)" if days else ""
            date_param = (f"-{days} days",) if days else ()
            base = """
                SELECT sf.file_path, sf.tool_name, sf.first_seen_at,
                       sf.session_id, s.summary
                FROM session_files sf
                JOIN sessions s ON s.id = sf.session_id
            """
            if repo and repo != "all":
                sql = (
                    base
                    + f" WHERE s.repository = ?{date_filter} ORDER BY sf.first_seen_at DESC LIMIT ?"
                )
                rows = conn.execute(sql, (repo, *date_param, limit)).fetchall()
            else:
                where = f" WHERE 1=1{date_filter}" if days else ""
                sql = base + where + " ORDER BY sf.first_seen_at DESC LIMIT ?"
                rows = conn.execute(sql, (*date_param, limit)).fetchall()
            return [
                {
                    "provider": self.provider_id,
                    "file_path": r["file_path"],
                    "tool_name": r["tool_name"],
                    "date": (r["first_seen_at"] or "")[:10],
                    "session_id": short_id(r["session_id"]),
                    "session_summary": r["summary"],
                }
                for r in rows
            ]
        finally:
            conn.close()

    def list_checkpoints(
        self, repo: str | None, limit: int, days: int | None
    ) -> list[dict]:
        if not self._has_db():
            return []
        conn = connect_ro(self.db_path)
        try:
            date_filter = " AND c.created_at >= datetime('now', ?)" if days else ""
            date_param = (f"-{days} days",) if days else ()
            base = """
                SELECT c.checkpoint_number, c.title, c.overview, c.created_at,
                       c.session_id, s.summary as session_summary
                FROM checkpoints c
                JOIN sessions s ON s.id = c.session_id
            """
            if repo and repo != "all":
                sql = (
                    base
                    + f" WHERE s.repository = ?{date_filter} ORDER BY c.created_at DESC LIMIT ?"
                )
                rows = conn.execute(sql, (repo, *date_param, limit)).fetchall()
            else:
                where = f" WHERE 1=1{date_filter}" if days else ""
                sql = base + where + " ORDER BY c.created_at DESC LIMIT ?"
                rows = conn.execute(sql, (*date_param, limit)).fetchall()
            return [
                {
                    "provider": self.provider_id,
                    "checkpoint_number": r["checkpoint_number"],
                    "title": r["title"],
                    "overview": (r["overview"] or "")[:300],
                    "date": (r["created_at"] or "")[:10],
                    "session_id": short_id(r["session_id"]),
                    "session_summary": r["session_summary"],
                }
                for r in rows
            ]
        finally:
            conn.close()

    def search(
        self, query: str, repo: str | None, limit: int, days: int | None
    ) -> list[dict]:
        if not self._has_db():
            return self._state_search(query=query, repo=repo, limit=limit, days=days)
        from ..commands.search import sanitize_fts5_query

        fts_query = sanitize_fts5_query(query)
        if fts_query is None:
            return []
        conn = connect_ro(self.db_path)
        try:
            date_clause = " AND s.created_at >= datetime('now', ?)" if days else ""
            date_param = (f"-{days} days",) if days else ()
            if repo and repo != "all":
                sql = (
                    """
                    SELECT si.content, si.session_id, si.source_type,
                           s.summary, s.created_at, s.repository
                    FROM search_index si JOIN sessions s ON s.id = si.session_id
                    WHERE search_index MATCH ? AND s.repository = ?
                    """
                    + date_clause
                    + " ORDER BY rank LIMIT ?"
                )
                rows = conn.execute(
                    sql, (fts_query, repo, *date_param, limit)
                ).fetchall()
            else:
                sql = (
                    """
                    SELECT si.content, si.session_id, si.source_type,
                           s.summary, s.created_at, s.repository
                    FROM search_index si JOIN sessions s ON s.id = si.session_id
                    WHERE search_index MATCH ?
                    """
                    + date_clause
                    + " ORDER BY rank LIMIT ?"
                )
                rows = conn.execute(sql, (fts_query, *date_param, limit)).fetchall()

            return [
                {
                    "provider": self.provider_id,
                    "session_id": short_id(r["session_id"]),
                    "session_id_full": r["session_id"],
                    "source_type": r["source_type"],
                    "summary": r["summary"],
                    "repository": r["repository"],
                    "date": (r["created_at"] or "")[:10],
                    "content": (r["content"] or "")[:500],
                }
                for r in rows
            ]
        finally:
            conn.close()

    def get_session(
        self, session_id: str, turns: int | None, full: bool
    ) -> dict | None:
        if not self._has_db():
            return self._state_get_session(
                session_id=session_id, turns=turns, full=full
            )
        if not _SID_RE.match(session_id) or not session_id.replace("-", ""):
            return None
        sid = session_id.lower()
        conn = connect_ro(self.db_path)
        try:
            row = conn.execute(
                "SELECT * FROM sessions WHERE id = ? OR id LIKE ?",
                (sid, f"{sid}%"),
            ).fetchone()
            if not row:
                return None
            full_id = row["id"]
            if turns is not None:
                turns_rows = conn.execute(
                    "SELECT turn_index, user_message, assistant_response, timestamp "
                    "FROM turns WHERE session_id = ? ORDER BY turn_index LIMIT ?",
                    (full_id, turns),
                ).fetchall()
            else:
                turns_rows = conn.execute(
                    "SELECT turn_index, user_message, assistant_response, timestamp "
                    "FROM turns WHERE session_id = ? ORDER BY turn_index",
                    (full_id,),
                ).fetchall()
            mx = 99999 if full else 500
            turn_payload = [
                {
                    "idx": t["turn_index"],
                    "user": (t["user_message"] or "")[:mx],
                    "assistant": (t["assistant_response"] or "")[:mx],
                    "timestamp": t["timestamp"],
                }
                for t in turns_rows
            ]
            files = [
                dict(f)
                for f in conn.execute(
                    "SELECT file_path, tool_name, turn_index FROM session_files WHERE session_id = ?",
                    (full_id,),
                ).fetchall()
            ]
            refs = [
                dict(r)
                for r in conn.execute(
                    "SELECT ref_type, ref_value, turn_index FROM session_refs WHERE session_id = ?",
                    (full_id,),
                ).fetchall()
            ]
            checkpoints = [
                {
                    "n": c["checkpoint_number"],
                    "title": c["title"],
                    "overview": (c["overview"] or "")[:300],
                }
                for c in conn.execute(
                    "SELECT checkpoint_number, title, overview FROM checkpoints "
                    "WHERE session_id = ? ORDER BY checkpoint_number",
                    (full_id,),
                ).fetchall()
            ]
            return {
                "provider": self.provider_id,
                "id": full_id,
                "repository": row["repository"],
                "branch": row["branch"],
                "summary": row["summary"],
                "created_at": row["created_at"],
                "turns_count": len(turns_rows),
                "turns": turn_payload,
                "files": files,
                "refs": refs,
                "checkpoints": checkpoints,
            }
        finally:
            conn.close()

    def _parse_state_session(self, file_path: Path) -> dict:
        session_id = file_path.parent.name
        created_at = None
        cwd = None
        git_root = None
        repo_from_context = None
        candidate_paths: list[str] = []
        turns: list[dict] = []
        last_text = None
        try:
            with file_path.open("r", encoding="utf-8", errors="replace") as f:
                for line in f:
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        event = json.loads(line)
                    except json.JSONDecodeError:
                        continue
                    etype = event.get("type")
                    data = event.get("data") or {}
                    ts = event.get("timestamp")

                    if etype == "session.start":
                        session_id = data.get("sessionId") or session_id
                        created_at = created_at or ts
                        context = data.get("context") or {}
                        if isinstance(context, dict):
                            cwd = context.get("cwd") or cwd
                            git_root = context.get("gitRoot") or git_root
                            if isinstance(context.get("repository"), str):
                                repo_from_context = (
                                    context.get("repository") or repo_from_context
                                )
                    elif etype == "tool.execution_start":
                        candidate_paths.extend(
                            _extract_path_candidates(data.get("arguments"))
                        )

                    text = None
                    role = None
                    if etype == "user.message":
                        text = data.get("content") or data.get("transformedContent")
                        role = "user"
                    elif etype == "assistant.message":
                        text = data.get("content")
                        role = "assistant"

                    if not text:
                        continue
                    text = str(text).strip()
                    if not text or text == last_text:
                        continue
                    last_text = text
                    turns.append(
                        {
                            "idx": len(turns),
                            "user": text if role == "user" else "",
                            "assistant": text if role == "assistant" else "",
                            "timestamp": ts,
                        }
                    )
        except OSError:
            pass

        summary = ""
        for t in turns:
            if t.get("user"):
                summary = t["user"].splitlines()[0][:120]
                break
        if not summary:
            summary = file_path.name

        created_str = ""
        if isinstance(created_at, str) and created_at:
            created_str = created_at
        else:
            created_str = utc_iso_from_ts(file_path.stat().st_mtime)

        repository = repo_from_context
        if not repository:
            for maybe_repo_path in (git_root, cwd, *_dedupe_paths(candidate_paths)):
                if not isinstance(maybe_repo_path, str) or not maybe_repo_path:
                    continue
                repository = _detect_repo_for_path(maybe_repo_path)
                if repository:
                    break
        if not repository:
            repository = _local_workspace_label(
                git_root or cwd or next(iter(_dedupe_paths(candidate_paths)), None)
            )

        return {
            "provider": self.provider_id,
            "id_short": short_id(session_id),
            "id_full": session_id,
            "repository": repository or "unknown",
            "branch": "unknown",
            "summary": summary,
            "date": created_str[:10] if created_str else "",
            "created_at": created_str,
            "turns_count": len(turns),
            "files_count": 0,
            "_turns": turns,
            "_path": str(file_path),
        }

    def _state_list_sessions(
        self, repo: str | None, limit: int, days: int | None
    ) -> list[dict]:
        rows = []
        for fp in self._state_files():
            parsed = self._parse_state_session(fp)
            if repo and repo != "all" and parsed.get("repository") != repo:
                continue
            if not is_within_days(parsed.get("created_at"), days):
                continue
            rows.append({k: v for k, v in parsed.items() if not k.startswith("_")})
            if len(rows) >= limit:
                break
        return rows

    def _state_search(
        self, query: str, repo: str | None, limit: int, days: int | None
    ) -> list[dict]:
        q = query.strip().lower()
        if not q:
            return []
        out = []
        for fp in self._state_files():
            parsed = self._parse_state_session(fp)
            if repo and repo != "all" and parsed.get("repository") != repo:
                continue
            if not is_within_days(parsed.get("created_at"), days):
                continue
            for t in parsed.get("_turns", []):
                content = f"{t.get('user', '')}\n{t.get('assistant', '')}".strip()
                if q not in content.lower():
                    continue
                out.append(
                    {
                        "provider": self.provider_id,
                        "session_id": short_id(parsed["id_full"]),
                        "session_id_full": parsed["id_full"],
                        "source_type": "turn",
                        "summary": parsed["summary"],
                        "repository": parsed["repository"],
                        "date": parsed["date"],
                        "content": content[:500],
                    }
                )
                if len(out) >= limit:
                    return out
        return out

    def _state_get_session(
        self, session_id: str, turns: int | None, full: bool
    ) -> dict | None:
        sid = session_id.strip().lower()
        for fp in self._state_files():
            parsed = self._parse_state_session(fp)
            full_id = str(parsed["id_full"]).lower()
            if not (full_id == sid or full_id.startswith(sid)):
                continue
            turn_rows = parsed.get("_turns", [])
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
                "id": parsed["id_full"],
                "repository": parsed["repository"],
                "branch": parsed["branch"],
                "summary": parsed["summary"],
                "created_at": parsed["created_at"],
                "turns_count": len(turn_rows),
                "turns": turn_rows,
                "files": [],
                "refs": [],
                "checkpoints": [],
            }
        return None


_PATH_HINT_KEYS = {
    "path",
    "cwd",
    "filePath",
    "workspaceFolder",
    "dirPath",
    "resourcePath",
    "includePattern",
}


def _extract_path_candidates(obj: object) -> list[str]:
    paths: list[str] = []
    if isinstance(obj, dict):
        for key, value in obj.items():
            if (
                key in _PATH_HINT_KEYS
                and isinstance(value, str)
                and value.strip().startswith(("/", "~"))
            ):
                paths.append(value.strip())
            paths.extend(_extract_path_candidates(value))
    elif isinstance(obj, list):
        for item in obj:
            paths.extend(_extract_path_candidates(item))
    return paths


def _dedupe_paths(paths: list[str]) -> list[str]:
    out: list[str] = []
    seen: set[str] = set()
    for path in paths:
        if path in seen:
            continue
        seen.add(path)
        out.append(path)
    return out


def _detect_repo_for_path(path_str: str) -> str | None:
    path = Path(path_str).expanduser()
    candidate = path if path.is_dir() else path.parent
    return detect_repo_for_cwd(str(candidate))


def _local_workspace_label(path_str: str | None) -> str | None:
    if not path_str:
        return None
    path = Path(path_str).expanduser()
    candidate = path if path.is_dir() else path.parent
    return f"local:{candidate}"
