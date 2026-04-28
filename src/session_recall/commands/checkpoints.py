"""List recent checkpoints with session context."""

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
    limit = getattr(args, "limit", None) or 5
    days = getattr(args, "days", None)
    checkpoints = []
    for provider in providers:
        checkpoints.extend(provider.list_checkpoints(repo=repo, limit=limit, days=days))
    checkpoints = sorted(checkpoints, key=lambda c: c.get("date") or "", reverse=True)[
        :limit
    ]

    # Strip provider field when single-provider (reduces token overhead)
    _provider_ids = {r.get("provider") for r in checkpoints if "provider" in r}
    if len(_provider_ids) <= 1:
        for r in checkpoints:
            r.pop("provider", None)

    output(
        {"repo": repo or "all", "count": len(checkpoints), "checkpoints": checkpoints},
        json_mode=getattr(args, "json", False),
    )
    return 0
