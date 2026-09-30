"""Immutable registry of independent, synthetic-only adapter checks."""

from __future__ import annotations

from pathlib import Path
import sqlite3
from types import MappingProxyType
from typing import Any, Callable, Mapping

from ._check_runtime import hash_store, run_json, synthetic_store, trusted_manifest


def _guard(callback: Callable[[], bool]) -> bool:
    try:
        return callback() is True
    except Exception:
        return False


def artifact_manifest_v1(artifact: Path, context: Any) -> bool:
    return _guard(lambda: bool(trusted_manifest(artifact, context)))


def synthetic_schema_v1(artifact: Path, context: Any) -> bool:
    def check() -> bool:
        manifest = trusted_manifest(artifact, context)
        with synthetic_store(manifest) as store:
            code, body = run_json(artifact, store, ["schema-check", "--json"])
            return code == 0 and body == {
                "ok": True,
                "profiles": manifest["profile_ids"],
                "diagnostics": [],
            }

    return _guard(check)


def trial_cli_contract_v1(artifact: Path, context: Any) -> bool:
    def check() -> bool:
        manifest = trusted_manifest(artifact, context)
        with synthetic_store(manifest) as store:
            list_code, sessions = run_json(artifact, store, ["list", "--json", "--limit", "10"])
            repo_code, repos = run_json(artifact, store, ["repos", "--json", "--include-local"])
            expected_keys = {
                "id_full", "id_short", "summary", "created_at", "date", "branch",
                "repository", "turns_count", "files_count", "_trust_level",
            }
            return (
                list_code == 0
                and isinstance(sessions, list)
                and len(sessions) == 1
                and set(sessions[0]) == expected_keys
                and sessions[0]["summary"] == "synthetic reviewed session"
                and repo_code == 0
                and repos == {
                    "count": 1,
                    "repos": [{
                        "repository": "synthetic/reviewed",
                        "session_count": 1,
                        "last_seen": sessions[0]["created_at"],
                    }],
                }
            )

    return _guard(check)


def unknown_drift_rejected_v1(artifact: Path, context: Any) -> bool:
    def check() -> bool:
        manifest = trusted_manifest(artifact, context)
        with synthetic_store(manifest) as store:
            connection = sqlite3.connect(store.state)
            try:
                connection.execute("ALTER TABLE threads ADD COLUMN private_drift TEXT")
                connection.commit()
            finally:
                connection.close()
            for command in ("list", "repos"):
                code, body = run_json(artifact, store, [command, "--json"])
                if not (
                    code == 2
                    and isinstance(body, dict)
                    and body.get("error") == "schema_drift"
                    and body.get("query_executed") is False
                ):
                    return False
            return True

    return _guard(check)


def synthetic_no_write_v1(artifact: Path, context: Any) -> bool:
    def check() -> bool:
        manifest = trusted_manifest(artifact, context)
        with synthetic_store(manifest) as store:
            before = hash_store(store)
            for arguments in (
                ["schema-check", "--json"],
                ["list", "--json", "--limit", "10"],
                ["repos", "--json", "--include-local"],
            ):
                code, _body = run_json(artifact, store, arguments)
                if code != 0:
                    return False
            return hash_store(store) == before

    return _guard(check)


_REGISTRY: Mapping[str, Callable[[Path, Any], bool]] = MappingProxyType(
    {
        "artifact_manifest_v1": artifact_manifest_v1,
        "synthetic_schema_v1": synthetic_schema_v1,
        "trial_cli_contract_v1": trial_cli_contract_v1,
        "unknown_drift_rejected_v1": unknown_drift_rejected_v1,
        "synthetic_no_write_v1": synthetic_no_write_v1,
    }
)


def registry() -> Mapping[str, Callable[[Path, Any], bool]]:
    return _REGISTRY
