"""Hermetic synthetic-store helpers for production adapter checks."""

from __future__ import annotations

from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import dataclass
import hashlib
import json
import os
from pathlib import Path
import sqlite3
import subprocess
import sys
import tempfile
import time
from typing import Any, Iterator

from . import artifacts
from .contracts import ContractError


MAX_OUTPUT_BYTES = 256 * 1024
TIMEOUT_SECONDS = 30
ISOLATED_RUNNER: ContextVar[Any] = ContextVar("candidate_check_runner", default=None)


@contextmanager
def isolated_checks(runner: Any) -> Iterator[None]:
    token = ISOLATED_RUNNER.set(runner)
    try:
        yield
    finally:
        ISOLATED_RUNNER.reset(token)


@dataclass(frozen=True)
class SyntheticStore:
    root: Path
    state: Path
    history: Path
    sessions: Path


def trusted_manifest(path: Path, context: Any) -> dict[str, Any]:
    digests = {context.catalogue["seed_artifact_digest"]}
    for recipe in context.catalogue["recipes"]:
        digests.add(recipe["source_adapter_digest"])
        digests.add(recipe["target_artifact_digest"])
    for artifact_digest in sorted(digests):
        try:
            return artifacts.manifest(path, artifact_digest)
        except ContractError:
            continue
    raise ContractError("artifact_untrusted", "artifact is not catalogue-pinned")


def _quote(value: str) -> str:
    return '"' + value.replace('"', '""') + '"'


def _create_table(connection: sqlite3.Connection, name: str, rows: list[list]) -> None:
    definitions = []
    primary = [row for row in rows if row[5]]
    for _cid, column, declared, not_null, default, pk_position in rows:
        part = f"{_quote(column)} {declared}"
        if pk_position and len(primary) == 1:
            part += " PRIMARY KEY"
        if not_null:
            part += " NOT NULL"
        if default is not None:
            part += f" DEFAULT {default}"
        definitions.append(part)
    if len(primary) > 1:
        ordered = sorted(primary, key=lambda row: row[5])
        definitions.append("PRIMARY KEY (" + ", ".join(_quote(row[1]) for row in ordered) + ")")
    connection.execute(f"CREATE TABLE {_quote(name)} ({', '.join(definitions)})")


def _default(row: list) -> object:
    _cid, _name, declared, not_null, default, _pk = row
    if not not_null:
        return None
    if default is not None:
        stripped = str(default).strip("'\"")
        return int(stripped) if stripped.isdigit() else stripped
    return 0 if declared in {"INTEGER", "BOOLEAN", "REAL"} else b"" if declared == "BLOB" else ""


def _create_database(path: Path, profile: dict[str, Any]) -> None:
    connection = sqlite3.connect(path)
    try:
        for name, rows in profile["tables"].items():
            _create_table(connection, name, rows)
        ceiling = profile["migration_ceiling"]
        for version in range(1, ceiling + 1):
            description = profile["migration_description"] if version == ceiling else f"migration {version}"
            connection.execute(
                "INSERT INTO _sqlx_migrations "
                "(version,description,installed_on,success,checksum,execution_time) "
                "VALUES (?,?,'2026-09-20 00:00:00',1,?,0)",
                (version, description, b""),
            )
        connection.commit()
    finally:
        connection.close()


def _insert_thread(path: Path, profile: dict[str, Any]) -> None:
    rows = profile["tables"]["threads"]
    names = [row[1] for row in rows]
    now = int(time.time() * 1000)
    overrides = {
        "id": "01999999-0001-7001-8000-000000000001",
        "rollout_path": "",
        "created_at": now // 1000,
        "updated_at": now // 1000,
        "source": "cli",
        "model_provider": "openai",
        "cwd": "/synthetic/reviewed",
        "title": "synthetic reviewed session",
        "first_user_message": "synthetic reviewed session",
        "preview": "synthetic reviewed session",
        "archived": 0,
        "git_origin_url": "https://github.com/synthetic/reviewed.git",
        "agent_path": None,
        "created_at_ms": now,
        "updated_at_ms": now,
        "recency_at_ms": now,
        "history_mode": "paginated",
        "originator": None,
        "daybreak_enabled": None,
    }
    values = [overrides.get(row[1], _default(row)) for row in rows]
    connection = sqlite3.connect(path)
    try:
        connection.execute(
            f"INSERT INTO threads ({', '.join(_quote(name) for name in names)}) "
            f"VALUES ({', '.join('?' for _ in names)})",
            values,
        )
        connection.commit()
    finally:
        connection.close()


@contextmanager
def synthetic_store(manifest: dict[str, Any]) -> Iterator[SyntheticStore]:
    with tempfile.TemporaryDirectory(prefix="session-recall-codex-check-") as temporary:
        root = Path(temporary)
        profiles = manifest["profiles"]
        state = root / profiles["state"]["db_filename"]
        history = root / profiles["history"]["db_filename"]
        sessions = root / "sessions"
        sessions.mkdir()
        _create_database(state, profiles["state"])
        _create_database(history, profiles["history"])
        _insert_thread(state, profiles["state"])
        yield SyntheticStore(root, state, history, sessions)


def run_json(artifact: Path, store: SyntheticStore, arguments: list[str]) -> tuple[int, Any]:
    environment = {
        "PATH": os.defpath,
        "PYTHONDONTWRITEBYTECODE": "1",
        "PYTHONIOENCODING": "utf-8",
        "PYTHONUTF8": "1",
        "NO_NETWORK": "1",
        "SESSION_RECALL_CODEX_STATE_DB": str(store.state),
        "SESSION_RECALL_CODEX_HISTORY_DB": str(store.history),
        "SESSION_RECALL_CODEX_SESSIONS_ROOT": str(store.sessions),
    }
    runner = ISOLATED_RUNNER.get()
    if runner is None:
        completed = subprocess.run(
            [sys.executable, str(artifact), *arguments], cwd=store.root,
            env=environment, stdin=subprocess.DEVNULL, capture_output=True,
            text=True, timeout=TIMEOUT_SECONDS, check=False,
        )
    else:
        environment.pop("PATH", None)
        environment.pop("NO_NETWORK", None)
        completed = runner.run(
            [artifact, *arguments], readable=[artifact, store.root], writable=None,
            cwd=store.root, env=environment, timeout=TIMEOUT_SECONDS,
        )
    if (
        len(completed.stdout.encode("utf-8")) > MAX_OUTPUT_BYTES
        or len(completed.stderr.encode("utf-8")) > MAX_OUTPUT_BYTES
    ):
        raise ContractError("check_output_too_large")
    try:
        value = json.loads(completed.stdout)
    except json.JSONDecodeError as exc:
        raise ContractError("check_invalid_json") from exc
    return completed.returncode, value


def hash_store(store: SyntheticStore) -> dict[str, str]:
    return {
        str(path.relative_to(store.root)): hashlib.sha256(path.read_bytes()).hexdigest()
        for path in sorted(store.root.rglob("*"))
        if path.is_file()
    }
