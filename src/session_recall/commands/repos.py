"""Summarize discovered repositories/workspaces from session history."""

from __future__ import annotations

import sys

from ..config import DB_PATH
from ..providers.discovery import get_active_providers
from ..util.format_output import output


def _print_human(rows: list[dict]) -> None:
    if not rows:
        print("No repositories discovered.")
        return
    print(
        f"{'Repository/Workspace':42s}  {'Sessions':>8s}  {'Last Seen':10s}  Providers"
    )
    print("-" * 90)
    for row in rows:
        name = str(row.get("repository") or "unknown")[:42]
        count = str(row.get("session_count") or 0)
        last = str(row.get("last_seen") or "")[:10]
        providers = ",".join(row.get("providers") or [])
        print(f"{name:42s}  {count:>8s}  {last:10s}  {providers}")


def run(args) -> int:
    limit = getattr(args, "limit", None) or 500
    days = getattr(args, "days", None) or 30
    include_local = bool(getattr(args, "include_local", False))

    try:
        providers = get_active_providers(
            getattr(args, "provider", "all"), db_path=DB_PATH
        )
    except ValueError as e:
        print(f"error: {e}", file=sys.stderr)
        return 2

    sessions: list[dict] = []
    for provider in providers:
        sessions.extend(provider.list_sessions(repo="all", limit=limit, days=days))

    buckets: dict[str, dict] = {}
    for sess in sessions:
        repo = str(sess.get("repository") or "unknown")
        created = str(sess.get("created_at") or "")
        provider = str(sess.get("provider") or "unknown")

        row = buckets.get(repo)
        if row is None:
            row = {
                "repository": repo,
                "session_count": 0,
                "last_seen": created,
                "providers": set(),
            }
            buckets[repo] = row
        row["session_count"] += 1
        if created > str(row["last_seen"] or ""):
            row["last_seen"] = created
        row["providers"].add(provider)

    rows = list(buckets.values())
    if not include_local:
        rows = [
            r for r in rows if not str(r.get("repository") or "").startswith("local:")
        ]
    rows.sort(
        key=lambda r: (-int(r["session_count"]), str(r["last_seen"] or "")),
        reverse=False,
    )
    for row in rows:
        row["providers"] = sorted(row["providers"])

    payload = {
        "count": len(rows),
        "days": days,
        "include_local": include_local,
        "repositories": rows,
    }

    if getattr(args, "json", False):
        output(payload, json_mode=True)
    else:
        _print_human(rows)
    return 0
