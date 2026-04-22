"""Health check orchestrator — run all 9 dimensions and report."""

import sys
from pathlib import Path
from ..health.scoring import overall_score
from ..health import (
    dim_freshness,
    dim_schema,
    dim_latency,
    dim_corpus,
    dim_summary_coverage,
    dim_repo_coverage,
    dim_concurrency,
    dim_e2e,
    dim_disclosure,
)
from ..config import DB_PATH
from ..providers.discovery import get_active_providers
from ..util.format_output import fmt_json

DIMS = [
    dim_freshness,
    dim_schema,
    dim_latency,
    dim_corpus,
    dim_summary_coverage,
    dim_repo_coverage,
    dim_concurrency,
    dim_e2e,
    dim_disclosure,
]

ZONE_ICON = {"GREEN": "🟢", "AMBER": "🟡", "RED": "🔴"}
ZONE_ICON["CALIBRATING"] = "⚪"


def _provider_dim(provider) -> dict:
    """Compute a lightweight health dimension for a provider backend."""
    sessions = provider.list_sessions(repo="all", limit=20, days=30)
    count = len(sessions)
    if count > 0:
        return {
            "name": f"Provider:{provider.provider_id}",
            "zone": "GREEN",
            "score": 10.0,
            "detail": f"{count} recent sessions detected",
            "hint": "",
        }
    return {
        "name": f"Provider:{provider.provider_id}",
        "zone": "AMBER",
        "score": 5.0,
        "detail": "Provider available, but no recent sessions found",
        "hint": f"Open/use {provider.provider_name} and retry health.",
    }


def run(args) -> int:
    provider_arg = getattr(args, "provider", "all")
    try:
        providers = get_active_providers(provider_arg, DB_PATH)
    except ValueError as e:
        print(f"error: {e}", file=sys.stderr)
        return 2

    has_sqlite = Path(DB_PATH).exists() and any(
        p.provider_id == "cli" for p in providers
    )
    results = [d.check() for d in DIMS] if has_sqlite else []

    if not has_sqlite:
        results.append(
            {
                "name": "SQLite Health Core",
                "zone": "CALIBRATING",
                "score": None,
                "detail": "session-store.db unavailable; running provider compatibility health",
                "hint": "Set SESSION_RECALL_DB if SQLite storage exists on this machine.",
            }
        )

    for provider in providers:
        results.append(_provider_dim(provider))

    score = overall_score(results)
    hints = [r["hint"] for r in results if r["zone"] != "GREEN" and r.get("hint")]

    if getattr(args, "json", False):
        print(
            fmt_json(
                {
                    "overall_score": score,
                    "dims": results,
                    "providers": [p.provider_id for p in providers],
                    "storage_mode": "sqlite" if has_sqlite else "provider-fallback",
                    "top_hints": hints[:3],
                }
            )
        )
    else:
        print(f"\n{'Dim':<3s} {'Name':<22s} {'Zone':<8s} {'Score':>5s}  Detail")
        print("-" * 70)
        for i, r in enumerate(results, 1):
            icon = ZONE_ICON.get(r["zone"], "?")
            score_str = f"{r['score']:5.1f}" if r.get("score") is not None else "  -  "
            print(
                f" {i:<2d} {r['name']:<22s} {icon} {r['zone']:<5s} {score_str}  {r['detail']}"
            )
        print("-" * 70)
        print(f"    {'Overall':<22s}        {score:5.1f}")
        if hints:
            print(f"\n💡 Hints:")
            for h in hints[:3]:
                print(f"   • {h}")
        print()
    return 0
