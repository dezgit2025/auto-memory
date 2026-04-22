"""Detect current repository from git remote or environment."""

import subprocess
import re


def parse_repo_url(url: str) -> str | None:
    """Parse owner/repo from common git remote URL formats."""
    if not url:
        return None
    m = re.match(r"git@[^:]+:(.+?)(?:\.git)?$", url)
    if m:
        return m.group(1)
    m = re.match(r"https?://[^/]+/(.+?)(?:\.git)?$", url)
    if m:
        return m.group(1)
    return None


def detect_repo_for_cwd(cwd: str, timeout: int = 5) -> str | None:
    """Return owner/repo for a specific working directory path."""
    try:
        url = subprocess.run(
            ["git", "-C", cwd, "remote", "get-url", "origin"],
            capture_output=True,
            text=True,
            timeout=timeout,
        ).stdout.strip()
    except (subprocess.TimeoutExpired, FileNotFoundError):
        return None
    return parse_repo_url(url)


def detect_repo() -> str | None:
    """Return 'owner/repo' from git remote origin, or None."""
    try:
        url = subprocess.run(
            ["git", "remote", "get-url", "origin"],
            capture_output=True,
            text=True,
            timeout=5,
        ).stdout.strip()
    except (subprocess.TimeoutExpired, FileNotFoundError):
        return None
    return parse_repo_url(url)
