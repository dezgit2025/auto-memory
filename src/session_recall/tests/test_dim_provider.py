"""Tests for session_recall.health.dim_provider."""

from __future__ import annotations

from pathlib import Path

from session_recall.health.dim_provider import (
    check_file_inventory,
    check_path_discovery,
    check_provider_health,
    check_recent_activity,
    check_trust_model,
)


# ---------------------------------------------------------------------------
# Fake providers
# ---------------------------------------------------------------------------

class FakeFileProvider:
    provider_id = "vscode"
    provider_name = "VS Code"

    def __init__(
        self,
        roots: list[str | Path],
        files: list | None = None,
        sessions: list | None = None,
    ):
        self._roots = [Path(r) for r in roots]
        self._files = files or []
        self._sessions = sessions or []

    def _iter_files(self, days: int | None = None) -> list:
        return self._files

    def list_sessions(
        self, repo: str | None = None, limit: int = 20, days: int | None = None
    ) -> list:
        return self._sessions

    def is_available(self) -> bool:
        return any(r.exists() for r in self._roots)


class FakeCliProvider:
    provider_id = "cli"
    provider_name = "Copilot CLI"

    def __init__(
        self,
        db_path: str | Path,
        state_root: str | Path,
        state_files: list | None = None,
        sessions: list | None = None,
    ):
        self.db_path = str(db_path)
        self.state_root = Path(state_root)
        self._state_file_list = state_files or []
        self._sessions = sessions or []

    def _state_files(self) -> list:
        return self._state_file_list

    def list_sessions(
        self, repo: str | None = None, limit: int = 20, days: int | None = None
    ) -> list:
        return self._sessions

    def _has_db(self) -> bool:
        return Path(self.db_path).is_file()

    def is_available(self) -> bool:
        return Path(self.db_path).exists() or bool(self._state_file_list)


# ---------------------------------------------------------------------------
# check_path_discovery
# ---------------------------------------------------------------------------


def test_check_path_discovery_found(tmp_path: Path) -> None:
    root = tmp_path / "vscode-storage"
    root.mkdir()
    provider = FakeFileProvider(roots=[root])

    result = check_path_discovery(provider)

    assert result["zone"] == "GREEN"
    assert result["score"] == 10.0
    assert len(result["matched_paths"]) >= 1


def test_check_path_discovery_missing() -> None:
    provider = FakeFileProvider(roots=["/nonexistent/a", "/nonexistent/b"])

    result = check_path_discovery(provider)

    assert result["zone"] == "RED"
    assert result["score"] == 0.0
    assert result["matched_paths"] == []


def test_check_path_discovery_override_used(tmp_path: Path) -> None:
    db_file = tmp_path / "session-store.db"
    db_file.write_text("fake-db")
    provider = FakeCliProvider(db_path=db_file, state_root=tmp_path)

    result = check_path_discovery(provider)

    assert result["zone"] == "GREEN"
    assert str(db_file) in result["matched_paths"]


# ---------------------------------------------------------------------------
# check_file_inventory
# ---------------------------------------------------------------------------


def test_check_file_inventory_zero_files(tmp_path: Path) -> None:
    root = tmp_path / "store"
    root.mkdir()
    provider = FakeFileProvider(roots=[root], files=[])

    result = check_file_inventory(provider)

    assert result["zone"] == "RED"
    assert result["file_count"] == 0


def test_check_file_inventory_single_file(tmp_path: Path) -> None:
    root = tmp_path / "store"
    root.mkdir()
    provider = FakeFileProvider(roots=[root], files=["a.jsonl"])

    result = check_file_inventory(provider)

    assert result["zone"] == "GREEN"
    assert result["file_count"] == 1


def test_check_file_inventory_healthy(tmp_path: Path) -> None:
    root = tmp_path / "store"
    root.mkdir()
    provider = FakeFileProvider(
        roots=[root], files=["a.jsonl", "b.jsonl", "c.jsonl"]
    )

    result = check_file_inventory(provider)

    assert result["zone"] == "GREEN"
    assert result["file_count"] == 3


# ---------------------------------------------------------------------------
# check_recent_activity
# ---------------------------------------------------------------------------


def test_check_recent_activity_no_recent(tmp_path: Path) -> None:
    root = tmp_path / "store"
    root.mkdir()
    provider = FakeFileProvider(roots=[root], sessions=[])

    result = check_recent_activity(provider, lookback_days=5)

    assert result["zone"] == "RED"
    assert result["sessions_found"] == 0


def test_check_recent_activity_within_lookback(tmp_path: Path) -> None:
    root = tmp_path / "store"
    root.mkdir()
    sessions = [{"id": i} for i in range(5)]
    provider = FakeFileProvider(roots=[root], sessions=sessions)

    result = check_recent_activity(provider, lookback_days=5)

    assert result["zone"] == "GREEN"
    assert result["sessions_found"] == 5


def test_check_recent_activity_respects_lookback_param(tmp_path: Path) -> None:
    root = tmp_path / "store"
    root.mkdir()
    provider = FakeFileProvider(roots=[root], sessions=[{"id": 1}])

    result = check_recent_activity(provider, lookback_days=14)

    assert result["lookback_days"] == 14


# ---------------------------------------------------------------------------
# check_trust_model
# ---------------------------------------------------------------------------


def test_check_trust_model_third_party() -> None:
    provider = FakeFileProvider(roots=["/fake"])

    result = check_trust_model(provider)

    assert result["trust_level"] == "untrusted_third_party"
    assert result["fences_enabled"] is True


def test_check_trust_model_first_party(tmp_path: Path) -> None:
    provider = FakeCliProvider(db_path="/fake.db", state_root=tmp_path)

    result = check_trust_model(provider)

    assert result["trust_level"] == "trusted_first_party"
    assert result["fences_enabled"] is False


# ---------------------------------------------------------------------------
# check_provider_health (orchestrator)
# ---------------------------------------------------------------------------


def test_check_provider_health_orchestrator(tmp_path: Path) -> None:
    root = tmp_path / "store"
    root.mkdir()
    sessions = [{"id": i} for i in range(3)]
    files = ["a.jsonl", "b.jsonl"]
    provider = FakeFileProvider(roots=[root], files=files, sessions=sessions)

    results = check_provider_health(provider)

    assert len(results) == 4
    assert all(r["zone"] == "GREEN" for r in results)


def test_check_provider_health_mixed_zones(tmp_path: Path) -> None:
    root = tmp_path / "store"
    root.mkdir()
    provider = FakeFileProvider(roots=[root], files=[], sessions=[])

    results = check_provider_health(provider)

    assert len(results) == 4
    zones = [r["zone"] for r in results]
    assert "RED" in zones
