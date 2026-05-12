"""Standalone CLI for the Claude Code session-recall backend."""
from __future__ import annotations

import argparse
import json
import sys


def _env_gate() -> None:
    import os

    if os.environ.get("SESSION_RECALL_ENABLE_CLAUDE_BACKEND") != "1":
        print(
            "session-recall-cc requires SESSION_RECALL_ENABLE_CLAUDE_BACKEND=1\n"
            "See: https://github.com/dezgit2025/auto-memory#claude-code",
            file=sys.stderr,
        )
        sys.exit(2)


def _dump(obj: object) -> None:
    print(json.dumps(obj, indent=2, default=str))


def _cmd_list(args: argparse.Namespace) -> int:
    from .provider import ClaudeCodeProvider

    rows = ClaudeCodeProvider().list_sessions(
        repo=args.repo, limit=args.limit, days=args.days,
    )
    if args.json:
        _dump({"count": len(rows), "sessions": rows})
    else:
        for r in rows:
            print(f"{r.get('id', '?')[:12]}  {r.get('last_seen', '')}  {r.get('summary', '')}")
        print(f"\n{len(rows)} session(s)")
    return 0


def _cmd_search(args: argparse.Namespace) -> int:
    from .provider import ClaudeCodeProvider

    rows = ClaudeCodeProvider().search(
        query=args.query, repo=args.repo, limit=args.limit, days=args.days,
    )
    if args.json:
        _dump({"query": args.query, "count": len(rows), "results": rows})
    else:
        for r in rows:
            print(f"{r.get('session_id', '?')[:12]}  {r.get('snippet', '')}")
        print(f"\n{len(rows)} result(s)")
    return 0


def _cmd_files(args: argparse.Namespace) -> int:
    from .provider import ClaudeCodeProvider

    rows = ClaudeCodeProvider().recent_files(
        repo=args.repo, limit=args.limit, days=args.days,
    )
    if args.json:
        _dump({"count": len(rows), "files": rows})
    else:
        for r in rows:
            print(f"{r.get('file_path', '?')}  {r.get('tool_name', '')}  {r.get('last_seen', '')}")
        print(f"\n{len(rows)} file(s)")
    return 0


def _cmd_show(args: argparse.Namespace) -> int:
    from .provider import ClaudeCodeProvider

    result = ClaudeCodeProvider().get_session(
        session_id=args.session_id, turns=args.turns, full=False,
    )
    if result is None:
        print(f"session not found: {args.session_id}", file=sys.stderr)
        return 1
    if args.json:
        _dump(result)
    else:
        print(f"Session: {result.get('id', '?')}")
        print(f"Summary: {result.get('summary', '')}")
        print(f"Repo:    {result.get('repository', '')}")
        print(f"Turns:   {result.get('turns_count', 0)}")
        for t in result.get("turns", []):
            print(f"\n  [{t.get('turn_index', '?')}] User: {t.get('user_msg', '')[:120]}")
            print(f"       Asst: {t.get('assistant_msg', '')[:120]}")
    return 0


def _cmd_health(args: argparse.Namespace) -> int:
    from datetime import datetime, timezone

    from .index import _index_path

    idx = _index_path()
    info: dict = {"index_exists": idx.exists(), "index_path": str(idx)}
    if idx.exists():
        stat = idx.stat()
        info["index_size_bytes"] = stat.st_size
        info["index_mtime"] = datetime.fromtimestamp(
            stat.st_mtime, tz=timezone.utc,
        ).isoformat()
        try:
            import sqlite3

            conn = sqlite3.connect(str(idx))
            try:
                row = conn.execute("SELECT COUNT(*) FROM cc_sessions").fetchone()
                info["sessions"] = row[0] if row else 0
                row = conn.execute(
                    "SELECT COUNT(DISTINCT repository) FROM cc_sessions",
                ).fetchone()
                info["projects"] = row[0] if row else 0
            finally:
                conn.close()
        except Exception:
            info["sessions"] = 0
            info["projects"] = 0
    else:
        info["index_size_bytes"] = 0
        info["index_mtime"] = None
        info["sessions"] = 0
        info["projects"] = 0
    if args.json:
        _dump(info)
    else:
        for k, v in info.items():
            print(f"{k}: {v}")
    return 0


def _cmd_index(args: argparse.Namespace) -> int:
    from .index import build_index

    stats = build_index(rebuild=args.rebuild)
    if args.json:
        _dump(stats)
    else:
        print(
            f"indexed={stats['indexed']}"
            f" skipped={stats['skipped']}"
            f" errors={stats['errors']}"
        )
    return 0


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="session-recall-cc",
        description="Query Claude Code session history",
    )
    sub = parser.add_subparsers(dest="command")

    # list
    p_list = sub.add_parser("list", help="List recent sessions")
    p_list.add_argument("--repo", default=None)
    p_list.add_argument("--limit", type=int, default=10)
    p_list.add_argument("--days", type=int, default=30)
    p_list.add_argument("--json", action="store_true", default=True)

    # search
    p_search = sub.add_parser("search", help="FTS5 search")
    p_search.add_argument("query")
    p_search.add_argument("--repo", default=None)
    p_search.add_argument("--limit", type=int, default=10)
    p_search.add_argument("--days", type=int, default=30)
    p_search.add_argument("--json", action="store_true", default=True)

    # files
    p_files = sub.add_parser("files", help="Recent files")
    p_files.add_argument("--repo", default=None)
    p_files.add_argument("--limit", type=int, default=20)
    p_files.add_argument("--days", type=int, default=30)
    p_files.add_argument("--json", action="store_true", default=True)

    # show
    p_show = sub.add_parser("show", help="Show session detail")
    p_show.add_argument("session_id")
    p_show.add_argument("--turns", type=int, default=None)
    p_show.add_argument("--json", action="store_true", default=True)

    # health
    p_health = sub.add_parser("health", help="Health check")
    p_health.add_argument("--json", action="store_true", default=True)

    # index
    p_index = sub.add_parser("index", help="Manual index management")
    p_index.add_argument("--rebuild", action="store_true")
    p_index.add_argument("--json", action="store_true", default=True)

    return parser


_DISPATCH = {
    "list": _cmd_list,
    "search": _cmd_search,
    "files": _cmd_files,
    "show": _cmd_show,
    "health": _cmd_health,
    "index": _cmd_index,
}


def main(argv: list[str] | None = None) -> None:
    _env_gate()
    parser = _build_parser()
    args = parser.parse_args(argv)
    if not args.command:
        parser.print_help()
        sys.exit(1)
    handler = _DISPATCH.get(args.command)
    if handler is None:
        print(f"unknown command: {args.command}", file=sys.stderr)
        sys.exit(1)
    sys.exit(handler(args))
