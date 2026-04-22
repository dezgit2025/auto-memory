"""Show detailed info for a single session."""

import re
import sys
from ..config import DB_PATH
from ..providers.discovery import get_active_providers
from ..util.format_output import output

_SID_RE = re.compile(r"^[0-9a-fA-F-]{4,}$")


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

    sid = args.session_id.strip()
    selected_provider = getattr(args, "provider", "cli")
    cli_like_id = selected_provider == "cli" or ":" not in sid
    if cli_like_id and (not _SID_RE.match(sid) or not sid.replace("-", "")):
        print(
            f"error: invalid session id '{args.session_id}' "
            f"(expected hex, 4+ chars)",
            file=sys.stderr,
        )
        return 2
    sid = sid.lower()
    for provider in providers:
        result = provider.get_session(
            session_id=sid,
            turns=getattr(args, "turns", None),
            full=getattr(args, "full", False),
        )
        if result:
            output(result, json_mode=getattr(args, "json", False))
            return 0
    print(f"No session found matching '{sid}'", file=sys.stderr)
    return 1
