#!/usr/bin/env python3
"""Build a deterministic, self-contained session-recall Codex adapter zipapp."""

from __future__ import annotations

import argparse
import hashlib
import io
import json
import os
import stat
import sys
import zipfile
from pathlib import Path


ENTRY_POINT = "session_recall.providers.codex.cli:main"
STORAGE_FAMILY = "codex-state-v5-history-v1"
PROFILE_RESOURCE = (
    "session_recall/providers/codex/verifications/captured-profiles.json"
)
FIXED_TIME = (1980, 1, 1, 0, 0, 0)
MAX_SOURCE_FILES = 512
MAX_SOURCE_FILE_BYTES = 1_048_576
MAX_TOTAL_SOURCE_BYTES = 16_777_216
MAX_PATH_BYTES = 4096
USED_TABLES = {
    "state": ("threads", "_sqlx_migrations"),
    "history": ("thread_items", "thread_turns", "_sqlx_migrations"),
}
PROFILE_52_COLUMNS = (
    [38, "originator", "TEXT", 0, None, 0],
    [39, "daybreak_enabled", "BOOLEAN", 0, None, 0],
)
MAIN_SOURCE = b"""from session_recall.providers.codex.cli import main

if __name__ == "__main__":
    main()
"""


class BuildError(RuntimeError):
    """A bounded input or deterministic-build contract was violated."""


