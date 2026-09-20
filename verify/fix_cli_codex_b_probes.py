"""Stage B gate composition and independent trust probe."""

from __future__ import annotations

import json
import sys
import tempfile
from pathlib import Path

from fix_cli_codex_b_common import (
    probe_cli_auto_policy,
    probe_lifecycle_and_unknown,
    require_trust_observation,
)
from fix_cli_codex_common import ROOT, VerifyFailure, require, run


EXPLICIT_TESTS = [
    ROOT / "verify/test_codex_artifact.py",
    ROOT / "verify/test_codex_store.py",
    ROOT / "verify/test_codex_store_security.py",
    ROOT / "verify/test_codex_store_review.py",
    ROOT / "verify/test_codex_factory.py",
    ROOT / "verify/test_codex_launcher.py",
]


def probe_b_tests() -> list[str]:
    result = run(
        [sys.executable, "-m", "pytest", str(ROOT / "src"),
         *(str(path) for path in EXPLICIT_TESTS), "-q", "-p", "no:cacheprovider",
         "--import-mode=importlib"],
        timeout=240,
    )
    require(result)
    return ["full-src=pass", "artifact=pass", "store=pass",
            "store-security=pass", "factory=pass", "launcher=pass"]


def trust_observation(*, pythonpath: Path | None = None) -> dict:
    script = r'''
import copy, json, tempfile
from pathlib import Path
from session_recall.codex_fix import trust
value = trust.load_catalogue()
forged = copy.deepcopy(value)
forged["catalogue_id"] = "private-forged-catalogue"
raw = json.dumps(forged, ensure_ascii=False, sort_keys=True,
                 separators=(",", ":")).encode("utf-8")
with tempfile.TemporaryDirectory(prefix="codex-trust-probe-") as temp:
    path = Path(temp) / "catalogue.json"
    path.write_bytes(raw)
    trust._catalogue_resource = lambda: path
    try:
        trust.load_catalogue()
    except Exception as exc:
        accepted, code = False, getattr(exc, "code", type(exc).__name__)
    else:
        accepted, code = True, None
print(json.dumps({"accepted": accepted, "code": code,
                  "mutant": getattr(trust, "VERIFY_MUTANT_EXECUTED", False)}))
'''
    env = {"PYTHONPATH": str(pythonpath)} if pythonpath is not None else None
    with tempfile.TemporaryDirectory(prefix="fix-cli-codex-b-trust-") as temp:
        result = require(run([sys.executable, "-c", script], env=env, cwd=Path(temp)))
    try:
        return json.loads(result.stdout.splitlines()[-1])
    except (IndexError, json.JSONDecodeError) as exc:
        raise VerifyFailure(f"trust probe emitted invalid evidence: {result.stdout!r}") from exc


def probe_trust_guard() -> list[str]:
    observed = trust_observation()
    require_trust_observation(observed)
    if observed.get("mutant"):
        raise VerifyFailure("production trust module contains mutant marker")
    return ["forged-catalogue=rejected", "reason=catalogue_untrusted"]


def probe_b_package() -> list[str]:
    from fix_cli_codex_b_package import verify_b_package

    return verify_b_package()


L1_PROBES = {
    "B1": lambda: [*probe_b_tests(), *probe_trust_guard()],
    "B2": lambda: [*probe_lifecycle_and_unknown(), *probe_cli_auto_policy()],
    "B3": probe_b_package,
}


def run_l2():
    yield "B1-tests", probe_b_tests
    yield "B1-trust", probe_trust_guard
    yield "B2-lifecycle", probe_lifecycle_and_unknown
    yield "B2-cli-auto", probe_cli_auto_policy
    yield "B3-package", probe_b_package
