"""Frozen production-boundary tests for the deterministic Codex fixer."""

from __future__ import annotations

import copy
import hashlib
import inspect
import json
import sys
from pathlib import Path

import pytest

from session_recall.codex_fix import artifacts, checks, cli, factory, trust
from session_recall.codex_fix.contracts import ContractError, parse, validate


pytest.register_assert_rewrite("verify.codex_factory_fixtures")

from verify.codex_factory_fixtures import (  # noqa: E402
    CHECK_IDS,
    VERIFY_COMMON,
    canonical,
    config_value,
    controller_args,
    install_cached,
    sha256,
    write_selection,
)


pytest_plugins = ("verify.codex_factory_fixtures",)


def _args(world, root: Path, **changes):
    return controller_args(
        root=str(root),
        state_db=str(world.store["state"]),
        history_db=str(world.store["history"]),
        sessions_root=str(world.store["sessions"]),
        **changes,
    )


def _json_output(capsys):
    output = capsys.readouterr().out
    lines = [line for line in output.splitlines() if line.strip()]
    assert lines, "CLI emitted no JSON response"
    return json.loads(lines[-1])


def test_controller_config_is_exact_local_only_contract(tmp_path):
    value = config_value(root=str(tmp_path / "root"))
    assert validate(value, "ControllerConfig") is value
    assert parse(canonical(value).decode("utf-8"), "ControllerConfig") == value

    for forbidden in ("catalogue", "transport", "billing_context", "test_hooks"):
        with pytest.raises(ContractError):
            validate({**value, forbidden: "attacker-controlled"}, "ControllerConfig")
    with pytest.raises(ContractError):
        validate({**value, "root": "x" * 4097}, "ControllerConfig")


def test_bundled_catalogue_pin_rejects_tamper_and_attacker_self_hash(
    trusted_catalogue, tmp_path, monkeypatch
):
    world = trusted_catalogue
    assert trust.load_catalogue() == world.catalogue

    forged = copy.deepcopy(world.catalogue)
    forged["catalogue_id"] = "attacker-catalogue-v1"
    forged_path = tmp_path / "catalogue-v1.json"
    forged_path.write_bytes(canonical(forged))
    forged_self_hash = hashlib.sha256(canonical(forged)).hexdigest()
    assert forged_self_hash != trust.TRUSTED_CATALOGUE_SHA256
    monkeypatch.setattr(trust, "_catalogue_resource", lambda: forged_path)
    with pytest.raises(ContractError) as raised:
        trust.load_catalogue()
    assert raised.value.code == "catalogue_untrusted"


def test_default_factory_is_lazy_read_only_and_explicit(
    trusted_catalogue, tmp_path
):
    world = trusted_catalogue
    root = tmp_path / "absent-managed-root"
    before_store = VERIFY_COMMON.hash_tree(world.store["root"])
    context = factory.production_context(_args(world, root))

    assert not root.exists()
    assert VERIFY_COMMON.hash_tree(world.store["root"]) == before_store
    assert context.policy == {
        "format_version": 1,
        "known_recipe_mode": "explicit",
        "startup_trigger": "none",
        "allow_downloads": False,
    }
    assert context.paths["current_selection"] == root / "selection/current.json"
    assert context.adapter_identity == {
        "kind": "bundled",
        "artifact_digest": world.target_digest,
        "profile_id": "codex-state-v5-migration-55",
    }
    assert set(context.check_registry) == CHECK_IDS


def test_cli_paths_override_config_but_persisted_policy_is_respected(
    trusted_catalogue, tmp_path
):
    config_root = tmp_path / "config-root"
    override_root = tmp_path / "override-root"
    override_state = tmp_path / "override-state.sqlite"
    configured_history = tmp_path / "configured-history.sqlite"
    configured_sessions = tmp_path / "configured-sessions"
    policy = {
        "format_version": 1,
        "known_recipe_mode": "auto_opt_in",
        "startup_trigger": "none",
        "allow_downloads": False,
    }
    config = config_value(
        root=str(config_root),
        state_db=str(tmp_path / "configured-state.sqlite"),
        history_db=str(configured_history),
        sessions_root=str(configured_sessions),
        activation_policy=policy,
    )
    config_path = tmp_path / "controller.json"
    config_path.write_bytes(canonical(config))
    args = controller_args(
        root=str(override_root),
        state_db=str(override_state),
        config=str(config_path),
        command="check",
    )
    context = factory.production_context(args)

    assert context.managed_root == override_root
    assert context.paths["state_db"] == override_state
    assert context.paths["history_db"] == configured_history
    assert context.paths["sessions_root"] == configured_sessions
    assert context.policy == policy
    assert not config_root.exists() and not override_root.exists()


