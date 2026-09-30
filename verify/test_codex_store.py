"""Independent durable-store acceptance tests for Codex adapter activation."""

from __future__ import annotations

import importlib.util
import json
import os
import subprocess
import sys
import time
from pathlib import Path

import pytest

from session_recall.codex_fix.contracts import digest
from session_recall.codex_fix.store import apply, recover_pending, rollback

ROOT = Path(__file__).resolve().parents[1]
FIXTURES_PATH = ROOT / "verify" / "codex_store_fixtures.py"


def _load_fixtures():
    spec = importlib.util.spec_from_file_location("codex_store_fixtures", FIXTURES_PATH)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


FIXTURES = _load_fixtures()
CHECK_IDS = FIXTURES.CHECK_IDS
database_hashes = FIXTURES.database_hashes
load_case = FIXTURES.load_case
load_context = FIXTURES.load_context
prepare_case = FIXTURES.prepare_case
WORKER = r"""
import json, sys
from pathlib import Path
sys.path.insert(0, str(Path(sys.argv[1]) / 'verify'))
from codex_store_fixtures import FilePhaseHook, load_case
from session_recall.codex_fix.store import apply
root = Path(sys.argv[2])
phase = None if sys.argv[3] == '-' else sys.argv[3]
ready = None if sys.argv[4] == '-' else Path(sys.argv[4])
release = None if sys.argv[5] == '-' else Path(sys.argv[5])
crash = None if sys.argv[6] == '-' else int(sys.argv[6])
hook = FilePhaseHook(phase, ready=ready, release=release, crash_code=crash) if phase else None
case = load_case(root, hooks=hook)
print(json.dumps(apply(case.plan, case.context), sort_keys=True), flush=True)
"""


@pytest.fixture()
def store_case(tmp_path):
    return prepare_case(tmp_path / "case")


def _selection(case) -> dict:
    return json.loads(case.context.paths["current_selection"].read_text(encoding="utf-8"))


def _worker(root: Path, phase="-", ready="-", release="-", crash="-"):
    return subprocess.Popen(
        [
            sys.executable,
            "-c",
            WORKER,
            str(ROOT),
            str(root),
            str(phase),
            str(ready),
            str(release),
            str(crash),
        ],
        cwd=ROOT,
        env={**os.environ, "PYTHONDONTWRITEBYTECODE": "1"},
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )


def _wait_for(path: Path, process: subprocess.Popen, timeout: float = 10) -> None:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if path.exists():
            return
        assert process.poll() is None, process.stderr.read()
        time.sleep(0.02)
    pytest.fail(f"timed out waiting for {path.name}")


def test_apply_active_all_checks_and_repeat_is_no_op(store_case):
    before_hashes = database_hashes(store_case.context.managed_root.parent)
    result = apply(store_case.plan, store_case.context)
    assert result["status"] == "active"
    assert result["operation_id"] == digest(store_case.plan)[7:]
    assert result["executed_check_ids"] == CHECK_IDS
    assert store_case.calls == CHECK_IDS
    selected = _selection(store_case)
    assert selected["artifact_digest"] == store_case.metadata["target_digest"]
    assert selected["generation"] == 8
    journal = json.loads(
        (
            store_case.context.managed_root
            / "journal"
            / f"{store_case.operation_id}.json"
        ).read_text(encoding="utf-8")
    )
    assert journal["operation_id"] == store_case.operation_id
    assert journal["phase"] == "complete"

    selected_bytes = store_case.context.paths["current_selection"].read_bytes()
    repeated = apply(store_case.plan, store_case.context)
    assert repeated["status"] == "no_op"
    assert repeated["current_selection"] == selected
    assert store_case.context.paths["current_selection"].read_bytes() == selected_bytes
    assert database_hashes(store_case.context.managed_root.parent) == before_hashes


def test_stale_recapture_before_commit_refuses_without_selection_change(store_case):
    stale = load_case(
        store_case.context.managed_root.parent,
        stale_recapture=True,
    )
    before = stale.context.paths["current_selection"].read_bytes()
    result = apply(stale.plan, stale.context)
    assert result["status"] == "stale_plan"
    assert result["reason_code"] == "storage_changing"
    assert stale.context.paths["current_selection"].read_bytes() == before


