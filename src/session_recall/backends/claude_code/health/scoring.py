"""Weighted overall score for Claude Code health dimensions."""
from __future__ import annotations

_WEIGHTS = {
    "dim_index": 2,
    "dim_freshness": 2,
    "dim_corpus": 2,
    "dim_latency": 1,
    "dim_coverage": 1,
    "dim_surfaces": 1,
}


def overall_score(dimensions: list[dict]) -> float:
    """Weighted average. index+freshness+corpus are weighted 2x, others 1x."""
    total_w = 0
    total_s = 0.0
    for d in dimensions:
        w = _WEIGHTS.get(d["name"], 1)
        total_w += w
        total_s += d["score"] * w
    return round(total_s / total_w, 1) if total_w else 0.0


def zone_for_score(score: float) -> str:
    if score >= 8:
        return "GREEN"
    if score >= 5:
        return "AMBER"
    return "RED"