def _canonical_bytes(value: object) -> bytes:
    return json.dumps(
        value,
        ensure_ascii=False,
        allow_nan=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")


def _digest(value: object) -> str:
    data = value if isinstance(value, bytes) else _canonical_bytes(value)
    return "sha256:" + hashlib.sha256(data).hexdigest()


def _repo_paths() -> tuple[Path, Path, Path]:
    script = Path(__file__)
    if script.is_symlink():
        raise BuildError("builder script must not be a symlink")
    root = script.resolve().parents[1]
    package = root / "src" / "session_recall"
    profile = package / "providers" / "codex" / "verifications" / "captured-profiles.json"
    for path, label in ((package, "source package"), (profile, "reviewed profile")):
        if path.is_symlink() or not path.exists():
            raise BuildError(f"{label} is missing or a symlink: {path}")
    return root, package, profile


def _load_profile(path: Path, target: int) -> dict[str, object]:
    try:
        raw = path.read_bytes()
    except OSError as exc:
        raise BuildError(f"cannot read reviewed profile: {exc}") from exc
    if len(raw) > MAX_SOURCE_FILE_BYTES:
        raise BuildError("reviewed profile exceeds the file-size limit")
    try:
        profile = json.loads(raw)
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise BuildError(f"reviewed profile is invalid JSON: {exc}") from exc
    if not isinstance(profile, dict) or set(profile) != {"state", "history"}:
        raise BuildError("reviewed profile must contain exactly state and history")

    state = profile["state"]
    history = profile["history"]
    if not isinstance(state, dict) or not isinstance(history, dict):
        raise BuildError("state and history profiles must be JSON objects")
    if (
        state.get("profile") != "codex-state-v5-migration-55"
        or state.get("migration_ceiling") != 55
        or history.get("profile") != "codex-thread-history-v1-migration-6"
        or history.get("migration_ceiling") != 6
    ):
        raise BuildError("reviewed source is not the expected state-55/history-6 profile")
    columns = state.get("tables", {}).get("threads")
    if not isinstance(columns, list) or tuple(columns[-2:]) != PROFILE_52_COLUMNS:
        raise BuildError("reviewed source does not end with the two migration-53/54 columns")
    if target == 52:
        state["profile"] = "codex-state-v5-migration-52"
        state["migration_ceiling"] = 52
        state["migration_description"] = "projects recency"
        state["tables"]["threads"] = columns[:-2]
    return profile


def _used_profile(profile: dict[str, object], side: str) -> dict[str, object]:
    item = profile[side]
    tables = []
    for table_name in USED_TABLES[side]:
        try:
            rows = item["tables"][table_name]
        except (KeyError, TypeError) as exc:
            raise BuildError(f"profile omits used table {side}.{table_name}") from exc
        columns = []
        for row in rows:
            if not isinstance(row, list) or len(row) != 6:
                raise BuildError(f"invalid PRAGMA row in {side}.{table_name}")
            columns.append(
                {
                    "cid": row[0],
                    "name": row[1],
                    "declared_type": row[2],
                    "not_null": bool(row[3]),
                    "default_sql": row[4],
                    "pk_position": row[5],
                }
            )
        tables.append({"name": table_name, "columns": columns})
    return {
        "filename": item["db_filename"],
        "migration_ceiling": item["migration_ceiling"],
        "failed_migrations": item["failed_migrations"],
        "json1": item["json1"],
        "tables": tables,
    }


def _schema_fingerprint(profile: dict[str, object]) -> str:
    semantic = {
        "storage_family": STORAGE_FAMILY,
        "state": _used_profile(profile, "state"),
        "history": _used_profile(profile, "history"),
    }
    return _digest(semantic)


def _include_source(relative: Path) -> bool:
    parts = relative.parts
    if relative.suffix != ".py":
        return False
    if "tests" in parts or "__pycache__" in parts or "codex_fix" in parts:
        return False
    if parts[:3] == ("providers", "codex", "verifications"):
        return False
    return True


def _source_entries(package: Path) -> dict[str, bytes]:
    entries: dict[str, bytes] = {}
    total = 0
    for path in sorted(package.rglob("*"), key=lambda item: item.as_posix()):
        if path.is_symlink():
            raise BuildError(f"source tree contains a symlink: {path}")
        if not path.is_file():
            continue
        relative = path.relative_to(package)
        if not _include_source(relative):
            continue
        archive_path = Path("session_recall", relative).as_posix()
        if len(archive_path.encode("utf-8")) > 512:
            raise BuildError(f"archive path is too long: {archive_path}")
        data = path.read_bytes()
        if len(data) > MAX_SOURCE_FILE_BYTES:
            raise BuildError(f"source file exceeds size limit: {relative}")
        total += len(data)
        if total > MAX_TOTAL_SOURCE_BYTES or len(entries) >= MAX_SOURCE_FILES:
            raise BuildError("source tree exceeds the bounded artifact limits")
        entries[archive_path] = data
    if "session_recall/providers/codex/cli.py" not in entries:
        raise BuildError("Codex CLI entry point is missing from the source set")
    return entries


def _manifest(profile: dict[str, object], fingerprint: str) -> dict[str, object]:
    return {
        "format_version": 1,
        "entry_point": ENTRY_POINT,
        "profile_ids": {
            "state": profile["state"]["profile"],
            "history": profile["history"]["profile"],
        },
        "schema_fingerprint": fingerprint,
        "profiles": profile,
    }


def _zip_info(name: str) -> zipfile.ZipInfo:
    info = zipfile.ZipInfo(name, FIXED_TIME)
    info.compress_type = zipfile.ZIP_STORED
    info.create_system = 3
    info.external_attr = (stat.S_IFREG | 0o644) << 16
    return info


def _build_bytes(package: Path, profile: dict[str, object]) -> tuple[bytes, str]:
    fingerprint = _schema_fingerprint(profile)
    entries = _source_entries(package)
    entries["__main__.py"] = MAIN_SOURCE
    entries[PROFILE_RESOURCE] = _canonical_bytes(profile)
    entries["ADAPTER-MANIFEST.json"] = _canonical_bytes(_manifest(profile, fingerprint))
    output = io.BytesIO()
    with zipfile.ZipFile(output, "w", compression=zipfile.ZIP_STORED) as archive:
        for name in sorted(entries):
            archive.writestr(_zip_info(name), entries[name])
    return output.getvalue(), fingerprint


def _output_path(raw: str) -> Path:
    if not raw or len(raw.encode("utf-8")) > MAX_PATH_BYTES:
        raise BuildError("output path is empty or too long")
    unexpanded = Path(raw)
    if ".." in unexpanded.parts or unexpanded.suffix != ".pyz":
        raise BuildError("output must be a normalized .pyz path without '..'")
    output = unexpanded.expanduser()
    parent = output.parent.resolve(strict=True)
    if not parent.is_dir():
        raise BuildError("output parent is not a directory")
    if len(str(parent / output.name).encode("utf-8")) > MAX_PATH_BYTES:
        raise BuildError("resolved output path is too long")
    cursor = output.parent
    while cursor != cursor.parent:
        if cursor.is_symlink():
            raise BuildError(f"output ancestor is a symlink: {cursor}")
        cursor = cursor.parent
    return parent / output.name


def _write_once(path: Path, data: bytes) -> None:
    if path.exists() or path.is_symlink():
        if path.is_symlink() or not path.is_file():
            raise BuildError("output exists but is not a regular file")
        if path.stat().st_size != len(data):
            raise BuildError("output exists with different bytes")
        if path.read_bytes() != data:
            raise BuildError("output exists with different bytes")
        return
    try:
        descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o644)
        with os.fdopen(descriptor, "wb") as handle:
            handle.write(data)
            handle.flush()
            os.fsync(handle.fileno())
    except FileExistsError as exc:
        raise BuildError("output appeared concurrently") from exc


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--profile", required=True, choices=("52", "55"))
    parser.add_argument("--output", required=True, metavar="PATH.pyz")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    try:
        _root, package, profile_path = _repo_paths()
        profile = _load_profile(profile_path, int(args.profile))
        artifact, fingerprint = _build_bytes(package, profile)
        output = _output_path(args.output)
        _write_once(output, artifact)
    except (BuildError, KeyError, OSError, RuntimeError, TypeError, ValueError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    summary = {
        "artifact_digest": _digest(artifact),
        "schema_fingerprint": fingerprint,
        "output": str(output),
        "profile_ids": {
            "state": profile["state"]["profile"],
            "history": profile["history"]["profile"],
        },
    }
    print(_canonical_bytes(summary).decode("utf-8"))
    return 0


if __name__ == "__main__":
    sys.exit(main())
