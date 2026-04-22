"""List recently touched files with session attribution."""

import sys
from ..config import DB_PATH
from ..providers.discovery import get_active_providers
from ..util.detect_repo import detect_repo
from ..util.format_output import output


def run(args) -> int:
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
            for p in problems:
                print(f"   - {p}", file=sys.stderr)
            return 2

    repo = getattr(args, "repo", None) or detect_repo()
    limit = getattr(args, "limit", None) or 10
    days = getattr(args, "days", None)
    files = []
    for provider in providers:
        files.extend(provider.recent_files(repo=repo, limit=limit, days=days))

    files = sorted(files, key=lambda f: f.get("date") or "", reverse=True)[:limit]
    output(
        {"repo": repo or "all", "count": len(files), "files": files},
        json_mode=getattr(args, "json", False),
    )
    return 0
