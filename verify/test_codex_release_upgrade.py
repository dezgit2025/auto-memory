"""Release compatibility from a managed 0.5.1 adapter to 0.6.0 and back."""

from __future__ import annotations

from argparse import Namespace
from dataclasses import replace
import hashlib
import importlib.util
from pathlib import Path
import subprocess
import sys

from session_recall.codex_fix import cli, engine, factory, launcher, store, trust
from session_recall.codex_fix.contracts import canonical_bytes

ROOT = Path(__file__).resolve().parents[1]
COMMON = ROOT / "verify/fix_cli_codex_common.py"
SPEC = importlib.util.spec_from_file_location("release_upgrade_common", COMMON)
assert SPEC is not None and SPEC.loader is not None
VERIFY_COMMON = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = VERIFY_COMMON
SPEC.loader.exec_module(VERIFY_COMMON)


def _args(world: dict, root: Path, command: str = "check") -> Namespace:
    return Namespace(
        command=command,
        root=str(root),
        state_db=str(world["state"]),
        history_db=str(world["history"]),
        sessions_root=str(world["sessions"]),
        config=None,
        auto=False,
        json=True,
        repair=None,
        plan=None,
        candidate=None,
        challenge=None,
        yes=False,
    )


def _database_hashes(world: dict) -> dict[str, str]:
    return {
        name: hashlib.sha256(world[name].read_bytes()).hexdigest()
        for name in ("state", "history")
    }


def _version(path: Path, context) -> str:
    environment = launcher._environment(context)
    completed = subprocess.run(
        [sys.executable, str(path), "--version"],
        env=environment,
        text=True,
        capture_output=True,
        check=False,
        timeout=30,
    )
    assert completed.returncode == 0, completed.stderr
    return completed.stdout.strip()


def test_managed_051_profile55_explicitly_upgrades_to_060_and_rolls_back(tmp_path):
    world = VERIFY_COMMON.build_fixture(tmp_path / "synthetic-state55")
    root = tmp_path / "managed"
    root.mkdir(mode=0o700)
    catalogue = trust.load_catalogue()
    upgrade = next(
        recipe
        for recipe in catalogue["recipes"]
        if recipe["recipe_id"] == "codex-adapter051-state55-to-060-state55-v1"
    )
    old_digest = upgrade["source_adapter_digest"]
    selection_dir = root / "selection"
    selection_dir.mkdir(mode=0o700)
    selection = {
        "format_version": 1,
        "generation": 9,
        "artifact_digest": old_digest,
        "source": "managed",
        "recipe_id": "installed-0.5.1",
        "activated_plan_digest": "sha256:" + "5" * 64,
    }
    (selection_dir / "current.json").write_bytes(canonical_bytes(selection))
    before = _database_hashes(world)

    context = factory.production_context(_args(world, root))
    observation = engine.observe(context.recapture(), context)
    context = replace(context, current_observation=observation)
    classification = engine.classify(observation, context)
    assert classification == {
        "format_version": 1,
        "status": "known_repair",
        "observation_digest": observation["input_fingerprint"],
        "recipe_id": upgrade["recipe_id"],
        "reason_code": None,
    }
    repair_plan = engine.plan(classification, context)
    applied = store.apply(repair_plan, context)
    assert applied["status"] == "active"
    assert applied["current_selection"]["artifact_digest"] == upgrade["target_artifact_digest"]
    assert _database_hashes(world) == before

    target_path, target_manifest = launcher._selected(
        factory.production_context(_args(world, root, command="launch"))
    )
    assert target_manifest["profile_ids"]["state"] == "codex-state-v5-migration-55"
    assert _version(target_path, context) == "0.6.0"
    assert _database_hashes(world) == before

    fresh = factory.production_context(_args(world, root, command="rollback"))
    rolled_back = store.rollback(applied["operation_id"], fresh)
    assert rolled_back["status"] == "rolled_back"
    assert rolled_back["current_selection"]["artifact_digest"] == old_digest
    assert _database_hashes(world) == before

    restored = factory.production_context(_args(world, root, command="launch"))
    old_path, old_manifest = launcher._selected(restored)
    assert old_manifest["profile_ids"]["state"] == "codex-state-v5-migration-55"
    assert _version(old_path, restored) == "0.5.1"
    assert _database_hashes(world) == before


def test_fixer_version_does_not_construct_context(capsys):
    calls = []

    def forbidden_context(_args):
        calls.append(True)
        raise AssertionError("--version must not construct a production context")

    try:
        cli.main(["--version"], context_factory=forbidden_context)
    except SystemExit as exc:
        assert exc.code == 0
    assert calls == []
    assert capsys.readouterr().out.strip() == "0.6.0"
