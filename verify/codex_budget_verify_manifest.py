"""Protected-file validation for the standalone budget-only verifier."""

from __future__ import annotations

import hashlib
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
MANIFEST = ROOT / "verify/codex-budget-hashes.txt"
UNIT_REQUIRED = {
    "src/session_recall/__init__.py",
    "src/session_recall/codex_fix/__init__.py",
    "src/session_recall/codex_fix/contracts.py",
    "src/session_recall/codex_fix/_contract_schema.py",
    "src/session_recall/codex_fix/_controller_config.py",
    "src/session_recall/codex_fix/budget.py",
    "src/session_recall/codex_fix/c_contracts.py",
    "src/session_recall/codex_fix/_c_validators.py",
    "src/session_recall/codex_fix/tests/__init__.py",
    "src/session_recall/codex_fix/tests/conftest.py",
    "src/session_recall/codex_fix/tests/_c_budget_fixtures.py",
    "src/session_recall/codex_fix/tests/test_c_budget_contracts.py",
    "src/session_recall/codex_fix/tests/test_c_budget_ledger.py",
    "src/session_recall/codex_fix/tests/test_c_budget_review.py",
    "verify/codex_budget_verify.py",
    "verify/codex_budget_verify_manifest.py",
    "verify/codex_budget_verify_probes.py",
}
STORE_REQUIRED = {
    "src/session_recall/codex_fix/budget_store.py",
    "verify/c_budget_store_fixtures.py",
    "verify/test_c_budget_store.py",
    "verify/test_c_budget_store_proofs.py",
    "verify/test_c_budget_store_headroom.py",
    "verify/test_c_budget_store_review.py",
}


class ManifestInfra(RuntimeError):
    pass


class ManifestTamper(RuntimeError):
    pass


def _entries() -> dict[str, str]:
    try:
        lines = MANIFEST.read_text(encoding="utf-8").splitlines()
    except OSError as exc:
        raise ManifestInfra(f"budget hash manifest unavailable: {MANIFEST}") from exc
    entries: dict[str, str] = {}
    for number, line in enumerate(lines, 1):
        if not line.strip() or line.lstrip().startswith("#"):
            continue
        parts = line.split(maxsplit=1)
        if len(parts) != 2:
            raise ManifestTamper(f"invalid budget manifest line {number}")
        expected, relative = parts[0].lower(), parts[1].strip()
        path = Path(relative)
        if (
            len(expected) != 64
            or any(character not in "0123456789abcdef" for character in expected)
            or path.is_absolute()
            or ".." in path.parts
            or "." in path.parts
            or relative != path.as_posix()
            or relative in entries
            or relative == str(MANIFEST.relative_to(ROOT))
        ):
            raise ManifestTamper(f"invalid budget manifest entry: {relative}")
        target = (ROOT / path).resolve()
        try:
            target.relative_to(ROOT.resolve())
        except ValueError as exc:
            raise ManifestTamper(f"budget manifest path escapes: {relative}") from exc
        if not target.is_file():
            raise ManifestTamper(f"budget manifest target missing: {relative}")
        if hashlib.sha256(target.read_bytes()).hexdigest() != expected:
            raise ManifestTamper(f"budget manifest digest mismatch: {relative}")
        entries[relative] = expected
    return entries


def verify_manifest(level: str) -> None:
    entries = _entries()
    required = set(UNIT_REQUIRED)
    if level == "store":
        required.update(STORE_REQUIRED)
        required.update(
            str(path.relative_to(ROOT))
            for path in (ROOT / "src/session_recall/codex_fix").glob(
                "_budget_store_*.py"
            )
        )
    missing = sorted(required - entries.keys())
    if missing:
        raise ManifestTamper(f"budget manifest omits: {missing}")
