"""Trust-boundary tests for selected Codex adapter launch artifacts."""

from __future__ import annotations

import hashlib
import importlib.util
import shutil
import sys
import zipfile
from pathlib import Path
from unittest.mock import patch

import pytest

from session_recall.codex_fix import artifacts, launcher
from session_recall.codex_fix.contracts import ContractError, canonical_bytes, validate


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


def _untrusted_selected_case(tmp_path):
    case = FIXTURES.prepare_case(tmp_path / "launcher-trust")
    trusted_target = Path(case.metadata["target_path"])
    mutant = tmp_path / "harmless-modified-55.pyz"
    shutil.copyfile(trusted_target, mutant)
    with zipfile.ZipFile(mutant, "a") as archive:
        archive.comment = b"harmless-untrusted-selection-marker"

    untrusted_digest = "sha256:" + hashlib.sha256(mutant.read_bytes()).hexdigest()
    trusted_digests = {
        case.context.catalogue["seed_artifact_digest"],
        *(
            value
            for recipe in case.context.catalogue["recipes"]
            for value in (
                recipe["source_adapter_digest"],
                recipe["target_artifact_digest"],
            )
        ),
    }
    assert untrusted_digest not in trusted_digests

    cache = (
        case.context.managed_root
        / "artifacts"
        / "sha256"
        / untrusted_digest.removeprefix("sha256:")
        / "adapter.pyz"
    )
    cache.parent.mkdir(parents=True)
    cache.write_bytes(mutant.read_bytes())
    selection = validate(
        {
            "format_version": 1,
            "generation": 8,
            "artifact_digest": untrusted_digest,
            "source": "managed",
            "recipe_id": "untrusted-self-hash",
            "activated_plan_digest": "sha256:" + "e" * 64,
        },
        "Selection",
    )
    case.context.paths["current_selection"].write_bytes(canonical_bytes(selection))
    return case, cache, untrusted_digest


def test_resolve_rejects_self_hashed_artifact_absent_from_trusted_catalogue(tmp_path):
    case, cache, untrusted_digest = _untrusted_selected_case(tmp_path)
    assert artifacts.manifest(cache, untrusted_digest)["profile_ids"]["state"] == (
        "codex-state-v5-migration-55"
    )

    with pytest.raises(ContractError) as raised:
        artifacts.resolve(untrusted_digest, case.context)
    assert raised.value.code == "untrusted_artifact"


def test_launcher_refuses_untrusted_selection_before_os_exec(tmp_path):
    case, _cache, _digest = _untrusted_selected_case(tmp_path)
    exec_calls = []

    def forbidden_exec(*args):
        exec_calls.append(args)
        raise AssertionError("launcher reached OS exec for an untrusted artifact")

    with patch("session_recall.codex_fix.launcher.os.execve", forbidden_exec):
        with pytest.raises(ContractError) as raised:
            launcher.launch(["schema-check", "--json"], case.context)
    assert raised.value.code == "untrusted_artifact"
    assert exec_calls == []


def test_catalogue_seed_and_recipe_artifacts_remain_resolvable(tmp_path):
    case = FIXTURES.prepare_case(tmp_path / "launcher-positive")
    allowed = {
        case.context.catalogue["seed_artifact_digest"],
        *(
            value
            for recipe in case.context.catalogue["recipes"]
            for value in (
                recipe["source_adapter_digest"],
                recipe["target_artifact_digest"],
            )
        ),
    }
    assert allowed == {
        case.metadata["source_digest"],
        case.metadata["target_digest"],
    }
    for artifact_digest in allowed:
        path = artifacts.resolve(artifact_digest, case.context)
        assert artifacts.manifest(path, artifact_digest)["profile_ids"]["state"] in {
            "codex-state-v5-migration-52",
            "codex-state-v5-migration-55",
        }
