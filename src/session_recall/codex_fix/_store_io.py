"""Filesystem, locking, record, and subprocess primitives for the store."""

from __future__ import annotations

from contextlib import contextmanager
from datetime import datetime, timezone
import errno
import fcntl
import json
import os
from pathlib import Path
import stat
import subprocess
import sys
import tempfile
from typing import Any, Iterator

from .contracts import ContractError, canonical_bytes, parse, validate

MAX_RECORD_BYTES = 2 * 1024 * 1024


def timestamp() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def protect_root(root: Path) -> None:
    try:
        metadata = root.lstat()
    except OSError as exc:
        raise ContractError("invalid_root", "managed root is unavailable") from exc
    if root.is_symlink() or not stat.S_ISDIR(metadata.st_mode):
        raise ContractError("invalid_root", "managed root is not a directory")
    if metadata.st_uid != os.getuid() or stat.S_IMODE(metadata.st_mode) & 0o077:
        raise ContractError("invalid_root", "managed root must be user-owned and private")
    for ancestor in (root.absolute(), *root.absolute().parents):
        item = ancestor.lstat()
        if ancestor.is_symlink():
            raise ContractError("invalid_root", "managed root ancestry has a symlink")
        writable = stat.S_IMODE(item.st_mode) & 0o022
        if writable and not item.st_mode & stat.S_ISVTX:
            raise ContractError("invalid_root", "managed root ancestry is writable")


def directory(root: Path, relative: str) -> Path:
    current = root
    for component in Path(relative).parts:
        current /= component
        try:
            current.mkdir(mode=0o700)
        except FileExistsError:
            pass
        metadata = current.lstat()
        if current.is_symlink() or not stat.S_ISDIR(metadata.st_mode):
            raise ContractError("invalid_root", "managed store path is unsafe")
        if metadata.st_uid != os.getuid():
            raise ContractError("invalid_root", "managed store path has another owner")
    return current


