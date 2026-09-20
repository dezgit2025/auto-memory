"""Trust and metadata preconditions shared by store activation paths."""

from __future__ import annotations

from typing import Any

from session_recall.codex_metadata import StorageChangingError

from .contracts import ContractError, digest, validate

CHECK_IDS = [
    "artifact_manifest_v1",
    "synthetic_schema_v1",
    "trial_cli_contract_v1",
    "unknown_drift_rejected_v1",
    "synthetic_no_write_v1",
]


def plan_trust(plan: dict[str, Any], context: Any) -> dict[str, Any]:
    validate(plan, "Plan")
    validate(context.catalogue, "Catalogue")
    validate(context.policy, "ActivationPolicy")
    if (
        digest(context.catalogue) != context.catalogue_digest
        or digest(context.policy) != context.policy_digest
        or plan["catalogue_digest"] != context.catalogue_digest
        or plan["policy_digest"] != context.policy_digest
    ):
        raise ContractError("stale_plan")
    if plan["check_ids"] != CHECK_IDS:
        raise ContractError("invalid_check_set")
    expected_activation = (
        "opted_in_known_auto"
        if context.policy["known_recipe_mode"] == "auto_opt_in"
        else "explicit_apply"
    )
    if plan["activation"] != expected_activation:
        raise ContractError("stale_plan")
    recipes = [
        recipe
        for recipe in context.catalogue["recipes"]
        if recipe["recipe_id"] == plan["recipe_id"]
        and recipe["source_adapter_digest"] == plan["source_adapter_digest"]
        and recipe["target_artifact_digest"] == plan["target_artifact_digest"]
        and recipe["check_ids"] == plan["check_ids"]
    ]
    if len(recipes) != 1:
        raise ContractError("stale_plan")
    return recipes[0]


def recapture_matching(context: Any, schema_fingerprint: str) -> dict[str, Any]:
    try:
        snapshot = context.recapture()
    except StorageChangingError as exc:
        raise ContractError("storage_changing") from exc
    except Exception as exc:
        raise ContractError("storage_changing") from exc
    try:
        validate(snapshot, "SchemaSnapshot")
    except ContractError as exc:
        raise ContractError("stale_recapture") from exc
    if snapshot["schema_fingerprint"] != schema_fingerprint:
        raise ContractError("storage_changing")
    return snapshot


def source_preconditions(
    plan: dict[str, Any], context: Any, recipe: dict[str, Any]
) -> tuple[dict[str, Any], dict[str, Any]]:
    observation = context.current_observation
    if observation is None or plan["input_fingerprint"] != observation["input_fingerprint"]:
        raise ContractError("stale_plan")
    validate(observation, "Observation")
    if (
        observation["catalogue_digest"] != context.catalogue_digest
        or observation["policy_digest"] != context.policy_digest
        or observation["adapter"] != context.adapter_identity
        or observation["adapter"]["artifact_digest"] != plan["source_adapter_digest"]
        or recipe["schema_fingerprint"]
        != observation["snapshot"]["schema_fingerprint"]
    ):
        raise ContractError("stale_plan")
    snapshot = recapture_matching(context, recipe["schema_fingerprint"])
    return observation, snapshot
