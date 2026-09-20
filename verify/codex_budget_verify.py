#!/usr/bin/env python3
"""Standalone synthetic verifier for Stage C budget units C1/C2 only."""

from __future__ import annotations

import argparse
import importlib
import json
import os
import shutil
import subprocess
import sys
import tempfile
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
C1_TEST_DIR = ROOT / "src/session_recall/codex_fix/tests"
C1_TESTS = [
    C1_TEST_DIR / "test_c_budget_contracts.py",
    C1_TEST_DIR / "test_c_budget_ledger.py",
    C1_TEST_DIR / "test_c_budget_review.py",
]
C2_TESTS = [ROOT / "verify" / f"test_c_budget_store{s}.py" for s in ("", "_review", "_proofs", "_headroom")]
PROBES = None
MANIFEST_API = None

class VerifyFailure(AssertionError):
    pass

class InfraFailure(RuntimeError):
    pass

class SelfTestFailure(RuntimeError):
    pass


class VerifyTimeout(RuntimeError):
    pass


class ArgumentFailure(ValueError):
    pass


class JsonParser(argparse.ArgumentParser):
    def error(self, message: str) -> None:
        raise ArgumentFailure(message)


def _bootstrap() -> None:
    global PROBES, MANIFEST_API
    try:
        PROBES = importlib.import_module("codex_budget_verify_probes")
        MANIFEST_API = importlib.import_module("codex_budget_verify_manifest")
    except Exception as exc:
        raise InfraFailure(
            f"budget verifier helper bootstrap failed: {type(exc).__name__}: {exc}"
        ) from exc


def _environment(home: Path, *, pythonpath: str | None = None) -> dict[str, str]:
    environment = {
        "HOME": str(home),
        "LC_ALL": "C",
        "TZ": "UTC",
        "PATH": os.defpath,
        "PYTHONHASHSEED": "0",
        "PYTHONDONTWRITEBYTECODE": "1",
        "PYTEST_DISABLE_PLUGIN_AUTOLOAD": "1",
        "NO_NETWORK": "1",
    }
    if pythonpath is not None:
        environment["PYTHONPATH"] = pythonpath
    return environment


def _run(argv: list[str], *, cwd: Path, env: dict[str, str], timeout: int = 120):
    try:
        return subprocess.run(
            argv,
            cwd=cwd,
            env=env,
            text=True,
            capture_output=True,
            timeout=timeout,
            check=False,
        )
    except subprocess.TimeoutExpired as exc:
        raise VerifyTimeout(f"timeout after {timeout}s") from exc


def _pytest(paths: list[Path]) -> None:
    with tempfile.TemporaryDirectory(prefix="codex-budget-pytest-") as temporary:
        home = Path(temporary)
        config = home / "pytest-empty.ini"
        config.write_text("[pytest]\n", encoding="utf-8")
        child_path = os.pathsep.join((str(ROOT), str(ROOT / "src")))
        environment = _environment(home, pythonpath=child_path)
        preflight = _run(
            [
                sys.executable,
                "-c",
                "import json,pathlib,pytest;"
                "import session_recall.codex_fix.budget as b;"
                "print(json.dumps({'budget':str(pathlib.Path(b.__file__).resolve()),"
                "'pytest':pytest.__version__},sort_keys=True))",
            ],
            cwd=home,
            env=environment,
            timeout=30,
        )
        if preflight.returncode != 0:
            raise InfraFailure(
                "pytest/product import preflight failed: "
                + (preflight.stdout + preflight.stderr)[-1000:]
            )
        try:
            provenance = json.loads(preflight.stdout.splitlines()[-1])
            budget_path = Path(provenance["budget"])
            budget_path.relative_to((ROOT / "src").resolve())
        except (IndexError, KeyError, json.JSONDecodeError, ValueError) as exc:
            raise InfraFailure("budget import did not resolve under repository src") from exc
        result = _run(
            [
                sys.executable,
                "-m",
                "pytest",
                "-c",
                str(config),
                f"--rootdir={ROOT}",
                "-W",
                "error",
                "--noconftest",
                *(str(path) for path in paths),
                "-q",
                "-p",
                "no:cacheprovider",
                "--import-mode=importlib",
            ],
            cwd=ROOT,
            env=environment,
            timeout=180,
        )
    if result.returncode != 0:
        detail = (result.stdout + result.stderr)[-2000:]
        if result.returncode == 1:
            raise VerifyFailure(f"pytest assertions failed: {detail}")
        raise InfraFailure(f"pytest collection/dependency exit {result.returncode}: {detail}")


def _behavior_child() -> dict:
    probe = (
        "import json;from codex_budget_verify_probes import behavior_observation;"
        "print(json.dumps(behavior_observation(),sort_keys=True))"
    )
    with tempfile.TemporaryDirectory(prefix="codex-budget-probe-") as temporary:
        result = _run(
            [sys.executable, "-c", probe], cwd=Path(temporary),
            env=_environment(
                Path(temporary), pythonpath=os.pathsep.join(
                    (str(ROOT / "src"), str(ROOT / "verify"))
                )
            ), timeout=30,
        )
    if result.returncode != 0:
        raise InfraFailure(
            f"behavior probe dependency failure: {(result.stdout + result.stderr)[-1000:]}"
        )
    try:
        return json.loads(result.stdout.splitlines()[-1])
    except (IndexError, json.JSONDecodeError) as exc:
        raise InfraFailure("behavior probe emitted invalid JSON") from exc


