from __future__ import annotations

import importlib.util
import json
import os
import sqlite3
import subprocess
import sys
from dataclasses import replace
from pathlib import Path

import pytest
from session_recall.codex_fix import cli
from session_recall.codex_fix.contracts import canonical_bytes, digest, validate
from session_recall.codex_fix.store import apply, recover_pending
from session_recall.codex_metadata import StorageChangingError


ROOT = Path(__file__).resolve().parents[1]
FIXTURES_PATH = ROOT / "verify" / "codex_store_fixtures.py"


def _load_fixtures():
    existing = sys.modules.get("codex_store_fixtures")
    if existing is not None:
        return existing
    spec = importlib.util.spec_from_file_location("codex_store_fixtures", FIXTURES_PATH)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


FIXTURES = _load_fixtures()
WORKER = r"""
import os, sys
from pathlib import Path
sys.path.insert(0, str(Path(sys.argv[1]) / 'verify'))
from codex_store_fixtures import FilePhaseHook, load_case
from session_recall.codex_fix.store import apply
root, phase, mode = Path(sys.argv[2]), sys.argv[3], sys.argv[4]
if mode == 'normal':
    hook = FilePhaseHook(phase, crash_code=91)
else:
    class RollbackHook:
        def on_phase(self, value):
            if value == 'selection_committed':
                case_path.write_bytes(b'broken-target-after-commit')
            if value == phase:
                os._exit(91)
    seed = load_case(root)
    case_path = Path(seed.metadata['target_path'])
    hook = RollbackHook()
case = load_case(root, hooks=hook)
apply(case.plan, case.context)
"""


