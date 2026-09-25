"""Fresh installs ship a schema-57/history-7 adapter without a managed selection."""

from argparse import Namespace
import hashlib
import json
from pathlib import Path
import subprocess
import sys

from session_recall.codex_fix import factory, launcher
from session_recall.codex_fix.tests.conftest import _build_database


def test_fresh_seed_runs_against_synthetic_57_7_without_selection(tmp_path):
    managed = tmp_path / "managed"
    args = Namespace(
        command="launch", root=str(managed), state_db=str(tmp_path / "state.sqlite"),
        history_db=str(tmp_path / "history.sqlite"),
        sessions_root=str(tmp_path / "sessions"), config=None, auto=False,
        json=False, repair=None, plan=None,
    )
    context = factory.production_context(args)
    artifact, manifest = launcher._selected(context)
    assert manifest["profile_ids"] == {
        "state": "codex-state-v5-migration-57",
        "history": "codex-thread-history-v1-migration-7",
    }
    state = Path(args.state_db)
    history = Path(args.history_db)
    _build_database(state, manifest["profiles"]["state"])
    _build_database(history, manifest["profiles"]["history"])
    Path(args.sessions_root).mkdir()
    before = (hashlib.sha256(state.read_bytes()).hexdigest(),
              hashlib.sha256(history.read_bytes()).hexdigest())
    environment = launcher._environment(context)
    completed = subprocess.run(
        [sys.executable, str(artifact), "schema-check", "--json"],
        env=environment, text=True, capture_output=True, check=False, timeout=30,
    )
    assert completed.returncode == 0, completed.stderr
    assert json.loads(completed.stdout)["ok"] is True
    assert not (managed / "selection/current.json").exists()
    assert before == (hashlib.sha256(state.read_bytes()).hexdigest(),
                      hashlib.sha256(history.read_bytes()).hexdigest())
