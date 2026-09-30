"""Digest-pinned, local-only adapter artifact resolution and inspection."""

from __future__ import annotations

import hashlib
import importlib.resources
import io
import json
import os
from pathlib import Path
import stat
from typing import Any
import zipfile

from .contracts import ContractError, canonical_bytes, digest, validate

MAX_ARTIFACT_BYTES = 32 * 1024 * 1024
MAX_RESOURCE_BYTES = 2 * 1024 * 1024
MAX_EXECUTABLE_BYTES = 1024 * 1024
MAX_EXPANDED_BYTES = 24 * 1024 * 1024
MAX_ENTRIES = 515
ENTRY_POINT = "session_recall.providers.codex.cli:main"
PROFILE_RESOURCE = "session_recall/providers/codex/verifications/captured-profiles.json"
USED_TABLES = {
    "state": ("threads", "_sqlx_migrations"),
    "history": ("thread_items", "thread_turns", "_sqlx_migrations"),
}


def _hex_digest(value: str) -> str:
    if (
        not isinstance(value, str)
        or len(value) != 71
        or not value.startswith("sha256:")
        or any(character not in "0123456789abcdef" for character in value[7:])
    ):
        raise ContractError("invalid_artifact", "invalid artifact digest")
    return value[7:]


def _regular(path: Path) -> os.stat_result:
    try:
        metadata = path.lstat()
    except OSError as exc:
        raise ContractError("artifact_missing", "artifact is unavailable") from exc
    if path.is_symlink() or not stat.S_ISREG(metadata.st_mode):
        raise ContractError("invalid_artifact", "artifact is not a regular file")
    if metadata.st_size > MAX_ARTIFACT_BYTES:
        raise ContractError("invalid_artifact", "artifact exceeds size limit")
    return metadata


def _within(path: Path, root: Path) -> bool:
    try:
        path.absolute().relative_to(root.absolute())
    except ValueError:
        return False
    return True


def _no_symlink_components(path: Path, root: Path) -> None:
    if not _within(path, root):
        raise ContractError("invalid_artifact", "artifact escaped its trusted root")
    cursor = root.absolute()
    if cursor.is_symlink():
        raise ContractError("invalid_artifact", "artifact root is a symlink")
    for component in path.absolute().relative_to(cursor).parts:
        cursor /= component
        if cursor.is_symlink():
            raise ContractError("invalid_artifact", "artifact path contains a symlink")


def _require_catalogue_membership(artifact_digest: str, context: Any) -> None:
    try:
        catalogue = context.catalogue
        validate(catalogue, "Catalogue")
        if digest(catalogue) != context.catalogue_digest:
            raise ContractError("untrusted_artifact")
        allowed = {catalogue["seed_artifact_digest"]}
        for recipe in catalogue["recipes"]:
            allowed.add(recipe["source_adapter_digest"])
            allowed.add(recipe["target_artifact_digest"])
    except (AttributeError, KeyError, TypeError, ContractError) as exc:
        raise ContractError(
            "untrusted_artifact", "artifact catalogue trust is unavailable"
        ) from exc
    if artifact_digest not in allowed:
        raise ContractError(
            "untrusted_artifact", "artifact digest is absent from the trusted catalogue"
        )


def resolve(artifact_digest: str, context: Any) -> Path:
    """Resolve a digest only from the managed cache or bundled artifact data."""
    hex_digest = _hex_digest(artifact_digest)
    _require_catalogue_membership(artifact_digest, context)
    managed_root = Path(context.managed_root)
    cached = managed_root / "artifacts" / "sha256" / hex_digest / "adapter.pyz"
    _no_symlink_components(cached, managed_root)
    if cached.exists() or cached.is_symlink():
        _regular(cached)
        return cached

    resource = importlib.resources.files("session_recall.codex_fix")
    bundled_item = resource.joinpath("data", "artifacts", f"{hex_digest}.pyz")
    try:
        bundled = Path(os.fspath(bundled_item))
    except TypeError as exc:
        raise ContractError(
            "artifact_missing", "bundled artifact is not filesystem-backed"
        ) from exc
    bundle_root = Path(os.fspath(resource)).joinpath("data", "artifacts")
    _no_symlink_components(bundled, bundle_root)
    _regular(bundled)
    return bundled


def _read_bounded(archive: zipfile.ZipFile, name: str) -> bytes:
    try:
        info = archive.getinfo(name)
    except KeyError as exc:
        raise ContractError("invalid_artifact", f"artifact omits {name}") from exc
    if info.file_size > MAX_RESOURCE_BYTES:
        raise ContractError("invalid_artifact", f"artifact resource is too large: {name}")
    data = archive.read(info)
    if len(data) != info.file_size:
        raise ContractError("invalid_artifact", f"artifact resource is truncated: {name}")
    return data


def _inspect_members(infos: list[zipfile.ZipInfo]) -> None:
    if len(infos) > MAX_ENTRIES:
        raise ContractError("invalid_artifact", "artifact has too many entries")
    total = 0
    names: set[str] = set()
    for info in infos:
        name = info.filename
        parts = Path(name).parts
        if (
            name in names
            or not name
            or name.startswith("/")
            or ".." in parts
            or "\\" in name
            or info.is_dir()
            or info.flag_bits & 0x1
        ):
            raise ContractError("invalid_artifact", "artifact has an unsafe entry")
        names.add(name)
        limit = MAX_EXECUTABLE_BYTES if name.endswith(".py") else MAX_RESOURCE_BYTES
        if info.file_size > limit:
            raise ContractError("invalid_artifact", f"artifact entry is too large: {name}")
        total += info.file_size
        if total > MAX_EXPANDED_BYTES:
            raise ContractError("invalid_artifact", "artifact expands beyond its budget")


