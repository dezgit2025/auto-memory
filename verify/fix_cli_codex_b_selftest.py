"""Stage B verifier mutation self-test."""

from __future__ import annotations

import shutil
import tempfile
from pathlib import Path

from fix_cli_codex_b_common import require_trust_observation
from fix_cli_codex_b_probes import trust_observation
from fix_cli_codex_common import ROOT, InfraFailure, VerifyFailure


def self_test_trust_bypass() -> list[str]:
    with tempfile.TemporaryDirectory(prefix="fix-cli-codex-b-mutant-") as temp:
        target = Path(temp)
        package = target / "session_recall"
        shutil.copytree(ROOT / "src/session_recall", package)
        trust_path = package / "codex_fix/trust.py"
        source = trust_path.read_text(encoding="utf-8")
        needle = "    if actual != TRUSTED_CATALOGUE_SHA256:\n"
        replacement = (
            "    global VERIFY_MUTANT_EXECUTED\n"
            "    VERIFY_MUTANT_EXECUTED = True\n"
            "    if False and actual != TRUSTED_CATALOGUE_SHA256:\n"
        )
        if source.count(needle) != 1:
            raise InfraFailure("cannot construct copied catalogue-trust mutant")
        trust_path.write_text(source.replace(needle, replacement), encoding="utf-8")
        observed = trust_observation(pythonpath=target)
        if observed != {"accepted": True, "code": None, "mutant": True}:
            raise VerifyFailure(f"trust mutant did not execute as designed: {observed!r}")
        try:
            require_trust_observation(observed)
        except VerifyFailure as exc:
            if str(exc) != "catalogue_trust_bypass":
                raise VerifyFailure(f"B self-test failed for wrong reason: {exc}") from exc
        else:
            raise VerifyFailure("normal trust detector accepted the copied bypass mutant")
    return ["mutant-imported=true", "expected-detection=catalogue_trust_bypass"]
