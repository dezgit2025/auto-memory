"""Private filesystem and atomic-publication primitives for the C2 budget store."""

from __future__ import annotations

from contextlib import contextmanager
import errno
import fcntl
import os
from pathlib import Path
import stat
import tempfile
from typing import Any, Iterator

from .contracts import ContractError, canonical_bytes

MAX_RECORD_BYTES = 1024 * 1024


def protect_root(root: Path) -> None:
    try:
        metadata = root.lstat()
    except OSError as exc:
        raise ContractError("invalid_budget_root") from exc
    if root.is_symlink() or not stat.S_ISDIR(metadata.st_mode):
        raise ContractError("invalid_budget_root")
    if metadata.st_uid != os.getuid() or stat.S_IMODE(metadata.st_mode) & 0o077:
        raise ContractError("invalid_budget_root")
    for ancestor in (root.absolute(), *root.absolute().parents):
        item = ancestor.lstat()
        if ancestor.is_symlink():
            raise ContractError("invalid_budget_root")
        if stat.S_IMODE(item.st_mode) & 0o022 and not item.st_mode & stat.S_ISVTX:
            raise ContractError("invalid_budget_root")


def safe_directory(path: Path, *, create: bool = False) -> Path:
    if create:
        try:
            path.mkdir(mode=0o700)
        except FileExistsError:
            pass
    try:
        metadata = path.lstat()
    except OSError as exc:
        raise ContractError("budget_store_missing") from exc
    if (
        path.is_symlink()
        or not stat.S_ISDIR(metadata.st_mode)
        or metadata.st_uid != os.getuid()
        or stat.S_IMODE(metadata.st_mode) & 0o077
    ):
        raise ContractError("unsafe_budget_store")
    return path


def fsync_directory(path: Path) -> None:
    descriptor = os.open(path, os.O_RDONLY | getattr(os, "O_DIRECTORY", 0))
    try:
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


@contextmanager
def budget_lock(root: Path) -> Iterator[None]:
    locks = root / "locks"
    try:
        locks.mkdir(mode=0o700)
    except FileExistsError:
        pass
    safe_directory(locks)
    path = locks / "budget.lock"
    flags = os.O_RDWR | os.O_CREAT | getattr(os, "O_CLOEXEC", 0) | getattr(os, "O_NOFOLLOW", 0)
    descriptor = os.open(path, flags, 0o600)
    try:
        opened = os.fstat(descriptor)
        if (
            not stat.S_ISREG(opened.st_mode)
            or opened.st_uid != os.getuid()
            or stat.S_IMODE(opened.st_mode) & 0o077
        ):
            raise ContractError("unsafe_budget_lock")
        try:
            fcntl.flock(descriptor, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError as exc:
            if exc.errno in {errno.EACCES, errno.EAGAIN}:
                raise ContractError("budget_busy") from exc
            raise ContractError("locking_unavailable") from exc
        yield
    finally:
        os.close(descriptor)


def read_bytes(path: Path) -> bytes:
    try:
        before = path.lstat()
    except OSError as exc:
        raise ContractError("budget_store_missing") from exc
    if path.is_symlink() or not stat.S_ISREG(before.st_mode) or before.st_size > MAX_RECORD_BYTES:
        raise ContractError("unsafe_budget_record")
    flags = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_NONBLOCK", 0)
    descriptor = os.open(path, flags)
    try:
        opened = os.fstat(descriptor)
        if (
            not stat.S_ISREG(opened.st_mode)
            or opened.st_uid != os.getuid()
            or stat.S_IMODE(opened.st_mode) & 0o077
        ):
            raise ContractError("unsafe_budget_record")
        with os.fdopen(descriptor, "rb") as handle:
            descriptor = -1
            data = handle.read(MAX_RECORD_BYTES + 1)
            after = os.fstat(handle.fileno())
    finally:
        if descriptor >= 0:
            os.close(descriptor)
    identities = {
        (item.st_dev, item.st_ino, item.st_size, item.st_mtime_ns)
        for item in (before, opened, after)
    }
    if len(data) > MAX_RECORD_BYTES or len(identities) != 1:
        raise ContractError("unsafe_budget_record")
    return data


def atomic_record(path: Path, value: dict[str, Any], hooks: Any | None) -> None:
    data = canonical_bytes(value)
    if len(data) > MAX_RECORD_BYTES:
        raise ContractError("budget_record_too_large")
    descriptor, raw_temporary = tempfile.mkstemp(
        prefix=".controller-ledger.", suffix=".tmp", dir=path.parent
    )
    temporary = Path(raw_temporary)
    try:
        os.fchmod(descriptor, 0o600)
        with os.fdopen(descriptor, "wb") as handle:
            descriptor = -1
            handle.write(data)
            handle.flush()
            os.fsync(handle.fileno())
        if hooks is not None:
            hooks.on_phase("before_replace")
        os.replace(temporary, path)
        fsync_directory(path.parent)
        if hooks is not None:
            hooks.on_phase("after_replace")
    finally:
        if descriptor >= 0:
            os.close(descriptor)
        try:
            temporary.unlink()
        except FileNotFoundError:
            pass


def initialize_record(
    root: Path,
    budget_directory: Path,
    path: Path,
    value: dict[str, Any],
    hooks: Any | None,
) -> None:
    if budget_directory.exists() or budget_directory.is_symlink():
        if budget_directory.is_symlink():
            raise ContractError("unsafe_budget_store")
        raise ContractError("budget_already_initialized")
    temporary = Path(tempfile.mkdtemp(prefix=".budget-v1.", dir=root))
    os.chmod(temporary, 0o700)
    temporary_record = temporary / path.name
    descriptor = -1
    try:
        data = canonical_bytes(value)
        if len(data) > MAX_RECORD_BYTES:
            raise ContractError("budget_record_too_large")
        descriptor = os.open(
            temporary_record,
            os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_CLOEXEC", 0),
            0o600,
        )
        with os.fdopen(descriptor, "wb") as handle:
            descriptor = -1
            handle.write(data)
            handle.flush()
            os.fsync(handle.fileno())
        fsync_directory(temporary)
        if hooks is not None:
            hooks.on_phase("before_replace")
        os.rename(temporary, budget_directory)
        fsync_directory(root)
        if hooks is not None:
            hooks.on_phase("after_replace")
    finally:
        if descriptor >= 0:
            os.close(descriptor)
        if temporary.exists():
            try:
                temporary_record.unlink()
            except FileNotFoundError:
                pass
            try:
                temporary.rmdir()
            except OSError:
                pass
