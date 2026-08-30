"""Synthetic legacy rollout JSONL files + adversarial variants."""

import json
import os
from pathlib import Path

LEGACY_USER_TEXT = "legacy hello from rollout"
LEGACY_AGENT_TEXT = "legacy agent reply"


def write_good_rollout(path: Path) -> Path:
    """Mixed current + old legacy shapes, plus ignorable noise records."""
    path.parent.mkdir(parents=True, exist_ok=True)
    records = [
        {"type": "session_meta", "payload": {"id": "synthetic"}},
        {"type": "event_msg",
         "payload": {"type": "user_message", "message": LEGACY_USER_TEXT}},
        {"type": "event_msg",
         "payload": {"type": "agent_reasoning", "text": "IGNORED reasoning"}},
        {"type": "event_msg",
         "payload": {"type": "agent_message", "message": LEGACY_AGENT_TEXT}},
        {"type": "response_item",
         "payload": {"type": "message", "role": "user",
                     "content": [{"type": "input_text",
                                  "text": "old-shape user text"}]}},
    ]
    with open(path, "w", encoding="utf-8") as f:
        for rec in records:
            f.write(json.dumps(rec) + "\n")
    return path


def write_drifted_rollout(path: Path) -> Path:
    """Only unknown shapes — must trigger rollout_shape_unrecognized."""
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        for i in range(4):
            f.write(json.dumps({"type": f"mystery_{i}", "blob": {"x": i}}) + "\n")
    return path


def write_malformed_rollout(path: Path) -> Path:
    """Valid line, then broken JSON, then valid line."""
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        f.write(json.dumps({"type": "event_msg",
                            "payload": {"type": "user_message",
                                        "message": "before the break"}}) + "\n")
        f.write("{this is not json at all\n")
        f.write(json.dumps({"type": "event_msg",
                            "payload": {"type": "agent_message",
                                        "message": "after the break"}}) + "\n")
    return path


def write_oversized_rollout(path: Path) -> Path:
    """Single line larger than the shared reader's 1MB bound."""
    path.parent.mkdir(parents=True, exist_ok=True)
    big = json.dumps({"type": "event_msg",
                      "payload": {"type": "user_message",
                                  "message": "A" * 1_100_000}})
    with open(path, "w", encoding="utf-8") as f:
        f.write(big + "\n")
    return path


def write_escape_symlink(sessions_root: Path, outside_dir: Path) -> Path:
    """Symlink under sessions_root pointing outside it (containment test)."""
    outside_dir.mkdir(parents=True, exist_ok=True)
    target = outside_dir / "outside-secret.jsonl"
    write_good_rollout(target)
    link = sessions_root / "2026" / "08" / "27" / "rollout-escape.jsonl"
    link.parent.mkdir(parents=True, exist_ok=True)
    if not link.exists():
        os.symlink(target, link)
    return link


def build_all(sessions_root: Path, outside_dir: Path) -> dict:
    base = sessions_root / "2026" / "08" / "27"
    return {
        "good": write_good_rollout(base / "rollout-legacy-recent.jsonl"),
        "drifted": write_drifted_rollout(base / "rollout-drifted.jsonl"),
        "malformed": write_malformed_rollout(base / "rollout-malformed.jsonl"),
        "oversized": write_oversized_rollout(base / "rollout-oversized.jsonl"),
        "escape": write_escape_symlink(sessions_root, outside_dir),
    }