def _artifact_bytes(path: Path) -> bytes:
    initial = _regular(path)
    flags = os.O_RDONLY | getattr(os, "O_CLOEXEC", 0) | getattr(os, "O_NOFOLLOW", 0)
    descriptor = os.open(path, flags)
    try:
        opened = os.fstat(descriptor)
        if not stat.S_ISREG(opened.st_mode) or opened.st_size > MAX_ARTIFACT_BYTES:
            raise ContractError("invalid_artifact", "artifact is not a bounded file")
        with os.fdopen(descriptor, "rb") as handle:
            descriptor = -1
            data = handle.read(MAX_ARTIFACT_BYTES + 1)
            after = os.fstat(handle.fileno())
    finally:
        if descriptor >= 0:
            os.close(descriptor)
    identities = {
        (item.st_dev, item.st_ino, item.st_size, item.st_mtime_ns)
        for item in (initial, opened, after)
    }
    if len(data) > MAX_ARTIFACT_BYTES or len(identities) != 1:
        raise ContractError("invalid_artifact", "artifact changed while reading")
    return data


def _load_canonical(data: bytes, label: str) -> dict[str, Any]:
    try:
        value = json.loads(data.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ContractError("invalid_artifact", f"invalid {label} JSON") from exc
    if not isinstance(value, dict) or canonical_bytes(value) != data:
        raise ContractError("invalid_artifact", f"{label} is not canonical")
    return value


def _used_profile(profile: dict[str, Any], side: str) -> dict[str, Any]:
    expected = {
        "profile", "db_filename", "migration_ceiling", "migration_description",
        "failed_migrations", "json1", "tables",
    }
    if not isinstance(profile, dict) or set(profile) != expected:
        raise ContractError("invalid_artifact", f"invalid {side} profile")
    tables = profile["tables"]
    if not isinstance(tables, dict) or set(tables) != set(USED_TABLES[side]):
        raise ContractError("invalid_artifact", f"invalid {side} tables")
    projected = []
    for table_name in USED_TABLES[side]:
        rows = tables[table_name]
        if not isinstance(rows, list):
            raise ContractError("invalid_artifact", f"invalid {side}.{table_name}")
        columns = []
        for row in rows:
            if not isinstance(row, list) or len(row) != 6:
                raise ContractError("invalid_artifact", "invalid profile column")
            columns.append(
                {
                    "cid": row[0], "name": row[1], "declared_type": row[2],
                    "not_null": bool(row[3]), "default_sql": row[4],
                    "pk_position": row[5],
                }
            )
        projected.append({"name": table_name, "columns": columns})
    result = {
        "filename": profile["db_filename"],
        "migration_ceiling": profile["migration_ceiling"],
        "failed_migrations": profile["failed_migrations"],
        "json1": profile["json1"],
        "tables": projected,
    }
    validate(result, "UsedProfile")
    return result


def manifest(path: Path, expected_digest: str) -> dict[str, Any]:
    """Verify artifact bytes and its frozen manifest/resource relationship."""
    expected_hex = _hex_digest(expected_digest)
    artifact = _artifact_bytes(path)
    if hashlib.sha256(artifact).hexdigest() != expected_hex:
        raise ContractError("artifact_digest_mismatch", "artifact digest does not match")
    try:
        with zipfile.ZipFile(io.BytesIO(artifact)) as archive:
            _inspect_members(archive.infolist())
            raw_manifest = _read_bounded(archive, "ADAPTER-MANIFEST.json")
            raw_profiles = _read_bounded(archive, PROFILE_RESOURCE)
    except (OSError, zipfile.BadZipFile, RuntimeError) as exc:
        raise ContractError("invalid_artifact", "artifact is not a valid ZIP") from exc
    value = _load_canonical(raw_manifest, "adapter manifest")
    if set(value) != {
        "format_version", "entry_point", "profile_ids", "schema_fingerprint", "profiles"
    } or value["format_version"] != 1 or value["entry_point"] != ENTRY_POINT:
        raise ContractError("invalid_artifact", "adapter manifest shape is invalid")
    profiles = value["profiles"]
    if not isinstance(profiles, dict) or set(profiles) != {"state", "history"}:
        raise ContractError("invalid_artifact", "adapter profiles are invalid")
    if canonical_bytes(profiles) != raw_profiles:
        raise ContractError("invalid_artifact", "manifest profiles differ from resource")
    profile_ids = value["profile_ids"]
    expected_ids = {side: profiles[side].get("profile") for side in ("state", "history")}
    if profile_ids != expected_ids:
        raise ContractError("invalid_artifact", "profile identifiers are inconsistent")
    semantic = {
        "storage_family": "codex-state-v5-history-v1",
        "state": _used_profile(profiles["state"], "state"),
        "history": _used_profile(profiles["history"], "history"),
    }
    if value["schema_fingerprint"] != digest(semantic):
        raise ContractError("invalid_artifact", "manifest schema digest is inconsistent")
    return value
