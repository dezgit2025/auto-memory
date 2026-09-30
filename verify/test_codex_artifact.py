"""Independent acceptance tests for reproducible Codex adapter zipapps."""

from __future__ import annotations

import hashlib
import importlib.util
import json
import os
import re
import subprocess
import sys
import zipfile
from pathlib import Path

import pytest

from session_recall import __version__


ROOT = Path(__file__).resolve().parents[1]
BUILDER = ROOT / "scripts" / "build-codex-adapter.py"
COMMON = ROOT / "verify" / "fix_cli_codex_common.py"
MANIFEST_FIELDS = {
    "format_version",
    "entry_point",
    "profile_ids",
    "schema_fingerprint",
    "profiles",
}
STATE_55 = "codex-state-v5-migration-55"
HISTORY_6 = "codex-thread-history-v1-migration-6"
DIGEST_RE = re.compile(r"sha256:[0-9a-f]{64}\Z")


def _load_verify_common():
    spec = importlib.util.spec_from_file_location("artifact_verify_common", COMMON)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


VERIFY_COMMON = _load_verify_common()


def _run(argv: list[str], *, env: dict[str, str] | None = None):
    merged = os.environ.copy()
    merged.update(
        {
            "PYTHONDONTWRITEBYTECODE": "1",
            "PYTEST_DISABLE_PLUGIN_AUTOLOAD": "1",
        }
    )
    if env:
        merged.update(env)
    return subprocess.run(
        argv,
        cwd=ROOT,
        env=merged,
        text=True,
        capture_output=True,
        timeout=60,
        check=False,
    )


def _last_json(stdout: str) -> dict:
    lines = [line for line in stdout.splitlines() if line.strip()]
    assert lines, "command produced no JSON summary"
    return json.loads(lines[-1])


def _build(profile: int, output: Path) -> dict:
    result = _run(
        [
            sys.executable,
            str(BUILDER),
            "--profile",
            str(profile),
            "--output",
            str(output),
        ]
    )
    assert result.returncode == 0, result.stderr
    summary = _last_json(result.stdout)
    assert set(summary) == {
        "artifact_digest",
        "schema_fingerprint",
        "output",
        "profile_ids",
    }
    assert summary["output"] == str(output)
    assert summary["artifact_digest"] == (
        "sha256:" + hashlib.sha256(output.read_bytes()).hexdigest()
    )
    assert DIGEST_RE.fullmatch(summary["artifact_digest"])
    assert DIGEST_RE.fullmatch(summary["schema_fingerprint"])
    return summary


def _manifest(path: Path) -> dict:
    matches = []
    with zipfile.ZipFile(path) as archive:
        for name in archive.namelist():
            if not name.endswith(".json"):
                continue
            try:
                value = json.loads(archive.read(name))
            except (UnicodeDecodeError, json.JSONDecodeError):
                continue
            if isinstance(value, dict) and set(value) == MANIFEST_FIELDS:
                matches.append(value)
    assert len(matches) == 1
    return matches[0]


@pytest.fixture(scope="module")
def artifacts(tmp_path_factory):
    root = tmp_path_factory.mktemp("codex-adapter-artifacts")
    first_55 = root / "adapter-55-a.pyz"
    second_55 = root / "adapter-55-b.pyz"
    adapter_52 = root / "adapter-52.pyz"
    return {
        "root": root,
        "55a": first_55,
        "55b": second_55,
        "52": adapter_52,
        "summary55a": _build(55, first_55),
        "summary55b": _build(55, second_55),
        "summary52": _build(52, adapter_52),
    }


