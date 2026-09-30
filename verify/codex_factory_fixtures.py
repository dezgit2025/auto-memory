"""Trusted synthetic fixtures for production Codex fixer boundary tests."""

from __future__ import annotations

import hashlib
import importlib.util
import json
import sys
import zipfile
from argparse import Namespace
from pathlib import Path
from types import SimpleNamespace

import pytest


ROOT = Path(__file__).resolve().parents[1]
COMMON = ROOT / "verify/fix_cli_codex_common.py"
DATA = ROOT / "src/session_recall/codex_fix/data"
TRUSTED_PIN = "81502713f58ee74d62f17028c43a385506f84ff524145be472d30332396818d8"
CHECK_IDS = {
    "artifact_manifest_v1",
    "synthetic_schema_v1",
    "trial_cli_contract_v1",
    "unknown_drift_rejected_v1",
    "synthetic_no_write_v1",
}


def _load_common():
    spec = importlib.util.spec_from_file_location("factory_verify_common", COMMON)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


VERIFY_COMMON = _load_common()


def canonical(value: object) -> bytes:
    return json.dumps(
        value, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    ).encode("utf-8")


def sha256(data: bytes) -> str:
    return "sha256:" + hashlib.sha256(data).hexdigest()


def adapter_manifest(path: Path) -> dict:
    with zipfile.ZipFile(path) as archive:
        return json.loads(archive.read("ADAPTER-MANIFEST.json"))


def controller_args(**changes) -> Namespace:
    values = {
        "command": "check",
        "root": None,
        "state_db": None,
        "history_db": None,
        "sessions_root": None,
        "config": None,
        "auto": False,
        "json": True,
        "repair": None,
        "plan": None,
    }
    values.update(changes)
    return Namespace(**values)


def config_value(**changes) -> dict:
    value = {
        "format_version": 1,
        "root": None,
        "state_db": None,
        "history_db": None,
        "sessions_root": None,
        "activation_policy": {
            "format_version": 1,
            "known_recipe_mode": "explicit",
            "startup_trigger": "none",
            "allow_downloads": False,
        },
    }
    value.update(changes)
    return value


def install_cached(root: Path, artifact: Path, artifact_digest: str) -> Path:
    target = root / "artifacts/sha256" / artifact_digest.removeprefix("sha256:")
    target.mkdir(parents=True, mode=0o700)
    cached = target / "adapter.pyz"
    cached.write_bytes(artifact.read_bytes())
    return cached


def write_selection(root: Path, artifact_digest: str) -> Path:
    selection = {
        "format_version": 1,
        "generation": 1,
        "artifact_digest": artifact_digest,
        "source": "managed",
        "recipe_id": "profile52-seed",
        "activated_plan_digest": "sha256:" + "c" * 64,
    }
    directory = root / "selection"
    directory.mkdir(parents=True, mode=0o700)
    path = directory / "current.json"
    path.write_bytes(canonical(selection))
    return path


@pytest.fixture(scope="module")
def factory_world(tmp_path_factory):
    base = tmp_path_factory.mktemp("codex-factory")
    catalogue_path = DATA / "catalogue-v1.json"
    catalogue = json.loads(catalogue_path.read_text(encoding="utf-8"))
    source_digest = catalogue["recipes"][0]["source_adapter_digest"]
    target_digest = catalogue["seed_artifact_digest"]
    artifact52 = DATA / "artifacts" / f"{source_digest.removeprefix('sha256:')}.pyz"
    artifact55 = DATA / "artifacts" / f"{target_digest.removeprefix('sha256:')}.pyz"
    manifest55 = adapter_manifest(artifact55)
    assert set(catalogue["recipes"][0]["check_ids"]) == CHECK_IDS
    assert hashlib.sha256(canonical(catalogue)).hexdigest() == TRUSTED_PIN
    store = VERIFY_COMMON.build_fixture(base / "store")
    return SimpleNamespace(
        base=base,
        artifact52=artifact52,
        artifact55=artifact55,
        source_digest=source_digest,
        target_digest=target_digest,
        manifest55=manifest55,
        catalogue=catalogue,
        catalogue_path=catalogue_path,
        catalogue_pin=TRUSTED_PIN,
        store=store,
    )


@pytest.fixture()
def trusted_catalogue(factory_world):
    from session_recall.codex_fix import trust

    assert trust.TRUSTED_CATALOGUE_SHA256 == factory_world.catalogue_pin
    return factory_world
