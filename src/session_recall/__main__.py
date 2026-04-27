"""auto-memory CLI — progressive session disclosure for Copilot CLI."""
import argparse
import sys
import time

from .config import TELEMETRY_PATH
from .util import telemetry


def _non_negative_int(v):
    """Argparse type: non-negative integer."""
    i = int(v)
    if i < 0:
        raise argparse.ArgumentTypeError(f"must be >= 0, got {v}")
    return i


TIER_MAP = {
    "list": 1, "files": 1, "checkpoints": 1,   # Tier 1 — cheap scan
    "search": 2,                                  # Tier 2 — focused search
    "show": 3,                                    # Tier 3 — deep dive
    "export": 3,                                  # Tier 3 — export sessions
    "health": 0, "schema-check": 0,              # Tier 0 — meta/ops
    "calibrate": 0,                               # Tier 0 — meta (Phase 4)
    "cc-index": 0,                                # Tier 0 — Claude Code index
    "install-mode": 0,                            # Tier 0 — install/hook setup
    "prune": 0,                                   # Tier 0 — prune old index entries
    "serve": 0,                                   # Tier 0 — MCP stdio server
}

# Commands that route through the Copilot-only SQLite command modules when
# a non-copilot backend is not explicitly selected.
_NON_COPILOT_BACKENDS = ("claude", "aider", "cursor", "all", None)


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="auto-memory", description="Query Copilot CLI session history")
    parser.add_argument("--backend", choices=["copilot", "claude", "aider", "cursor", "all"], default=None,
                        help="Session backend (default: auto-detect)")
    sub = parser.add_subparsers(dest="command")

    p_list = sub.add_parser("list", help="Recent sessions")
    p_list.add_argument("--repo", default=None)
    p_list.add_argument("--limit", type=int, default=None)
    p_list.add_argument("--days", type=int, default=None, help="Only include sessions from last N days (default 30)")
    p_list.add_argument("--json", action="store_true")

    p_schema = sub.add_parser("schema-check", help="Validate DB schema")
    p_schema.add_argument("--json", action="store_true")

    p_files = sub.add_parser("files", help="Recently touched files")
    p_files.add_argument("--json", action="store_true")
    p_files.add_argument("--repo", default=None)
    p_files.add_argument("--limit", type=int, default=None)
    p_files.add_argument("--days", type=int, default=None, help="Only include files from last N days")

    p_cp = sub.add_parser("checkpoints", help="Recent checkpoints")
    p_cp.add_argument("--json", action="store_true")
    p_cp.add_argument("--repo", default=None)
    p_cp.add_argument("--limit", type=int, default=None)
    p_cp.add_argument("--days", type=int, default=None, help="Only include checkpoints from last N days")

    p_show = sub.add_parser("show", help="Show session details")
    p_show.add_argument("session_id")
    p_show.add_argument("--json", action="store_true")
    p_show.add_argument("--turns", type=_non_negative_int, default=None)
    p_show.add_argument("--full", action="store_true")

    p_search = sub.add_parser("search", help="Full-text search")
    p_search.add_argument("query")
    p_search.add_argument("--json", action="store_true")
    p_search.add_argument("--repo", default=None)
    p_search.add_argument("--limit", type=int, default=None)
    p_search.add_argument("--days", type=int, default=None, help="Only include sessions from last N days")

    p_health = sub.add_parser("health", help="Health check (9 dimensions)")
    p_health.add_argument("--json", action="store_true")

    p_cci = sub.add_parser("cc-index", help="Build/update Claude Code session index")
    p_cci.add_argument("--rebuild", action="store_true")
    p_cci.add_argument("--status", action="store_true")

    p_im = sub.add_parser("install-mode", help="Detect Claude Code surfaces and configure hooks")
    p_im.add_argument("--setup", action="store_true")
    p_im.add_argument("--dry-run", action="store_true")
    p_im.add_argument("--project", action="store_true",
                      help="Write session-recall block into CLAUDE.md in current directory")
    p_im.add_argument("--project-path", default=None,
                      help="Path to CLAUDE.md (default: ./CLAUDE.md)")
    p_im.add_argument("--mcp", action="store_true",
                      help="Wire MCP server into claude_desktop_config.json")

    p_exp = sub.add_parser("export", help="Export sessions to markdown or JSON")
    p_exp.add_argument("--format", choices=["md", "json"], default="md")
    p_exp.add_argument("--output", default=None, help="Output file (default: stdout)")
    p_exp.add_argument("--session", default=None, help="Specific session ID to export")
    p_exp.add_argument("--repo", default=None)
    p_exp.add_argument("--days", type=int, default=30)
    p_exp.add_argument("--limit", type=int, default=20)
    p_exp.add_argument("--backend", default=None)  # local override (not the global flag)

    p_prune = sub.add_parser("prune", help="Remove old sessions from the Claude Code index")
    p_prune.add_argument("--days", type=int, default=90,
                         help="Remove sessions not seen in last N days (default: 90)")
    p_prune.add_argument("--dry-run", action="store_true")
    p_prune.add_argument("--json", action="store_true")

    sub.add_parser("serve", help="Start MCP tool server (stdio)")

    return parser


