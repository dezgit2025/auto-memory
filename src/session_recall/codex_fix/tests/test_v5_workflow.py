"""End-to-end V5 candidate review, approval, activation, and rollback gates."""

from __future__ import annotations

from dataclasses import replace
import io
import json

import pytest

from session_recall.codex_fix import approval, assist, cli, launcher, store
from session_recall.codex_fix import _assist_budget
from session_recall.codex_fix._assist_budget import approve_budget
from session_recall.codex_fix.policy import model_policy
from session_recall.codex_fix.contracts import ContractError, canonical_bytes
from session_recall.codex_fix.sandbox import Sandbox

from ._v5_workflow_fixtures import (
    CHECK_IDS,
    RecordingGenerate,
    build_workflow_world,
    database_hashes,
    production_context,
    refreshed_context,
    selection_bytes,
)


@pytest.fixture(autouse=True)
def historical_v2_policy(monkeypatch):
    monkeypatch.setattr(assist, "production_model_policy", model_policy)
    monkeypatch.setattr(_assist_budget, "production_model_policy", model_policy)


@pytest.fixture()
def workflow_world(synthetic_store):
    return build_workflow_world(synthetic_store)


def _generate_review(world, generator=None):
    selected = world.generator if generator is None else generator
    before_selection = selection_bytes(world)
    before_databases = database_hashes(world)
    result = assist.assist(world.context, generate_fn=selected, sandbox=Sandbox())
    assert result["status"] == "action_needed"
    assert result["action"] == "candidate_review"
    assert len(result["candidate_id"]) == 64
    assert result["review"]["check_ids"] == [*CHECK_IDS, "sandbox_denials_v1"]
    assert result["review"]["verdict"] == "pass"
    assert isinstance(result["diff"], str) and result["diff"]
    assert "rollback --repair OPERATION_ID" in result["rollback"]
    assert selection_bytes(world) == before_selection
    assert database_hashes(world) == before_databases
    stored = approval.load_review(world.context.managed_root, result["candidate_id"])
    assert stored["result"] == result["review"]
    return result


def test_unknown_to_review_approval_activation_launcher_and_rollback(
    workflow_world, monkeypatch, capsys
):
    world = workflow_world
    original_databases = database_hashes(world)
    pending = _generate_review(world)
    candidate_id = pending["candidate_id"]
    assert len(world.generator.calls) == 1

    before_unconfirmed = selection_bytes(world)
    monkeypatch.setattr(cli.sys, "stdin", io.StringIO("yes\n"))
    code = cli.main(
        ["--json", "approve", "--candidate", candidate_id],
        context_factory=lambda _args: world.context,
    )
    body = json.loads(capsys.readouterr().out)
    assert code == 2 and body["status"] == "action_needed"
    assert selection_bytes(world) == before_unconfirmed
    assert not (world.context.managed_root / "approvals" / f"{candidate_id}.json").exists()

    unchanged = approval.effective_catalogue(world.catalogue, world.context)
    assert unchanged == world.catalogue
    approved = approval.approve(candidate_id, world.context, actor="workflow-maintainer")
    assert approved["decision"] == "approved"
    with pytest.raises(ContractError, match="approval_conflict"):
        approval.approve(candidate_id, world.context, actor="different-maintainer")
    effective = approval.effective_catalogue(world.catalogue, world.context)
    assert len(effective["recipes"]) == len(world.catalogue["recipes"]) + 1

    fresh = refreshed_context(world, effective)
    applied = assist.apply_candidate(candidate_id, fresh)
    assert applied["status"] == "active"
    restarted = production_context(world)
    selected_path, manifest = launcher._selected(restarted)
    assert selected_path.is_file()
    assert manifest["profile_ids"]["state"] == "codex-state-v5-migration-56"
    assert database_hashes(world) == original_databases

    repeated = assist.apply_candidate(candidate_id, restarted)
    assert repeated["status"] == "no_op"
    rolled_back = store.rollback(applied["operation_id"], restarted)
    assert rolled_back["status"] == "rolled_back_incompatible"
    rollback_restart = production_context(world)
    restored_path, restored_manifest = launcher._selected(rollback_restart)
    assert restored_path.is_file()
    assert restored_manifest["profile_ids"]["state"] == "codex-state-v5-migration-57"


