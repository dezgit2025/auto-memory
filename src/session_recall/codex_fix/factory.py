"""Lazy production dependency factory for the deterministic Codex fixer."""

from __future__ import annotations

import os
from argparse import Namespace
from dataclasses import replace
from pathlib import Path
from typing import Any

from session_recall.codex_metadata import inspect
from session_recall.db.connect import connect_ro_raising

from . import artifacts, checks, trust
from ._store_io import read_json
from .context import Context
from .contracts import ContractError, digest, parse, validate


DEFAULT_POLICY = {
    "format_version": 1,
    "known_recipe_mode": "explicit",
    "startup_trigger": "none",
    "allow_downloads": False,
}
MAX_CONFIG_BYTES = 2 * 1024 * 1024


def _arg(args: Namespace, name: str) -> Any:
    return getattr(args, name, None)


def _path(value: str | None, fallback: str, label: str) -> Path:
    raw = value if value is not None else fallback
    if not isinstance(raw, str) or not raw or "\x00" in raw or len(raw.encode()) > 4096:
        raise ContractError("invalid_config", f"invalid {label} path")
    return Path(raw).expanduser()


def _read_config(raw_path: str | None) -> dict[str, Any] | None:
    if raw_path is None:
        return None
    path = _path(raw_path, "", "config")
    try:
        metadata = path.lstat()
        if path.is_symlink() or not path.is_file() or metadata.st_size > MAX_CONFIG_BYTES:
            raise ContractError("invalid_config", "controller config is unsafe")
        text = path.read_text(encoding="utf-8")
        return parse(text, "ControllerConfig")
    except ContractError:
        raise
    except (OSError, UnicodeError) as exc:
        raise ContractError("invalid_config", "controller config is unreadable") from exc


def _choose(args: Namespace, config: dict[str, Any] | None, name: str) -> str | None:
    explicit = _arg(args, name)
    if explicit is not None:
        return explicit
    return None if config is None else config[name]


def _root(args: Namespace, config: dict[str, Any] | None) -> Path:
    selected = _choose(args, config, "root")
    if selected is None:
        selected = os.environ.get("SESSION_RECALL_CODEX_FIX_ROOT")
    if selected is None:
        state_home = os.environ.get("XDG_STATE_HOME")
        selected = (
            str(Path(state_home) / "session-recall-codex-fix")
            if state_home
            else "~/.local/state/session-recall-codex-fix"
        )
    return _path(selected, "", "managed root")


def _storage_path(
    args: Namespace,
    config: dict[str, Any] | None,
    name: str,
    environment: str,
    fallback: str,
) -> Path:
    selected = _choose(args, config, name)
    if selected is None:
        selected = os.environ.get(environment)
    return _path(selected, fallback, name)


def _recapture(paths: dict[str, Path]):
    def capture() -> dict[str, Any]:
        state = connect_ro_raising(str(paths["state_db"]))
        try:
            history = connect_ro_raising(str(paths["history_db"]))
        except BaseException:
            state.close()
            raise
        try:
            return inspect((state, history))
        finally:
            history.close()
            state.close()

    return capture


def _identity(
    current_selection: Path,
    managed_root: Path,
    catalogue: dict[str, Any],
) -> dict[str, Any]:
    selection = read_json(current_selection, "Selection", missing_ok=True)
    if selection is None:
        kind = "bundled"
        artifact_digest = catalogue["seed_artifact_digest"]
    else:
        kind = selection["source"]
        artifact_digest = selection["artifact_digest"]

    provisional = type("ArtifactContext", (), {
        "managed_root": managed_root,
        "catalogue": catalogue,
        "catalogue_digest": digest(catalogue),
    })()
    profile_id = None
    try:
        path = artifacts.resolve(artifact_digest, provisional)
        value = artifacts.manifest(path, artifact_digest)
        profile_id = value["profile_ids"]["state"]
    except ContractError:
        if selection is None:
            raise
    return validate(
        {"kind": kind, "artifact_digest": artifact_digest, "profile_id": profile_id},
        "AdapterIdentity",
    )


def production_context(args: Namespace) -> Context:
    """Compose trusted local dependencies without opening either Codex database."""
    config = _read_config(_arg(args, "config"))
    managed_root = _root(args, config)
    paths = {
        "state_db": _storage_path(
            args, config, "state_db", "SESSION_RECALL_CODEX_STATE_DB", "~/.codex/state_5.sqlite"
        ),
        "history_db": _storage_path(
            args, config, "history_db", "SESSION_RECALL_CODEX_HISTORY_DB",
            "~/.codex/thread_history_1.sqlite",
        ),
        "sessions_root": _storage_path(
            args, config, "sessions_root", "SESSION_RECALL_CODEX_SESSIONS_ROOT",
            "~/.codex/sessions",
        ),
        "current_selection": managed_root / "selection" / "current.json",
    }
    policy = validate(
        dict(DEFAULT_POLICY) if config is None else config["activation_policy"],
        "ActivationPolicy",
    )
    catalogue = trust.load_catalogue()
    context = Context(
        paths=paths,
        managed_root=managed_root,
        catalogue=catalogue,
        catalogue_digest=digest(catalogue),
        policy=policy,
        policy_digest=digest(policy),
        check_registry=checks.registry(),
        recapture=_recapture(paths),
        test_hooks=None,
        adapter_identity=_identity(paths["current_selection"], managed_root, catalogue),
        current_observation=None,
    )
    from .assist import effective_context
    return effective_context(context)


def with_observation(context: Context) -> Context:
    """Recapture metadata and bind a fresh observation to an immutable Context."""
    from .engine import observe

    return replace(context, current_observation=observe(context.recapture(), context))
