"""V5 candidate sandbox capability and denial tests."""

from __future__ import annotations

import json
from pathlib import Path
import sys

import pytest

from session_recall.codex_fix.contracts import ContractError
from session_recall.codex_fix.sandbox import Sandbox


pytestmark = pytest.mark.skipif(sys.platform != "darwin", reason="SBPL is macOS-only")


PROBE = r'''import json, os, socket, subprocess, sys
from pathlib import Path

readable, writable, credential, controller, symlink, codex = map(Path, sys.argv[1:])
results = {}

def attempt(name, callback):
    try:
        callback()
    except BaseException:
        results[name] = "denied"
    else:
        results[name] = "allowed"

attempt("readable", lambda: readable.read_text())
attempt("scratch_write", lambda: (writable / "made.txt").write_text("ok"))
attempt("credential", lambda: credential.read_text())
attempt("controller", lambda: controller.read_text())
attempt("symlink_escape", lambda: symlink.read_text())
attempt("network", lambda: socket.socket().bind(("127.0.0.1", 0)))
attempt("nested_codex", lambda: subprocess.run([str(codex), "--version"], check=True))
print(json.dumps(results, sort_keys=True))
'''


def _write(path: Path, value: str) -> Path:
    path.write_text(value, encoding="utf-8")
    return path


def test_candidate_runtime_allows_only_declared_inputs_and_scratch(tmp_path):
    candidate = tmp_path / "candidate"
    candidate.mkdir()
    script = _write(candidate / "probe.py", PROBE)
    readable = _write(candidate / "input.txt", "synthetic")
    scratch = tmp_path / "scratch"
    scratch.mkdir()
    protected = tmp_path / "protected"
    protected.mkdir()
    credential = _write(protected / "credential", "secret")
    controller = _write(protected / "controller.py", "protected")
    escape = candidate / "escape"
    escape.symlink_to(credential)
    codex = Path.home() / ".local" / "bin" / "codex"

    completed = Sandbox().run(
        [script, readable, scratch, credential, controller, escape, codex],
        readable=[candidate],
        writable=scratch,
        cwd=candidate,
        env={"CANDIDATE_MARKER": "yes", "HOME": str(Path.home())},
        timeout=10,
    )

    assert completed.returncode == 0, completed.stderr
    assert json.loads(completed.stdout) == {
        "controller": "denied",
        "credential": "denied",
        "nested_codex": "denied",
        "network": "denied",
        "readable": "allowed",
        "scratch_write": "allowed",
        "symlink_escape": "denied",
    }
    assert (scratch / "made.txt").read_text() == "ok"
    assert credential.read_text() == "secret"
    assert controller.read_text() == "protected"


def test_read_only_candidate_cannot_write_its_workspace(tmp_path):
    candidate = tmp_path / "candidate"
    candidate.mkdir()
    script = _write(
        candidate / "write.py",
        "from pathlib import Path\nPath(__file__).with_name('changed').write_text('bad')\n",
    )
    completed = Sandbox().run(
        [script], readable=[candidate], writable=None, cwd=candidate, env={}, timeout=10
    )
    assert completed.returncode != 0
    assert not (candidate / "changed").exists()


def test_unsafe_or_implicit_paths_fail_before_launch(tmp_path):
    candidate = tmp_path / "candidate"
    candidate.mkdir()
    script = _write(candidate / "ok.py", "print('ok')\n")
    link = tmp_path / "linked"
    link.symlink_to(candidate, target_is_directory=True)
    sandbox = Sandbox()

    with pytest.raises(ContractError, match="sandbox_path_unsafe"):
        sandbox.run([script], readable=[link], writable=None, cwd=candidate, env={}, timeout=10)
    with pytest.raises(ContractError, match="sandbox_cwd_denied"):
        sandbox.run([script], readable=[script], writable=None, cwd=tmp_path, env={}, timeout=10)
    with pytest.raises(ContractError, match="sandbox_environment"):
        sandbox.run(
            [script], readable=[candidate], writable=None, cwd=candidate,
            env={"OPENAI_API_KEY": "secret"}, timeout=10,
        )


def test_probe_uses_only_its_disposable_workspace(tmp_path):
    workspace = tmp_path / "probe"
    workspace.mkdir()
    completed = Sandbox().probe(workspace)
    assert completed.returncode == 0, completed.stderr
    assert json.loads(completed.stdout) == {
        "child_exec": "denied",
        "network": "denied",
        "protected_read": "denied",
        "protected_write": "denied",
        "readable": "allowed",
        "scratch_write": "allowed",
        "symlink_escape": "denied",
    }


def test_output_flood_fails_closed_and_is_bounded(tmp_path):
    candidate = tmp_path / "candidate"
    candidate.mkdir()
    script = _write(candidate / "flood.py", "print('x' * 300000)\n")
    with pytest.raises(ContractError, match="sandbox_output_limit"):
        Sandbox().run(
            [script], readable=[candidate], writable=None, cwd=candidate, env={}, timeout=10
        )


def test_timeout_kills_the_candidate_process_group(tmp_path):
    candidate = tmp_path / "candidate"
    candidate.mkdir()
    script = _write(candidate / "sleep.py", "import time\ntime.sleep(30)\n")
    with pytest.raises(ContractError, match="sandbox_timeout"):
        Sandbox().run(
            [script], readable=[candidate], writable=None, cwd=candidate, env={}, timeout=1
        )


def test_sqlite_runtime_uses_only_exact_library_files(tmp_path):
    candidate = tmp_path / "candidate"
    candidate.mkdir()
    script = _write(
        candidate / "sqlite_ok.py",
        "import sqlite3\nconnection = sqlite3.connect(':memory:')\n"
        "print(connection.execute('select 1').fetchone()[0])\n",
    )
    sandbox = Sandbox()
    profile = sandbox._profile([candidate.resolve()], None)
    assert '(subpath "/opt/homebrew")' not in profile
    assert '(subpath "/opt/homebrew/opt/sqlite")' not in profile
    for dependency in sandbox.dependencies:
        assert f'(literal "{dependency}")' in profile
        assert f'(allow file-map-executable (literal "{dependency}"))' in profile
    completed = sandbox.run(
        [script], readable=[candidate], writable=None, cwd=candidate, env={}, timeout=10
    )
    assert completed.returncode == 0, completed.stderr
    assert completed.stdout.strip() == "1"
