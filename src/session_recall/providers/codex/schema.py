"""Fixed schema pre-flight for the Codex provider (plan §5).

Single source of truth: the machine-captured profiles JSON. Every fixture,
verifier, and this pre-flight read the same file — never hand-typed columns.

Runs on ALREADY-OPEN connections (§16 Fix 2): this module never opens or
closes a database, so validation and query always share connections.
"""

import json
from pathlib import Path

from ._schema_report import SchemaReport, drift_json, format_drift_human, success_json
from .errors import CodexSchemaDrift

__all__ = [
    "STATE_PROFILE_NAME", "HISTORY_PROFILE_NAME", "USED_TABLES",
    "SchemaReport", "check_schema", "preflight",
    "drift_json", "format_drift_human", "success_json",
]

_PROFILES_PATH = Path(__file__).parent / "verifications" / "captured-profiles.json"
_PROFILES = json.loads(_PROFILES_PATH.read_text())

STATE_PROFILE_NAME = _PROFILES["state"]["profile"]
HISTORY_PROFILE_NAME = _PROFILES["history"]["profile"]

# §19: thread_spawn_edges is deliberately NOT a used table.
USED_TABLES = {
    "state": ("threads", "_sqlx_migrations"),
    "history": ("thread_items", "thread_turns", "_sqlx_migrations"),
}


def _table_info(conn, table: str) -> list:
    rows = conn.execute(f'PRAGMA table_info("{table}")').fetchall()
    return [list(r) for r in rows]


def _diff_columns(side: str, table: str, expected: list, actual: list) -> list:
    """Ordered full-definition comparison with specific messages (§5.1)."""
    if not actual:
        return [f"{side}: missing table {table}"]
    if [list(e) for e in expected] == actual:
        return []
    exp_names = [e[1] for e in expected]
    act_names = [a[1] for a in actual]
    diffs = [f"{side}: {table} missing column {n}"
             for n in exp_names if n not in act_names]
    diffs += [f"{side}: {table} has unexpected column {n}"
              for n in act_names if n not in exp_names]
    exp_by = {e[1]: list(e) for e in expected}
    act_by = {a[1]: a for a in actual}
    for name in exp_names:
        if name in act_by and exp_by[name] != act_by[name]:
            diffs.append(
                f"{side}: {table} column {name} definition changed "
                f"(expected {exp_by[name]}, found {act_by[name]})"
            )
    return diffs or [f"{side}: {table} column order changed"]


def _check_migrations(conn, side: str, ceiling: int, report: SchemaReport):
    failed = conn.execute(
        "SELECT COUNT(*) FROM _sqlx_migrations WHERE success = 0"
    ).fetchone()[0]
    if failed:
        report.differences.append(f"{side}: {failed} failed migration row(s)")
    found = conn.execute(
        "SELECT MAX(version) FROM _sqlx_migrations WHERE success = 1"
    ).fetchone()[0]
    report.found[side] = {"migration": found}
    if found != ceiling:
        report.differences.append(
            f"{side}: migration ceiling {found} != expected {ceiling}"
        )


def _check_json1(conn, side: str, report: SchemaReport):
    try:
        conn.execute("SELECT json_valid('{}')").fetchone()
    except Exception:
        report.differences.append(f"{side}: SQLite JSON1 support unavailable")


def _collect_diagnostics(conn, side: str, used: tuple, report: SchemaReport):
    rows = conn.execute(
        "SELECT type, name FROM sqlite_master "
        "WHERE name NOT LIKE 'sqlite_%' ORDER BY type, name"
    ).fetchall()
    for otype, name in rows:
        if not (otype == "table" and name in used):
            report.diagnostics.append(f"{side}: extra {otype} {name}")


def _check_side(conn, side: str, profile: dict, report: SchemaReport):
    used = USED_TABLES[side]
    for table in used:
        expected = profile["tables"][table]
        report.differences.extend(
            _diff_columns(side, table, expected, _table_info(conn, table))
        )
    if not any("missing table _sqlx_migrations" in d for d in report.differences):
        _check_migrations(conn, side, profile["migration_ceiling"], report)
    _check_json1(conn, side, report)
    _collect_diagnostics(conn, side, used, report)


def check_schema(state_conn, history_conn) -> SchemaReport:
    """Full fixed pre-flight on already-open connections. Never queries rows."""
    report = SchemaReport(expected_profiles={
        "state": STATE_PROFILE_NAME, "history": HISTORY_PROFILE_NAME,
    })
    _check_side(state_conn, "state", _PROFILES["state"], report)
    _check_side(history_conn, "history", _PROFILES["history"], report)
    report.ok = not report.differences
    return report


def preflight(state_conn, history_conn) -> SchemaReport:
    """Gate for every data command: raise CodexSchemaDrift on any drift."""
    report = check_schema(state_conn, history_conn)
    if not report.ok:
        exc = CodexSchemaDrift(
            "Codex storage schema changed; session data was not queried.",
            report.differences,
        )
        exc.report = report
        raise exc
    return report
