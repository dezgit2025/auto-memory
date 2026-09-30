"""Independent Stage B behavioral probes."""

from __future__ import annotations

import copy
import hashlib
import io
import json
import sys
import tempfile
from argparse import Namespace
from contextlib import redirect_stdout
from dataclasses import replace
from pathlib import Path

from fix_cli_codex_common import VerifyFailure, build_fixture, hash_tree


CHECK_IDS = [
    "artifact_manifest_v1",
    "synthetic_schema_v1",
    "trial_cli_contract_v1",
    "unknown_drift_rejected_v1",
    "synthetic_no_write_v1",
]


def _args(root: Path, store: dict[str, Path], **changes) -> Namespace:
    values = {
        "command": "check", "root": str(root), "state_db": str(store["state"]),
        "history_db": str(store["history"]), "sessions_root": str(store["sessions"]),
        "config": None, "auto": False, "json": True, "repair": None, "plan": None,
    }
    values.update(changes)
    return Namespace(**values)


def _selection(source_digest: str) -> dict:
    return {
        "format_version": 1,
        "generation": 1,
        "artifact_digest": source_digest,
        "source": "managed",
        "recipe_id": "profile52-seed",
        "activated_plan_digest": "sha256:" + "c" * 64,
    }


def _write_source_selection(root: Path, source_digest: str) -> Path:
    from session_recall.codex_fix.contracts import canonical_bytes, validate

    root.mkdir(mode=0o700)
    directory = root / "selection"
    directory.mkdir(mode=0o700)
    path = directory / "current.json"
    path.write_bytes(canonical_bytes(validate(_selection(source_digest), "Selection")))
    return path


def _catalogue() -> dict:
    from session_recall.codex_fix.trust import load_catalogue

    return load_catalogue()


def _read_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def probe_lifecycle_and_unknown() -> list[str]:
    from session_recall.codex_fix import factory, store
    from session_recall.codex_fix.contracts import ContractError, digest
    from session_recall.codex_fix.engine import classify, observe, plan

    with tempfile.TemporaryDirectory(prefix="fix-cli-codex-b2-") as temp:
        forbidden_before = {
            name for name in sys.modules
            if name.startswith(("openai", "session_recall.codex_fix.transport"))
        }
        root = Path(temp).resolve()
        synthetic = build_fixture(root / "synthetic-55")
        managed = root / "managed"
        catalogue = _catalogue()
        recipe = catalogue["recipes"][0]
        selection_path = _write_source_selection(managed, recipe["source_adapter_digest"])
        context = factory.production_context(_args(managed, synthetic))
        before = hash_tree(synthetic["root"])
        snapshot = context.recapture()
        observation = observe(snapshot, context)
        observed = replace(context, current_observation=observation)
        classification = classify(observation, observed)
        if classification["status"] != "known_repair":
            raise VerifyFailure(f"expected known_repair, got {classification!r}")
        repair_plan = plan(classification, observed)
        applied = store.apply(repair_plan, observed)
        if applied["status"] != "active" or applied["executed_check_ids"] != CHECK_IDS:
            raise VerifyFailure(f"real apply failed: {applied!r}")
        active = _read_json(selection_path)
        if active["artifact_digest"] != recipe["target_artifact_digest"]:
            raise VerifyFailure("apply did not select the reviewed target artifact")
        repeated = store.apply(repair_plan, observed)
        if repeated["status"] != "no_op" or _read_json(selection_path) != active:
            raise VerifyFailure(f"reapply was not an exact no-op: {repeated!r}")
        rolled = store.rollback(applied["operation_id"], observed)
        if rolled["status"] != "rolled_back_incompatible":
            raise VerifyFailure(f"rollback was not honest about schema incompatibility: {rolled!r}")
        if _read_json(selection_path)["artifact_digest"] != recipe["source_adapter_digest"]:
            raise VerifyFailure("rollback did not restore the source artifact")
        if hash_tree(synthetic["root"]) != before:
            raise VerifyFailure("B lifecycle modified synthetic Codex storage")

        unknown_snapshot = copy.deepcopy(snapshot)
        unknown_snapshot["state"]["tables"][0]["columns"].append(
            {"cid": 40, "name": "private_unknown", "declared_type": "TEXT",
             "not_null": False, "default_sql": None, "pk_position": 0}
        )
        semantic = {key: unknown_snapshot[key] for key in ("storage_family", "state", "history")}
        unknown_snapshot["schema_fingerprint"] = digest(semantic)
        unknown_observation = observe(unknown_snapshot, context)
        unknown_context = replace(context, current_observation=unknown_observation)
        unknown = classify(unknown_observation, unknown_context)
        if unknown["status"] != "assistance_eligible" or unknown["reason_code"] != "no_recipe":
            raise VerifyFailure(f"unknown schema routed incorrectly: {unknown!r}")
        try:
            plan(unknown, unknown_context)
        except ContractError as exc:
            if exc.code != "no_recipe":
                raise VerifyFailure(f"unknown planning failed for wrong reason: {exc.code}") from exc
        else:
            raise VerifyFailure("unknown schema unexpectedly produced a plan")
        forbidden = {
            name for name in sys.modules
            if name.startswith(("openai", "session_recall.codex_fix.transport"))
        } - forbidden_before
        if forbidden:
            raise VerifyFailure(f"B routing loaded an AI transport: {sorted(forbidden)}")
    return ["known52-to-55=active", "reapply=no_op", "rollback=incompatible-honest",
            "unknown=no_recipe", "ai_calls=0", "codex-store-hashes=unchanged"]


