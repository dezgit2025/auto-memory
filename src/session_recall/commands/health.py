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
from ..health.dim_provider import check_provider_health
from ..config import DB_PATH, ENABLE_FILE_BACKENDS
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


def run(args) -> int:
    provider_arg = getattr(args, "provider", "all")

    # Helpful error when file backends not enabled
    if provider_arg in {"vscode", "jetbrains", "neovim"} and not ENABLE_FILE_BACKENDS:
        msg = (
            f"error: {provider_arg} provider is not enabled.\n\n"
            "To enable: export SESSION_RECALL_ENABLE_FILE_BACKENDS=1\n"
            "See: deploy/install-other-backends.md"
        )
        print(msg, file=sys.stderr)
        return 2

    try:
        providers = get_active_providers(provider_arg, DB_PATH)
    except ValueError as e:
        print(f"error: {e}", file=sys.stderr)
        return 2

    has_sqlite = Path(DB_PATH).exists() and any(
        p.provider_id == "cli" for p in providers
    )
    sqlite_results = [d.check() for d in DIMS] if has_sqlite else []
    results = list(sqlite_results)

    if not has_sqlite:
        calibrating = {
            "name": "SQLite Health Core",
            "zone": "CALIBRATING",
            "score": None,
            "detail": "session-store.db unavailable; running provider compatibility health",
            "hint": "Set SESSION_RECALL_DB if SQLite storage exists on this machine.",
        }
        results.append(calibrating)
        sqlite_results.append(calibrating)

    # Collect per-provider health dims
    provider_health: dict[str, dict] = {}
    for provider in providers:
        provider_dims = check_provider_health(provider)
        results.extend(provider_dims)
        # Backward-compat summary dim (keeps "Provider:<id>" in dims list)
        scores = [d["score"] for d in provider_dims if d.get("score") is not None]
        min_score = min(scores) if scores else 0.0
        zone = "GREEN" if min_score >= 7 else "AMBER" if min_score >= 4 else "RED"
        results.append({
            "name": f"Provider:{provider.provider_id}",
            "zone": zone,
            "score": min_score,
            "detail": f"{len(provider_dims)} sub-checks completed",
        })
        avail_fn = getattr(provider, "is_available", None)
        provider_health[provider.provider_id] = {
            "provider_name": provider.provider_name,
            "available": avail_fn() if avail_fn else True,
            "dimensions": provider_dims,
        }

    score = overall_score(results)
    hints = [r["hint"] for r in results if r["zone"] != "GREEN" and r.get("hint")]

    if getattr(args, "json", False):
        print(
            fmt_json(
                {
                    "overall_score": score,
                    "dims": results,
                    "dimensions": results,
                    "providers": provider_health,
                    "storage_mode": "sqlite" if has_sqlite else "provider-fallback",
                    "top_hints": hints[:3],
                }
            )
        )
    else:
        print(f"\n{'Dim':<3s} {'Name':<22s} {'Zone':<8s} {'Score':>5s}  Detail")
        print("-" * 70)
        num = 0
        for r in sqlite_results:
            num += 1
            icon = ZONE_ICON.get(r["zone"], "?")
            score_str = f"{r['score']:5.1f}" if r.get("score") is not None else "  -  "
            print(
                f" {num:<2d} {r['name']:<22s} {icon} {r['zone']:<5s} {score_str}  {r['detail']}"
            )
        for provider in providers:
            pdims = provider_health[provider.provider_id]["dimensions"]
            num += 1
            print(f" {num:<2d} Provider:{provider.provider_id}")
            for j, d in enumerate(pdims):
                tree = "└─" if j == len(pdims) - 1 else "├─"
                icon = ZONE_ICON.get(d["zone"], "?")
                score_str = f"{d['score']:5.1f}"
                print(
                    f"      {tree} {d['name']:<18s} {icon} {d['zone']:<5s} {score_str}  {d['detail']}"
                )
        print("-" * 70)
        print(f"    {'Overall':<22s}        {score:5.1f}")
        if hints:
            print("\n💡 Hints:")
            for h in hints[:3]:
                print(f"   • {h}")
        print()
    return 0
