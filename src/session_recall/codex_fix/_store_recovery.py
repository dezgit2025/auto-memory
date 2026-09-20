"""Recovery reconciliation for interrupted adapter store operations."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from . import artifacts
from ._store_io import phase, postcheck, read_json, result, selection, write_selection
from .contracts import ContractError

PENDING_PHASES = {
    "prepared",
    "artifact_verified",
    "staged",
    "checks_passed",
    "selection_committed",
    "postcheck_passed",
    "rollback_required",
}


def journal_binding(path: Path, journal: dict[str, Any]) -> None:
    operation_id = journal["operation_id"]
    plan_digest = journal["plan_digest"]
    if (
        path.name != f"{operation_id}.json"
        or plan_digest != f"sha256:{operation_id}"
        or journal["target_selection"]["activated_plan_digest"] != plan_digest
    ):
        raise ContractError("journal_binding_mismatch")


def _recover_one(
    path: Path,
    context: Any,
    selection_dir: Path,
    current_path: Path,
) -> dict[str, Any]:
    journal = read_json(path, "Journal")
    assert journal is not None
    journal_binding(path, journal)
    current = selection(current_path)
    prior = journal["prior_selection"]
    target_selection = journal["target_selection"]
    if current == prior:
        phase(path, journal, "rolled_back", context)
        return result(
            "recovered",
            operation_id=journal["operation_id"],
            plan_digest=journal["plan_digest"],
            prior=prior,
            current=current,
            reason="rolled_back_before_commit",
        )
    if current == target_selection:
        try:
            target = artifacts.resolve(target_selection["artifact_digest"], context)
            artifacts.manifest(target, target_selection["artifact_digest"])
            healthy = postcheck(target, context)
        except ContractError:
            healthy = False
        if healthy:
            phase(path, journal, "postcheck_passed", context)
            phase(path, journal, "complete", context)
            return result(
                "recovered",
                operation_id=journal["operation_id"],
                plan_digest=journal["plan_digest"],
                prior=prior,
                current=current,
                reason="completed_after_commit",
            )
        if prior is None:
            phase(path, journal, "failed", context, "recovery_unavailable")
            return result(
                "failed", operation_id=journal["operation_id"],
                plan_digest=journal["plan_digest"], current=current,
                reason="recovery_unavailable",
            )
        try:
            old = artifacts.resolve(prior["artifact_digest"], context)
            artifacts.manifest(old, prior["artifact_digest"])
            write_selection(selection_dir, current_path, current, prior)
            current = prior
        except ContractError:
            phase(path, journal, "failed", context, "recovery_unavailable")
            return result(
                "failed", operation_id=journal["operation_id"],
                plan_digest=journal["plan_digest"], prior=prior,
                current=current, reason="recovery_unavailable",
            )
        phase(path, journal, "rolled_back", context, "postcheck_failed")
        return result(
            "recovered",
            operation_id=journal["operation_id"],
            plan_digest=journal["plan_digest"],
            prior=prior,
            current=current,
            reason="rolled_back_after_failed_postcheck",
        )
    phase(path, journal, "failed", context, "selection_mismatch")
    return result(
        "failed",
        operation_id=journal["operation_id"],
        plan_digest=journal["plan_digest"],
        prior=prior,
        current=current,
        reason="selection_mismatch",
    )


def recover_locked(
    context: Any,
    journal_dir: Path,
    selection_dir: Path,
    current_path: Path,
) -> dict[str, Any] | None:
    for path in sorted(journal_dir.glob("*.json")):
        try:
            journal = read_json(path, "Journal")
            assert journal is not None
            journal_binding(path, journal)
        except ContractError:
            return result(
                "failed",
                current=selection(current_path),
                reason="journal_binding_mismatch",
            )
        if journal["phase"] in PENDING_PHASES:
            return _recover_one(path, context, selection_dir, current_path)
    return None
