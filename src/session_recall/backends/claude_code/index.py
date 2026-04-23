"""Build and query a SQLite FTS5 index over Claude Code session JSONL files."""
from __future__ import annotations
import pathlib
import sqlite3
import sys
import time
from typing import Optional

INDEX_PATH = pathlib.Path.home() / ".claude" / ".sr-index.db"

_DDL_STATEMENTS = [
    """CREATE TABLE IF NOT EXISTS cc_sessions (
        id TEXT PRIMARY KEY,
        cwd TEXT, repository TEXT, branch TEXT,
        summary TEXT, first_seen TEXT, last_seen TEXT,
        turns_count INTEGER, files_count INTEGER, version TEXT
    )""",
    """CREATE TABLE IF NOT EXISTS cc_turns (
        session_id TEXT, turn_index INTEGER,
        user_msg TEXT, assistant_msg TEXT, timestamp TEXT,
        PRIMARY KEY (session_id, turn_index)
    )""",
    """CREATE TABLE IF NOT EXISTS cc_files (
        session_id TEXT, file_path TEXT, tool_name TEXT,
        PRIMARY KEY (session_id, file_path)
    )""",
    "CREATE TABLE IF NOT EXISTS cc_meta (key TEXT PRIMARY KEY, value TEXT)",
    """CREATE VIRTUAL TABLE IF NOT EXISTS cc_search USING fts5(
        session_id UNINDEXED, user_msg, assistant_msg, summary
    )""",
]


def _open(path: pathlib.Path = INDEX_PATH) -> sqlite3.Connection:
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(path))
    conn.row_factory = sqlite3.Row
    for stmt in _DDL_STATEMENTS:
        conn.execute(stmt)
    conn.commit()
    return conn


def _get_meta(conn: sqlite3.Connection, key: str) -> Optional[str]:
    row = conn.execute("SELECT value FROM cc_meta WHERE key=?", (key,)).fetchone()
    return row["value"] if row else None


def _set_meta(conn: sqlite3.Connection, key: str, value: str) -> None:
    conn.execute("INSERT OR REPLACE INTO cc_meta(key,value) VALUES(?,?)", (key, value))


def build_index(*, rebuild: bool = False, verbose: bool = False) -> dict:
    """Incrementally (or fully) index all Claude Code sessions. Returns stats dict."""
    from .detect import list_session_files
    from .reader import parse_session

    conn = _open()
    indexed = 0
    skipped = 0
    errors = 0
    try:
        conn.execute("BEGIN")
        if rebuild:
            conn.execute("DELETE FROM cc_sessions")
            conn.execute("DELETE FROM cc_turns")
            conn.execute("DELETE FROM cc_files")
            conn.execute("DELETE FROM cc_search")

        last_run = _get_meta(conn, "last_run_epoch")
        cutoff_mtime = float(last_run) if (last_run and not rebuild) else 0.0

        files = list_session_files()

        for jf in files:
            try:
                mtime = jf.stat().st_mtime
            except OSError:
                continue
            if mtime <= cutoff_mtime:
                skipped += 1
                continue

            try:
                session = parse_session(jf)
            except OSError as e:
                print(f"warning: cannot read {jf}: {e}", file=sys.stderr)
                errors += 1
                continue
            if not session:
                continue

            sid = session["id"]
            conn.execute(
                "INSERT OR REPLACE INTO cc_sessions VALUES (?,?,?,?,?,?,?,?,?,?)",
                (sid, session["cwd"], session["repository"], session["branch"],
                 session["summary"], session["first_seen"], session["last_seen"],
                 session["turns_count"], session["files_count"], session["version"])
            )
            conn.execute("DELETE FROM cc_turns WHERE session_id=?", (sid,))
            conn.execute("DELETE FROM cc_files WHERE session_id=?", (sid,))
            conn.execute("DELETE FROM cc_search WHERE session_id=?", (sid,))

            for i, turn in enumerate(session.get("turns", [])):
                conn.execute(
                    "INSERT OR REPLACE INTO cc_turns VALUES (?,?,?,?,?)",
                    (sid, i, turn["user"], turn["assistant"], turn["timestamp"])
                )
                conn.execute(
                    "INSERT INTO cc_search(session_id, user_msg, assistant_msg, summary) VALUES (?,?,?,?)",
                    (sid, turn["user"], turn["assistant"], session["summary"])
                )
            for f in session.get("files", []):
                conn.execute(
                    "INSERT OR IGNORE INTO cc_files VALUES (?,?,?)",
                    (sid, f["file_path"], f["tool_name"])
                )
            indexed += 1

        _set_meta(conn, "last_run_epoch", str(time.time()))
        conn.commit()
    except BaseException:
        conn.rollback()
        raise
    finally:
        conn.close()

    return {"indexed": indexed, "skipped": skipped, "errors": errors, "total": indexed + skipped + errors}


