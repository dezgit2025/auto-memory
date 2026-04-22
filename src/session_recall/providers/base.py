"""Provider interface for session storage backends."""

from __future__ import annotations

from abc import ABC, abstractmethod


class StorageProvider(ABC):
    """Common interface for all session storage providers."""

    provider_id: str
    provider_name: str

    @abstractmethod
    def is_available(self) -> bool:
        """Return True when this provider can be used on this machine."""

    @abstractmethod
    def list_sessions(
        self, repo: str | None, limit: int, days: int | None
    ) -> list[dict]:
        """List sessions in provider-native storage."""

    @abstractmethod
    def recent_files(
        self, repo: str | None, limit: int, days: int | None
    ) -> list[dict]:
        """List recent files with session attribution if available."""

    @abstractmethod
    def list_checkpoints(
        self, repo: str | None, limit: int, days: int | None
    ) -> list[dict]:
        """List checkpoint-style milestones if available."""

    @abstractmethod
    def search(
        self, query: str, repo: str | None, limit: int, days: int | None
    ) -> list[dict]:
        """Search session content."""

    @abstractmethod
    def get_session(
        self, session_id: str, turns: int | None, full: bool
    ) -> dict | None:
        """Return a single session payload, or None when not found."""

    def schema_problems(self) -> list[str]:
        """Return schema validation issues if meaningful for this provider."""
        return []
