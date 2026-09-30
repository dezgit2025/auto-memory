"""Hermetic helpers for the Stage A Codex recall verifier."""

from __future__ import annotations

import hashlib
import json
import os
import shutil
import sqlite3
import subprocess
import tempfile
import time
from dataclasses import dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
ORACLE = ROOT / "verify/fixtures/codex-reviewed-55.json"
PROFILE = ROOT / "src/session_recall/providers/codex/verifications/captured-profiles.json"
ORACLE_SHA256 = "c880534b0aa1f8fccfdda5c1408f32481c7e6a7e795ec1b575412c0d803279ad"
USED_TABLES = {
    "state": ("threads", "_sqlx_migrations"),
    "history": ("thread_items", "thread_turns", "_sqlx_migrations"),
}


class VerifyFailure(AssertionError):
    """Observable product or contract failure."""


class InfraFailure(RuntimeError):
    """Verifier prerequisite failure that is safe to retry."""


class TamperFailure(RuntimeError):
    """Protected verifier input or anti-cheat contract changed."""


class TimeoutFailure(RuntimeError):
    """A bounded verifier subprocess exceeded its deadline."""


@dataclass(frozen=True)
class Result:
    argv: tuple[str, ...]
    returncode: int
    stdout: str
    stderr: str


def run(argv: list[str], *, env: dict[str, str] | None = None,
        cwd: Path | None = None, timeout: int = 60) -> Result:
    merged = os.environ.copy()
    for name in (
        "PYTHONPATH", "PYTHONHOME", "PYTEST_ADDOPTS",
        "SESSION_RECALL_CODEX_STATE_DB", "SESSION_RECALL_CODEX_HISTORY_DB",
        "SESSION_RECALL_CODEX_SESSIONS_ROOT", "SESSION_RECALL_CODEX_FIX_ROOT",
    ):
        merged.pop(name, None)
    missing = Path(tempfile.gettempdir()) / (
        f"session-recall-no-store-{os.getpid()}-{time.monotonic_ns()}"
    )
    merged.update({
        "PYTHONHASHSEED": "0",
        "PYTHONDEVMODE": "1",
        "PYTHONDONTWRITEBYTECODE": "1",
        "PYTEST_DISABLE_PLUGIN_AUTOLOAD": "1",
        "PIP_NO_INDEX": "1",
        "PIP_DISABLE_PIP_VERSION_CHECK": "1",
        "NO_NETWORK": "1",
        "TZ": "UTC",
        "LC_ALL": "C",
        "SESSION_RECALL_CODEX_STATE_DB": str(missing / "state_5.sqlite"),
        "SESSION_RECALL_CODEX_HISTORY_DB": str(missing / "thread_history_1.sqlite"),
        "SESSION_RECALL_CODEX_SESSIONS_ROOT": str(missing / "sessions"),
        "SESSION_RECALL_CODEX_FIX_ROOT": str(missing / "fix-root"),
    })
    if env:
        merged.update(env)
    merged.pop("PYTHONHOME", None)
    merged.pop("PYTEST_ADDOPTS", None)
    merged["PYTEST_DISABLE_PLUGIN_AUTOLOAD"] = "1"
    merged["PIP_NO_INDEX"] = "1"
    merged["PIP_DISABLE_PIP_VERSION_CHECK"] = "1"
    try:
        proc = subprocess.run(
            argv, cwd=cwd or ROOT, env=merged, text=True,
            capture_output=True, timeout=timeout, check=False,
        )
    except subprocess.TimeoutExpired as exc:
        raise TimeoutFailure(f"timeout after {timeout}s: {argv!r}") from exc
    return Result(tuple(argv), proc.returncode, proc.stdout, proc.stderr)


def require(result: Result, code: int = 0, contains: str | None = None) -> Result:
    if result.returncode != code:
        raise VerifyFailure(
            f"{result.argv!r}: exit {result.returncode}, wanted {code}; "
            f"stdout={result.stdout[-800:]!r} stderr={result.stderr[-800:]!r}"
        )
    text = result.stdout + result.stderr
    if contains is not None and contains not in text:
        raise VerifyFailure(f"{result.argv!r}: missing {contains!r} in {text[-1200:]!r}")
    return result


def load_json(path: Path) -> dict:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise InfraFailure(f"cannot load {path}: {exc}") from exc


def load_oracle() -> dict:
    try:
        digest = hashlib.sha256(ORACLE.read_bytes()).hexdigest()
    except OSError as exc:
        raise InfraFailure(f"reviewed oracle missing: {ORACLE}") from exc
    if digest != ORACLE_SHA256:
        raise TamperFailure(f"reviewed oracle digest changed: {digest}")
    return load_json(ORACLE)


def compared_profile(profile: dict) -> dict:
    """Exclude ancillary migration descriptions; retain all safety metadata."""
    out: dict[str, dict] = {}
    for side, tables in USED_TABLES.items():
        item = profile[side]
        out[side] = {
            "profile": item["profile"],
            "migration_ceiling": item["migration_ceiling"],
            "failed_migrations": item.get("failed_migrations", 0),
            "json1": item.get("json1", True),
            "tables": {name: item["tables"][name] for name in tables},
        }
    return out


def qident(value: str) -> str:
    return '"' + value.replace('"', '""') + '"'


