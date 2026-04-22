"""List recent sessions for the current (or specified) repository."""

import sys

from ..config import DB_PATH
from ..providers.discovery import get_active_providers
from ..util.detect_repo import detect_repo
from ..util.format_output import output


def run(args) -> int:
    """Execute the list subcommand. Returns exit code."""
    repo = args.repo or detect_repo()
    limit = args.limit or 50
    days = args.days or 30
    try:
        providers = get_active_providers(
            getattr(args, "provider", "cli"), db_path=DB_PATH
        )
    except ValueError as e:
        print(f"error: {e}", file=sys.stderr)
        return 2

    cli_providers = [p for p in providers if p.provider_id == "cli"]
    if cli_providers:
        problems = cli_providers[0].schema_problems()
        if problems:
            print("❌ Schema drift:", file=sys.stderr)
            for p in problems:
                print(f"   - {p}", file=sys.stderr)
            return 2

    sessions = []
    recent_files = []
    for provider in providers:
        sessions.extend(provider.list_sessions(repo=repo, limit=limit, days=days))
        recent_files.extend(provider.recent_files(repo=repo, limit=10, days=days))

    scope = repo or "all"
    scope_fallback_used = False
    selected_provider = getattr(args, "provider", "all")
    has_non_cli_provider = any(
        getattr(p, "provider_id", "") != "cli" for p in providers
    )
    allow_cli_topup = selected_provider == "cli" or (
        selected_provider == "all" and has_non_cli_provider
    )
    if repo and repo != "all" and len(sessions) < limit and allow_cli_topup:
        # Some providers cannot always infer repo ownership from raw event logs.
        # Top up from all repos so recall remains useful instead of looking sparse.
        existing_keys = {
            (str(s.get("provider") or ""), str(s.get("id_full") or s.get("id") or ""))
            for s in sessions
        }
        filled = len(sessions)
        added_count = 0
        for provider in providers:
            if getattr(provider, "provider_id", "") != "cli":
                continue
            if filled >= limit:
                break
            candidates = provider.list_sessions(repo="all", limit=limit, days=days)
            for candidate in candidates:
                key = (
                    str(candidate.get("provider") or ""),
                    str(candidate.get("id_full") or candidate.get("id") or ""),
                )
                if key in existing_keys:
                    continue
                sessions.append(candidate)
                existing_keys.add(key)
                filled += 1
                added_count += 1
                if filled >= limit:
                    break
        if added_count > 0:
            scope = "all"
            scope_fallback_used = True

    # Keep scope metadata accurate: if any all-scope top-up happened, scope must be all.
    if scope_fallback_used:
        scope = "all"

    sessions = sorted(
        sessions,
        key=lambda s: s.get("created_at") or "",
        reverse=True,
    )[:limit]
    recent_files = sorted(
        recent_files, key=lambda f: f.get("date") or "", reverse=True
    )[:10]

    data = {
        "repo": scope,
        "count": len(sessions),
        "sessions": sessions,
        "recent_files": recent_files,
        "scope_fallback_used": scope_fallback_used,
    }
    output(data, json_mode=args.json)
    return 0
