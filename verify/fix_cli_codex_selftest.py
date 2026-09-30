"""Mutation self-test for the Stage A verifier."""

from __future__ import annotations

import json
import os
import shutil
import sys
import tempfile
from pathlib import Path

from fix_cli_codex_common import (
    ROOT, InfraFailure, VerifyFailure, build_fixture, fixture_env, require, run,
)
from fix_cli_codex_probes import _mutate, require_no_query_observation


def self_test_broken_preflight() -> list[str]:
    """Run a copied package whose preflight deliberately permits drift."""
    with tempfile.TemporaryDirectory(prefix="fix-cli-codex-mutant-") as temp:
        target = Path(temp)
        package = target / "session_recall"
        shutil.copytree(ROOT / "src/session_recall", package)
        schema_path = package / "providers/codex/schema.py"
        source = schema_path.read_text(encoding="utf-8")
        marker = "def preflight(state_conn, history_conn) -> SchemaReport:"
        if marker not in source:
            raise InfraFailure("cannot construct isolated preflight mutant")
        prefix = source.split(marker, 1)[0]
        schema_path.write_text(
            prefix + marker + "\n"
            "    global VERIFY_MUTANT_EXECUTED\n"
            "    VERIFY_MUTANT_EXECUTED = True\n"
            "    return check_schema(state_conn, history_conn)\n",
            encoding="utf-8",
        )
        store = build_fixture(target / "store")
        _mutate(store, "private_column", "selftest_" + os.urandom(8).hex())
        script = """
import json
from unittest.mock import Mock, patch
from session_recall.providers.codex import schema
from session_recall.providers.codex.cli import main
m = Mock(return_value=[])
with patch('session_recall.providers.codex.provider.select_threads', m):
    try:
        main(['list', '--json'])
    except SystemExit as exc:
        code = exc.code
print(json.dumps({'code': code, 'calls': m.call_count,
                  'mutant': getattr(schema, 'VERIFY_MUTANT_EXECUTED', False)}))
"""
        env = fixture_env(store)
        env["PYTHONPATH"] = str(target)
        result = require(run([sys.executable, "-c", script], env=env, cwd=target), 0)
        observed = json.loads(result.stdout.splitlines()[-1])
        if observed != {"code": 0, "calls": 1, "mutant": True}:
            raise VerifyFailure(f"isolated mutant did not execute as designed: {observed!r}")
        try:
            require_no_query_observation(observed, "list")
        except VerifyFailure as exc:
            if not str(exc).startswith("preflight_bypass_query_count:list:1"):
                raise VerifyFailure(f"self-test failed for wrong reason: {exc}") from exc
        else:
            raise VerifyFailure("normal no-query gate accepted the broken preflight mutant")
    return ["mutant-imported=true", "expected-detection=preflight_bypass_query_count"]
