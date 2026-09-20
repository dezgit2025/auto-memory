"""Pure candidate preparation and deterministic artifact construction."""

import hashlib
import io
import json
from types import SimpleNamespace
import zipfile

import pytest

from session_recall.codex_fix import candidate
from session_recall.codex_fix.contracts import ContractError, canonical_bytes, digest
from session_recall.codex_fix.policy import model_policy


PROFILE = "session_recall/providers/codex/verifications/captured-profiles.json"


def _raw_digest(data):
    return "sha256:" + hashlib.sha256(data).hexdigest()


def _zip(entries):
    stream = io.BytesIO()
    with zipfile.ZipFile(stream, "w") as archive:
        for name, data in sorted(entries.items()):
            info = zipfile.ZipInfo(name, (1980, 1, 1, 0, 0, 0))
            info.external_attr = 0o100644 << 16
            archive.writestr(info, data)
    return stream.getvalue()


def _snapshot():
    def table(name, extra=()):
        columns = [{"cid": 0, "name": "id", "declared_type": "TEXT", "not_null": True,
                    "default_sql": None, "pk_position": 1}]
        columns.extend(extra)
        return {"name": name, "columns": columns}
    semantic = {
        "storage_family": "codex-state-v5-history-v1",
        "state": {"filename": "state_5.sqlite", "migration_ceiling": 56,
                  "failed_migrations": 0, "json1": True,
                  "tables": [table("threads", [{"cid": 1, "name": "future", "declared_type": "TEXT", "not_null": False, "default_sql": None, "pk_position": 0}]), table("_sqlx_migrations")]},
        "history": {"filename": "thread_history_1.sqlite", "migration_ceiling": 6,
                    "failed_migrations": 0, "json1": True,
                    "tables": [table("thread_items"), table("thread_turns"), table("_sqlx_migrations")]},
    }
    return {"format_version": 1, **semantic, "schema_fingerprint": digest(semantic), "diagnostics": []}


def _base(tmp_path):
    profiles = candidate.target_profiles(_snapshot(), None)
    entries = {
        "session_recall/providers/codex/schema.py": b"OLD = True\n",
        PROFILE: canonical_bytes(profiles),
        "untouched.txt": b"same",
    }
    # build_bytes validates the final manifest, while its base only needs bounded ZIP entries.
    raw = _zip(entries)
    path = tmp_path / "base.pyz"
    path.write_bytes(raw)
    return path, raw


def _request(base, raw):
    policy = model_policy()
    snapshot = _snapshot()
    return {
        "format_version": 1,
        "incident_id": "incident-56",
        "input_fingerprint": "sha256:" + "1" * 64,
        "base_artifact_digest": _raw_digest(raw),
        "catalogue_digest": "sha256:" + "2" * 64,
        "policy_digest": digest(policy),
        "acceptance_contract_digest": candidate.ACCEPTANCE_DIGEST,
        "allowed_paths": sorted(candidate.ALLOWED),
        "schema_diff": {"differences": [canonical_bytes(snapshot).decode()]},
        "source_files": [{"path": "session_recall/providers/codex/schema.py", "sha256": _raw_digest(b"OLD = True\n"), "content": "OLD = True\n"}, {"path": PROFILE, "sha256": _raw_digest(canonical_bytes(candidate.target_profiles(snapshot, None))), "content": canonical_bytes(candidate.target_profiles(snapshot, None)).decode()}],
    }


def _candidate(request, snapshot, **changes):
    content = canonical_bytes(candidate.target_profiles(snapshot, None)).decode()
    value = {"format_version": 1, "input_digest": digest(request),
             "base_artifact_digest": request["base_artifact_digest"],
             "files": [{"path": PROFILE, "sha256": _raw_digest(content.encode()), "content": content}]}
    value.update(changes)
    return value


def test_build_is_deterministic_preserves_unlisted_entries_and_rebuilds_manifest(tmp_path):
    base, raw = _base(tmp_path)
    snapshot = _snapshot()
    request = _request(base, raw)
    generated = _candidate(request, snapshot)
    first = candidate.build_bytes(request, generated, snapshot, base)
    second = candidate.build_bytes(request, generated, snapshot, base)
    assert first == second
    with zipfile.ZipFile(io.BytesIO(first)) as archive:
        assert archive.read("untouched.txt") == b"same"
        assert json.loads(archive.read(PROFILE)) == candidate.target_profiles(snapshot, None)
        manifest = json.loads(archive.read("ADAPTER-MANIFEST.json"))
        assert manifest["schema_fingerprint"] == snapshot["schema_fingerprint"]


