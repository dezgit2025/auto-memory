"""Independent acceptance contract for the reviewed Codex migration-55 profile."""

import hashlib
import json
from pathlib import Path


ORACLE_SHA256 = "c880534b0aa1f8fccfdda5c1408f32481c7e6a7e795ec1b575412c0d803279ad"
REPO_ROOT = Path(__file__).resolve().parents[5]
ORACLE_PATH = REPO_ROOT / "verify" / "fixtures" / "codex-reviewed-55.json"
RUNTIME_PROFILE_PATH = (
    Path(__file__).resolve().parent.parent
    / "verifications"
    / "captured-profiles.json"
)


def _load(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def _acceptance_projection(profile: dict) -> dict:
    """Exclude migration descriptions; compare every acceptance-critical field."""
    return {
        side: {
            "profile": entry["profile"],
            "db_filename": entry["db_filename"],
            "migration_ceiling": entry["migration_ceiling"],
            "failed_migrations": entry["failed_migrations"],
            "json1": entry["json1"],
            "tables": entry["tables"],
        }
        for side, entry in profile.items()
    }


def test_reviewed_oracle_digest_is_frozen():
    assert hashlib.sha256(ORACLE_PATH.read_bytes()).hexdigest() == ORACLE_SHA256


def test_reviewed_oracle_identifies_exact_target():
    oracle = _load(ORACLE_PATH)
    assert oracle["state"]["profile"] == "codex-state-v5-migration-55"
    assert oracle["state"]["migration_ceiling"] == 55
    assert oracle["history"]["profile"] == "codex-thread-history-v1-migration-6"
    assert oracle["history"]["migration_ceiling"] == 6
    assert oracle["state"]["tables"]["threads"][-2:] == [
        [38, "originator", "TEXT", 0, None, 0],
        [39, "daybreak_enabled", "BOOLEAN", 0, None, 0],
    ]


def test_runtime_profile_matches_reviewed_oracle_projection():
    assert _acceptance_projection(_load(RUNTIME_PROFILE_PATH)) == (
        _acceptance_projection(_load(ORACLE_PATH))
    )
