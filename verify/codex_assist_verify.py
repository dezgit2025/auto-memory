#!/usr/bin/env python3
"""Independent V5 assist verifier with mutation self-test and installed-wheel L2."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile


ROOT = Path(__file__).resolve().parents[1]
SCOPE = "codex-assist-v5"


def emit(level: str, verdict: str, cases: list[dict], *, full: bool, exit_code: int) -> int:
    print(json.dumps({"format_version": 1, "verdict": verdict, "scope": SCOPE,
                      "level": level, "full_stage_c_verified": full, "exit": exit_code,
                      "cases": cases},
                     sort_keys=True, separators=(",", ":")))
    return exit_code


def run(argv: list[str], *, cwd: Path, env=None, timeout=600) -> subprocess.CompletedProcess[str]:
    return subprocess.run(argv, cwd=cwd, env=env, text=True, capture_output=True, timeout=timeout)


def self_test() -> int:
    cases = []
    with tempfile.TemporaryDirectory(prefix="codex-assist-mutant-") as raw:
        work = Path(raw)
        shutil.copytree(ROOT / "src", work / "src")
        tests = work / "src/session_recall/codex_fix/tests"
        source_test = ROOT / "src/session_recall/codex_fix/tests/test_v5_candidate.py"
        shutil.copy2(source_test, tests / "test_v5_candidate.py")
        validator = work / "src/session_recall/codex_fix/_candidate_contracts.py"
        text = validator.read_text(encoding="utf-8")
        needle = "if actual != expected:\n        _fail(\"source_digest_mismatch\")"
        if text.count(needle) != 1:
            return emit("self-test", "infrastructure", [{"id": "mutation", "status": "fixture_drift"}],
                        full=False, exit_code=2)
        validator.write_text(text.replace(needle, "if False and actual != expected:\n        _fail(\"source_digest_mismatch\")"), encoding="utf-8")
        env = {**os.environ, "PYTHONPATH": str(work / "src"), "PYTEST_DISABLE_PLUGIN_AUTOLOAD": "1"}
        result = run([sys.executable, "-m", "pytest", "-q", "-W", "error",
                      str(tests / "test_v5_candidate.py")], cwd=work, env=env)
        caught = (
            result.returncode == 1
            and "FAILED" in result.stdout
            and "test_build_rejects_stale_or_unexpected_candidate_mutations[hash]" in result.stdout
            and "DID NOT RAISE" in result.stdout
            and "ContractError" in result.stdout
        )
        cases.append({"id": "candidate-source-digest-mutant", "status": "caught" if caught else "escaped",
                      "returncode": result.returncode})
        return emit("self-test", "pass" if caught else "fail", cases,
                    full=False, exit_code=0 if caught else 1)


def l2() -> int:
    cases: list[dict] = []
    env = {key: value for key, value in os.environ.items()
           if key not in {"PYTHONPATH", "PYTHONHOME"}}
    env.update({"PYTEST_DISABLE_PLUGIN_AUTOLOAD": "1", "PYTHONDONTWRITEBYTECODE": "1"})
    if sys.platform != "darwin" or shutil.which("sandbox-exec") is None:
        cases.append({"id": "real-sbpl", "status": "infrastructure"})
        return emit("L2", "infrastructure", cases, full=False, exit_code=2)
    probe = run(["sandbox-exec", "-p", "(version 1)(allow default)", "/usr/bin/true"],
                cwd=ROOT, env=env, timeout=30)
    if probe.returncode != 0:
        cases.append({"id": "real-sbpl", "status": "infrastructure",
                      "returncode": probe.returncode})
        return emit("L2", "infrastructure", cases, full=False, exit_code=2)
    cases.append({"id": "real-sbpl", "status": "pass"})
    suites = sorted((ROOT / "src/session_recall/codex_fix/tests").glob("test_v5_*.py"))
    tested = run([sys.executable, "-m", "pytest", "-q", "-W", "error", *map(str, suites)],
                 cwd=ROOT, env=env, timeout=900)
    cases.append({"id": "v5-pytest", "status": "pass" if tested.returncode == 0 else "fail",
                  "returncode": tested.returncode})
    if tested.returncode:
        return emit("L2", "fail", cases, full=False, exit_code=1)
    with tempfile.TemporaryDirectory(prefix="codex-assist-wheel-") as raw:
        work = Path(raw)
        dist = work / "dist"
        dist.mkdir()
        wheel = run([sys.executable, "-m", "pip", "wheel", "--no-deps", "--no-build-isolation",
                     "--wheel-dir", str(dist), str(ROOT)], cwd=work, env=env, timeout=600)
        if wheel.returncode:
            cases.append({"id": "offline-wheel", "status": "infrastructure", "returncode": wheel.returncode})
            return emit("L2", "infrastructure", cases, full=False, exit_code=2)
        wheels = list(dist.glob("*.whl"))
        if len(wheels) != 1:
            return emit("L2", "infrastructure", [*cases, {"id": "wheel-count", "status": "invalid"}],
                        full=False, exit_code=2)
        venv = work / "venv"
        made = run([sys.executable, "-m", "venv", str(venv)], cwd=work, env=env)
        python = venv / "bin/python"
        installed = run([str(python), "-m", "pip", "install", "--no-deps", "--no-index", str(wheels[0])],
                        cwd=work, env=env)
        if made.returncode or installed.returncode:
            return emit("L2", "infrastructure", [*cases, {"id": "isolated-install", "status": "fail"}],
                        full=False, exit_code=2)
        e2e_env = {**env, "VERIFY_ROOT": str(work / "world"), "VERIFY_WHEEL_ROOT": str(ROOT)}
        Path(e2e_env["VERIFY_ROOT"]).mkdir(mode=0o700)
        e2e = run([str(python), str(ROOT / "verify/codex_assist_e2e.py")], cwd=work,
                  env=e2e_env, timeout=900)
        try:
            detail = json.loads(e2e.stdout.splitlines()[-1])
        except (IndexError, json.JSONDecodeError):
            detail = {"status": "fail", "reason": "non-json-e2e-output"}
        status = detail.get("status")
        cases.append({"id": "installed-wheel-workflow", "status": status,
                      "returncode": e2e.returncode,
                      "wheel_sha256": hashlib.sha256(wheels[0].read_bytes()).hexdigest()})
        if status == "infrastructure" or e2e.returncode == 2:
            return emit("L2", "infrastructure", cases, full=False, exit_code=2)
        passed = e2e.returncode == 0 and status == "pass"
        return emit("L2", "pass" if passed else "fail", cases,
                    full=passed, exit_code=0 if passed else 1)


def main() -> int:
    parser = argparse.ArgumentParser()
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--self-test", action="store_true")
    group.add_argument("--level", choices=("L2", "workflow"))
    args = parser.parse_args()
    return self_test() if args.self_test else l2()


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (OSError, subprocess.SubprocessError, ValueError) as exc:
        raise SystemExit(
            emit("unknown", "infrastructure", [{"id": "verifier-exception",
                                                  "status": "infrastructure",
                                                  "reason": str(exc)[:512]}],
                 full=False, exit_code=2)
        )
