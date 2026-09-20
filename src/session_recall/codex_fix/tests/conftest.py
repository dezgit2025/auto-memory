"""Hermetic fixtures for the deterministic Codex fixer contracts."""

from __future__ import annotations

import json
import sqlite3
from contextlib import contextmanager
from dataclasses import replace
from pathlib import Path
from types import SimpleNamespace

import pytest

from session_recall.codex_fix.context import Context
from session_recall.codex_fix.contracts import canonical_bytes, digest, validate
from session_recall.codex_fix.engine import classify, observe
from session_recall.codex_metadata import inspect


ORACLE_PATH = (
    Path(__file__).resolve().parents[4] / "verify/fixtures/codex-reviewed-55.json"
)
SOURCE_DIGEST = "sha256:" + "5" * 64
TARGET_DIGEST = "sha256:" + "a" * 64
CHECK_IDS = [
    "artifact_manifest_v1",
    "synthetic_schema_v1",
    "trial_cli_contract_v1",
    "unknown_drift_rejected_v1",
    "synthetic_no_write_v1",
]


def _create_table_sql(name: str, rows: list[list[object]]) -> str:
    columns = []
    primary = [row for row in rows if row[5]]
    single_primary = len(primary) == 1
    for _cid, column, declared, not_null, default, pk_position in rows:
        part = f'"{column}" {declared}'
        if single_primary and pk_position:
            part += " PRIMARY KEY"
        if not_null:
            part += " NOT NULL"
        if default is not None:
            part += f" DEFAULT {default}"
        columns.append(part)
    if primary and not single_primary:
        ordered = sorted(primary, key=lambda row: row[5])
        columns.append(
            "PRIMARY KEY (" + ", ".join(f'"{row[1]}"' for row in ordered) + ")"
        )
    return f'CREATE TABLE "{name}" ({", ".join(columns)})'


def _build_database(path: Path, profile: dict[str, object]) -> None:
    connection = sqlite3.connect(path)
    try:
        for name, rows in profile["tables"].items():
            connection.execute(_create_table_sql(name, rows))
        for version in range(1, profile["migration_ceiling"] + 1):
            description = (
                profile["migration_description"]
                if version == profile["migration_ceiling"]
                else f"migration {version:03d}"
            )
            connection.execute(
                "INSERT INTO _sqlx_migrations "
                "(version, description, installed_on, success, checksum, execution_time) "
                "VALUES (?, ?, '2026-09-20 00:00:00', 1, ?, 0)",
                (version, description, b""),
            )
        connection.commit()
    finally:
        connection.close()


@contextmanager
def readonly_pair(store: SimpleNamespace):
    state = sqlite3.connect(f"file:{store.state_db}?mode=ro", uri=True)
    history = sqlite3.connect(f"file:{store.history_db}?mode=ro", uri=True)
    try:
        yield state, history
    finally:
        state.close()
        history.close()


@pytest.fixture()
def synthetic_store(tmp_path: Path) -> SimpleNamespace:
    with ORACLE_PATH.open(encoding="utf-8") as handle:
        oracle = json.load(handle)
    root = tmp_path / "codex-fix"
    root.mkdir()
    state_db = root / oracle["state"]["db_filename"]
    history_db = root / oracle["history"]["db_filename"]
    _build_database(state_db, oracle["state"])
    _build_database(history_db, oracle["history"])
    sessions_root = root / "sessions"
    sessions_root.mkdir()
    return SimpleNamespace(
        root=root,
        state_db=state_db,
        history_db=history_db,
        sessions_root=sessions_root,
        oracle=oracle,
    )


@pytest.fixture()
def reviewed_snapshot(synthetic_store: SimpleNamespace) -> dict[str, object]:
    with readonly_pair(synthetic_store) as connections:
        return inspect(connections)


@pytest.fixture()
def engine_case_factory(synthetic_store: SimpleNamespace, reviewed_snapshot):
    def make_case(
        route: str = "known",
        *,
        adapter_kind: str = "managed",
        policy_mode: str = "explicit",
    ) -> SimpleNamespace:
        recipe = {
            "recipe_id": "codex-state52-artifact-to-state55-v1",
            "source_adapter_digest": SOURCE_DIGEST,
            "schema_fingerprint": reviewed_snapshot["schema_fingerprint"],
            "target_artifact_digest": TARGET_DIGEST,
            "check_ids": CHECK_IDS,
        }
        recipes = [] if route == "unknown" else [recipe]
        if route == "ambiguous":
            recipes.append({**recipe, "recipe_id": "state52-to-state55-alternate"})
        catalogue = validate(
            {
                "format_version": 1,
                "catalogue_id": "bundled-catalogue-v1",
                "seed_artifact_digest": TARGET_DIGEST,
                "recipes": recipes,
            },
            "Catalogue",
        )
        policy = validate(
            {
                "format_version": 1,
                "known_recipe_mode": policy_mode,
                "startup_trigger": "none",
                "allow_downloads": False,
            },
            "ActivationPolicy",
        )
        identity = validate(
            {
                "kind": adapter_kind,
                "artifact_digest": SOURCE_DIGEST if adapter_kind != "legacy" else None,
                "profile_id": (
                    "codex-state-v5-migration-52" if adapter_kind != "legacy" else None
                ),
            },
            "AdapterIdentity",
        )
        selection = validate(
            {
                "format_version": 1,
                "generation": 7,
                "artifact_digest": SOURCE_DIGEST,
                "source": "managed",
                "recipe_id": "profile52-seed",
                "activated_plan_digest": "sha256:" + "c" * 64,
            },
            "Selection",
        )
        managed_root = synthetic_store.root / f"managed-{route}-{adapter_kind}-{policy_mode}"
        managed_root.mkdir(exist_ok=True)
        current_selection = managed_root / "current.json"
        current_selection.write_bytes(canonical_bytes(selection))

        def recapture():
            with readonly_pair(synthetic_store) as connections:
                return inspect(connections)

        checks = {check_id: (lambda *_args, **_kwargs: True) for check_id in CHECK_IDS}
        context = Context(
            paths={
                "state_db": synthetic_store.state_db,
                "history_db": synthetic_store.history_db,
                "sessions_root": synthetic_store.sessions_root,
                "current_selection": current_selection,
            },
            managed_root=managed_root,
            catalogue=catalogue,
            catalogue_digest=digest(catalogue),
            policy=policy,
            policy_digest=digest(policy),
            check_registry=checks,
            recapture=recapture,
            test_hooks=None,
            adapter_identity=identity,
            current_observation=None,
        )
        observation = observe(reviewed_snapshot, context)
        context = replace(context, current_observation=observation)
        classification = classify(observation, context)
        return SimpleNamespace(
            context=context,
            observation=observation,
            classification=classification,
            catalogue=catalogue,
            policy=policy,
            identity=identity,
            selection=selection,
            recipe=recipe,
        )

    return make_case
