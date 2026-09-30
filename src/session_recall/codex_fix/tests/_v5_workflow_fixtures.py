"""Synthetic migration-56 fixtures for the full V5 review workflow."""

from __future__ import annotations

from argparse import Namespace
from dataclasses import replace
import hashlib
from pathlib import Path
import sqlite3
from types import SimpleNamespace

from session_recall.codex_fix import candidate, candidate_checks, checks, trust
from session_recall.codex_fix.context import Context
from session_recall.codex_fix.contracts import canonical_bytes, digest, validate
from session_recall.codex_fix.engine import classify, observe
from session_recall.codex_fix.policy import model_policy
from session_recall.codex_metadata import inspect

from .conftest import readonly_pair


PROFILE = "session_recall/providers/codex/verifications/captured-profiles.json"
CHECK_IDS = [
    "artifact_manifest_v1",
    "synthetic_schema_v1",
    "trial_cli_contract_v1",
    "unknown_drift_rejected_v1",
    "synthetic_no_write_v1",
]


def raw_digest(data: bytes) -> str:
    return "sha256:" + hashlib.sha256(data).hexdigest()


def database_hashes(world) -> dict[str, str]:
    return {
        name: hashlib.sha256(path.read_bytes()).hexdigest()
        for name, path in {
            "state": world.store.state_db,
            "history": world.store.history_db,
        }.items()
    }


def selection_bytes(world) -> bytes:
    return world.context.paths["current_selection"].read_bytes()


class RecordingGenerate:
    def __init__(self, snapshot: dict, mutation: str | None = None):
        self.snapshot = snapshot
        self.mutation = mutation
        self.calls: list[tuple[dict, dict]] = []

    def __call__(self, request: dict, policy: dict, **_kwargs) -> dict:
        self.calls.append((request, policy))
        content = canonical_bytes(candidate.target_profiles(self.snapshot, None)).decode()
        generated = {
            "format_version": 1,
            "input_digest": digest(request),
            "base_artifact_digest": request["base_artifact_digest"],
            "files": [{"path": PROFILE, "sha256": raw_digest(content.encode()),
                       "content": content}],
        }
        if self.mutation == "self_approval":
            generated["approved"] = True
        elif self.mutation == "wrong_profile":
            bad = "{}"
            generated["files"] = [
                {"path": PROFILE, "sha256": raw_digest(bad.encode()), "content": bad}
            ]
        elif self.mutation == "same_target_variant":
            unchanged = next(
                item for item in request["source_files"] if item["path"].endswith("schema.py")
            )
            generated["files"].append(unchanged)
        return {
            "status": "completed",
            "candidate": generated,
            "evidence": {
                "requested_model": "gpt-6-astra",
                "requested_effort": "medium",
                "reported_model": "gpt-6-astra",
                "reported_effort": "medium",
                "usage": {"input_tokens": 16_000, "output_tokens": 16_000},
            },
        }


def _migrate_to_56(path: Path) -> None:
    connection = sqlite3.connect(path)
    try:
        connection.execute("ALTER TABLE threads ADD COLUMN synthetic_future TEXT")
        connection.execute(
            "INSERT INTO _sqlx_migrations "
            "(version,description,installed_on,success,checksum,execution_time) "
            "VALUES (56,'synthetic migration 056','2026-09-20 00:00:00',1,?,0)",
            (b"",),
        )
        connection.commit()
    finally:
        connection.close()


def refreshed_context(world, catalogue: dict | None = None) -> Context:
    selected = world.context.catalogue if catalogue is None else catalogue
    provisional = replace(
        world.context,
        catalogue=selected,
        catalogue_digest=digest(selected),
        check_registry=candidate_checks.guarded_registry(selected),
        current_observation=None,
    )
    observation = observe(provisional.recapture(), provisional)
    return replace(provisional, current_observation=observation)


def production_context(world) -> Context:
    from session_recall.codex_fix.factory import production_context as build

    return build(
        Namespace(
            root=str(world.context.managed_root),
            state_db=str(world.store.state_db),
            history_db=str(world.store.history_db),
            sessions_root=str(world.store.sessions_root),
            config=None,
        )
    )


def build_workflow_world(synthetic_store):
    _migrate_to_56(synthetic_store.state_db)
    with readonly_pair(synthetic_store) as connections:
        snapshot = inspect(connections)
    catalogue = trust.load_catalogue()
    base_digest = catalogue["seed_artifact_digest"]
    managed_root = synthetic_store.root / "workflow-managed"
    selection_dir = managed_root / "selection"
    selection_dir.mkdir(parents=True)
    managed_root.chmod(0o700)
    selection_dir.chmod(0o700)
    selection = validate(
        {
            "format_version": 1,
            "generation": 1,
            "artifact_digest": base_digest,
            "source": "managed",
            "recipe_id": "profile55-seed",
            "activated_plan_digest": "sha256:" + "c" * 64,
        },
        "Selection",
    )
    current_selection = selection_dir / "current.json"
    current_selection.write_bytes(canonical_bytes(selection))
    activation_policy = validate(
        {
            "format_version": 1,
            "known_recipe_mode": "explicit",
            "startup_trigger": "none",
            "allow_downloads": False,
        },
        "ActivationPolicy",
    )

    def recapture():
        with readonly_pair(synthetic_store) as connections:
            return inspect(connections)

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
        policy=activation_policy,
        policy_digest=digest(activation_policy),
        check_registry=checks.registry(),
        recapture=recapture,
        test_hooks=None,
        adapter_identity=validate(
            {
                "kind": "managed",
                "artifact_digest": base_digest,
                "profile_id": "codex-state-v5-migration-55",
            },
            "AdapterIdentity",
        ),
        current_observation=None,
    )
    context = replace(context, current_observation=observe(snapshot, context))
    assert classify(context.current_observation, context)["status"] == "assistance_eligible"
    return SimpleNamespace(
        store=synthetic_store,
        context=context,
        snapshot=snapshot,
        catalogue=catalogue,
        base_digest=base_digest,
        policy=model_policy(),
        generator=RecordingGenerate(snapshot),
    )
