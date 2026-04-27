"""prune command — remove old sessions from the Claude Code index."""
import sys

from ..util.format_output import output


def run(args) -> int:
    try:
        from ..backends.claude_code import index as idx_mod
    except ImportError as e:
        print(f"error: Claude Code backend unavailable: {e}", file=sys.stderr)
        return 1

    if not idx_mod.INDEX_PATH.exists():
        print("error: index not found — run cc-index first", file=sys.stderr)
        return 1

    days = getattr(args, "days", 90) or 90
    dry_run = getattr(args, "dry_run", False)
    json_mode = getattr(args, "json", False)
    cutoff = f"-{days} days"

    count = _prune(idx_mod, cutoff, dry_run)

    data = {
        "days": days,
        "removed": 0 if dry_run else count,
        "would_remove": count if dry_run else None,
        "dry_run": dry_run,
    }
    if not json_mode:
        print(_status_message(count, days, dry_run))
    output(data, json_mode=json_mode)
    return 0


def _prune(idx_mod, cutoff: str, dry_run: bool) -> int:
    """Delete sessions older than cutoff; return the count of matched sessions."""
    conn = idx_mod._open()
    try:
        row = conn.execute(
            "SELECT COUNT(*) FROM cc_sessions WHERE last_seen < datetime('now', ?)",
            (cutoff,),
        ).fetchone()
        count = row[0] if row else 0

        if dry_run or count == 0:
            return count

        old_ids_subquery = (
            "SELECT id FROM cc_sessions WHERE last_seen < datetime('now', ?)"
        )
        conn.execute("BEGIN")
        try:
            for table in ("cc_turns", "cc_files", "cc_search"):
                conn.execute(
                    f"DELETE FROM {table} WHERE session_id IN ({old_ids_subquery})",
                    (cutoff,),
                )
            conn.execute(
                "DELETE FROM cc_sessions WHERE last_seen < datetime('now', ?)",
                (cutoff,),
            )
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        return count
    finally:
        conn.close()


def _status_message(count: int, days: int, dry_run: bool) -> str:
    if dry_run:
        return f"[dry-run] Would remove {count} session(s) older than {days} days"
    if count == 0:
        return f"Nothing to prune (no sessions older than {days} days)"
    return f"Pruned {count} session(s) older than {days} days"
