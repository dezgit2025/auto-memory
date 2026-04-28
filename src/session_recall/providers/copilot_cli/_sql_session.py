"""SQLite session detail query for Copilot CLI provider."""

from __future__ import annotations

import sqlite3


def sql_get_session(
    conn: sqlite3.Connection,
    provider_id: str,
    session_id: str,
    turns: int | None,
    full: bool,
) -> dict | None:
    sid = session_id.lower()
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
        "provider": provider_id,
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
        "_trust_level": "trusted_first_party",
    }