def test_forged_check_set_and_failed_check_never_activate(store_case):
    selection_path = store_case.context.paths["current_selection"]
    before = selection_path.read_bytes()
    forged = {**store_case.plan, "check_ids": CHECK_IDS[:-1]}
    forged_result = apply(forged, store_case.context)
    assert forged_result["status"] == "invalid"
    assert forged_result["reason_code"] == "invalid_check_set"
    assert selection_path.read_bytes() == before

    failed = load_case(
        store_case.context.managed_root.parent,
        failing_check="trial_cli_contract_v1",
    )
    failed_result = apply(failed.plan, failed.context)
    assert failed_result["status"] == "failed"
    assert failed_result["reason_code"] == "check_failed"
    assert failed_result["executed_check_ids"] == CHECK_IDS[:3]
    assert selection_path.read_bytes() == before


@pytest.mark.parametrize("kind", ["tamper", "symlink"])
def test_target_tamper_or_symlink_refuses_activation(tmp_path, kind):
    case = prepare_case(tmp_path / kind)
    target = Path(case.metadata["target_path"])
    if kind == "tamper":
        target.write_bytes(target.read_bytes() + b"tamper")
    else:
        backup = tmp_path / "outside-target.pyz"
        backup.write_bytes(target.read_bytes())
        target.unlink()
        target.symlink_to(backup)
    before = case.context.paths["current_selection"].read_bytes()
    result = apply(case.plan, case.context)
    assert result["status"] == "failed"
    assert case.context.paths["current_selection"].read_bytes() == before


def test_one_writer_lock_returns_busy_while_first_writer_is_barriered(store_case):
    root = store_case.context.managed_root.parent
    ready, release = root / "writer-ready", root / "writer-release"
    first = _worker(root, "prepared", ready, release)
    _wait_for(ready, first)
    second = _worker(root)
    second_out, second_err = second.communicate(timeout=10)
    assert second.returncode == 0, second_err
    assert json.loads(second_out)["status"] == "busy"
    release.write_text("release", encoding="utf-8")
    first_out, first_err = first.communicate(timeout=15)
    assert first.returncode == 0, first_err
    assert json.loads(first_out)["status"] == "active"


@pytest.mark.parametrize(
    ("phase", "reason"),
    [
        ("prepared", "rolled_back_before_commit"),
        ("selection_committed", "completed_after_commit"),
    ],
)
def test_os_exit_recovery_reconciles_actual_state(tmp_path, phase, reason):
    case = prepare_case(tmp_path / phase)
    crashed = _worker(case.context.managed_root.parent, phase, "-", "-", 91)
    _stdout, _stderr = crashed.communicate(timeout=15)
    assert crashed.returncode == 91
    recovered_context = load_context(case.context.managed_root.parent)
    result = recover_pending(recovered_context.context)
    assert result["status"] == "recovered"
    assert result["reason_code"] == reason
    selected = json.loads(
        recovered_context.context.paths["current_selection"].read_text(encoding="utf-8")
    )
    expected = (
        case.metadata["source_digest"]
        if phase == "prepared"
        else case.metadata["target_digest"]
    )
    assert selected["artifact_digest"] == expected


def test_corrupt_active_target_rollback_restores_52_and_reports_incompatible(store_case):
    applied = apply(store_case.plan, store_case.context)
    assert applied["status"] == "active"
    Path(store_case.metadata["target_path"]).write_bytes(b"corrupt-active-target")

    result = rollback(store_case.operation_id, store_case.context)
    assert result["status"] == "rolled_back_incompatible"
    assert result["reason_code"] == "schema_unsupported_after_rollback"
    selected = _selection(store_case)
    assert selected["artifact_digest"] == store_case.metadata["source_digest"]
    assert selected["generation"] == 9
    assert selected["artifact_digest"] != applied["current_selection"]["artifact_digest"]
