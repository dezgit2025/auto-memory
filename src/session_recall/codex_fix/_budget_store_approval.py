"""Immutable verified-human event contract for the C2 budget store."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from .contracts import ContractError, digest


@dataclass(frozen=True)
class ApprovalEvent:
    source_id: str
    event_id: str
    challenge_digest: str
    decision: str
    actor_label: str
    approved_at: str


def validate_event(event: Any, source: Any, challenge: dict[str, Any]) -> ApprovalEvent:
    if not isinstance(event, ApprovalEvent):
        raise ContractError("invalid_approval_event")
    if (
        event.source_id != getattr(source, "source_id", None)
        or event.challenge_digest != digest(challenge)
        or event.decision != "continue"
        or not event.event_id
        or not event.actor_label
    ):
        raise ContractError("approval_binding_mismatch")
    return event
