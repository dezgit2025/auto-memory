"""Durable activation, recovery, and rollback for reviewed adapter artifacts."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from . import artifacts
from ._store_io import (
    activation_lock,
    directory,
    phase,
    postcheck,
    protect_root,
    read_json,
    result,
    selection,
    timestamp,
    write_selection,
)
from ._store_recovery import journal_binding, recover_locked
from ._store_preconditions import (
    CHECK_IDS,
    plan_trust,
    recapture_matching,
    source_preconditions,
)
from .contracts import ContractError, digest, validate
def _paths(context: Any) -> tuple[Path, Path, Path]:
    root = Path(context.managed_root)
    protect_root(root)
    journal_dir = directory(root, "journal")
    selection_dir = directory(root, "selection")
    current = Path(context.paths["current_selection"])
    if current.parent != selection_dir:
        raise ContractError("invalid_root", "selection path is not canonical")
    return journal_dir, selection_dir, current


def _target_artifact(plan: dict[str, Any], snapshot: dict[str, Any], context: Any) -> Path:
    target = artifacts.resolve(plan["target_artifact_digest"], context)
    manifest = artifacts.manifest(target, plan["target_artifact_digest"])
    if manifest["schema_fingerprint"] != snapshot["schema_fingerprint"]:
        raise ContractError("artifact_schema_mismatch")
    return target


def _journal_for(plan: dict[str, Any], prior: dict[str, Any]) -> tuple[dict[str, Any], str, str]:
    plan_digest = digest(plan)
    operation_id = plan_digest[7:]
    target = validate(
        {
            "format_version": 1,
            "generation": prior["generation"] + 1,
            "artifact_digest": plan["target_artifact_digest"],
            "source": "managed",
            "recipe_id": plan["recipe_id"],
            "activated_plan_digest": plan_digest,
        },
        "Selection",
    )
    now = timestamp()
    journal = validate(
        {
            "format_version": 1,
            "operation_id": operation_id,
            "plan_digest": plan_digest,
            "phase": "prepared",
            "prior_selection": prior,
            "target_selection": target,
            "started_at": now,
            "updated_at": now,
            "failure": None,
        },
        "Journal",
    )
    return journal, operation_id, plan_digest


def apply(plan: dict[str, Any], context: Any) -> dict[str, Any]:
    try:
        journal_dir, selection_dir, current_path = _paths(context)
    except ContractError as exc:
        return result("invalid", reason=exc.code)
    with activation_lock(context.managed_root) as acquired:
        if not acquired:
            return result("busy", reason="lock_busy")
        recovered = recover_locked(context, journal_dir, selection_dir, current_path)
        if recovered is not None:
            return recovered
        try:
            recipe = plan_trust(plan, context)
        except ContractError as exc:
            status = "stale_plan" if exc.code == "stale_plan" else "invalid"
            return result(status, plan_digest=digest(plan) if isinstance(plan, dict) else None, reason=exc.code)
        plan_digest = digest(plan)
        operation_id = plan_digest[7:]
        prior = selection(current_path)
        if prior is None:
            return result("invalid", operation_id=operation_id, plan_digest=plan_digest, reason="selection_missing")
        if (
            prior["artifact_digest"] == plan["target_artifact_digest"]
            and prior["activated_plan_digest"] == plan_digest
        ):
            try:
                snapshot = recapture_matching(context, recipe["schema_fingerprint"])
                _target_artifact(plan, snapshot, context)
            except ContractError as exc:
                status = "storage_changing" if exc.code == "storage_changing" else "stale_plan" if exc.code == "stale_recapture" else "failed"
                reason = "storage_changing" if exc.code == "stale_recapture" else exc.code
                return result(status, operation_id=operation_id, plan_digest=plan_digest, current=prior, reason=reason)
            return result("no_op", operation_id=operation_id, plan_digest=plan_digest, current=prior)
        try:
            _observation, snapshot = source_preconditions(plan, context, recipe)
        except ContractError as exc:
            status = "storage_changing" if exc.code == "storage_changing" else "stale_plan"
            reason = "storage_changing" if exc.code == "stale_recapture" else exc.code
            return result(status, operation_id=operation_id, plan_digest=plan_digest, current=prior, reason=reason)
        if (
            prior["artifact_digest"] != plan["source_adapter_digest"]
            or digest(prior) != plan["prior_selection_digest"]
        ):
            return result("stale_plan", operation_id=operation_id, plan_digest=plan_digest, current=prior, reason="source_identity_mismatch")
        journal, operation_id, plan_digest = _journal_for(plan, prior)
        journal_path = journal_dir / f"{operation_id}.json"
        journal_binding(journal_path, journal)
        phase(journal_path, journal, "prepared", context)
        try:
            target = _target_artifact(plan, snapshot, context)
            phase(journal_path, journal, "artifact_verified", context)
            directory(context.managed_root, f"staging/{operation_id}")
            phase(journal_path, journal, "staged", context)
        except ContractError as exc:
            phase(journal_path, journal, "failed", context, exc.code)
            return result("failed", operation_id=operation_id, plan_digest=plan_digest, prior=prior, current=prior, reason=exc.code)
        executed: list[str] = []
        for check_id in CHECK_IDS:
            executed.append(check_id)
            callback = context.check_registry.get(check_id)
            try:
                passed = callback is not None and callback(target, context) is True
            except Exception:
                passed = False
            if not passed:
                phase(journal_path, journal, "failed", context, "check_failed")
                return result("failed", operation_id=operation_id, plan_digest=plan_digest, prior=prior, current=prior, checks=executed, reason="check_failed")
        phase(journal_path, journal, "checks_passed", context)
        target_selection = journal["target_selection"]
        try:
            recapture_matching(context, recipe["schema_fingerprint"])
        except ContractError as exc:
            phase(journal_path, journal, "failed", context, exc.code)
            return result(
                "storage_changing", operation_id=operation_id,
                plan_digest=plan_digest, prior=prior, current=prior,
                checks=executed, reason="storage_changing",
            )
        write_selection(selection_dir, current_path, prior, target_selection)
        phase(journal_path, journal, "selection_committed", context)
        if not postcheck(target, context):
            phase(journal_path, journal, "rollback_required", context, "postcheck_failed")
            write_selection(selection_dir, current_path, target_selection, prior)
            phase(journal_path, journal, "rolled_back", context, "postcheck_failed")
            return result("failed", operation_id=operation_id, plan_digest=plan_digest, prior=prior, current=prior, checks=executed, reason="postcheck_failed")
        phase(journal_path, journal, "postcheck_passed", context)
        phase(journal_path, journal, "complete", context)
        return result("active", operation_id=operation_id, plan_digest=plan_digest, prior=prior, current=target_selection, checks=executed)


def recover_pending(context: Any) -> dict[str, Any] | None:
    try:
        journal_dir, selection_dir, current_path = _paths(context)
    except ContractError as exc:
        return result("invalid", reason=exc.code)
    with activation_lock(context.managed_root) as acquired:
        if not acquired:
            return result("busy", reason="lock_busy")
        return recover_locked(context, journal_dir, selection_dir, current_path)


def rollback(operation_id: str, context: Any) -> dict[str, Any]:
    if not isinstance(operation_id, str) or len(operation_id) != 64 or any(character not in "0123456789abcdef" for character in operation_id):
        return result("invalid", reason="invalid_operation_id")
    try:
        journal_dir, selection_dir, current_path = _paths(context)
    except ContractError as exc:
        return result("invalid", reason=exc.code)
    with activation_lock(context.managed_root) as acquired:
        if not acquired:
            return result("busy", reason="lock_busy")
        recovered = recover_locked(context, journal_dir, selection_dir, current_path)
        if recovered is not None and recovered["operation_id"] == operation_id:
            return recovered
        path = journal_dir / f"{operation_id}.json"
        try:
            journal = read_json(path, "Journal")
            if journal is None:
                raise ContractError("unknown_operation_id")
            journal_binding(path, journal)
            prior = journal["prior_selection"]
            current = selection(current_path)
            if prior is None or current is None:
                raise ContractError("rollback_unavailable")
            target = journal["target_selection"]
            if journal["phase"] == "rolled_back":
                already_restored = (
                    current["artifact_digest"] == prior["artifact_digest"]
                    and current["activated_plan_digest"] == journal["plan_digest"]
                    and current["generation"] > target["generation"]
                )
                if already_restored:
                    return result(
                        "no_op",
                        operation_id=operation_id,
                        plan_digest=journal["plan_digest"],
                        prior=target,
                        current=current,
                    )
            if current != target:
                return result(
                    "stale_plan",
                    operation_id=operation_id,
                    plan_digest=journal["plan_digest"],
                    current=current,
                    reason="selection_mismatch",
                )
            old = artifacts.resolve(prior["artifact_digest"], context)
            artifacts.manifest(old, prior["artifact_digest"])
        except ContractError as exc:
            if exc.code == "record_missing":
                return result("invalid", operation_id=operation_id, reason="unknown_operation_id")
            status = "invalid" if exc.code == "unknown_operation_id" else "failed"
            return result(status, operation_id=operation_id, reason=exc.code)
        restored = validate(
            {
                **prior,
                "generation": current["generation"] + 1,
                "activated_plan_digest": journal["plan_digest"],
            },
            "Selection",
        )
        write_selection(selection_dir, current_path, current, restored)
        phase(path, journal, "rolled_back", context)
        compatible = postcheck(old, context)
        return result(
            "rolled_back" if compatible else "rolled_back_incompatible",
            operation_id=operation_id,
            plan_digest=journal["plan_digest"],
            prior=current,
            current=restored,
            reason=None if compatible else "schema_unsupported_after_rollback",
        )
