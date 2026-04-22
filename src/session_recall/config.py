"""Configuration constants for auto-memory CLI."""

import os
from pathlib import Path

DB_PATH = os.environ.get(
    "SESSION_RECALL_DB",
    str(Path.home() / ".copilot" / "session-store.db"),
)

CLI_SESSION_STATE_ROOT = os.environ.get(
    "SESSION_RECALL_CLI_STATE_ROOT",
    str(Path.home() / ".copilot" / "session-state"),
)

TELEMETRY_PATH = os.environ.get(
    "SESSION_RECALL_TELEMETRY",
    str(Path.home() / ".copilot" / "scripts" / ".session-recall-stats.json"),
)

VSCODE_WORKSPACE_STORAGE = os.environ.get("SESSION_RECALL_VSCODE_STORAGE")
JETBRAINS_SESSIONS_ROOT = os.environ.get("SESSION_RECALL_JETBRAINS_ROOT")
NEOVIM_SESSIONS_ROOT = os.environ.get("SESSION_RECALL_NEOVIM_ROOT")

RETRY_DELAYS_MS = [50, 150, 450]
MAX_RETRIES = len(RETRY_DELAYS_MS)

EXPECTED_SCHEMA_VERSION = 1
