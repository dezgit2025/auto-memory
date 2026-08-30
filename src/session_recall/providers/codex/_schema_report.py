"""Schema pre-flight report container and §5.3 output formatting."""

from dataclasses import dataclass, field

_ACTION = "Update session-recall-codex for the installed Codex schema."
_REVIEW = "The adapter must be reviewed and updated for this Codex version."


@dataclass
class SchemaReport:
    """Result of the fixed schema pre-flight (plan §5.1)."""

    ok: bool = True
    differences: list = field(default_factory=list)
    diagnostics: list = field(default_factory=list)
    expected_profiles: dict = field(default_factory=dict)
    found: dict = field(default_factory=dict)


def _found_line(report: SchemaReport) -> str:
    parts = []
    for side in ("state", "history"):
        info = report.found.get(side, {})
        if "migration" in info:
            parts.append(f"{side} migration {info['migration']}")
    return "; ".join(parts) if parts else "(not determined)"


def format_drift_human(report: SchemaReport) -> str:
    """Human-readable stderr report per plan §5.3."""
    expected = ", ".join(report.expected_profiles.values())
    lines = [
        "error: Codex storage schema changed; session data was not queried.",
        f"expected: {expected}",
        f"found:    {_found_line(report)}",
    ]
    lines.extend(f"difference: {d}" for d in report.differences)
    lines.append("")
    lines.append("Run: session-recall-codex schema-check --json")
    lines.append(_REVIEW)
    return "\n".join(lines)


def drift_json(report: SchemaReport) -> dict:
    """Stable JSON drift object per plan §5.3 — exact key set."""
    return {
        "ok": False,
        "error": "schema_drift",
        "query_executed": False,
        "expected_profiles": dict(report.expected_profiles),
        "differences": list(report.differences),
        "action": _ACTION,
    }


def success_json(report: SchemaReport) -> dict:
    """schema-check success shape (spec.yaml: ok + both profile names)."""
    return {
        "ok": True,
        "profiles": dict(report.expected_profiles),
        "diagnostics": list(report.diagnostics),
    }


def format_diagnostics_human(report: SchemaReport) -> list[str]:
    """Human lines for pass-through diagnostics (schema-check, non-JSON).

    A healthy live store legitimately has dozens of tables/indexes/triggers
    session-recall never touches, so "extra <type>" diagnostics collapse to
    one count line per side. Anything else stays itemized. JSON output
    keeps the full list.
    """
    counts: dict[str, dict[str, int]] = {}
    lines: list[str] = []
    for d in report.diagnostics:
        side, _, rest = d.partition(": ")
        if rest.startswith("extra ") and len(rest.split()) == 3:
            otype = rest.split()[1]
            counts.setdefault(side, {})[otype] = (
                counts.get(side, {}).get(otype, 0) + 1
            )
        else:
            lines.append(f"diagnostic: {d}")
    for side, by_type in counts.items():
        summary = ", ".join(
            f"{n} extra {otype}{'es' if otype.endswith('x') else 's'}"
            for otype, n in sorted(by_type.items())
        )
        lines.append(
            f"diagnostic: {side}: {summary} not used by session-recall "
            "(ignored; see --json for names)"
        )
    return lines