def _cli_json(argv: list[str]) -> tuple[int, dict]:
    from session_recall.codex_fix import cli

    output = io.StringIO()
    with redirect_stdout(output):
        code = cli.main(argv)
    lines = [line for line in output.getvalue().splitlines() if line.strip()]
    if not lines:
        raise VerifyFailure(f"companion CLI emitted no JSON for {argv!r}")
    return code, json.loads(lines[-1])


def probe_cli_auto_policy() -> list[str]:
    from session_recall.codex_fix.contracts import canonical_bytes

    with tempfile.TemporaryDirectory(prefix="fix-cli-codex-b-auto-") as temp:
        root = Path(temp).resolve()
        synthetic = build_fixture(root / "synthetic-55")
        common = [
            "--json", "--state-db", str(synthetic["state"]),
            "--history-db", str(synthetic["history"]),
            "--sessions-root", str(synthetic["sessions"]),
        ]
        explicit_root = root / "explicit"
        code, body = _cli_json([*common, "--root", str(explicit_root), "check", "--auto"])
        if code != 2 or body["status"] != "invalid" or explicit_root.exists():
            raise VerifyFailure(f"explicit default auto gate failed: {code}, {body!r}")

        managed = root / "opted-in"
        recipe = _catalogue()["recipes"][0]
        _write_source_selection(managed, recipe["source_adapter_digest"])
        config = {
            "format_version": 1, "root": str(managed), "state_db": None,
            "history_db": None, "sessions_root": None,
            "activation_policy": {"format_version": 1, "known_recipe_mode": "auto_opt_in",
                                  "startup_trigger": "none", "allow_downloads": False},
        }
        config_path = root / "controller.json"
        config_path.write_bytes(canonical_bytes(config))
        config_hash = hashlib.sha256(config_path.read_bytes()).hexdigest()
        before = hash_tree(synthetic["root"])
        code, body = _cli_json([*common, "--config", str(config_path), "check", "--auto"])
        if code != 0 or body["status"] != "active":
            raise VerifyFailure(f"persisted opt-in did not apply known repair: {code}, {body!r}")
        if hashlib.sha256(config_path.read_bytes()).hexdigest() != config_hash:
            raise VerifyFailure("auto apply rewrote persisted policy")
        if hash_tree(synthetic["root"]) != before:
            raise VerifyFailure("auto apply modified synthetic Codex storage")
    return ["explicit-auto=invalid", "persisted-optin=active", "policy=unchanged"]


def require_trust_observation(observed: dict) -> None:
    if observed.get("accepted") is True:
        raise VerifyFailure("catalogue_trust_bypass")
    if observed.get("code") != "catalogue_untrusted":
        raise VerifyFailure(f"catalogue rejection reason changed: {observed!r}")
