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
    "list": 1,
    "files": 1,
    "checkpoints": 1,  # Tier 1 — cheap scan
    "repos": 1,  # Tier 1 — discovery summary
    "search": 2,  # Tier 2 — focused search
    "show": 3,  # Tier 3 — deep dive
    "health": 0,
    "schema-check": 0,  # Tier 0 — meta/ops
    "calibrate": 0,  # Tier 0 — meta (Phase 4)
}


def main() -> None:
    telemetry.init(TELEMETRY_PATH)
    t0 = time.monotonic()
    parser = argparse.ArgumentParser(
        prog="auto-memory",
        description="Query session history across supported storage providers",
    )
    sub = parser.add_subparsers(dest="command")

    p_list = sub.add_parser("list", help="Recent sessions")
    p_list.add_argument("--repo", default=None)
    p_list.add_argument("--limit", type=int, default=None)
    p_list.add_argument(
        "--days",
        type=int,
        default=None,
        help="Only include sessions from last N days (default 30)",
    )
    p_list.add_argument(
        "--provider",
        choices=["all", "cli", "vscode", "jetbrains", "neovim", "claude_code"],
        default="all",
    )
    p_list.add_argument("--json", action="store_true")

    p_schema = sub.add_parser("schema-check", help="Validate storage compatibility")
    p_schema.add_argument("--json", action="store_true")
    p_schema.add_argument(
        "--provider",
        choices=["all", "cli", "vscode", "jetbrains", "neovim", "claude_code"],
        default="all",
    )

    p_files = sub.add_parser("files", help="Recently touched files")
    p_files.add_argument("--json", action="store_true")
    p_files.add_argument("--repo", default=None)
    p_files.add_argument("--limit", type=int, default=None)
    p_files.add_argument(
        "--days", type=int, default=None, help="Only include files from last N days"
    )
    p_files.add_argument(
        "--provider",
        choices=["all", "cli", "vscode", "jetbrains", "neovim", "claude_code"],
        default="all",
    )

    p_cp = sub.add_parser("checkpoints", help="Recent checkpoints")
    p_cp.add_argument("--json", action="store_true")
    p_cp.add_argument("--repo", default=None)
    p_cp.add_argument("--limit", type=int, default=None)
    p_cp.add_argument(
        "--days",
        type=int,
        default=None,
        help="Only include checkpoints from last N days",
    )
    p_cp.add_argument(
        "--provider",
        choices=["all", "cli", "vscode", "jetbrains", "neovim", "claude_code"],
        default="all",
    )

    p_repos = sub.add_parser("repos", help="Discovered repositories/workspaces")
    p_repos.add_argument("--json", action="store_true")
    p_repos.add_argument("--limit", type=int, default=None)
    p_repos.add_argument(
        "--days", type=int, default=None, help="Only include sessions from last N days"
    )
    p_repos.add_argument(
        "--include-local",
        action="store_true",
        help="Include local:* workspace attributions",
    )
    p_repos.add_argument(
        "--provider",
        choices=["all", "cli", "vscode", "jetbrains", "neovim", "claude_code"],
        default="all",
    )

    p_show = sub.add_parser("show", help="Show session details")
    p_show.add_argument("session_id")
    p_show.add_argument("--json", action="store_true")
    p_show.add_argument("--turns", type=_non_negative_int, default=None)
    p_show.add_argument("--full", action="store_true")
    p_show.add_argument(
        "--provider",
        choices=["all", "cli", "vscode", "jetbrains", "neovim", "claude_code"],
        default="all",
    )

    p_search = sub.add_parser("search", help="Full-text search")
    p_search.add_argument("query")
    p_search.add_argument("--json", action="store_true")
    p_search.add_argument("--repo", default=None)
    p_search.add_argument("--limit", type=int, default=None)
    p_search.add_argument(
        "--days", type=int, default=None, help="Only include sessions from last N days"
    )
    p_search.add_argument(
        "--provider",
        choices=["all", "cli", "vscode", "jetbrains", "neovim", "claude_code"],
        default="all",
    )

    p_health = sub.add_parser(
        "health", help="Health check (SQLite core or provider fallback)"
    )
    p_health.add_argument("--json", action="store_true")
    p_health.add_argument(
        "--provider",
        choices=["all", "cli", "vscode", "jetbrains", "neovim", "claude_code"],
        default="all",
    )

    args = parser.parse_args()
    if not args.command:
        parser.print_help()
        sys.exit(1)

    exit_code = 1
    if args.command == "list":
        from .commands.list_sessions import run

        exit_code = run(args)
    elif args.command == "schema-check":
        from .commands.schema_check_cmd import run

        exit_code = run(args)
    elif args.command == "files":
        from .commands.files import run

        exit_code = run(args)
    elif args.command == "checkpoints":
        from .commands.checkpoints import run

        exit_code = run(args)
    elif args.command == "repos":
        from .commands.repos import run

        exit_code = run(args)
    elif args.command == "show":
        from .commands.show_session import run

        exit_code = run(args)
    elif args.command == "search":
        from .commands.search import run

        exit_code = run(args)
    elif args.command == "health":
        from .commands.health import run

        exit_code = run(args)
    else:
        print(
            f"'{args.command}' not yet implemented. Coming in Phase 2.", file=sys.stderr
        )

    duration_ms = int((time.monotonic() - t0) * 1000)
    tier = TIER_MAP.get(args.command)  # None if command unknown
    qhash = None
    sid_prefix = None
    wtier = None  # Phase 4 will populate this
    if args.command == "search":
        qhash = telemetry.query_hash(getattr(args, "query", "") or "")
    elif args.command == "show":
        sid = getattr(args, "session_id", "") or ""
        sid_prefix = sid[:8] if sid else None
    telemetry.record(
        cmd=args.command,
        duration_ms=duration_ms,
        exit_code=exit_code,
        tier=tier,
        query_hash=qhash,
        session_id_prefix=sid_prefix,
        window_tier=wtier,
    )
    sys.exit(exit_code)


if __name__ == "__main__":
    main()