def query_sessions(*, repo: Optional[str] = None, limit: int = 10, days: int = 30) -> list[dict]:
    if not INDEX_PATH.exists():
        return []
    conn = _open()
    try:
        days_filter = f"-{days} days"
        if repo and repo != "all":
            rows = conn.execute(
                "SELECT * FROM cc_sessions WHERE repository=? AND last_seen >= datetime('now',?) ORDER BY last_seen DESC LIMIT ?",
                (repo, days_filter, limit)
            ).fetchall()
        else:
            rows = conn.execute(
                "SELECT * FROM cc_sessions WHERE last_seen >= datetime('now',?) ORDER BY last_seen DESC LIMIT ?",
                (days_filter, limit)
            ).fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()


def query_files(*, repo: Optional[str] = None, limit: int = 20, days: int = 30) -> list[dict]:
    if not INDEX_PATH.exists():
        return []
    conn = _open()
    try:
        days_filter = f"-{days} days"
        if repo and repo != "all":
            rows = conn.execute(
                """SELECT f.file_path, f.tool_name, s.last_seen, s.id as session_id, s.repository
                   FROM cc_files f JOIN cc_sessions s ON s.id=f.session_id
                   WHERE s.repository=? AND s.last_seen >= datetime('now',?)
                   ORDER BY s.last_seen DESC LIMIT ?""",
                (repo, days_filter, limit)
            ).fetchall()
        else:
            rows = conn.execute(
                """SELECT f.file_path, f.tool_name, s.last_seen, s.id as session_id, s.repository
                   FROM cc_files f JOIN cc_sessions s ON s.id=f.session_id
                   WHERE s.last_seen >= datetime('now',?)
                   ORDER BY s.last_seen DESC LIMIT ?""",
                (days_filter, limit)
            ).fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()


def query_search(query: str, *, repo: Optional[str] = None, limit: int = 10, days: int = 30) -> list[dict]:
    if not INDEX_PATH.exists():
        return []
    safe_q = query.replace('"', '""')
    conn = _open()
    days_filter = f"-{days} days"
    try:
        if repo and repo != "all":
            rows = conn.execute(
                """SELECT cs.session_id, cs.user_msg, cs.summary, s.repository, s.branch, s.last_seen
                   FROM cc_search cs JOIN cc_sessions s ON s.id=cs.session_id
                   WHERE cc_search MATCH ? AND s.repository=? AND s.last_seen >= datetime('now',?)
                   ORDER BY rank LIMIT ?""",
                (safe_q, repo, days_filter, limit)
            ).fetchall()
        else:
            rows = conn.execute(
                """SELECT cs.session_id, cs.user_msg, cs.summary, s.repository, s.branch, s.last_seen
                   FROM cc_search cs JOIN cc_sessions s ON s.id=cs.session_id
                   WHERE cc_search MATCH ? AND s.last_seen >= datetime('now',?)
                   ORDER BY rank LIMIT ?""",
                (safe_q, days_filter, limit)
            ).fetchall()
        return [dict(r) for r in rows]
    except sqlite3.OperationalError as e:
        msg = str(e).lower()
        if "fts5" in msg or "syntax" in msg or "no such table" in msg:
            # bad query or schema issue — surface it so caller knows results are empty due to error
            print(f"warning: search error: {e}", file=sys.stderr)
            return []
        raise
    finally:
        conn.close()


def query_show(session_id: str, *, turns: Optional[int] = None) -> Optional[dict]:
    if not INDEX_PATH.exists():
        return None
    conn = _open()
    try:
        row = conn.execute(
            "SELECT * FROM cc_sessions WHERE id LIKE ? LIMIT 1",
            (session_id + "%",)
        ).fetchone()
        if not row:
            return None
        sid = row["id"]
        if turns is not None:
            turn_rows = conn.execute(
                "SELECT * FROM cc_turns WHERE session_id=? ORDER BY turn_index LIMIT ?",
                (sid, turns)
            ).fetchall()
        else:
            turn_rows = conn.execute(
                "SELECT * FROM cc_turns WHERE session_id=? ORDER BY turn_index",
                (sid,)
            ).fetchall()
        file_rows = conn.execute(
            "SELECT file_path, tool_name FROM cc_files WHERE session_id=?", (sid,)
        ).fetchall()
        return {
            **dict(row),
            "turns": [dict(t) for t in turn_rows],
            "files": [dict(f) for f in file_rows],
        }
    finally:
        conn.close()