def test_corrupt_active_candidate_does_not_block_fresh_cli_rollback(
    workflow_world, capsys
):
    world = workflow_world
    pending = _generate_review(world)
    candidate_id = pending["candidate_id"]
    approval.approve(candidate_id, world.context, actor="workflow-maintainer")
    applied = assist.apply_candidate(candidate_id, world.context)
    assert applied["status"] == "active"
    restarted = production_context(world)
    active_path, _manifest = launcher._selected(restarted)
    active_path.write_bytes(b"corrupt candidate")

    recovery = production_context(world)
    code = cli.main(
        ["--json", "rollback", "--repair", applied["operation_id"]],
        context_factory=lambda _args: recovery,
    )
    body = json.loads(capsys.readouterr().out)
    assert code == 0
    assert body["status"] == "rolled_back_incompatible"
    restored = production_context(world)
    _path, manifest = launcher._selected(restored)
    assert manifest["profile_ids"]["state"] == "codex-state-v5-migration-57"


def test_same_target_different_candidate_cannot_create_ambiguous_approval(
    workflow_world
):
    world = workflow_world
    first = _generate_review(world)
    budget = assist.assist(
        world.context, generate_fn=world.generator, sandbox=Sandbox()
    )
    assert budget["action"] == "budget_approval"
    approve_budget(world.context.managed_root, budget["challenge"]["challenge_id"])
    variant = RecordingGenerate(world.snapshot, mutation="same_target_variant")
    second = _generate_review(world, generator=variant)
    assert second["candidate_id"] != first["candidate_id"]
    first_review = approval.load_review(
        world.context.managed_root, first["candidate_id"]
    )
    second_review = approval.load_review(
        world.context.managed_root, second["candidate_id"]
    )
    assert second_review["artifact_digest"] == first_review["artifact_digest"]

    approval.approve(first["candidate_id"], world.context, actor="maintainer")
    with pytest.raises(ContractError, match="ambiguous_candidate_approval"):
        approval.approve(second["candidate_id"], world.context, actor="maintainer")
    approvals = list((world.context.managed_root / "approvals").glob("*.json"))
    assert [path.stem for path in approvals] == [first["candidate_id"]]


def test_stale_schema_and_tampered_review_never_approve(workflow_world):
    world = workflow_world
    pending = _generate_review(world)
    candidate_id = pending["candidate_id"]
    review_path = world.context.managed_root / "candidates" / candidate_id / "review.json"
    original = review_path.read_bytes()
    tampered = {**pending["review"], "artifact_digest": "sha256:" + "0" * 64}
    review_path.write_bytes(canonical_bytes(tampered))
    with pytest.raises(ContractError):
        approval.approve(candidate_id, world.context, actor="maintainer")
    assert not (world.context.managed_root / "approvals" / f"{candidate_id}.json").exists()
    review_path.write_bytes(original)

    stale_snapshot = {**world.snapshot, "schema_fingerprint": "sha256:" + "9" * 64}
    stale = replace(world.context, recapture=lambda: stale_snapshot)
    with pytest.raises(ContractError, match="stale_candidate_schema"):
        approval.approve(candidate_id, stale, actor="maintainer")


@pytest.mark.parametrize("mutation", ["self_approval", "wrong_profile"])
def test_generated_self_approval_or_failing_candidate_never_activates(
    workflow_world, mutation
):
    world = workflow_world
    generator = RecordingGenerate(world.snapshot, mutation=mutation)
    before = selection_bytes(world)
    with pytest.raises(ContractError):
        assist.assist(world.context, generate_fn=generator, sandbox=Sandbox())
    assert selection_bytes(world) == before
    assert not (world.context.managed_root / "approvals").exists()
    assert len(generator.calls) == 1


def test_repeat_assist_requests_budget_approval_without_retry(workflow_world):
    world = workflow_world
    _generate_review(world)
    before = selection_bytes(world)
    second = assist.assist(world.context, generate_fn=world.generator, sandbox=Sandbox())
    assert second["status"] == "action_needed"
    assert second["action"] == "budget_approval"
    assert isinstance(second["challenge"], dict)
    assert len(second["challenge"]["challenge_id"]) == 64
    third = assist.assist(world.context, generate_fn=world.generator, sandbox=Sandbox())
    assert third["status"] == "action_needed"
    assert third["action"] == "budget_approval"
    assert third["challenge"] == second["challenge"]
    assert len(world.generator.calls) == 1
    assert selection_bytes(world) == before
    approve_budget(world.context.managed_root, second["challenge"]["challenge_id"])
    with pytest.raises(ContractError):
        approve_budget(world.context.managed_root, second["challenge"]["challenge_id"])
    resumed = assist.assist(
        world.context, generate_fn=world.generator, sandbox=Sandbox()
    )
    assert resumed["status"] == "action_needed"
    assert resumed["action"] == "candidate_review"
    assert len(world.generator.calls) == 2
