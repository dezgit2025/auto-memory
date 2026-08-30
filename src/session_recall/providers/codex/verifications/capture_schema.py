"""Read-only capture of the live Codex SQLite schema.

Produces the fixed schema profiles (plan section 5.1) that the codex
pre-flight check is built from.  Never writes to Codex-owned files:
every connection is opened with URI ``mode=ro`` plus
``PRAGMA query_only = ON``.

Usage:
    python3 capture_schema.py            # print capture JSON to stdout
    python3 capture_schema.py --write    # also save captured-profiles.json
    python3 capture_schema.py --check    # compare saved profiles vs live

Exit codes: 0 ok/match, 2 mismatch or bad state, 4 database missing.
"""

import argparse
import json
import os
import re
import sqlite3
import sys
from pathlib import Path

OUT_PATH = Path(__file__).resolve().parent / "captured-profiles.json"

STATE_DB_ENV = "SESSION_RECALL_CODEX_STATE_DB"
HISTORY_DB_ENV = "SESSION_RECALL_CODEX_HISTORY_DB"
DEFAULT_STATE_DB = "~/.codex/state_5.sqlite"
DEFAULT_HISTORY_DB = "~/.codex/thread_history_1.sqlite"

STATE_TABLES = ("threads", "_sqlx_migrations")
HISTORY_TABLES = ("thread_items", "thread_turns", "_sqlx_migrations")


def _resolve(env_var: str, default: str) -> Path:
    return Path(os.environ.get(env_var, default)).expanduser()


def _connect_ro(path: Path) -> sqlite3.Connection:
    if not path.is_file():
        raise FileNotFoundError(str(path))
    conn = sqlite3.connect(f"file:{path}?mode=ro", uri=True, timeout=0.5)
    conn.execute("PRAGMA query_only = ON")
    return conn


def _filename_version(path: Path) -> str:
    m = re.search(r"_(\d+)\.sqlite$", path.name)
    return m.group(1) if m else "0"


def _capture_db(path: Path, tables: tuple, family: str) -> dict:
    """Capture ordered table_info, migration ceiling, and JSON1 support."""
    conn = _connect_ro(path)
    try:
        info = {}
        for table in tables:
            rows = conn.execute(f"PRAGMA table_info({table})").fetchall()
            # Ordered rows: [cid, name, type, notnull, dflt_value, pk]
            info[table] = [list(r) for r in rows]
        row = conn.execute(
            "SELECT MAX(version) FROM _sqlx_migrations WHERE success = 1"
        ).fetchone()
        ceiling = row[0] if row else None
        desc_row = conn.execute(
            "SELECT description FROM _sqlx_migrations WHERE version = ?",
            (ceiling,),
        ).fetchone()
        failed = conn.execute(
            "SELECT COUNT(*) FROM _sqlx_migrations WHERE success = 0"
        ).fetchone()[0]
        json1 = conn.execute("SELECT json_valid('{}')").fetchone()[0]
    finally:
        conn.close()
    version = _filename_version(path)
    return {
        "profile": f"codex-{family}-v{version}-migration-{ceiling}",
        "db_filename": path.name,
        "migration_ceiling": ceiling,
        "migration_description": desc_row[0] if desc_row else None,
        "failed_migrations": failed,
        "json1": bool(json1),
        "tables": info,
    }


def capture_all() -> dict:
    state_path = _resolve(STATE_DB_ENV, DEFAULT_STATE_DB)
    history_path = _resolve(HISTORY_DB_ENV, DEFAULT_HISTORY_DB)
    return {
        "state": _capture_db(state_path, STATE_TABLES, "state"),
        "history": _capture_db(history_path, HISTORY_TABLES, "thread-history"),
    }


def _diff(expected: dict, found: dict, prefix: str = "") -> list:
    """Compare two capture dicts; return human-readable difference lines."""
    diffs = []
    for key in ("state", "history"):
        exp, got = expected.get(key, {}), found.get(key, {})
        for field in ("profile", "db_filename", "migration_ceiling",
                      "migration_description", "failed_migrations", "json1"):
            if exp.get(field) != got.get(field):
                diffs.append(
                    f"{key}.{field}: expected {exp.get(field)!r}, "
                    f"found {got.get(field)!r}"
                )
        exp_tables, got_tables = exp.get("tables", {}), got.get("tables", {})
        for table in sorted(set(exp_tables) | set(got_tables)):
            if exp_tables.get(table) != got_tables.get(table):
                diffs.append(f"{key}.tables.{table}: column definitions differ")
    return diffs


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--write", action="store_true",
                        help="save capture to captured-profiles.json")
    parser.add_argument("--check", action="store_true",
                        help="compare saved profiles against the live schema")
    args = parser.parse_args(argv)

    try:
        capture = capture_all()
    except FileNotFoundError as exc:
        print(f"error: database not found: {exc}", file=sys.stderr)
        return 4

    if args.check:
        if not OUT_PATH.is_file():
            print(f"error: no saved capture at {OUT_PATH}", file=sys.stderr)
            return 2
        expected = json.loads(OUT_PATH.read_text())
        diffs = _diff(expected, capture)
        if diffs:
            print("schema drift vs saved capture:", file=sys.stderr)
            for line in diffs:
                print(f"  - {line}", file=sys.stderr)
            return 2
        print(json.dumps({"ok": True, "profiles": [
            capture["state"]["profile"], capture["history"]["profile"]]}))
        return 0

    text = json.dumps(capture, indent=2, default=str)
    if args.write:
        OUT_PATH.write_text(text + "\n")
        print(f"wrote {OUT_PATH}", file=sys.stderr)
    print(text)
    return 0


if __name__ == "__main__":
    sys.exit(main())
