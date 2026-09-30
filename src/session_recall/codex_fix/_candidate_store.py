"""Private durable records for the foreground candidate review workflow."""
from __future__ import annotations

import json
import os
from pathlib import Path
import stat
import tempfile
from typing import Any

from .contracts import ContractError, canonical_bytes, _pairs, _reject_float
from ._store_io import directory, fsync_directory, protect_root


def read_record(path: Path) -> dict[str, Any]:
    before = path.lstat()
    if (not stat.S_ISREG(before.st_mode) or before.st_uid != os.getuid()
            or stat.S_IMODE(before.st_mode) & 0o077 or before.st_size > 2 * 1024 * 1024):
        raise ContractError("unsafe_candidate_record")
    fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
    with os.fdopen(fd, 'rb') as handle:
        opened = os.fstat(handle.fileno())
        data = handle.read(2 * 1024 * 1024 + 1)
        after = os.fstat(handle.fileno())
    identities = {(s.st_ino, s.st_dev, s.st_size, s.st_mtime_ns) for s in (before, opened, after)}
    if len(identities) != 1:
        raise ContractError("candidate_record_changed")
    try:
        value = json.loads(data, object_pairs_hook=_pairs, parse_float=_reject_float)
    except (ValueError, UnicodeError) as exc:
        raise ContractError("invalid_candidate_record") from exc
    if not isinstance(value, dict) or canonical_bytes(value) != data:
        raise ContractError("invalid_candidate_record")
    return value


def write_once(root: Path, relative: str, value: dict[str, Any]) -> Path:
    """Publish immutable canonical bytes atomically; identical retries are harmless."""
    protect_root(root)
    if '..' in Path(relative).parts or Path(relative).is_absolute():
        raise ContractError("invalid_candidate_path")
    path = root / relative
    parent = directory(root, str(Path(relative).parent))
    data = canonical_bytes(value)
    if path.exists() or path.is_symlink():
        if read_record(path) != value:
            raise ContractError("candidate_record_conflict")
        return path
    fd, temporary = tempfile.mkstemp(prefix='.candidate-', dir=parent)
    try:
        with os.fdopen(fd, 'wb') as handle:
            handle.write(data)
            handle.flush()
            os.fsync(handle.fileno())
        try:
            os.link(temporary, path)
        except FileExistsError:
            if read_record(path) != value:
                raise ContractError("candidate_record_conflict") from None
        fsync_directory(parent)
    finally:
        Path(temporary).unlink()
    return path


def identifier(value: str) -> str:
    if not isinstance(value, str) or len(value) != 64 or any(c not in '0123456789abcdef' for c in value):
        raise ContractError('invalid_candidate_id')
    return value
