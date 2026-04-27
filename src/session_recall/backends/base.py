"""Abstract session backend interface."""
from __future__ import annotations
from abc import ABC, abstractmethod
from typing import Optional


class SessionBackend(ABC):
    @property
    @abstractmethod
    def name(self) -> str:
        """Backend identifier: 'copilot' or 'claude'."""

    @abstractmethod
    def is_available(self) -> bool:
        """Return True if the backing data store exists and is readable."""

    @abstractmethod
    def list_sessions(self, *, repo: Optional[str] = None, limit: int = 10, days: int = 30) -> list[dict]:
        """Return recent sessions as dicts matching SessionRecord shape."""

    @abstractmethod
    def list_files(self, *, repo: Optional[str] = None, limit: int = 20, days: int = 30) -> list[dict]:
        """Return recently touched files as dicts matching FileRecord shape."""

    @abstractmethod
    def search(self, query: str, *, repo: Optional[str] = None, limit: int = 10, days: int = 30) -> list[dict]:
        """Full-text search. Returns list of dicts with session + snippet fields."""

    @abstractmethod
    def show_session(self, session_id: str, *, turns: Optional[int] = None) -> Optional[dict]:
        """Return full session detail dict, or None if not found."""

    @abstractmethod
    def health(self) -> dict:
        """Return health dict with 'score', 'zone', 'dimensions' keys."""
