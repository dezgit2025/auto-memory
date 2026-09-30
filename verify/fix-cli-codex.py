#!/usr/bin/env python3
"""Stage-gated verifier for plans/fix-cli-codex.md."""

from __future__ import annotations

import argparse
import importlib
import json
import subprocess
import sys
import time

from fix_cli_codex_common import (
    ROOT, InfraFailure, TamperFailure, TimeoutFailure, VerifyFailure,
)
from fix_cli_codex_manifest import verify_protected_manifest
from fix_cli_codex_probes import L1_PROBES, run_l2
from fix_cli_codex_selftest import self_test_broken_preflight


class ArgumentFailure(ValueError):
    """Command-line contract failure rendered as a JSON verdict."""


class JsonArgumentParser(argparse.ArgumentParser):
    def error(self, message: str) -> None:
        raise ArgumentFailure(message)


def emit(verdict: str, gate: str, stage_gate: str, exit_code: int, cases: list[str],
         reason: str | None = None, started: float | None = None) -> None:
    body: dict[str, object] = {
        "verdict": verdict,
        "gate": gate,
        "stage_gate": stage_gate,
        "exit": exit_code,
        "executed_case_ids": cases,
    }
    if reason:
        body["reason"] = reason
    if started is not None:
        body["duration_ms"] = round((time.monotonic() - started) * 1000)
    print(json.dumps(body, sort_keys=True))


def parser() -> argparse.ArgumentParser:
    out = JsonArgumentParser(
        description="Verify the Codex recall repair",
        epilog="Argument errors emit JSON; --help is the documented non-JSON exception.",
    )
    selected = out.add_mutually_exclusive_group(required=True)
    selected.add_argument("--phase", choices=("A", "B", "C"))
    selected.add_argument("--through", choices=("A", "B", "C"))
    out.add_argument("--level", choices=("L1", "L2"), default="L2")
    out.add_argument(
        "--step", choices=("A1", "A2", "A3", "A4", "A5", "B1", "B2", "B3")
    )
    out.add_argument("--self-test", action="store_true")
    return out


def run_c(self_test: bool) -> list[str]:
    command = [sys.executable, str(ROOT / 'verify/codex_assist_verify.py')]
    command.extend(['--self-test'] if self_test else ['--level', 'L2'])
    try:
        result = subprocess.run(command, cwd=ROOT, capture_output=True, text=True, timeout=300, check=False)
        body = json.loads(result.stdout.strip().splitlines()[-1])
    except (OSError, subprocess.SubprocessError, ValueError, IndexError) as exc:
        raise InfraFailure(f'V5 verifier unavailable: {type(exc).__name__}') from exc
    if result.returncode == 2:
        raise InfraFailure(body.get('reason', 'V5 verification infrastructure unavailable'))
    if result.returncode != 0 or body.get('verdict') != 'pass':
        raise VerifyFailure(body.get('reason', 'V5 verification failed'))
    if not self_test and body.get('full_stage_c_verified') is not True:
        raise VerifyFailure('V5 verifier did not establish full Stage C')
    return body.get('executed_case_ids', body.get('cases', []))


def main(argv: list[str] | None = None) -> int:
    started = time.monotonic()
    try:
        args = parser().parse_args(argv)
    except ArgumentFailure as exc:
        emit("error", "phase", "arguments", 2, [], str(exc), started)
        return 2
    selected = args.phase or args.through
    gate = "end" if args.self_test else ("phase" if args.level == "L1" else "end")
    stage_gate = f"{selected}-{args.level}" + (f"-{args.step}" if args.step else "")
    cases: list[str] = []
    try:
        verify_protected_manifest(include_b=selected in {"B", "C"})
        cases.append("protected-manifest")
        if selected == "C":
            if args.level != 'L2' or args.step is not None:
                raise InfraFailure('V5 Stage C supports the complete L2 gate only')
            if args.self_test:
                cases.extend(run_c(True))
                emit('pass', gate, 'C-self-test', 0, cases, started=started)
                return 0
        if args.self_test:
            if selected == "A":
                stage_gate = "A-self-test"
                details = self_test_broken_preflight()
                cases.extend(["A-SELF-PREFLIGHT-BYPASS", *details])
            else:
                stage_gate = "B-self-test"
                a_details = self_test_broken_preflight()
                cases.extend(["A-SELF-PREFLIGHT-BYPASS", *a_details])
                module = importlib.import_module("fix_cli_codex_b_selftest")
                details = module.self_test_trust_bypass()
                cases.extend(["B-SELF-CATALOGUE-TRUST-BYPASS", *details])
        elif args.level == "L1":
            if args.step is None:
                raise InfraFailure(f"L1 requires --step {selected}1..{selected}{'5' if selected == 'A' else '3'}")
            if not args.step.startswith(selected):
                raise InfraFailure(f"{selected} L1 cannot execute step {args.step}")
            if selected == "A":
                details = L1_PROBES[args.step]()
            else:
                module = importlib.import_module("fix_cli_codex_b_probes")
                details = module.L1_PROBES[args.step]()
            cases.extend([args.step, *details])
        else:
            if args.step is not None:
                raise InfraFailure("L2 is cumulative and does not accept --step")
            for case_id, probe in run_l2():
                cases.append(case_id)
                details = probe()
                cases.extend(details)
            if selected in {"B", "C"}:
                module = importlib.import_module("fix_cli_codex_b_probes")
                for case_id, probe in module.run_l2():
                    cases.append(case_id)
                    details = probe()
                    cases.extend(details)
            if selected == 'C':
                cases.extend(run_c(False))
    except VerifyFailure as exc:
        code = 3 if args.self_test else 1
        emit("fail", gate, stage_gate, code, cases, str(exc), started)
        return code
    except TamperFailure as exc:
        emit("fail", gate, stage_gate, 3, cases, str(exc), started)
        return 3
    except TimeoutFailure as exc:
        emit("fail", gate, stage_gate, 124, cases, str(exc), started)
        return 124
    except InfraFailure as exc:
        emit("error", gate, stage_gate, 2, cases, str(exc), started)
        return 2
    except Exception as exc:
        code = 3 if args.self_test else 2
        verdict = "fail" if args.self_test else "error"
        emit(verdict, gate, stage_gate, code, cases,
             f"unexpected verifier error {type(exc).__name__}: {exc}", started)
        return code
    emit("pass", gate, stage_gate, 0, cases, started=started)
    return 0


if __name__ == "__main__":
    sys.exit(main())