def create_table(conn: sqlite3.Connection, name: str, columns: list[list]) -> None:
    defs: list[str] = []
    pk_cols = [row for row in columns if row[5]]
    for _cid, col, ctype, notnull, default, pk in columns:
        part = f"{qident(col)} {ctype}"
        if pk and len(pk_cols) == 1:
            part += " PRIMARY KEY"
        if notnull:
            part += " NOT NULL"
        if default is not None:
            part += f" DEFAULT {default}"
        defs.append(part)
    if len(pk_cols) > 1:
        ordered = sorted(pk_cols, key=lambda row: row[5])
        defs.append("PRIMARY KEY (" + ", ".join(qident(row[1]) for row in ordered) + ")")
    conn.execute(f"CREATE TABLE {qident(name)} ({', '.join(defs)})")


def create_db(path: Path, side: str, profile: dict) -> None:
    conn = sqlite3.connect(path)
    try:
        for table, columns in profile[side]["tables"].items():
            create_table(conn, table, columns)
        ceiling = profile[side]["migration_ceiling"]
        description = profile[side].get("migration_description", "reviewed")
        for version in range(1, ceiling + 1):
            conn.execute(
                "INSERT INTO _sqlx_migrations "
                "(version, description, installed_on, success, checksum, execution_time) "
                "VALUES (?, ?, ?, 1, ?, 0)",
                (version, description if version == ceiling else f"migration {version}",
                 "2026-01-01 00:00:00", b""),
            )
        conn.commit()
    finally:
        conn.close()


def _default_value(row: list) -> object:
    _cid, _name, ctype, notnull, default, _pk = row
    if not notnull:
        return None
    if default is not None:
        if str(default).strip("'\"").isdigit():
            return int(str(default).strip("'\""))
        return str(default).strip("'\"")
    if ctype in {"INTEGER", "BOOLEAN", "REAL"}:
        return 0
    if ctype == "BLOB":
        return b""
    return ""


def _insert_threads(path: Path, profile: dict) -> None:
    now = int(time.time() * 1000)
    day = 86_400_000
    rows = [
        dict(id="01999999-0001-7001-8000-000000000001", title="verify remote newest",
             cwd="/verify/remote", git_origin_url="https://github.com/verify/remote.git",
             created_at_ms=now-day, updated_at_ms=now-day, recency_at_ms=now-day),
        dict(id="01999999-0002-7002-8000-000000000002", title="verify local scratch",
             cwd="/verify/local", git_origin_url=None,
             created_at_ms=now-2*day, updated_at_ms=now-2*day, recency_at_ms=now-2*day),
        dict(id="01999999-0003-7003-8000-000000000003", title="verify remote older",
             cwd="/verify/remote", git_origin_url="https://github.com/verify/remote.git",
             created_at_ms=now-3*day, updated_at_ms=now-3*day, recency_at_ms=now-3*day),
        dict(id="01999999-0004-7004-8000-000000000004", title="verify archived",
             cwd="/verify/remote", git_origin_url="https://github.com/verify/remote.git",
             archived=1, created_at_ms=now-day-day//2,
             updated_at_ms=now-day-day//2, recency_at_ms=now-day-day//2),
        dict(id="01999999-0005-7005-8000-000000000005", title="verify guardian",
             cwd="/verify/remote", git_origin_url="https://github.com/verify/remote.git",
             source='{"subagent":{"other":"guardian"}}', created_at_ms=now-day//2,
             updated_at_ms=now-day//2, recency_at_ms=now-day//2),
    ]
    columns = profile["state"]["tables"]["threads"]
    names = [row[1] for row in columns]
    conn = sqlite3.connect(path)
    try:
        for overrides in rows:
            millis = overrides["created_at_ms"]
            base = {
                "rollout_path": "", "created_at": millis // 1000,
                "updated_at": millis // 1000, "source": "cli",
                "model_provider": "openai", "preview": overrides["title"],
                "first_user_message": overrides["title"], "archived": 0,
                "agent_path": None, "history_mode": "paginated",
                "has_user_event": 1, "originator": None, "daybreak_enabled": None,
            }
            base.update(overrides)
            values = [base.get(row[1], _default_value(row)) for row in columns]
            sql = (f"INSERT INTO threads ({', '.join(qident(n) for n in names)}) "
                   f"VALUES ({', '.join('?' for _ in names)})")
            conn.execute(sql, values)
        conn.commit()
    finally:
        conn.close()


def build_fixture(root: Path) -> dict[str, Path]:
    profile = load_oracle()
    root.mkdir(parents=True, exist_ok=False)
    (root / "sessions").mkdir()
    state = root / "state_5.sqlite"
    history = root / "thread_history_1.sqlite"
    create_db(state, "state", profile)
    create_db(history, "history", profile)
    _insert_threads(state, profile)
    return {"root": root, "state": state, "history": history,
            "sessions": root / "sessions"}


def fixture_env(store: dict[str, Path]) -> dict[str, str]:
    return {
        "SESSION_RECALL_CODEX_STATE_DB": str(store["state"]),
        "SESSION_RECALL_CODEX_HISTORY_DB": str(store["history"]),
        "SESSION_RECALL_CODEX_SESSIONS_ROOT": str(store["sessions"]),
    }


def hash_tree(root: Path) -> dict[str, str]:
    return {str(path.relative_to(root)): hashlib.sha256(path.read_bytes()).hexdigest()
            for path in sorted(root.rglob("*")) if path.is_file()}


def installed_cli() -> Path:
    found = shutil.which("session-recall-codex")
    if not found:
        raise InfraFailure("session-recall-codex is not installed on PATH")
    path = Path(found).resolve()
    if not path.is_file():
        raise InfraFailure(f"installed CLI is not a file: {path}")
    return path
