"""Sidecar entry point for pre-warming the Claude Code FTS5 index.

Usage:
    python -m session_recall.providers.claude_code.sidecar --once
    python -m session_recall.providers.claude_code.sidecar --watch 300
"""
from __future__ import annotations

import argparse
import sys
import time


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Pre-warm the Claude Code session index.",
    )
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument(
        "--once", action="store_true", help="Single indexing pass, then exit."
    )
    group.add_argument(
        "--watch", type=int, metavar="SECS", help="Re-index every SECS seconds."
    )
    parser.add_argument("--rebuild", action="store_true", help="Force full rebuild.")
    parser.add_argument("--verbose", action="store_true", help="Print indexing stats.")
    args = parser.parse_args(argv)

    from .index import build_index

    if args.once:
        stats = build_index(rebuild=args.rebuild, verbose=args.verbose)
        if args.verbose:
            print(
                f"indexed={stats['indexed']}"
                f" skipped={stats['skipped']}"
                f" errors={stats['errors']}"
            )
        return 0

    # --watch mode
    while True:
        try:
            stats = build_index(rebuild=False, verbose=args.verbose)
            if args.verbose:
                print(
                    f"indexed={stats['indexed']}"
                    f" skipped={stats['skipped']}"
                    f" errors={stats['errors']}"
                )
        except Exception as exc:
            print(f"error: {exc}", file=sys.stderr)
        time.sleep(args.watch)


if __name__ == "__main__":
    raise SystemExit(main())
