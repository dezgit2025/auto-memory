"""Dependency container for provider-independent fixer operations."""

from __future__ import annotations

from dataclasses import dataclass
import os
from pathlib import Path
from types import MappingProxyType
from typing import Any, Callable, Mapping

from .contracts import ContractError, digest, validate


@dataclass(frozen=True)
class Context:
    """All trusted inputs needed by deterministic diagnosis and planning.

    ``paths`` contains exactly ``state_db``, ``history_db``, ``sessions_root``,
    and ``current_selection`` as :class:`Path` values. Production factories must
    derive ``current_selection`` from ``managed_root``; this value is injectable
    here only so hermetic controller tests do not need production state.
    """

    paths: Mapping[str, Path]
    managed_root: Path
    catalogue: dict[str, Any]
    catalogue_digest: str
    policy: dict[str, Any]
    policy_digest: str
    check_registry: Mapping[str, Callable[..., bool]]
    recapture: Callable[[], dict[str, Any]]
    test_hooks: Any | None
    adapter_identity: dict[str, Any]
    current_observation: dict[str, Any] | None = None

    def __post_init__(self) -> None:
        expected = {"state_db", "history_db", "sessions_root", "current_selection"}
        copied_paths = dict(self.paths)
        if set(copied_paths) != expected or any(
            not isinstance(path, Path) for path in copied_paths.values()
        ):
            raise ContractError("invalid_context", "Context.paths is invalid")
        if not isinstance(self.managed_root, Path):
            raise ContractError("invalid_context", "managed_root must be a Path")
        managed = Path(os.path.abspath(self.managed_root))
        selection = Path(os.path.abspath(copied_paths["current_selection"]))
        try:
            relative_selection = selection.relative_to(managed)
        except ValueError as exc:
            raise ContractError(
                "invalid_context", "current_selection must be inside managed_root"
            ) from exc
        cursor = managed
        if cursor.is_symlink():
            raise ContractError("invalid_context", "managed_root must not be a symlink")
        for component in relative_selection.parts[:-1]:
            cursor /= component
            if cursor.is_symlink():
                raise ContractError(
                    "invalid_context", "current_selection has a symlink parent"
                )
        object.__setattr__(self, "paths", MappingProxyType(copied_paths))
        validate(self.catalogue, "Catalogue")
        validate(self.policy, "ActivationPolicy")
        validate(self.adapter_identity, "AdapterIdentity")
        if digest(self.catalogue) != self.catalogue_digest:
            raise ContractError("digest_mismatch", "catalogue digest does not match")
        if digest(self.policy) != self.policy_digest:
            raise ContractError("digest_mismatch", "policy digest does not match")
        if not callable(self.recapture):
            raise ContractError("invalid_context", "recapture must be callable")
        if self.current_observation is not None:
            validate(self.current_observation, "Observation")