def test_profile55_build_is_canonical_and_reproducible(artifacts):
    first = artifacts["55a"]
    second = artifacts["55b"]
    assert first.read_bytes() == second.read_bytes()
    assert artifacts["summary55a"]["artifact_digest"] == (
        artifacts["summary55b"]["artifact_digest"]
    )

    with zipfile.ZipFile(first) as archive:
        infos = archive.infolist()
        names = [info.filename for info in infos]
        assert names == sorted(names)
        assert len({info.date_time for info in infos}) == 1
        assert infos[0].date_time == (1980, 1, 1, 0, 0, 0)
        assert all(((info.external_attr >> 16) & 0o777) == 0o644 for info in infos)
        assert not any(
            {"codex_fix", "tests", "__pycache__"}.intersection(Path(name).parts)
            or name.endswith((".pyc", ".pyo"))
            for name in names
        )

    manifest = _manifest(first)
    assert set(manifest) == MANIFEST_FIELDS
    assert manifest["format_version"] == 1
    assert manifest["entry_point"] == "session_recall.providers.codex.cli:main"
    assert manifest["profile_ids"] == {
        "state": STATE_55,
        "history": HISTORY_6,
    }
    assert manifest["profiles"]["state"]["profile"] == STATE_55
    assert manifest["profiles"]["history"]["profile"] == HISTORY_6
    assert manifest["schema_fingerprint"] == (
        artifacts["summary55a"]["schema_fingerprint"]
    )
    assert manifest["profile_ids"] == artifacts["summary55a"]["profile_ids"]


def test_zipapp55_runs_public_cli_against_synthetic_store(artifacts):
    store = VERIFY_COMMON.build_fixture(artifacts["root"] / "synthetic-55")
    env = VERIFY_COMMON.fixture_env(store)
    before = VERIFY_COMMON.hash_tree(store["root"])
    artifact = str(artifacts["55a"])

    version = _run([sys.executable, artifact, "--version"], env=env)
    assert version.returncode == 0, version.stderr
    assert version.stdout.strip() == __version__

    schema = _run([sys.executable, artifact, "schema-check", "--json"], env=env)
    assert schema.returncode == 0, schema.stderr
    schema_json = json.loads(schema.stdout)
    assert schema_json["ok"] is True
    assert schema_json["profiles"] == {"state": STATE_55, "history": HISTORY_6}

    listed = _run(
        [sys.executable, artifact, "list", "--json", "--limit", "10"], env=env
    )
    assert listed.returncode == 0, listed.stderr
    assert [row["summary"] for row in json.loads(listed.stdout)] == [
        "verify remote newest",
        "verify local scratch",
        "verify remote older",
    ]

    repos = _run([sys.executable, artifact, "repos", "--json"], env=env)
    assert repos.returncode == 0, repos.stderr
    assert json.loads(repos.stdout) == {
        "count": 1,
        "repos": [
            {
                "repository": "verify/remote",
                "session_count": 2,
                "last_seen": json.loads(repos.stdout)["repos"][0]["last_seen"],
            }
        ],
    }
    assert VERIFY_COMMON.hash_tree(store["root"]) == before


def test_zipapp52_rejects_synthetic55_before_queries(artifacts):
    store = VERIFY_COMMON.build_fixture(artifacts["root"] / "mismatch-55")
    env = VERIFY_COMMON.fixture_env(store)
    artifact = str(artifacts["52"])
    before = VERIFY_COMMON.hash_tree(store["root"])

    for command in (["schema-check", "--json"], ["list", "--json"]):
        result = _run([sys.executable, artifact, *command], env=env)
        assert result.returncode == 2
        body = json.loads(result.stdout)
        assert body["error"] == "schema_drift"
        assert body["query_executed"] is False
    assert VERIFY_COMMON.hash_tree(store["root"]) == before


def test_builder_refuses_symlink_and_different_existing_output(tmp_path):
    target = tmp_path / "target.pyz"
    target.write_bytes(b"target-sentinel")
    symlink = tmp_path / "linked.pyz"
    symlink.symlink_to(target)
    existing = tmp_path / "existing.pyz"
    existing.write_bytes(b"existing-sentinel")

    for output in (symlink, existing):
        result = _run(
            [
                sys.executable,
                str(BUILDER),
                "--profile",
                "55",
                "--output",
                str(output),
            ]
        )
        assert result.returncode != 0

    assert symlink.is_symlink()
    assert target.read_bytes() == b"target-sentinel"
    assert existing.read_bytes() == b"existing-sentinel"