@pytest.mark.parametrize("mutation", ["base", "path", "hash", "profile"])
def test_build_rejects_stale_or_unexpected_candidate_mutations(tmp_path, mutation):
    base, raw = _base(tmp_path)
    snapshot = _snapshot()
    request = _request(base, raw)
    generated = _candidate(request, snapshot)
    if mutation == "base":
        request["base_artifact_digest"] = "sha256:" + "f" * 64
    elif mutation == "path":
        generated["files"][0]["path"] = "session_recall/providers/codex/tests/test_cli.py"
    elif mutation == "hash":
        generated["files"][0]["sha256"] = "sha256:" + "f" * 64
    else:
        generated["files"][0]["content"] = "{}"
        generated["files"][0]["sha256"] = _raw_digest(b"{}")
    with pytest.raises(ContractError):
        candidate.build_bytes(request, generated, snapshot, base)


def test_prepare_uses_trusted_observation_policy_and_allowlisted_archive_sources(tmp_path, monkeypatch):
    base, raw = _base(tmp_path)
    snapshot = _snapshot()
    threads = snapshot["state"]["tables"][0]["columns"]
    threads.extend(
        {"cid": index, "name": f"synthetic_column_{index:03d}",
         "declared_type": "TEXT", "not_null": False,
         "default_sql": None, "pk_position": 0}
        for index in range(2, 202)
    )
    semantic = {key: snapshot[key] for key in ("storage_family", "state", "history")}
    snapshot["schema_fingerprint"] = digest(semantic)
    policy = model_policy()
    observation = {"snapshot": snapshot, "input_fingerprint": "sha256:" + "1" * 64,
                   "adapter": {"kind": "managed", "artifact_digest": _raw_digest(raw), "profile_id": "old"},
                   "catalogue_digest": "sha256:" + "2" * 64, "policy_digest": "sha256:" + "3" * 64,
                   "format_version": 1}
    context = SimpleNamespace(current_observation=observation, catalogue_digest=observation["catalogue_digest"])
    strict_manifest = candidate.artifacts.manifest
    monkeypatch.setattr(candidate.artifacts, "resolve", lambda *_: base)
    monkeypatch.setattr(
        candidate.artifacts,
        "manifest",
        lambda path, expected: {} if path == base else strict_manifest(path, expected),
    )
    request = candidate.prepare(context, policy)
    assert request["policy_digest"] == digest(policy)
    assert request["acceptance_contract_digest"] == candidate.ACCEPTANCE_DIGEST
    assert {item["path"] for item in request["source_files"]} == {PROFILE, "session_recall/providers/codex/schema.py"}
    differences = request["schema_diff"]["differences"]
    assert all(len(item.encode("utf-8")) <= 4096 for item in differences)
    profile_parts = [item.split(":", 1)[1] for item in differences if item.startswith("target_profiles_part_")]
    provided_profile = "".join(profile_parts)
    assert provided_profile == canonical_bytes(candidate.target_profiles(snapshot, None)).decode()
    assert "future" in "".join(differences)
    generated = {
        "format_version": 1,
        "input_digest": digest(request),
        "base_artifact_digest": request["base_artifact_digest"],
        "files": [{"path": PROFILE, "sha256": _raw_digest(provided_profile.encode()),
                   "content": provided_profile}],
    }
    assert candidate.build_bytes(request, generated, snapshot, base).startswith(b"PK")


def test_build_rejects_duplicate_base_entries_and_oversized_replacements(tmp_path):
    base, raw = _base(tmp_path)
    snapshot = _snapshot()
    request = _request(base, raw)
    generated = _candidate(request, snapshot)

    duplicate = io.BytesIO()
    with pytest.warns(UserWarning, match="Duplicate name"):
        with zipfile.ZipFile(duplicate, "w") as archive:
            archive.writestr("same", b"a")
            archive.writestr("same", b"b")
    base.write_bytes(duplicate.getvalue())
    request["base_artifact_digest"] = _raw_digest(duplicate.getvalue())
    generated["input_digest"] = digest(request)
    generated["base_artifact_digest"] = request["base_artifact_digest"]
    with pytest.raises(ContractError):
        candidate.build_bytes(request, generated, snapshot, base)

    base, raw = _base(tmp_path)
    request = _request(base, raw)
    generated = _candidate(request, snapshot)
    content = "x" * (256 * 1024 + 1)
    generated["files"] = [{"path": PROFILE, "sha256": _raw_digest(content.encode()),
                           "content": content}]
    with pytest.raises(ContractError):
        candidate.build_bytes(request, generated, snapshot, base)
