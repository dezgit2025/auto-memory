"""Health check orchestrator — run all 9 dimensions and report."""
from ..health.scoring import overall_score
from ..health import (dim_freshness, dim_schema, dim_latency, dim_corpus,
                      dim_summary_coverage, dim_repo_coverage, dim_concurrency,
                      dim_e2e, dim_disclosure)
from ..util.format_output import fmt_json

DIMS = [dim_freshness, dim_schema, dim_latency, dim_corpus,
        dim_summary_coverage, dim_repo_coverage, dim_concurrency, dim_e2e,
        dim_disclosure]

ZONE_ICON = {"GREEN": "🟢", "AMBER": "🟡", "RED": "🔴"}
ZONE_ICON["CALIBRATING"] = "⚪"


def run(args) -> int:
    results = [d.check() for d in DIMS]
    score = overall_score(results)
    hints = [r["hint"] for r in results if r["zone"] != "GREEN" and r.get("hint")]

    if getattr(args, "json", False):
        print(fmt_json({"overall_score": score, "dims": results, "top_hints": hints[:3]}))
    else:
        print(f"\n{'Dim':<3s} {'Name':<22s} {'Zone':<8s} {'Score':>5s}  Detail")
        print("-" * 70)
        for i, r in enumerate(results, 1):
            icon = ZONE_ICON.get(r["zone"], "?")
            score_str = f"{r['score']:5.1f}" if r.get("score") is not None else "  -  "
            print(f" {i:<2d} {r['name']:<22s} {icon} {r['zone']:<5s} {score_str}  {r['detail']}")
        print("-" * 70)
        print(f"    {'Overall':<22s}        {score:5.1f}")
        if hints:
            print("\n💡 Hints:")
            for h in hints[:3]:
                print(f"   • {h}")
        print()
    return 0
