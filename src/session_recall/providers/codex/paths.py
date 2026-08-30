"""Codex storage path resolution and missing-storage diagnosis (plan §4.3, §16 Fix 6).

No globbing is ever used to pick a database to QUERY — a versioned filename
change must fail the pre-flight until the adapter is reviewed.  The sibling
scan below is diagnostics-only: it looks at FILENAMES to explain a failure
and never opens a file.
"""

import os
from dataclasses import dataclass
from pathlib import Path

DEFAULT_STATE_DB = "~/.codex/state_5.sqlite"
DEFAULT_HISTORY_DB = "~/.codex/thread_history_1.sqlite"
DEFAULT_SESSIONS_ROOT = "~/.codex/sessions"

ENV_STATE_DB = "SESSION_RECALL_CODEX_STATE_DB"
ENV_HISTORY_DB = "SESSION_RECALL_CODEX_HISTORY_DB"
ENV_SESSIONS_ROOT = "SESSION_RECALL_CODEX_SESSIONS_ROOT"


@dataclass(frozen=True)
class CodexPaths:
    """Resolved locations of Codex-owned storage (read-only targets)."""

    state_db: Path
    history_db: Path
    sessions_root: Path


def _resolve_one(env_var: str, default: str) -> Path:
    raw = os.environ.get(env_var) or default
    return Path(raw).expanduser()


def resolve_paths() -> CodexPaths:
    """Resolve the three configured paths; existence is checked by pre-flight."""
    return CodexPaths(
        state_db=_resolve_one(ENV_STATE_DB, DEFAULT_STATE_DB),
        history_db=_resolve_one(ENV_HISTORY_DB, DEFAULT_HISTORY_DB),
        sessions_root=_resolve_one(ENV_SESSIONS_ROOT, DEFAULT_SESSIONS_ROOT),
    )


def classify_missing_storage(codex_home: Path, expected_name: str) -> tuple[str, str]:
    """Diagnose a missing database: not installed vs storage version changed.

    Looks at FILENAMES only — never opens a sibling database (§16 Fix 6).
    Returns ``(error_code, human_message)``.
    """
    family = expected_name.split("_")[0]
    try:
        siblings = sorted(
            p.name
            for p in codex_home.iterdir()
            if p.name.startswith(family + "_") and p.suffix == ".sqlite"
        )
    except FileNotFoundError:
        siblings = []
    if siblings:
        return (
            "storage_version_changed",
            f"expected {expected_name}, found {', '.join(siblings)} — "
            "Codex changed its storage version; session-recall-codex must be "
            "reviewed and updated for this Codex release. "
            "Run: session-recall-codex schema-check --json",
        )
    return (
        "storage_missing",
        f"no Codex storage found under {codex_home} — is Codex installed? "
        f"(expected {expected_name})",
    )
