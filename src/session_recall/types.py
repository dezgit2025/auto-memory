from __future__ import annotations
from typing import TypedDict


class SessionRecord(TypedDict):
    id: str
    repository: str
    branch: str
    summary: str
    created_at: str
    updated_at: str
    turns_count: int
    files_count: int


class TurnRecord(TypedDict):
    turn_index: int
    user_message: str
    assistant_response: str
    timestamp: str


class FileRecord(TypedDict):
    file_path: str
    tool_name: str
    turn_index: int


class CheckpointRecord(TypedDict):
    checkpoint_number: int
    title: str
    overview: str
    created_at: str


class HealthDimResult(TypedDict):
    name: str
    score: float
    detail: str


class TelemetryEntry(TypedDict):
    command: str
    timestamp: str
    duration_ms: int
    ok: bool