def verify_unit() -> list[str]:
    discovered = sorted(C1_TEST_DIR.glob("test_*c_budget*.py"))
    if discovered != C1_TESTS:
        raise InfraFailure(f"C1 test set changed: {[path.name for path in discovered]}")
    _pytest(C1_TESTS)
    observed = _behavior_child()
    if observed.get("verdict") == "fail":
        raise VerifyFailure(observed.get("reason", "behavior probe failed"))
    if observed.get("verdict") != "pass":
        raise InfraFailure(observed.get("reason", "behavior probe error"))
    PROBES.require_usage(observed["usage"])
    return ["c1-tests=pass", "usage=18000", "grant=+32000",
            "grant-replay=rejected", "overshoot=35000-charged"]


def verify_store() -> list[str]:
    cases = verify_unit()
    if not all(path.is_file() for path in C2_TESTS):
        raise InfraFailure("one or more frozen C2 store tests are missing")
    _pytest(C2_TESTS)
    return [*cases, "c2-store-tests=pass", "crash=old-or-new", "concurrency=one-hold"]


def self_test() -> list[str]:
    with tempfile.TemporaryDirectory(prefix="codex-budget-mutant-") as temporary:
        target = Path(temporary)
        shutil.copytree(ROOT / "src/session_recall", target / "session_recall")
        budget_path = target / "session_recall/codex_fix/budget.py"
        source = budget_path.read_text(encoding="utf-8")
        needle = '    return evidence["input_tokens"] + evidence["generated_tokens"]\n'
        replacement = (
            "    global VERIFY_MUTANT_EXECUTED\n"
            "    VERIFY_MUTANT_EXECUTED = True\n"
            '    return (evidence["input_tokens"] + evidence["cached_input_tokens"] + '
            'evidence["generated_tokens"] + evidence["reasoning_tokens"])\n'
        )
        if source.count(needle) != 1:
            raise SelfTestFailure("cannot construct exact usage mutant")
        budget_path.write_text(source.replace(needle, replacement), encoding="utf-8")
        probe = (
            "import json;from codex_budget_verify_probes import usage_observation;"
            "print(json.dumps(usage_observation(),sort_keys=True))"
        )
        pythonpath = os.pathsep.join((str(target), str(ROOT / "verify")))
        result = _run(
            [sys.executable, "-c", probe], cwd=target,
            env=_environment(target, pythonpath=pythonpath), timeout=30,
        )
        if result.returncode != 0:
            raise InfraFailure(
                f"mutant dependency/import failure: {(result.stdout + result.stderr)[-1000:]}"
            )
        try:
            observed = json.loads(result.stdout.splitlines()[-1])
        except (IndexError, json.JSONDecodeError) as exc:
            raise SelfTestFailure("mutant emitted invalid evidence") from exc
        if observed.get("mutant") is not True:
            raise SelfTestFailure(f"mutant was not imported: {observed!r}")
        try:
            PROBES.require_usage(observed)
        except PROBES.VerifyFailure as exc:
            if not str(exc).startswith("usage_subset_double_count:"):
                raise SelfTestFailure(f"wrong mutant detection: {exc}") from exc
        else:
            raise SelfTestFailure("normal usage detector accepted double counting")
    return ["mutant-imported=true", "double-count=detected", "dependency-failure=false"]


def emit(verdict: str, level: str, code: int, cases: list[str], started: float,
         reason: str | None = None) -> None:
    body = {
        "verdict": verdict, "scope": "budget-only", "level": level,
        "full_stage_c_verified": False, "exit": code,
        "executed_case_ids": cases,
        "duration_ms": round((time.monotonic() - started) * 1000),
    }
    if reason:
        body["reason"] = reason
    print(json.dumps(body, sort_keys=True))


def main(argv: list[str] | None = None) -> int:
    parser = JsonParser(
        description="Verify budget-only C1/C2 units",
        epilog="--help is the documented non-JSON exception.",
    )
    selected = parser.add_mutually_exclusive_group(required=True)
    selected.add_argument("--self-test", action="store_true")
    selected.add_argument("--level", choices=("unit", "store"))
    started = time.monotonic()
    try:
        args = parser.parse_args(argv)
    except ArgumentFailure as exc:
        return emit("error", "arguments", 2, [], started, str(exc)) or 2
    level = "self-test" if args.self_test else args.level
    try:
        _bootstrap()
        MANIFEST_API.verify_manifest("store" if args.level == "store" else "unit")
        cases = self_test() if args.self_test else (
            verify_unit() if args.level == "unit" else verify_store()
        )
    except VerifyTimeout as exc:
        return emit("error", level, 124, [], started, str(exc)) or 124
    except SelfTestFailure as exc:
        return emit("fail", level, 3, [], started, str(exc)) or 3
    except InfraFailure as exc:
        return emit("error", level, 2, [], started, str(exc)) or 2
    except VerifyFailure as exc:
        return emit("fail", level, 1, [], started, str(exc)) or 1
    except AssertionError as exc:
        return emit("fail", level, 1, [], started, str(exc)) or 1
    except MANIFEST_API.ManifestInfra as exc:
        return emit("error", level, 2, [], started, str(exc)) or 2
    except MANIFEST_API.ManifestTamper as exc:
        return emit("fail", level, 3, [], started, str(exc)) or 3
    except Exception as exc:
        reason = f"unexpected {type(exc).__name__}: {exc}"
        return emit("error", level, 2, [], started, reason) or 2
    emit("pass", level, 0, cases, started)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
