"""E2E tests for per-provider health CLI flags."""

import json
import os
import subprocess
import sys


def _run_health(*extra_args: str, env_override: dict[str, str] | None = None):
    """Run session-recall health as a subprocess, return CompletedProcess."""
    env = os.environ.copy()
    env.pop("SESSION_RECALL_ENABLE_FILE_BACKENDS", None)
    if env_override:
        env.update(env_override)
    return subprocess.run(
        [sys.executable, "-m", "session_recall", "health", *extra_args],
        capture_output=True,
        text=True,
        timeout=30,
        env=env,
        cwd="/tmp",
    )


def test_e2e_health_default_still_works():
    result = _run_health()
    assert result.returncode == 0, f"stderr: {result.stderr}"
    assert "Overall" in result.stdout


def test_e2e_health_provider_cli_json():
    result = _run_health("--provider", "cli", "--json")
    assert result.returncode == 0, f"stderr: {result.stderr}"
    data = json.loads(result.stdout)
    assert "providers" in data
    assert "dims" in data


def test_e2e_health_provider_cli_has_subdims():
    result = _run_health("--provider", "cli", "--json")
    assert result.returncode == 0, f"stderr: {result.stderr}"
    data = json.loads(result.stdout)
    cli_dims = data["providers"]["cli"]["dimensions"]
    assert len(cli_dims) == 4


def test_e2e_health_provider_vscode_not_enabled():
    result = _run_health("--provider", "vscode")
    assert result.returncode == 2
    assert "not enabled" in result.stderr.lower()


def test_e2e_health_provider_vscode_enabled_no_crash():
    result = _run_health(
        "--provider", "vscode",
        env_override={"SESSION_RECALL_ENABLE_FILE_BACKENDS": "1"},
    )
    assert result.returncode in (0, 2), (
        f"Unexpected exit code {result.returncode}\n"
        f"stdout: {result.stdout}\nstderr: {result.stderr}"
    )
    # Must not produce a Python traceback regardless of exit code
    assert "Traceback (most recent call last)" not in result.stderr
    if result.returncode == 2:
        # Clean error message, not a crash
        stderr_lower = result.stderr.lower()
        assert "unavailable" in stderr_lower or "not found" in stderr_lower or "error" in stderr_lower


def test_e2e_health_json_backward_compat():
    result = _run_health("--json")
    assert result.returncode == 0, f"stderr: {result.stderr}"
    data = json.loads(result.stdout)
    assert "dims" in data, "Missing backward-compat 'dims' key"
    for dim in data["dims"]:
        assert "name" in dim, f"dim missing 'name': {dim}"
        assert "zone" in dim, f"dim missing 'zone': {dim}"
        assert "score" in dim, f"dim missing 'score': {dim}"
