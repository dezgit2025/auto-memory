"""Standalone trial CLI for the Codex session-recall backend (plan §7, §4).

Trial build (Evidence Gate window): schema-check / list / repos only.
search, show, files, and health arrive in a later phase.

No env gate: invoking the dedicated binary is the opt-in (plan §1,
guardrail 7a pattern (b)).  Each command performs exactly one open per
database; pre-flight and queries share those connections (§16 Fix 2) —
``schema-check`` opens via ``open_codex_ro`` directly, while ``list`` and
``repos`` delegate to ``CodexProvider``, which owns the same contract.
"""

from __future__ import annotations

import argparse
import sys

_TRIAL_NOTE = "Trial build: search/show/files/health arrive in a later phase."


def _cmd_schema_check(args: argparse.Namespace) -> int:
    from .connect import open_codex_ro
    from .paths import resolve_paths
    from .schema import check_schema, drift_json, format_drift_human, success_json
    from .util_out import dump_json

    with open_codex_ro(resolve_paths()) as (state, history):
        report = check_schema(state, history)
    if report.ok:
        if args.json:
            dump_json(success_json(report))
        else:
            profiles = ", ".join(report.expected_profiles.values())
            print(f"ok: schema matches fixed profiles ({profiles})")
            for d in report.diagnostics:
                print(f"diagnostic: {d}")
        return 0
    if args.json:
        dump_json(drift_json(report))
    else:
        print(format_drift_human(report), file=sys.stderr)
    return 2


def _cmd_list(args: argparse.Namespace) -> int:
    from ...util.format_output import output
    from .provider import CodexProvider

    rows = CodexProvider().list_sessions(
        repo=args.repo,
        limit=args.limit,
        days=args.days,
        include_archived=args.include_archived,
    )
    output(rows, json_mode=args.json)
    return 0


def _cmd_repos(args: argparse.Namespace) -> int:
    from .provider import CodexProvider
    from .util_out import dump_json

    rows = CodexProvider().list_repos(
        limit=args.limit, days=args.days, include_local=args.include_local
    )
    if args.json:
        dump_json({"count": len(rows), "repos": rows})
    else:
        from ...util.format_output import sanitize_for_terminal

        for r in rows:
            print(
                f"{r['session_count']:>4}  {r['last_seen'][:10]}  "
                f"{sanitize_for_terminal(r['repository'])}"
            )
        print(f"\n{len(rows)} repository(ies)")
    return 0


def _handle(args: argparse.Namespace, fn) -> int:
    """Map CodexError subclasses to their §4.4 exit codes and output shapes."""
    from ._schema_report import drift_json, format_drift_human
    from .errors import CodexError, CodexSchemaDrift, CodexStorageMissing
    from .util_out import dump_json

    try:
        return fn(args)
    except CodexSchemaDrift as e:
        report = getattr(e, "report", None)
        if args.json and report is not None:
            dump_json(drift_json(report))
        elif report is not None:
            print(format_drift_human(report), file=sys.stderr)
        else:
            print(f"error: {e.message}", file=sys.stderr)
        return e.exit_code
    except CodexStorageMissing as e:
        if args.json:
            dump_json(
                {
                    "ok": False,
                    "error": e.code,
                    "query_executed": False,
                    "found": e.found,
                    "message": e.message,
                }
            )
        else:
            print(f"error: {e.message}", file=sys.stderr)
        return e.exit_code
    except CodexError as e:
        print(f"error: {e.message}", file=sys.stderr)
        return e.exit_code


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="session-recall-codex",
        description="Read-only recall over Codex CLI session history",
        epilog=_TRIAL_NOTE,
    )
    parser.add_argument("--version", action="store_true", help="print version")
    sub = parser.add_subparsers(dest="command")

    p_check = sub.add_parser(
        "schema-check", help="Validate Codex storage against the fixed profiles"
    )
    p_check.add_argument("--json", action="store_true")

    p_list = sub.add_parser("list", help="List recent Codex sessions")
    p_list.add_argument("--repo", default=None)
    p_list.add_argument("--limit", type=int, default=10)
    p_list.add_argument("--days", type=int, default=30)
    p_list.add_argument("--include-archived", action="store_true")
    p_list.add_argument("--json", action="store_true")

    p_repos = sub.add_parser("repos", help="Aggregate repositories")
    p_repos.add_argument("--limit", type=int, default=10)
    p_repos.add_argument("--days", type=int, default=30)
    p_repos.add_argument("--include-local", action="store_true")
    p_repos.add_argument("--json", action="store_true")

    return parser


_DISPATCH = {
    "schema-check": _cmd_schema_check,
    "list": _cmd_list,
    "repos": _cmd_repos,
}


def main(argv: list[str] | None = None) -> None:
    parser = _build_parser()
    args = parser.parse_args(argv)
    if args.version:
        from ... import __version__

        print(__version__)
        sys.exit(0)
    if not args.command:
        parser.print_help()
        sys.exit(1)
    try:
        sys.exit(_handle(args, _DISPATCH[args.command]))
    except KeyboardInterrupt:
        print("interrupted", file=sys.stderr)
        sys.exit(130)
