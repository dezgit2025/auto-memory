"""Read-only deterministic observation, classification, and planning."""

from __future__ import annotations

import os
import stat
from typing import Any

from .context import Context
from .contracts import ContractError, digest, parse, validate


def _context_integrity(context: Context) -> None:
    validate(context.catalogue, "Catalogue")
    validate(context.policy, "ActivationPolicy")
    validate(context.adapter_identity, "AdapterIdentity")
    if context.catalogue_digest != digest(context.catalogue):
        raise ContractError("digest_mismatch", "catalogue digest does not match")
    if context.policy_digest != digest(context.policy):
        raise ContractError("digest_mismatch", "policy digest does not match")


def observe(snapshot: dict[str, Any], context: Context) -> dict[str, Any]:
    """Bind a validated schema projection to trusted local controller inputs."""
    _context_integrity(context)
    validate(snapshot, "SchemaSnapshot")
    semantic = {
        "schema_fingerprint": snapshot["schema_fingerprint"],
        "adapter": context.adapter_identity,
        "catalogue_digest": context.catalogue_digest,
        "policy_digest": context.policy_digest,
    }
    return validate(
        {
            "format_version": 1,
            "snapshot": snapshot,
            "adapter": context.adapter_identity,
            "catalogue_digest": context.catalogue_digest,
            "policy_digest": context.policy_digest,
            "input_fingerprint": digest(semantic),
        },
        "Observation",
    )


def _classification(
    observation: dict[str, Any], status: str, recipe_id: str | None, reason: str | None
) -> dict[str, Any]:
    return validate(
        {
            "format_version": 1,
            "status": status,
            "observation_digest": observation["input_fingerprint"],
            "recipe_id": recipe_id,
            "reason_code": reason,
        },
        "Classification",
    )


def classify(observation: dict[str, Any], context: Context) -> dict[str, Any]:
    """Classify only exact identities and exact reviewed recipe matches."""
    _context_integrity(context)
    validate(observation, "Observation")
    if (
        observation["catalogue_digest"] != context.catalogue_digest
        or observation["policy_digest"] != context.policy_digest
        or observation["adapter"] != context.adapter_identity
    ):
        return _classification(observation, "invalid", None, "provenance_mismatch")

    snapshot = observation["snapshot"]
    if snapshot["state"]["failed_migrations"] or snapshot["history"]["failed_migrations"]:
        return _classification(observation, "invalid", None, "failed_migrations")
    if not snapshot["state"]["json1"] or not snapshot["history"]["json1"]:
        return _classification(observation, "invalid", None, "json1_missing")
    if any(
        not table["columns"]
        for profile in (snapshot["state"], snapshot["history"])
        for table in profile["tables"]
    ):
        return _classification(observation, "invalid", None, "storage_invalid")

    identity = observation["adapter"]
    if identity["kind"] == "legacy":
        if identity["artifact_digest"] is not None or identity["profile_id"] is not None:
            return _classification(observation, "invalid", None, "invalid_identity")
        return _classification(observation, "unmanaged_legacy", None, "unmanaged_legacy")
    if identity["artifact_digest"] is None or identity["profile_id"] is None:
        return _classification(observation, "invalid", None, "invalid_identity")

    fingerprint = snapshot["schema_fingerprint"]
    recipes = context.catalogue["recipes"]
    matches = [
        recipe
        for recipe in recipes
        if recipe["source_adapter_digest"] == identity["artifact_digest"]
        and recipe["schema_fingerprint"] == fingerprint
    ]
    if len(matches) > 1:
        return _classification(observation, "ambiguous_recipe", None, "ambiguous_recipe")
    if len(matches) == 1:
        return _classification(observation, "known_repair", matches[0]["recipe_id"], None)
    supported = any(
        recipe["target_artifact_digest"] == identity["artifact_digest"]
        and recipe["schema_fingerprint"] == fingerprint
        for recipe in recipes
    )
    if supported:
        return _classification(observation, "supported", None, None)
    return _classification(observation, "assistance_eligible", None, "no_recipe")


