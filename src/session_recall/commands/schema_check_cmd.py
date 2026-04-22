"""Schema-check subcommand — validates session-store.db structure."""

import sys
from ..config import DB_PATH
from ..providers.discovery import get_active_providers
from ..util.format_output import fmt_json


def run(args) -> int:
    """Execute schema-check across available providers."""
    provider_arg = getattr(args, "provider", "all")
    json_mode = getattr(args, "json", False)
    try:
        providers = get_active_providers(provider_arg, DB_PATH)
    except ValueError as e:
        if json_mode:
            print(fmt_json({"ok": False, "problems": [str(e)], "providers": []}))
        else:
            print(f"error: {e}", file=sys.stderr)
        return 2

    provider_rows = []
    all_problems = []
    for provider in providers:
        problems = provider.schema_problems()
        mode = "sqlite" if provider.provider_id == "cli" else "file"
        row = {
            "provider": provider.provider_id,
            "ok": not problems,
            "mode": mode,
            "problems": problems,
        }
        if provider.provider_id == "cli" and not problems:
            # In session-state fallback mode, schema checks are not applicable.
            row["mode"] = "session-state-or-sqlite"
            row["detail"] = (
                "Schema checks apply to SQLite when present; fallback event storage has no SQL schema."
            )
        provider_rows.append(row)
        for p in problems:
            all_problems.append(f"{provider.provider_id}: {p}")

    ok = len(all_problems) == 0
    if json_mode:
        print(
            fmt_json({"ok": ok, "problems": all_problems, "providers": provider_rows})
        )
        return 0 if ok else 2

    if ok:
        print("✅ Schema checks passed for active provider(s)")
        for row in provider_rows:
            print(f"   - {row['provider']}: OK ({row.get('mode', 'n/a')})")
        return 0

    print("❌ Schema/check compatibility issues detected.", file=sys.stderr)
    for problem in all_problems:
        print(f"   - {problem}", file=sys.stderr)
    return 2
