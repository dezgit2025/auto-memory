"""Pure candidate input preparation and deterministic adapter patch building."""

from __future__ import annotations

import hashlib
import io
from pathlib import Path
import tempfile
from typing import Any
import zipfile

from . import artifacts
from ._candidate_contracts import ALLOWED_PROVIDER_PATHS, validate_candidate, validate_input
from .c_contracts import validate_c
from .contracts import ContractError, canonical_bytes, digest, validate

ALLOWED = ALLOWED_PROVIDER_PATHS
CHECK_IDS = (
    "artifact_manifest_v1",
    "synthetic_schema_v1",
    "trial_cli_contract_v1",
    "unknown_drift_rejected_v1",
    "synthetic_no_write_v1",
    "sandbox_denials_v1",
)
ACCEPTANCE_DIGEST = digest(
    {"contract": "candidate-acceptance-v1", "check_ids": list(CHECK_IDS)}
)
FIXED_TIME = (1980, 1, 1, 0, 0, 0)


def _raw_digest(data: bytes) -> str:
    return "sha256:" + hashlib.sha256(data).hexdigest()


def _read_base(path: Path) -> tuple[bytes, dict[str, bytes]]:
    try:
        raw = artifacts._artifact_bytes(path)
        if len(raw) > artifacts.MAX_ARTIFACT_BYTES:
            raise ContractError("invalid_artifact")
        with zipfile.ZipFile(io.BytesIO(raw)) as archive:
            infos = archive.infolist()
            artifacts._inspect_members(infos)
            entries = {info.filename: archive.read(info) for info in infos}
    except ContractError:
        raise
    except (OSError, RuntimeError, zipfile.BadZipFile) as exc:
        raise ContractError("invalid_artifact") from exc
    return raw, entries


def _source(path: str, data: bytes) -> dict[str, str]:
    try:
        content = data.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise ContractError("invalid_source_content") from exc
    return {"path": path, "sha256": _raw_digest(data), "content": content}


def _profile(snapshot_profile: dict[str, Any], side: str) -> dict[str, Any]:
    tables = {}
    for table in snapshot_profile["tables"]:
        tables[table["name"]] = [
            [
                column["cid"], column["name"], column["declared_type"],
                int(column["not_null"]), column["default_sql"], column["pk_position"],
            ]
            for column in table["columns"]
        ]
    ceiling = snapshot_profile["migration_ceiling"]
    family = "codex-state-v5" if side == "state" else "codex-thread-history-v1"
    return {
        "profile": f"{family}-migration-{ceiling}",
        "db_filename": snapshot_profile["filename"],
        "migration_ceiling": ceiling,
        "migration_description": "synthetic schema repair",
        "failed_migrations": snapshot_profile["failed_migrations"],
        "json1": snapshot_profile["json1"],
        "tables": tables,
    }


def target_profiles(
    snapshot: dict[str, Any], base_profiles: dict[str, Any] | None
) -> dict[str, Any]:
    """Convert a trusted metadata snapshot to the adapter's captured profile form."""
    validate(snapshot, "SchemaSnapshot")
    # base_profiles is accepted for a stable future extension point; target data
    # is wholly controller-derived so candidate text cannot influence metadata.
    if base_profiles is not None and (
        not isinstance(base_profiles, dict) or set(base_profiles) != {"state", "history"}
    ):
        raise ContractError("invalid_artifact")
    return {side: _profile(snapshot[side], side) for side in ("state", "history")}


def _chunks(label: str, text: str, *, maximum: int = 3500) -> list[str]:
    """Split UTF-8 text without breaking a code point or the contract byte limit."""
    pieces: list[str] = []
    current: list[str] = []
    size = 0
    for character in text:
        encoded = len(character.encode("utf-8"))
        if current and size + encoded > maximum:
            pieces.append("".join(current))
            current, size = [], 0
        current.append(character)
        size += encoded
    if current:
        pieces.append("".join(current))
    width = len(str(len(pieces)))
    return [
        f"{label}_part_{index:0{width}d}_of_{len(pieces)}:{piece}"
        for index, piece in enumerate(pieces, 1)
    ]


def schema_differences(snapshot: dict[str, Any]) -> list[str]:
    """Give the worker exact controller-derived target bytes in bounded records."""
    profiles = canonical_bytes(target_profiles(snapshot, None)).decode("utf-8")
    metadata = canonical_bytes(snapshot).decode("utf-8")
    return [
        "Replace captured-profiles.json with the exact UTF-8 concatenation of "
        "target_profiles_part records after their colon, ordered by part number.",
        *_chunks("target_profiles", profiles),
        *_chunks("target_snapshot", metadata),
    ]


