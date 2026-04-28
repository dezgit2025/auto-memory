"""Full-text search across session turns and summaries."""

import re
import sys

from ..config import DB_PATH
from ..providers.discovery import get_active_providers
from ..util.detect_repo import detect_repo
from ..util.format_output import output
from ._lookback import resolve_days

# FTS5 special chars that cause syntax errors when unquoted
_FTS5_SPECIAL = re.compile(r'[.\-(){}[\]^~*:"+/\\@#$%&!?<>=|]')


def sanitize_fts5_query(raw: str) -> str | None:
    """Escape FTS5 special characters and add prefix matching.

    Returns None for empty/whitespace-only queries.
    Strategy: split on whitespace, quote each token that contains
    special chars, append * for prefix matching on every token.
    """
    stripped = raw.strip()
    if not stripped:
        return None
    tokens = stripped.split()
    safe_tokens = []
    for tok in tokens:
        escaped = tok.replace('"', '""')
        if _FTS5_SPECIAL.search(tok):
            safe_tokens.append(f'"{escaped}"')
        else:
            safe_tokens.append(f"{escaped}*")
    return " ".join(safe_tokens)


def run(args) -> int:
    raw_query = args.query
    repo = getattr(args, "repo", None) or detect_repo()
    limit = getattr(args, "limit", None) or 5
    user_days = getattr(args, "days", None)

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

    fts_query = sanitize_fts5_query(raw_query)
    if fts_query is None:
        data = {
            "query": raw_query,
            "repo": repo or "all",
            "count": 0,
            "results": [],
            "warning": "Empty query — nothing to search",
        }
        output(data, json_mode=getattr(args, "json", False))
        return 0

    results = []
    for provider in providers:
        effective_days = resolve_days(user_days, provider)
        results.extend(provider.search(raw_query, repo=repo, limit=limit, days=effective_days))

    scope = repo or "all"
    if not results and repo and repo != "all":
        for provider in providers:
            effective_days = resolve_days(user_days, provider)
            results.extend(
                provider.search(raw_query, repo="all", limit=limit, days=effective_days)
            )
        scope = "all"

    results = sorted(results, key=lambda r: r.get("date") or "", reverse=True)[:limit]

    # Strip provider field when single-provider (reduces token overhead)
    _provider_ids = {r.get("provider") for r in results if "provider" in r}
    if len(_provider_ids) <= 1:
        for r in results:
            r.pop("provider", None)

    data = {
        "query": raw_query,
        "repo": scope,
        "count": len(results),
        "results": results,
    }
    output(data, json_mode=getattr(args, "json", False))
    return 0
