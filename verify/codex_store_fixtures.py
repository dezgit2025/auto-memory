"""Hermetic real-artifact fixtures for the managed Codex adapter store tests."""

from __future__ import annotations

import hashlib
import importlib.util
import json
import os
import sqlite3
import subprocess
import sys
import time
from contextlib import contextmanager
from dataclasses import replace
from pathlib import Path
from types import SimpleNamespace

from session_recall.codex_fix.context import Context
from session_recall.codex_fix.contracts import canonical_bytes, digest, validate
from session_recall.codex_fix.engine import classify, observe, plan
from session_recall.codex_metadata import inspect


ROOT = Path(__file__).resolve().parents[1]
BUILDER = ROOT / "scripts" / "build-codex-adapter.py"
COMMON = ROOT / "verify" / "fix_cli_codex_common.py"
CHECK_IDS = [
    "artifact_manifest_v1",
    "synthetic_schema_v1",
    "trial_cli_contract_v1",
    "unknown_drift_rejected_v1",
    "synthetic_no_write_v1",
]


def _load_common():
    spec = importlib.util.spec_from_file_location("store_verify_common", COMMON)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


VERIFY_COMMON = _load_common()


def _run_builder(profile: int, output: Path) -> dict:
    result = subprocess.run(
        [sys.executable, str(BUILDER), "--profile", str(profile), "--output", str(output)],
        cwd=ROOT,
        env={**os.environ, "PYTHONDONTWRITEBYTECODE": "1"},
        text=True,
        capture_output=True,
        timeout=60,
        check=False,
    )
    assert result.returncode == 0, result.stderr
    return json.loads(result.stdout.splitlines()[-1])