@contextmanager
def activation_lock(root: Path) -> Iterator[bool]:
    lock_dir = directory(root, "locks")
    path = lock_dir / "activation.lock"
    flags = os.O_RDWR | os.O_CREAT | getattr(os, "O_CLOEXEC", 0) | getattr(os, "O_NOFOLLOW", 0)
    descriptor = os.open(path, flags, 0o600)
    try:
        opened = os.fstat(descriptor)
        if not stat.S_ISREG(opened.st_mode) or opened.st_uid != os.getuid():
            raise ContractError("invalid_root", "activation lock is unsafe")
        try:
            fcntl.flock(descriptor, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError as exc:
            if exc.errno in {errno.EACCES, errno.EAGAIN}:
                yield False
                return
            raise ContractError("locking_unavailable", "activation lock failed") from exc
        yield True
    finally:
        os.close(descriptor)


def fsync_directory(path: Path) -> None:
    descriptor = os.open(path, os.O_RDONLY | getattr(os, "O_DIRECTORY", 0))
    try:
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


def atomic_json(path: Path, value: dict[str, Any], kind: str) -> None:
    validate(value, kind)
    parent = path.parent
    if parent.is_symlink() or not parent.is_dir():
        raise ContractError("invalid_root", "record parent is unsafe")
    data = canonical_bytes(value)
    descriptor, temporary_name = tempfile.mkstemp(prefix=f".{path.name}.", dir=parent)
    temporary = Path(temporary_name)
    try:
        os.fchmod(descriptor, 0o600)
        with os.fdopen(descriptor, "wb") as handle:
            descriptor = -1
            handle.write(data)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
        fsync_directory(parent)
    finally:
        if descriptor >= 0:
            os.close(descriptor)
        try:
            temporary.unlink()
        except FileNotFoundError:
            pass


def read_json(path: Path, kind: str, *, missing_ok: bool = False) -> dict[str, Any] | None:
    try:
        metadata = path.lstat()
    except FileNotFoundError:
        if missing_ok:
            return None
        raise ContractError("record_missing", f"missing {kind}") from None
    if path.is_symlink() or not stat.S_ISREG(metadata.st_mode) or metadata.st_size > MAX_RECORD_BYTES:
        raise ContractError("invalid_record", f"unsafe {kind} record")
    flags = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_NONBLOCK", 0)
    descriptor = os.open(path, flags)
    try:
        opened = os.fstat(descriptor)
        if not stat.S_ISREG(opened.st_mode):
            raise ContractError("invalid_record", f"unsafe {kind} record")
        before_identity = (metadata.st_dev, metadata.st_ino, metadata.st_size, metadata.st_mtime_ns)
        opened_identity = (opened.st_dev, opened.st_ino, opened.st_size, opened.st_mtime_ns)
        if before_identity != opened_identity:
            raise ContractError("invalid_record", f"changing {kind} record")
        with os.fdopen(descriptor, "rb") as handle:
            descriptor = -1
            data = handle.read(MAX_RECORD_BYTES + 1)
            after = os.fstat(handle.fileno())
    finally:
        if descriptor >= 0:
            os.close(descriptor)
    if len(data) > MAX_RECORD_BYTES or (opened.st_dev, opened.st_ino, opened.st_size, opened.st_mtime_ns) != (
        after.st_dev, after.st_ino, after.st_size, after.st_mtime_ns
    ):
        raise ContractError("invalid_record", f"changing {kind} record")
    try:
        return parse(data.decode("utf-8"), kind)
    except UnicodeDecodeError as exc:
        raise ContractError("invalid_record", f"non-UTF-8 {kind} record") from exc


def result(
    status: str,
    *,
    operation_id: str | None = None,
    plan_digest: str | None = None,
    prior: dict[str, Any] | None = None,
    current: dict[str, Any] | None = None,
    checks: list[str] | None = None,
    reason: str | None = None,
) -> dict[str, Any]:
    return validate(
        {
            "format_version": 1,
            "status": status,
            "operation_id": operation_id,
            "plan_digest": plan_digest,
            "prior_selection": prior,
            "current_selection": current,
            "executed_check_ids": checks or [],
            "reason_code": reason,
        },
        "ExecutionResult",
    )


def phase(
    path: Path,
    journal: dict[str, Any],
    value: str,
    context: Any,
    failure: str | None = None,
) -> None:
    journal["phase"] = value
    journal["updated_at"] = timestamp()
    journal["failure"] = failure
    atomic_json(path, journal, "Journal")
    hooks = context.test_hooks
    if hooks is not None:
        hooks.on_phase(value)


def selection(path: Path) -> dict[str, Any] | None:
    return read_json(path, "Selection", missing_ok=True)


def write_selection(
    selection_dir: Path,
    current_path: Path,
    prior: dict[str, Any] | None,
    target: dict[str, Any],
) -> None:
    if prior is not None:
        atomic_json(selection_dir / "previous.json", prior, "Selection")
    atomic_json(current_path, target, "Selection")


def postcheck(artifact: Path, context: Any) -> bool:
    environment = {
        "PYTHONDONTWRITEBYTECODE": "1",
        "PYTHONIOENCODING": "utf-8",
        "PYTHONUTF8": "1",
        "SESSION_RECALL_CODEX_STATE_DB": str(context.paths["state_db"]),
        "SESSION_RECALL_CODEX_HISTORY_DB": str(context.paths["history_db"]),
        "SESSION_RECALL_CODEX_SESSIONS_ROOT": str(context.paths["sessions_root"]),
    }
    try:
        from hashlib import sha256
        from .artifacts import _artifact_bytes
        artifact_digest = 'sha256:' + sha256(_artifact_bytes(artifact)).hexdigest()
        novel = any(r['recipe_id'].startswith('candidate-') and r['target_artifact_digest'] == artifact_digest for r in context.catalogue['recipes'])
        if novel:
            from .sandbox import Sandbox
            reads = [artifact]
            for name in ('state_db', 'history_db'):
                path = context.paths[name]
                reads.append(path)
                reads.extend(Path(str(path) + suffix) for suffix in ('-wal', '-shm') if Path(str(path) + suffix).exists())
            with tempfile.TemporaryDirectory(prefix='codex-approved-postcheck-') as temporary:
                workdir = Path(temporary).resolve()
                completed = Sandbox().run([artifact, 'schema-check', '--json'],
                    readable=[*reads, workdir], writable=None, cwd=workdir,
                    env=environment, timeout=30)
        else:
            completed = subprocess.run(
                [sys.executable, str(artifact), "schema-check", "--json"],
                cwd=context.managed_root, env=environment, stdin=subprocess.DEVNULL,
                capture_output=True, text=True, timeout=30, check=False,
            )
    except (OSError, subprocess.SubprocessError, ContractError):
        return False
    if completed.returncode != 0 or len(completed.stdout.encode("utf-8")) > 256 * 1024:
        return False
    try:
        result = json.loads(completed.stdout)
    except (json.JSONDecodeError, UnicodeError):
        return False
    return isinstance(result, dict) and result.get("ok") is True
