"""Stable launcher for a digest-pinned selected or bundled Codex adapter."""

from __future__ import annotations

from argparse import Namespace
import os
from pathlib import Path
import subprocess
import sys
from typing import Any, Callable

from . import artifacts, factory
from ._store_io import read_json
from .context import Context
from .contracts import ContractError


def _selected(context: Context) -> tuple[Path, dict[str, Any]]:
    selection = read_json(context.paths["current_selection"], "Selection", missing_ok=True)
    artifact_digest = (
        context.catalogue["seed_artifact_digest"]
        if selection is None
        else selection["artifact_digest"]
    )
    path = artifacts.resolve(artifact_digest, context)
    return path, artifacts.manifest(path, artifact_digest)


def _environment(context: Context) -> dict[str, str]:
    environment = os.environ.copy()
    environment.pop("PYTHONPATH", None)
    environment.pop("PYTHONHOME", None)
    environment.update(
        {
            "PYTHONDONTWRITEBYTECODE": "1",
            "PYTHONIOENCODING": "utf-8",
            "PYTHONUTF8": "1",
            "SESSION_RECALL_CODEX_STATE_DB": str(context.paths["state_db"]),
            "SESSION_RECALL_CODEX_HISTORY_DB": str(context.paths["history_db"]),
            "SESSION_RECALL_CODEX_SESSIONS_ROOT": str(context.paths["sessions_root"]),
        }
    )
    return environment


def launch(argv: list[str], context: Context) -> int:
    """Validate, then replace this process with the active adapter on POSIX."""
    path, _manifest = _selected(context)
    command = [sys.executable, str(path), *argv]
    environment = _environment(context)
    if os.name == "posix":
        os.execve(sys.executable, command, environment)
        raise AssertionError("os.execve returned")
    completed = subprocess.run(command, env=environment, check=False)
    return completed.returncode


def _factory_args() -> Namespace:
    return Namespace(
        command="launch",
        root=None,
        state_db=None,
        history_db=None,
        sessions_root=None,
        config=None,
        auto=False,
        json=False,
        repair=None,
        plan=None,
    )


def main(
    argv: list[str] | None = None,
    *,
    context_factory: Callable[[Namespace], Context] = factory.production_context,
) -> int:
    arguments = list(sys.argv[1:] if argv is None else argv)
    try:
        context = context_factory(_factory_args())
        return launch(arguments, context)
    except ContractError as exc:
        print(f"error: {exc.code}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
