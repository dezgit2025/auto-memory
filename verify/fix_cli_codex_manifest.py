"""Protected verifier/test manifest enforcement."""

from __future__ import annotations

import hashlib

from fix_cli_codex_common import ROOT, InfraFailure, TamperFailure

MANIFEST = ROOT / "src/session_recall/providers/codex/verifications/BASELINE-HASHES.txt"


def verify_protected_manifest(*, include_b: bool = False) -> None:
    try:
        lines = MANIFEST.read_text(encoding="utf-8").splitlines()
    except OSError as exc:
        raise InfraFailure(f"protected hash manifest missing: {MANIFEST}") from exc
    entries: dict[str, str] = {}
    for number, line in enumerate(lines, 1):
        if not line.strip() or line.lstrip().startswith("#"):
            continue
        parts = line.split(maxsplit=1)
        if len(parts) != 2 or len(parts[0]) != 64:
            raise TamperFailure(f"invalid manifest line {number}")
        digest, relative = parts[0].lower(), parts[1].strip()
        if relative == str(MANIFEST.relative_to(ROOT)):
            raise TamperFailure("protected manifest must not hash itself")
        if relative in entries or not all(ch in "0123456789abcdef" for ch in digest):
            raise TamperFailure(f"invalid/duplicate manifest entry: {relative}")
        target = (ROOT / relative).resolve()
        try:
            target.relative_to(ROOT.resolve())
        except ValueError as exc:
            raise TamperFailure(f"manifest path escapes repository: {relative}") from exc
        if not target.is_file():
            raise TamperFailure(f"manifest target missing: {relative}")
        if hashlib.sha256(target.read_bytes()).hexdigest() != digest:
            raise TamperFailure(f"protected hash mismatch: {relative}")
        entries[relative] = digest
    required = {
        "verify/fix-cli-codex.py",
        "verify/fix-cli-codex.yaml",
        "verify/fixtures/codex-reviewed-55.json",
        "src/session_recall/providers/codex/verifications/captured-profiles.json",
        "src/session_recall/providers/codex/verifications/_verify_lib.sh",
        "src/session_recall/providers/codex/verifications/smoke.sh",
        "src/session_recall/providers/codex/verifications/verify_schema.sh",
        "src/session_recall/providers/codex/verifications/spec.yaml",
    }
    required.update(
        str(path.relative_to(ROOT))
        for path in (ROOT / "verify").glob("fix_cli_codex_*.py")
        if not path.name.startswith("fix_cli_codex_b")
    )
    required.update(
        str(path.relative_to(ROOT))
        for path in (ROOT / "src/session_recall/providers/codex/tests").glob("*.py")
    )
    if include_b:
        required.update({"pyproject.toml", "scripts/build-codex-adapter.py",
                         "src/session_recall/codex_metadata.py"})
        required.update(
            str(path.relative_to(ROOT))
            for path in (ROOT / "src/session_recall/codex_fix").glob("*.py")
        )
        required.update(
            str(path.relative_to(ROOT))
            for path in (ROOT / "src/session_recall/codex_fix/tests").glob("*.py")
        )
        required.update(
            str(path.relative_to(ROOT))
            for path in (ROOT / "src/session_recall/codex_fix/data").rglob("*")
            if path.is_file()
        )
        required.update(
            str(path.relative_to(ROOT))
            for path in (ROOT / "verify").glob("fix_cli_codex_b*.py")
        )
        required.update({
            "verify/codex_factory_fixtures.py", "verify/codex_store_fixtures.py",
            "verify/test_codex_artifact.py", "verify/test_codex_factory.py",
            "verify/test_codex_launcher.py", "verify/test_codex_store.py",
            "verify/test_codex_store_review.py", "verify/test_codex_store_security.py",
        })
        required.update(str(path.relative_to(ROOT)) for path in (ROOT / 'verify').glob('codex_assist*.py'))
    missing = sorted(required - entries.keys())
    if missing:
        raise TamperFailure(f"protected manifest omits: {missing}")