def _write(path: Path, value: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(canonical_bytes(value))


def _crash(case, phase: str, mode: str = "normal") -> None:
    result = subprocess.run(
        [
            sys.executable,
            "-c",
            WORKER,
            str(ROOT),
            str(case.context.managed_root.parent),
            phase,
            mode,
        ],
        cwd=ROOT,
        env={**os.environ, "PYTHONDONTWRITEBYTECODE": "1"},
        capture_output=True,
        text=True,
        timeout=15,
        check=False,
    )
    assert result.returncode == 91, result.stderr


def test_null_prior_failed_target_recovery_is_truthful_failure(tmp_path):
    case = FIXTURES.prepare_case(tmp_path / "null-prior")
    plan_digest = digest(case.plan)
    target = validate(
        {
            "format_version": 1,
            "generation": 8,
            "artifact_digest": case.metadata["target_digest"],
            "source": "managed",
            "recipe_id": case.plan["recipe_id"],
            "activated_plan_digest": plan_digest,
        },
        "Selection",
    )
    journal = validate(
        {
            "format_version": 1,
            "operation_id": plan_digest[7:],
            "plan_digest": plan_digest,
            "phase": "selection_committed",
            "prior_selection": None,
            "target_selection": target,
            "started_at": "2026-09-20T00:00:00Z",
            "updated_at": "2026-09-20T00:00:00Z",
            "failure": None,
        },
        "Journal",
    )
    selection_path = case.context.paths["current_selection"]
    _write(selection_path, target)
    journal_path = case.context.managed_root / "journal" / f"{plan_digest[7:]}.json"
    _write(journal_path, journal)
    Path(case.metadata["target_path"]).write_bytes(b"broken-selected-target")
    selected_before = selection_path.read_bytes()

    result = recover_pending(case.context)
    assert result["status"] == "failed"
    assert result["reason_code"] == "recovery_unavailable"
    assert result["current_selection"] == target
    assert selection_path.read_bytes() == selected_before
    assert json.loads(journal_path.read_text(encoding="utf-8"))["phase"] == "failed"


def _changing():
    raise StorageChangingError("synthetic metadata changed")


def test_apply_recapture_change_is_transient_storage_changing(tmp_path):
    case = FIXTURES.prepare_case(tmp_path / "changing-apply")
    context = replace(case.context, recapture=_changing)
    before = context.paths["current_selection"].read_bytes()

    result = apply(case.plan, context)
    assert result["status"] == "storage_changing"
    assert result["reason_code"] == "storage_changing"
    assert context.paths["current_selection"].read_bytes() == before


def test_cli_apply_recapture_change_exits_three_with_json_status(tmp_path, capsys):
    case = FIXTURES.prepare_case(tmp_path / "changing-cli")
    stable_recapture = case.context.recapture
    calls = 0

    def recapture_then_change():
        nonlocal calls
        calls += 1
        if calls == 1:
            return stable_recapture()
        raise StorageChangingError("synthetic metadata changed")

    context = replace(
        case.context,
        recapture=recapture_then_change,
        current_observation=None,
    )
    plan_path = tmp_path / "plan.json"
    plan_path.write_bytes(canonical_bytes(case.plan))
    before = context.paths["current_selection"].read_bytes()

    code = cli.main(
        ["--json", "apply", "--plan", str(plan_path)],
        context_factory=lambda _args: context,
    )
    body = json.loads(capsys.readouterr().out)
    assert code == 3
    assert body["ok"] is False
    assert body["status"] == "storage_changing"
    assert body["detail"]["status"] == "storage_changing"
    assert body["detail"]["reason_code"] == "storage_changing"
    assert context.paths["current_selection"].read_bytes() == before


def test_last_check_metadata_change_is_caught_before_selection(tmp_path):
    case = FIXTURES.prepare_case(tmp_path / "last-check-change")
    phases = []

    class RecordingHooks:
        def on_phase(self, phase):
            phases.append(phase)

    checks = dict(case.context.check_registry)
    original = checks[FIXTURES.CHECK_IDS[-1]]

    def mutate_after_check(artifact, context):
        assert original(artifact, context) is True
        connection = sqlite3.connect(context.paths["state_db"])
        try:
            connection.execute("ALTER TABLE threads ADD COLUMN changed_after_checks TEXT")
            connection.commit()
        finally:
            connection.close()
        return True

    checks[FIXTURES.CHECK_IDS[-1]] = mutate_after_check
    context = replace(case.context, check_registry=checks, test_hooks=RecordingHooks())
    before = context.paths["current_selection"].read_bytes()

    result = apply(case.plan, context)
    assert result["status"] == "storage_changing"
    assert result["reason_code"] == "storage_changing"
    assert "selection_committed" not in phases
    assert context.paths["current_selection"].read_bytes() == before


def test_fresh_production_cli_reapply_is_exact_no_op(tmp_path, capsys):
    case = FIXTURES.prepare_case(tmp_path / "fresh-cli-no-op")
    root = case.context.managed_root
    store = root.parent / "synthetic-55"
    common = [
        "--json",
        "--root",
        str(root),
        "--state-db",
        str(store / "state_5.sqlite"),
        "--history-db",
        str(store / "thread_history_1.sqlite"),
        "--sessions-root",
        str(store / "sessions"),
    ]
    assert cli.main([*common, "plan"]) == 0
    planned = json.loads(capsys.readouterr().out)
    assert planned["status"] == "planned"
    plan_path = tmp_path / "production-plan.json"
    plan_path.write_bytes(canonical_bytes(planned["detail"]))

    assert cli.main([*common, "apply", "--plan", str(plan_path)]) == 0
    active = json.loads(capsys.readouterr().out)
    assert active["status"] == "active"
    selection_path = root / "selection" / "current.json"
    selected = selection_path.read_bytes()
    generation = json.loads(selected)["generation"]

    assert cli.main([*common, "apply", "--plan", str(plan_path)]) == 0
    repeated = json.loads(capsys.readouterr().out)
    assert repeated["status"] == "no_op"
    assert selection_path.read_bytes() == selected
    assert json.loads(selected)["generation"] == generation


@pytest.mark.parametrize(
    ("phase", "reason", "selected"),
    [
        ("artifact_verified", "rolled_back_before_commit", "source"),
        ("staged", "rolled_back_before_commit", "source"),
        ("checks_passed", "rolled_back_before_commit", "source"),
        ("postcheck_passed", "completed_after_commit", "target"),
    ],
)
def test_recovery_at_remaining_normal_durable_boundaries(
    tmp_path, phase, reason, selected
):
    case = FIXTURES.prepare_case(tmp_path / phase)
    _crash(case, phase)
    loaded = FIXTURES.load_context(case.context.managed_root.parent)
    result = recover_pending(loaded.context)
    assert result["status"] == "recovered"
    assert result["reason_code"] == reason
    current = json.loads(
        loaded.context.paths["current_selection"].read_text(encoding="utf-8")
    )
    expected = case.metadata[f"{selected}_digest"]
    assert current["artifact_digest"] == expected


def test_complete_boundary_needs_no_recovery(tmp_path):
    case = FIXTURES.prepare_case(tmp_path / "complete")
    _crash(case, "complete")
    loaded = FIXTURES.load_context(case.context.managed_root.parent)
    assert recover_pending(loaded.context) is None
    assert json.loads(
        loaded.context.paths["current_selection"].read_text(encoding="utf-8")
    )["artifact_digest"] == case.metadata["target_digest"]


@pytest.mark.parametrize(
    ("phase", "expected_reason"),
    [
        ("rollback_required", "rolled_back_after_failed_postcheck"),
        ("rolled_back", None),
    ],
)
def test_failed_postcheck_rollback_boundaries(tmp_path, phase, expected_reason):
    case = FIXTURES.prepare_case(tmp_path / phase)
    _crash(case, phase, "rollback")
    loaded = FIXTURES.load_context(case.context.managed_root.parent)
    result = recover_pending(loaded.context)
    if phase == "rollback_required":
        assert result["status"] == "recovered"
        assert result["reason_code"] == expected_reason
    else:
        assert result is None
    assert json.loads(
        loaded.context.paths["current_selection"].read_text(encoding="utf-8")
    )["artifact_digest"] == case.metadata["source_digest"]
