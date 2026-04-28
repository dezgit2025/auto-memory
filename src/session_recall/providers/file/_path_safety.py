"""Path safety utilities — symlink escape prevention."""

from pathlib import Path


def is_under_root(candidate: Path, root: Path) -> bool:
    """True iff candidate.resolve() is the same as or a descendant of root.resolve()."""
    try:
        c = candidate.resolve(strict=True)
        r = root.resolve(strict=True)
    except (OSError, RuntimeError):
        return False
    try:
        c.relative_to(r)
        return True
    except ValueError:
        return False