def prepare(context: Any, policy: dict[str, Any]) -> dict[str, Any]:
    """Create the canonical, content-free worker request from trusted state."""
    observation = getattr(context, "current_observation", None)
    if not isinstance(observation, dict):
        raise ContractError("observation_required")
    snapshot = observation.get("snapshot")
    validate_c(policy, "ModelPolicy")
    validate(snapshot, "SchemaSnapshot")
    base_digest = observation.get("adapter", {}).get("artifact_digest")
    if not isinstance(base_digest, str):
        raise ContractError("managed_adapter_required")
    base_path = artifacts.resolve(base_digest, context)
    artifacts.manifest(base_path, base_digest)
    raw, entries = _read_base(base_path)
    if _raw_digest(raw) != base_digest:
        raise ContractError("artifact_digest_mismatch")
    sources = [
        _source(path, entries[path])
        for path in sorted(ALLOWED.intersection(entries))
    ]
    request = {
        "format_version": 1,
        "incident_id": "schema-" + observation["input_fingerprint"][7:31],
        "input_fingerprint": observation["input_fingerprint"],
        "base_artifact_digest": base_digest,
        "catalogue_digest": context.catalogue_digest,
        "policy_digest": digest(policy),
        "acceptance_contract_digest": ACCEPTANCE_DIGEST,
        "allowed_paths": sorted(source["path"] for source in sources),
        "schema_diff": {"differences": schema_differences(snapshot)},
        "source_files": sources,
    }
    return validate_input(request)


def _manifest(profiles: dict[str, Any], snapshot: dict[str, Any]) -> dict[str, Any]:
    return {
        "format_version": 1,
        "entry_point": artifacts.ENTRY_POINT,
        "profile_ids": {side: profiles[side]["profile"] for side in ("state", "history")},
        "schema_fingerprint": snapshot["schema_fingerprint"],
        "profiles": profiles,
    }


def _zip(entries: dict[str, bytes]) -> bytes:
    stream = io.BytesIO()
    with zipfile.ZipFile(stream, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=9) as archive:
        for name in sorted(entries):
            info = zipfile.ZipInfo(name, FIXED_TIME)
            info.compress_type = zipfile.ZIP_DEFLATED
            info.external_attr = 0o100644 << 16
            info.create_system = 3
            archive.writestr(info, entries[name])
    return stream.getvalue()


def build_bytes(
    request: dict[str, Any],
    candidate: dict[str, Any],
    snapshot: dict[str, Any],
    base_path: Path,
) -> bytes:
    """Apply validated full-file replacements and return a verified deterministic ZIP."""
    validate_input(request)
    validate_candidate(candidate, request)
    validate(snapshot, "SchemaSnapshot")
    if request["acceptance_contract_digest"] != ACCEPTANCE_DIGEST:
        raise ContractError("acceptance_contract_mismatch")
    raw, entries = _read_base(base_path)
    if _raw_digest(raw) != request["base_artifact_digest"]:
        raise ContractError("candidate_base_mismatch")
    replacements = {
        item["path"]: item["content"].encode("utf-8") for item in candidate["files"]
    }
    if set(replacements) - ALLOWED:
        raise ContractError("candidate_path_not_allowed")
    profiles = target_profiles(snapshot, None)
    expected_profile = canonical_bytes(profiles)
    if replacements.get(artifacts.PROFILE_RESOURCE) != expected_profile:
        raise ContractError("candidate_profile_mismatch")
    result = {**entries, **replacements}
    result[artifacts.PROFILE_RESOURCE] = expected_profile
    result["ADAPTER-MANIFEST.json"] = canonical_bytes(_manifest(profiles, snapshot))
    built = _zip(result)
    built_digest = _raw_digest(built)
    with tempfile.TemporaryDirectory(prefix="codex-candidate-check-") as temporary:
        path = Path(temporary) / "adapter.pyz"
        path.write_bytes(built)
        verified = artifacts.manifest(path, built_digest)
    if verified["schema_fingerprint"] != snapshot["schema_fingerprint"]:
        raise ContractError("candidate_profile_mismatch")
    return built


def build(
    request: dict[str, Any], candidate: dict[str, Any], snapshot: dict[str, Any], base_path: Path
) -> bytes:
    return build_bytes(request, candidate, snapshot, base_path)
