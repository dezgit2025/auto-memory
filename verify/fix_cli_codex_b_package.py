"""Isolated wheel proof for the companion fixer and stable launcher."""

from __future__ import annotations

import json
import os
import shutil
import sys
import tempfile
from pathlib import Path

from fix_cli_codex_common import (
    ROOT, InfraFailure, VerifyFailure, build_fixture, hash_tree, require, run,
)
from fix_cli_codex_package import _project_version


def _json(result, code: int = 0):
    require(result, code)
    try:
        return json.loads(result.stdout)
    except json.JSONDecodeError as exc:
        raise VerifyFailure(f"isolated command emitted invalid JSON: {result.stdout!r}") from exc


def verify_b_package() -> list[str]:
    version = _project_version()
    with tempfile.TemporaryDirectory(prefix="fix-cli-codex-b-wheel-") as temp:
        root = Path(temp).resolve()
        source = root / "source"
        source.mkdir()
        shutil.copytree(ROOT / "src", source / "src")
        shutil.copy2(ROOT / "pyproject.toml", source / "pyproject.toml")
        shutil.copy2(ROOT / "README.md", source / "README.md")
        wheels = root / "wheels"
        wheels.mkdir()
        require(run(
            [sys.executable, "-m", "pip", "wheel", "--no-deps", "--no-build-isolation",
             "--wheel-dir", str(wheels), str(source)], cwd=root, timeout=120,
        ))
        built = list(wheels.glob("*.whl"))
        if len(built) != 1:
            raise InfraFailure(f"expected one isolated wheel, found {[p.name for p in built]}")
        venv = root / "venv"
        require(run([sys.executable, "-m", "venv", str(venv)], cwd=root, timeout=60))
        bindir = venv / ("Scripts" if os.name == "nt" else "bin")
        python = bindir / ("python.exe" if os.name == "nt" else "python")
        fix_cli = bindir / (
            "session-recall-codex-fix.exe" if os.name == "nt" else "session-recall-codex-fix"
        )
        launcher = bindir / (
            "session-recall-codex.exe" if os.name == "nt" else "session-recall-codex"
        )
        require(run([str(python), "-m", "pip", "install", "--no-deps", str(built[0])],
                    cwd=root, timeout=120))
        if not fix_cli.is_file() or not launcher.is_file():
            raise InfraFailure("wheel omits companion or launcher entry point")

        provenance = _json(run(
            [str(python), "-c",
             "import importlib.resources as r,json,session_recall.codex_fix.factory as f;"
             "p=r.files('session_recall.codex_fix');"
             "print(json.dumps({'module':f.__file__,'catalogue':p.joinpath('data/catalogue-v1.json').is_file(),"
             "'artifacts':len(list(p.joinpath('data/artifacts').iterdir()))}))"],
            cwd=root,
        ))
        module_path = Path(provenance["module"]).resolve()
        if not module_path.is_relative_to(venv.resolve()) or not provenance["catalogue"]:
            raise VerifyFailure(f"wheel provenance/resource failure: {provenance!r}")
        if provenance["artifacts"] < 2:
            raise VerifyFailure("wheel omits one or more bundled seed artifacts")

        store = build_fixture(root / "synthetic-55")
        managed = root / "managed"
        common = [
            "--json", "--root", str(managed), "--state-db", str(store["state"]),
            "--history-db", str(store["history"]),
            "--sessions-root", str(store["sessions"]),
        ]
        catalogue = _json(run(
            [str(python), "-c",
             "import json;from session_recall.codex_fix.trust import load_catalogue;"
             "print(json.dumps(load_catalogue(),sort_keys=True,separators=(',',':')))"],
            cwd=root,
        ))
        recipe = catalogue["recipes"][0]
        selection = {
            "format_version": 1,
            "generation": 1,
            "artifact_digest": recipe["source_adapter_digest"],
            "source": "managed",
            "recipe_id": "profile52-seed",
            "activated_plan_digest": "sha256:" + "c" * 64,
        }
        managed.mkdir(mode=0o700)
        selection_dir = managed / "selection"
        selection_dir.mkdir(mode=0o700)
        selection_path = selection_dir / "current.json"
        selection_path.write_text(
            json.dumps(selection, sort_keys=True, separators=(",", ":")), encoding="utf-8"
        )
        store_before = hash_tree(store["root"])

        planned = _json(run([str(fix_cli), *common, "plan"], cwd=root))
        repair_plan = planned.get("detail")
        if not (
            planned.get("command") == "plan"
            and planned.get("ok") is True
            and planned.get("status") == "planned"
            and isinstance(repair_plan, dict)
            and repair_plan.get("source_adapter_digest") == recipe["source_adapter_digest"]
            and repair_plan.get("target_artifact_digest") == recipe["target_artifact_digest"]
        ):
            raise VerifyFailure(f"isolated companion plan differs: {planned!r}")
        plan_path = root / "reviewed-plan.json"
        plan_path.write_text(
            json.dumps(repair_plan, sort_keys=True, separators=(",", ":")), encoding="utf-8"
        )
        applied = _json(run(
            [str(fix_cli), *common, "apply", "--plan", str(plan_path)], cwd=root,
            timeout=120,
        ))
        execution = applied.get("detail")
        if not (
            applied.get("command") == "apply"
            and applied.get("ok") is True
            and applied.get("status") == "active"
            and isinstance(execution, dict)
            and execution.get("status") == "active"
            and execution.get("executed_check_ids") == recipe["check_ids"]
        ):
            raise VerifyFailure(f"isolated companion apply failed: {applied!r}")
        operation_id = execution.get("operation_id")
        if not isinstance(operation_id, str) or len(operation_id) != 64:
            raise VerifyFailure(f"isolated apply omitted operation identity: {execution!r}")
        active_selection = selection_path.read_bytes()
        if json.loads(active_selection)["artifact_digest"] != recipe["target_artifact_digest"]:
            raise VerifyFailure("isolated apply did not select target55")

        repeated = _json(run(
            [str(fix_cli), *common, "apply", "--plan", str(plan_path)], cwd=root,
            timeout=120,
        ))
        if not (
            repeated.get("status") == "no_op"
            and isinstance(repeated.get("detail"), dict)
            and repeated["detail"].get("status") == "no_op"
            and selection_path.read_bytes() == active_selection
        ):
            raise VerifyFailure(f"fresh-process reapply was not a no-op: {repeated!r}")
        env = {
            "SESSION_RECALL_CODEX_FIX_ROOT": str(managed),
            "SESSION_RECALL_CODEX_STATE_DB": str(store["state"]),
            "SESSION_RECALL_CODEX_HISTORY_DB": str(store["history"]),
            "SESSION_RECALL_CODEX_SESSIONS_ROOT": str(store["sessions"]),
        }
        launched_version = require(run([str(launcher), "--version"], env=env, cwd=root))
        if launched_version.stdout.strip() != version:
            raise VerifyFailure("isolated launcher did not execute the bundled adapter")
        schema = _json(run([str(launcher), "schema-check", "--json"], env=env, cwd=root))
        if schema.get("ok") is not True or schema.get("profiles") != {
            "state": "codex-state-v5-migration-55",
            "history": "codex-thread-history-v1-migration-6",
        }:
            raise VerifyFailure(f"selected target55 rejected synthetic55: {schema!r}")
        listed = _json(run([str(launcher), "list", "--json"], env=env, cwd=root))
        if [row["summary"] for row in listed] != [
            "verify remote newest", "verify local scratch", "verify remote older",
        ]:
            raise VerifyFailure(f"isolated launcher output differs: {listed!r}")

        rolled = _json(run(
            [str(fix_cli), *common, "rollback", "--repair", str(operation_id)], cwd=root,
            timeout=120,
        ))
        if rolled.get("status") != "rolled_back_incompatible" or rolled.get("ok") is not True:
            raise VerifyFailure(f"isolated rollback was not incompatibility-honest: {rolled!r}")
        if json.loads(selection_path.read_bytes())["artifact_digest"] != recipe["source_adapter_digest"]:
            raise VerifyFailure("isolated rollback did not restore source52")
        refused_schema = _json(
            run([str(launcher), "schema-check", "--json"], env=env, cwd=root), 2
        )
        refused_list = _json(run([str(launcher), "list", "--json"], env=env, cwd=root), 2)
        for refused in (refused_schema, refused_list):
            if refused.get("error") != "schema_drift" or refused.get("query_executed") is not False:
                raise VerifyFailure(f"selected source52 did not refuse synthetic55: {refused!r}")
        if hash_tree(store["root"]) != store_before:
            raise VerifyFailure("isolated B lifecycle modified synthetic Codex storage")
    return ["wheel-plan=known52-to55", "wheel-apply=active", "wheel-reapply=no_op",
            "wheel-launcher=target55", "wheel-rollback=incompatible-source52",
            "wheel-data=complete", "wheel-codex-store=unchanged"]