def _run_backend_command(args, backend_name) -> int:
    """Handle commands that fan out to a non-copilot backend (or 'all')."""
    from .backends import get_backend
    from .util.format_output import output

    b = get_backend(backend_name)
    json_mode = getattr(args, "json", False)
    repo = getattr(args, "repo", None)

    if args.command == "list":
        data = b.list_sessions(
            repo=repo,
            limit=getattr(args, "limit", None) or 10,
            days=getattr(args, "days", None) or 30,
        )
        output({"repo": repo or "all", "count": len(data), "sessions": data}, json_mode=json_mode)
        return 0

    if args.command == "files":
        data = b.list_files(
            repo=repo,
            limit=getattr(args, "limit", None) or 20,
            days=getattr(args, "days", None) or 30,
        )
        output({"repo": repo or "all", "count": len(data), "files": data}, json_mode=json_mode)
        return 0

    if args.command == "show":
        result = b.show_session(args.session_id, turns=getattr(args, "turns", None))
        if result is None:
            print("session not found", file=sys.stderr)
            return 1
        output(result, json_mode=json_mode)
        return 0

    if args.command == "search":
        data = b.search(
            args.query,
            repo=repo,
            limit=getattr(args, "limit", None) or 10,
            days=getattr(args, "days", None) or 30,
        )
        output({"query": args.query, "count": len(data), "results": data}, json_mode=json_mode)
        return 0

    if args.command == "health":
        output(b.health(), json_mode=json_mode)
        return 0

    # schema-check / checkpoints are not available on non-copilot backends.
    print(f"'{args.command}' is not available for the {backend_name} backend.", file=sys.stderr)
    return 1


def _dispatch(args) -> int:
    """Dispatch to the appropriate command module; returns exit code."""
    backend_name = getattr(args, "backend", None)
    cmd = args.command

    # Commands that may be served by non-copilot backends (or 'all').
    _backend_aware = {"list", "schema-check", "files", "checkpoints", "show", "search", "health"}
    if cmd in _backend_aware and backend_name in _NON_COPILOT_BACKENDS:
        return _run_backend_command(args, backend_name)

    # Copilot-only / meta commands — delegate to dedicated command modules.
    if cmd == "list":
        from .commands.list_sessions import run
        return run(args)
    if cmd == "schema-check":
        from .commands.schema_check_cmd import run
        return run(args)
    if cmd == "files":
        from .commands.files import run
        return run(args)
    if cmd == "checkpoints":
        from .commands.checkpoints import run
        return run(args)
    if cmd == "show":
        from .commands.show_session import run
        return run(args)
    if cmd == "search":
        from .commands.search import run
        return run(args)
    if cmd == "health":
        from .commands.health import run
        return run(args)
    if cmd == "cc-index":
        from .commands.index_cc import run
        return run(args)
    if cmd == "install-mode":
        from .commands.install_mode import run
        return run(args)
    if cmd == "export":
        from .commands.export import run
        return run(args)
    if cmd == "prune":
        from .commands.prune import run
        return run(args)
    if cmd == "serve":
        from .commands.serve import run
        return run(args)

    print(f"'{cmd}' not yet implemented. Coming in Phase 2.", file=sys.stderr)
    return 1


def main() -> None:
    telemetry.init(TELEMETRY_PATH)
    t0 = time.monotonic()

    parser = _build_parser()
    args = parser.parse_args()
    if not args.command:
        parser.print_help()
        sys.exit(1)

    exit_code = _dispatch(args)

    duration_ms = int((time.monotonic() - t0) * 1000)
    tier = TIER_MAP.get(args.command)  # None if command unknown
    qhash = None
    sid_prefix = None
    if args.command == "search":
        qhash = telemetry.query_hash(getattr(args, "query", "") or "")
    elif args.command == "show":
        sid = getattr(args, "session_id", "") or ""
        sid_prefix = sid[:8] if sid else None
    telemetry.record(cmd=args.command, duration_ms=duration_ms, exit_code=exit_code,
                     tier=tier, query_hash=qhash, session_id_prefix=sid_prefix,
                     window_tier=None)  # Phase 4 will populate window_tier
    sys.exit(exit_code)


if __name__ == "__main__":
    main()