def _write_json(path: Path, value: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(canonical_bytes(value))


@contextmanager
def _readonly_pair(root: Path):
    state = sqlite3.connect(f"file:{root / 'state_5.sqlite'}?mode=ro", uri=True)
    history = sqlite3.connect(
        f"file:{root / 'thread_history_1.sqlite'}?mode=ro", uri=True
    )
    try:
        yield state, history
    finally:
        state.close()
        history.close()


def _snapshot(store_root: Path) -> dict:
    with _readonly_pair(store_root) as connections:
        return inspect(connections)


def prepare_case(root: Path) -> SimpleNamespace:
    root.mkdir(mode=0o700)
    os.chmod(root, 0o700)
    managed = root / "managed"
    managed.mkdir(mode=0o700)
    VERIFY_COMMON.build_fixture(root / "synthetic-55")

    summaries = {}
    for profile in (52, 55):
        built = root / f"built-{profile}.pyz"
        summary = _run_builder(profile, built)
        hex_digest = summary["artifact_digest"].removeprefix("sha256:")
        cached = managed / "artifacts" / "sha256" / hex_digest / "adapter.pyz"
        cached.parent.mkdir(parents=True)
        cached.write_bytes(built.read_bytes())
        summaries[str(profile)] = {**summary, "path": str(cached)}

    source_digest = summaries["52"]["artifact_digest"]
    target_digest = summaries["55"]["artifact_digest"]
    selection = validate(
        {
            "format_version": 1,
            "generation": 7,
            "artifact_digest": source_digest,
            "source": "managed",
            "recipe_id": "profile52-seed",
            "activated_plan_digest": "sha256:" + "c" * 64,
        },
        "Selection",
    )
    _write_json(managed / "selection" / "current.json", selection)
    metadata = {
        "source_digest": source_digest,
        "target_digest": target_digest,
        "source_path": summaries["52"]["path"],
        "target_path": summaries["55"]["path"],
    }
    (root / "case.json").write_text(json.dumps(metadata), encoding="utf-8")
    return load_case(root)


def _context(
    root: Path,
    *,
    hooks=None,
    failing_check: str | None = None,
    stale_recapture: bool = False,
) -> tuple[Context, list[str], dict]:
    metadata = json.loads((root / "case.json").read_text(encoding="utf-8"))
    snapshot = _snapshot(root / "synthetic-55")
    recipe = {
        "recipe_id": "codex-state52-artifact-to-state55-v1",
        "source_adapter_digest": metadata["source_digest"],
        "schema_fingerprint": snapshot["schema_fingerprint"],
        "target_artifact_digest": metadata["target_digest"],
        "check_ids": CHECK_IDS,
    }
    catalogue = validate(
        {
            "format_version": 1,
            "catalogue_id": "store-test-catalogue-v1",
            "seed_artifact_digest": metadata["target_digest"],
            "recipes": [recipe],
        },
        "Catalogue",
    )
    policy = validate(
        {
            "format_version": 1,
            "known_recipe_mode": "explicit",
            "startup_trigger": "none",
            "allow_downloads": False,
        },
        "ActivationPolicy",
    )
    identity = validate(
        {
            "kind": "managed",
            "artifact_digest": metadata["source_digest"],
            "profile_id": "codex-state-v5-migration-52",
        },
        "AdapterIdentity",
    )
    calls: list[str] = []

    def make_check(check_id: str):
        def check(artifact_path: Path, context: Context) -> bool:
            assert artifact_path == Path(metadata["target_path"])
            assert context.managed_root == root / "managed"
            calls.append(check_id)
            return check_id != failing_check

        return check

    def recapture():
        current = _snapshot(root / "synthetic-55")
        if stale_recapture:
            current = {**current, "schema_fingerprint": "sha256:" + "0" * 64}
        return current

    context = Context(
        paths={
            "state_db": root / "synthetic-55" / "state_5.sqlite",
            "history_db": root / "synthetic-55" / "thread_history_1.sqlite",
            "sessions_root": root / "synthetic-55" / "sessions",
            "current_selection": root / "managed" / "selection" / "current.json",
        },
        managed_root=root / "managed",
        catalogue=catalogue,
        catalogue_digest=digest(catalogue),
        policy=policy,
        policy_digest=digest(policy),
        check_registry={check_id: make_check(check_id) for check_id in CHECK_IDS},
        recapture=recapture,
        test_hooks=hooks,
        adapter_identity=identity,
        current_observation=None,
    )
    observation = observe(snapshot, context)
    return replace(context, current_observation=observation), calls, metadata


def load_context(root: Path, **kwargs) -> SimpleNamespace:
    context, calls, metadata = _context(root, **kwargs)
    return SimpleNamespace(context=context, calls=calls, metadata=metadata)


def load_case(root: Path, **kwargs) -> SimpleNamespace:
    loaded = load_context(root, **kwargs)
    classification = classify(loaded.context.current_observation, loaded.context)
    repair_plan = plan(classification, loaded.context)
    return SimpleNamespace(
        **vars(loaded),
        classification=classification,
        plan=repair_plan,
        operation_id=digest(repair_plan)[7:],
    )


def database_hashes(root: Path) -> dict[str, str]:
    return {
        name: hashlib.sha256((root / "synthetic-55" / name).read_bytes()).hexdigest()
        for name in ("state_5.sqlite", "thread_history_1.sqlite")
    }


class FilePhaseHook:
    def __init__(
        self,
        phase: str,
        *,
        ready: Path | None = None,
        release: Path | None = None,
        crash_code: int | None = None,
    ):
        self.phase = phase
        self.ready = ready
        self.release = release
        self.crash_code = crash_code

    def on_phase(self, phase: str) -> None:
        if phase != self.phase:
            return
        if self.ready:
            self.ready.write_text("ready", encoding="utf-8")
        if self.crash_code is not None:
            os._exit(self.crash_code)
        if self.release:
            deadline = time.monotonic() + 10
            while not self.release.exists() and time.monotonic() < deadline:
                time.sleep(0.02)
            assert self.release.exists(), "barrier release timed out"