def test_cli_rejects_catalogue_override_before_context_creation(capsys):
    calls = []

    def forbidden_factory(_args):
        calls.append(True)
        raise AssertionError("context factory must not run for argument errors")

    code = cli.main(
        ["--json", "--catalogue", "/tmp/forged.json", "check"],
        context_factory=forbidden_factory,
    )
    body = _json_output(capsys)
    assert code == 2
    assert calls == []
    assert set(body) == {"format_version", "command", "ok", "status", "detail"}
    assert body["ok"] is False and body["status"] == "invalid"


def test_corrupt_active_artifact_still_builds_rollback_context_without_import(
    trusted_catalogue, tmp_path
):
    root = tmp_path / "managed"
    root.mkdir(mode=0o700)
    corrupt = tmp_path / "corrupt.pyz"
    corrupt.write_bytes(b"not-a-zip-and-never-imported")
    corrupt_digest = sha256(corrupt.read_bytes())
    install_cached(root, corrupt, corrupt_digest)
    write_selection(root, corrupt_digest)
    before_modules = set(sys.modules)
    args = controller_args(
        command="rollback",
        repair="operation-1",
        root=str(root),
        state_db=str(tmp_path / "missing-state.sqlite"),
        history_db=str(tmp_path / "missing-history.sqlite"),
        sessions_root=str(tmp_path / "missing-sessions"),
    )
    context = factory.production_context(args)

    assert context.adapter_identity == {
        "kind": "managed",
        "artifact_digest": corrupt_digest,
        "profile_id": None,
    }
    assert not any(
        name.startswith("session_recall.providers.codex")
        for name in set(sys.modules) - before_modules
    )


def test_artifact_resolution_prefers_valid_cache_then_uses_bundled_seed(
    trusted_catalogue, tmp_path
):
    world = trusted_catalogue
    bundled_context = factory.production_context(_args(world, tmp_path / "bundled"))
    bundled = artifacts.resolve(world.target_digest, bundled_context)
    assert bundled.resolve() == world.artifact55.resolve()
    assert artifacts.manifest(bundled, world.target_digest) == world.manifest55

    cache_root = tmp_path / "cached"
    cache_root.mkdir(mode=0o700)
    cached = install_cached(cache_root, world.artifact55, world.target_digest)
    cached_context = factory.production_context(_args(world, cache_root))
    assert artifacts.resolve(world.target_digest, cached_context) == cached


def test_artifact_resolution_rejects_symlink_and_digest_mismatch(
    trusted_catalogue, tmp_path
):
    world = trusted_catalogue
    root = tmp_path / "managed"
    context = factory.production_context(_args(world, root))
    root.mkdir(mode=0o700)
    expected = root / "artifacts/sha256" / world.target_digest[7:] / "adapter.pyz"
    expected.parent.mkdir(parents=True, mode=0o700)
    expected.symlink_to(world.artifact55)
    with pytest.raises(ContractError):
        artifacts.resolve(world.target_digest, context)
    with pytest.raises(ContractError) as raised:
        artifacts.manifest(world.artifact55, "sha256:" + "0" * 64)
    assert raised.value.code == "artifact_digest_mismatch"


def test_registry_is_immutable_and_all_real_checks_are_read_only(
    trusted_catalogue, tmp_path
):
    world = trusted_catalogue
    context = factory.production_context(_args(world, tmp_path / "checks"))
    registry = checks.registry()
    assert set(registry) == CHECK_IDS
    with pytest.raises(TypeError):
        registry["attacker-check"] = lambda *_args: True
    source = inspect.getsource(checks)
    assert "shell=True" not in source
    assert "~/.codex" not in source

    before = VERIFY_COMMON.hash_tree(world.store["root"])
    for check_id in sorted(CHECK_IDS):
        assert registry[check_id](world.artifact55, context) is True, check_id
    assert VERIFY_COMMON.hash_tree(world.store["root"]) == before


def test_check_auto_without_persisted_opt_in_is_invalid_and_writes_nothing(
    trusted_catalogue, tmp_path, capsys
):
    world = trusted_catalogue
    root = tmp_path / "no-auto-root"
    before = VERIFY_COMMON.hash_tree(world.store["root"])
    argv = [
        "--json",
        "--root", str(root),
        "--state-db", str(world.store["state"]),
        "--history-db", str(world.store["history"]),
        "--sessions-root", str(world.store["sessions"]),
        "check", "--auto",
    ]
    code = cli.main(argv, context_factory=factory.production_context)
    body = _json_output(capsys)
    assert code == 2
    assert body["ok"] is False and body["status"] == "invalid"
    assert not root.exists()
    assert VERIFY_COMMON.hash_tree(world.store["root"]) == before