def _read_selection(path: os.PathLike[str]) -> dict[str, Any] | None:
    try:
        before = os.lstat(path)
    except FileNotFoundError:
        return None
    if stat.S_ISLNK(before.st_mode) or not stat.S_ISREG(before.st_mode):
        raise ContractError("invalid_selection", "current selection is not a regular file")
    if before.st_size > 2 * 1024 * 1024:
        raise ContractError("too_large", "current selection exceeds 2 MiB")
    flags = (
        os.O_RDONLY
        | getattr(os, "O_CLOEXEC", 0)
        | getattr(os, "O_NOFOLLOW", 0)
        | getattr(os, "O_NONBLOCK", 0)
    )
    descriptor = -1
    try:
        descriptor = os.open(path, flags)
        opened = os.fstat(descriptor)
        if not stat.S_ISREG(opened.st_mode):
            raise ContractError(
                "invalid_selection", "current selection is not a regular file"
            )
        initial_identity = (before.st_dev, before.st_ino, before.st_size, before.st_mtime_ns)
        opened_identity = (opened.st_dev, opened.st_ino, opened.st_size, opened.st_mtime_ns)
        if initial_identity != opened_identity:
            raise ContractError("invalid_selection", "current selection changed while opening")
        with os.fdopen(descriptor, "rb") as handle:
            descriptor = -1
            payload = handle.read(2 * 1024 * 1024 + 1)
            after = os.fstat(handle.fileno())
    except OSError as exc:
        raise ContractError("invalid_selection", "current selection is unreadable") from exc
    finally:
        if descriptor >= 0:
            os.close(descriptor)
    identity_before = (opened.st_dev, opened.st_ino, opened.st_size, opened.st_mtime_ns)
    identity_after = (after.st_dev, after.st_ino, after.st_size, after.st_mtime_ns)
    if len(payload) > 2 * 1024 * 1024 or identity_before != identity_after:
        raise ContractError("invalid_selection", "current selection changed while reading")
    try:
        text = payload.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise ContractError("invalid_selection", "current selection is not UTF-8") from exc
    return parse(text, "Selection")


def plan(classification: dict[str, Any], context: Context) -> dict[str, Any]:
    """Construct a deterministic reviewed-recipe manifest without writing state."""
    _context_integrity(context)
    validate(classification, "Classification")
    refused = {
        "assistance_eligible": "no_recipe",
        "ambiguous_recipe": "ambiguous_recipe",
        "unmanaged_legacy": "unmanaged_legacy",
    }
    if classification["status"] in refused:
        raise ContractError(refused[classification["status"]])
    if classification["status"] != "known_repair":
        raise ContractError(classification["reason_code"] or "not_repairable")
    observation = context.current_observation
    if observation is None:
        raise ContractError("missing_observation")
    validate(observation, "Observation")
    if observation["input_fingerprint"] != classification["observation_digest"]:
        raise ContractError("stale_observation")
    expected = classify(observation, context)
    if expected != classification:
        raise ContractError("stale_classification")

    recipes = [
        item
        for item in context.catalogue["recipes"]
        if item["recipe_id"] == classification["recipe_id"]
        and item["source_adapter_digest"] == observation["adapter"]["artifact_digest"]
        and item["schema_fingerprint"] == observation["snapshot"]["schema_fingerprint"]
    ]
    if len(recipes) != 1:
        raise ContractError("ambiguous_recipe" if len(recipes) > 1 else "no_recipe")
    recipe = recipes[0]
    current = _read_selection(context.paths["current_selection"])
    if current is None:
        if observation["adapter"]["kind"] == "managed":
            raise ContractError("source_identity_mismatch")
        prior_digest = None
    else:
        if (
            current["artifact_digest"] != recipe["source_adapter_digest"]
            or current["artifact_digest"] != observation["adapter"]["artifact_digest"]
            or current["source"] != observation["adapter"]["kind"]
        ):
            raise ContractError("source_identity_mismatch")
        prior_digest = digest(current)
    activation = (
        "opted_in_known_auto"
        if context.policy["known_recipe_mode"] == "auto_opt_in"
        else "explicit_apply"
    )
    return validate(
        {
            "format_version": 1,
            "kind": "reviewed_recipe",
            "input_fingerprint": observation["input_fingerprint"],
            "source_adapter_digest": recipe["source_adapter_digest"],
            "catalogue_digest": context.catalogue_digest,
            "policy_digest": context.policy_digest,
            "recipe_id": recipe["recipe_id"],
            "target_artifact_digest": recipe["target_artifact_digest"],
            "check_ids": recipe["check_ids"],
            "prior_selection_digest": prior_digest,
            "activation": activation,
        },
        "Plan",
    )
