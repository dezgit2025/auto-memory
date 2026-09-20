"""Adversarial cross-binding and artifact-bound tests for the managed store."""

from __future__ import annotations

import hashlib
import importlib.util
import json
import os
import subprocess
import sys
import zipfile
from pathlib import Path

import pytest

from session_recall.codex_fix import artifacts
from session_recall.codex_fix.contracts import ContractError, canonical_bytes
from session_recall.codex_fix.store import apply, recover_pending, rollback

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
load_context = FIXTURES.load_context
prepare_case = FIXTURES.prepare_case
WORKER = r"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(sys.argv[1]) / 'verify'))
from codex_store_fixtures import FilePhaseHook, load_case
from session_recall.codex_fix.store import apply
case = load_case(Path(sys.argv[2]), hooks=FilePhaseHook(sys.argv[3], crash_code=91))
apply(case.plan, case.context)
"""


def _crash(case, phase: str) -> None:
    result = subprocess.run(
        [
            sys.executable,
            "-c",
            WORKER,
            str(ROOT),
            str(case.context.managed_root.parent),
            phase,
        ],
        cwd=ROOT,
        env={**os.environ, "PYTHONDONTWRITEBYTECODE": "1"},
        capture_output=True,
        text=True,
        timeout=15,
        check=False,
    )
    assert result.returncode == 91, result.stderr


def _selection(case) -> dict:
    return json.loads(case.context.paths["current_selection"].read_text(encoding="utf-8"))


def _journal_path(case) -> Path:
    return case.context.managed_root / "journal" / f"{case.operation_id}.json"


def _write_canonical(path: Path, value: dict) -> None:
    path.write_bytes(canonical_bytes(value))


def test_repeated_rollback_is_no_op_without_generation_change(tmp_path):
    case = prepare_case(tmp_path / "repeat-rollback")
    assert apply(case.plan, case.context)["status"] == "active"
    first = rollback(case.operation_id, case.context)
    assert first["status"] == "rolled_back_incompatible"
    before = case.context.paths["current_selection"].read_bytes()
    generation = _selection(case)["generation"]

    repeated = rollback(case.operation_id, case.context)
    assert repeated["status"] == "no_op"
    assert case.context.paths["current_selection"].read_bytes() == before
    assert _selection(case)["generation"] == generation


def test_stale_rollback_never_overwrites_newer_selection(tmp_path):
    case = prepare_case(tmp_path / "stale-rollback")
    assert apply(case.plan, case.context)["status"] == "active"
    current = _selection(case)
    newer = {
        **current,
        "generation": current["generation"] + 5,
        "activated_plan_digest": "sha256:" + "d" * 64,
    }
    _write_canonical(case.context.paths["current_selection"], newer)
    before = case.context.paths["current_selection"].read_bytes()

    result = rollback(case.operation_id, case.context)
    assert result["status"] == "stale_plan"
    assert result["reason_code"] == "selection_mismatch"
    assert case.context.paths["current_selection"].read_bytes() == before


def test_recovery_cannot_claim_rollback_when_both_artifacts_are_broken(tmp_path):
    case = prepare_case(tmp_path / "broken-both")
    _crash(case, "selection_committed")
    selected_before = case.context.paths["current_selection"].read_bytes()
    Path(case.metadata["target_path"]).write_bytes(b"broken-target")
    Path(case.metadata["source_path"]).write_bytes(b"broken-prior")

    loaded = load_context(case.context.managed_root.parent)
    result = recover_pending(loaded.context)
    assert result["status"] == "failed"
    assert result["reason_code"] == "recovery_unavailable"
    assert loaded.context.paths["current_selection"].read_bytes() == selected_before
    assert json.loads(_journal_path(case).read_text(encoding="utf-8"))["phase"] == "failed"


@pytest.mark.parametrize(
    "mutation",
    ["filename", "operation_id", "plan_digest", "target_plan_digest"],
)
def test_recovery_rejects_journal_cross_binding_without_selection_write(
    tmp_path, mutation
):
    case = prepare_case(tmp_path / f"binding-{mutation}")
    _crash(case, "prepared")
    path = _journal_path(case)
    journal = json.loads(path.read_text(encoding="utf-8"))
    if mutation == "filename":
        mutated_path = path.with_name("e" * 64 + ".json")
        path.rename(mutated_path)
        path = mutated_path
    elif mutation == "operation_id":
        journal["operation_id"] = "e" * 64
        _write_canonical(path, journal)
    elif mutation == "plan_digest":
        journal["plan_digest"] = "sha256:" + "e" * 64
        _write_canonical(path, journal)
    else:
        journal["target_selection"]["activated_plan_digest"] = "sha256:" + "e" * 64
        _write_canonical(path, journal)
    before = case.context.paths["current_selection"].read_bytes()

    loaded = load_context(case.context.managed_root.parent)
    result = recover_pending(loaded.context)
    assert result["status"] == "failed"
    assert result["reason_code"] == "journal_binding_mismatch"
    assert loaded.context.paths["current_selection"].read_bytes() == before


def _digest(path: Path) -> str:
    return "sha256:" + hashlib.sha256(path.read_bytes()).hexdigest()


def _mutant_zip(source: Path, output: Path, kind: str) -> None:
    with zipfile.ZipFile(source) as original, zipfile.ZipFile(
        output, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=9
    ) as mutant:
        for info in original.infolist():
            data = original.read(info)
            if kind == "executable" and info.filename == "__main__.py":
                data = b"x" * (1024 * 1024 + 1)
            elif kind == "resource" and info.filename == artifacts.PROFILE_RESOURCE:
                data = b"x" * (2 * 1024 * 1024 + 1)
            mutant.writestr(info, data)
        if kind == "entries":
            for index in range(max(0, 516 - len(original.infolist()))):
                mutant.writestr(f"padding/{index:04d}.txt", b"")
        elif kind == "aggregate":
            chunk = b"x" * (2 * 1024 * 1024)
            for index in range(13):
                mutant.writestr(f"aggregate/{index:02d}.bin", chunk)


@pytest.mark.parametrize("kind", ["entries", "executable", "resource", "aggregate"])
def test_pinned_zip_declared_limits_reject_before_execution(tmp_path, kind):
    case = prepare_case(tmp_path / f"zip-{kind}")
    mutant = tmp_path / f"{kind}.pyz"
    _mutant_zip(Path(case.metadata["target_path"]), mutant, kind)
    with pytest.raises(ContractError) as raised:
        artifacts.manifest(mutant, _digest(mutant))
    assert raised.value.code == "invalid_artifact"


def test_dangling_symlink_cache_parent_refuses_without_bundled_fallback(tmp_path):
    case = prepare_case(tmp_path / "dangling-parent")
    target = Path(case.metadata["target_path"])
    digest_dir = target.parent
    target.unlink()
    digest_dir.rmdir()
    digest_dir.symlink_to(tmp_path / "missing-cache-directory", target_is_directory=True)

    with pytest.raises(ContractError) as raised:
        artifacts.resolve(case.metadata["target_digest"], case.context)
    assert raised.value.code == "invalid_artifact"


def test_unknown_well_formed_operation_id_is_gracefully_refused(tmp_path):
    case = prepare_case(tmp_path / "unknown-operation")
    before = case.context.paths["current_selection"].read_bytes()
    result = rollback("f" * 64, case.context)
    assert result["status"] == "invalid"
    assert result["reason_code"] == "unknown_operation_id"
    assert case.context.paths["current_selection"].read_bytes() == before
