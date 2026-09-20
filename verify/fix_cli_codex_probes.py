"""Observable Stage A probes for fix-cli-codex.py."""

from __future__ import annotations

import json
import importlib.util
import os
import shutil
import sqlite3
import sys
import tempfile
from pathlib import Path

from fix_cli_codex_common import (
    ORACLE, PROFILE, ROOT, InfraFailure, VerifyFailure, build_fixture,
    compared_profile, fixture_env, hash_tree, installed_cli, load_json,
    load_oracle, qident, require, run,
)
from fix_cli_codex_package import verify_packaged_install
from fix_cli_codex_anticheat import scan as anti_cheat_scan


def probe_a1() -> list[str]:
    oracle = load_oracle()
    state = oracle["state"]
    history = oracle["history"]
    if state["profile"] != "codex-state-v5-migration-55" or state["migration_ceiling"] != 55:
        raise VerifyFailure("reviewed state profile identity/ceiling is not migration 55")
    if (history["profile"] != "codex-thread-history-v1-migration-6"
            or history["migration_ceiling"] != 6):
        raise VerifyFailure("reviewed history profile identity/ceiling is not migration 6")
    tail = state["tables"]["threads"][-2:]
    expected = [[38, "originator", "TEXT", 0, None, 0],
                [39, "daybreak_enabled", "BOOLEAN", 0, None, 0]]
    if tail != expected:
        raise VerifyFailure(f"reviewed new-column definitions differ: {tail!r}")
    for side, item in oracle.items():
        for table, rows in item["tables"].items():
            if [row[0] for row in rows] != list(range(len(rows))):
                raise VerifyFailure(f"non-contiguous column order: {side}.{table}")
            if len({row[1] for row in rows}) != len(rows):
                raise VerifyFailure(f"duplicate column name: {side}.{table}")
    return [f"oracle={ORACLE.relative_to(ROOT)}", "state=55", "history=6"]


def probe_a2_expected_red() -> list[str]:
    """Freeze the migration-52 refusal before the reviewed repair is applied."""
    candidate = load_json(PROFILE)
    if candidate["state"]["profile"] != "codex-state-v5-migration-52":
        raise VerifyFailure("A2 expected-red is only valid for the migration-52 adapter")
    cli = installed_cli()
    with tempfile.TemporaryDirectory(prefix="fix-cli-codex-a2-red-") as temp:
        store = build_fixture(Path(temp) / "reviewed-55")
        result = run([str(cli), "schema-check", "--json"], env=fixture_env(store))
        require(result, 2)
        body = json.loads(result.stdout)
        differences = "\n".join(body.get("differences", []))
        for needle in ("originator", "daybreak_enabled", "migration ceiling 55"):
            if needle not in differences:
                raise VerifyFailure(f"A2 refusal omitted reviewed difference {needle!r}")
        if body.get("query_executed") is not False:
            raise VerifyFailure("A2 refusal did not report query_executed:false")
    return ["expected-red=state52-vs-reviewed55", "refusal-reason=exact"]


def probe_a2() -> list[str]:
    anti_cheat_scan()
    result = run(
        [sys.executable, "-m", "pytest", str(ROOT / "src"), "-q",
         "-p", "no:cacheprovider", "--import-mode=importlib"],
        env={"PYTEST_DISABLE_PLUGIN_AUTOLOAD": "1"}, timeout=120,
    )
    require(result)
    if "failed" in result.stdout.lower():
        raise VerifyFailure(f"full regression output reports failure: {result.stdout[-800:]}")
    if importlib.util.find_spec("ruff") is None:
        raise InfraFailure("ruff is unavailable for the scoped lint gate")
    require(run([sys.executable, "-m", "ruff", "check", str(ROOT / "src")], timeout=60))
    return ["full-src-regression=pass", "ruff-src=pass", "skip-xfail-scan=pass"]


def _copy_store(store: dict[str, Path], destination: Path) -> dict[str, Path]:
    shutil.copytree(store["root"], destination)
    return {"root": destination, "state": destination / "state_5.sqlite",
            "history": destination / "thread_history_1.sqlite",
            "sessions": destination / "sessions"}


def _mutate(store: dict[str, Path], mutation: str, private_name: str) -> str:
    if mutation in {"private_column", "drop_preview", "state_future", "state_lower", "failed"}:
        path = store["state"]
    else:
        path = store["history"]
    conn = sqlite3.connect(path)
    try:
        if mutation == "private_column":
            conn.execute(f"ALTER TABLE threads ADD COLUMN {qident(private_name)} TEXT")
            needle = private_name
        elif mutation == "drop_preview":
            conn.execute("ALTER TABLE threads DROP COLUMN preview")
            needle = "missing column preview"
        elif mutation == "state_future":
            conn.execute("INSERT INTO _sqlx_migrations VALUES (56, 'private future', "
                         "'2026-01-01 00:00:00', 1, x'', 0)")
            needle = "migration ceiling 56"
        elif mutation == "state_lower":
            conn.execute("DELETE FROM _sqlx_migrations WHERE version = 55")
            needle = "migration ceiling 54"
        elif mutation == "history_future":
            conn.execute("INSERT INTO _sqlx_migrations VALUES (7, 'private future', "
                         "'2026-01-01 00:00:00', 1, x'', 0)")
            needle = "migration ceiling 7"
        elif mutation == "history_lower":
            conn.execute("DELETE FROM _sqlx_migrations WHERE version = 6")
            needle = "migration ceiling 5"
        elif mutation == "failed":
            conn.execute("UPDATE _sqlx_migrations SET success=0 WHERE version=55")
            needle = "failed migration"
        else:
            raise InfraFailure(f"unknown verifier mutation: {mutation}")
        conn.commit()
        return needle
    finally:
        conn.close()


def _json_result(result) -> dict:
    require(result, 0)
    try:
        return json.loads(result.stdout)
    except json.JSONDecodeError as exc:
        raise VerifyFailure(f"invalid JSON from {result.argv!r}: {result.stdout!r}") from exc


def _assert_drift(cli: Path, store: dict[str, Path], needle: str) -> None:
    result = run([str(cli), "schema-check", "--json"], env=fixture_env(store))
    require(result, 2)
    try:
        body = json.loads(result.stdout)
    except json.JSONDecodeError as exc:
        raise VerifyFailure(f"drift output is not JSON: {result.stdout!r}") from exc
    if body.get("error") != "schema_drift" or body.get("query_executed") is not False:
        raise VerifyFailure(f"wrong drift contract: {body!r}")
    differences = "\n".join(body.get("differences", []))
    if needle not in differences:
        raise VerifyFailure(f"mutation failed for wrong reason; wanted {needle!r}: {differences!r}")


def require_no_query_observation(observed: dict, command: str) -> None:
    if observed.get("calls") != 0:
        raise VerifyFailure(
            f"preflight_bypass_query_count:{command}:{observed.get('calls')}"
        )
    if observed.get("code") != 2:
        raise VerifyFailure(f"preflight_wrong_exit:{command}:{observed.get('code')}")


def _assert_no_query(cli: Path, store: dict[str, Path], command: str) -> None:
    first = cli.read_text(encoding="utf-8", errors="replace").splitlines()[0]
    python = first[2:] if first.startswith("#!") and os.path.isabs(first[2:]) else sys.executable
    script = """
import json
from unittest.mock import Mock, patch
from session_recall.providers.codex.cli import main
m = Mock(side_effect=AssertionError('SESSION_QUERY_EXECUTED'))
with patch('session_recall.providers.codex.provider.select_threads', m):
    try:
        main([COMMAND, '--json'])
    except SystemExit as exc:
        code = exc.code
print('__VERIFY_SENTINEL__' + json.dumps({'code': code, 'calls': m.call_count}))
""".replace("COMMAND", repr(command))
    result = run([python, "-c", script], env=fixture_env(store), cwd=store["root"])
    require(result, 0, "__VERIFY_SENTINEL__")
    marker = result.stdout.rsplit("__VERIFY_SENTINEL__", 1)[1].strip()
    observed = json.loads(marker)
    require_no_query_observation(observed, command)
    if '"query_executed": false' not in result.stdout:
        raise VerifyFailure(f"{command} omitted query_executed:false")


def probe_a3(*, self_test: bool = False) -> list[str]:
    cli = installed_cli()
    with tempfile.TemporaryDirectory(prefix="fix-cli-codex-a3-") as temp:
        base = build_fixture(Path(temp) / "base")
        good = run([str(cli), "schema-check", "--json"], env=fixture_env(base))
        body = _json_result(good)
        if body.get("profiles") != {
            "state": "codex-state-v5-migration-55",
            "history": "codex-thread-history-v1-migration-6",
        }:
            raise VerifyFailure(f"wrong success profiles: {body!r}")
        private_name = "private_" + os.urandom(8).hex()
        mutations = ("private_column",) if self_test else (
            "private_column", "drop_preview", "state_future", "state_lower",
            "history_future", "history_lower", "failed",
        )
        for mutation in mutations:
            target = _copy_store(base, Path(temp) / mutation)
            needle = _mutate(target, mutation, private_name)
            _assert_drift(cli, target, needle)
            if mutation == "private_column":
                _assert_no_query(cli, target, "list")
                _assert_no_query(cli, target, "repos")
    label = "known-bad-private-drift=detected" if self_test else "strict-mutations=7"
    return [label, "list-query-count=0", "repos-query-count=0"]


def probe_a4() -> list[str]:
    cli = installed_cli()
    if compared_profile(load_json(PROFILE)) != compared_profile(load_oracle()):
        raise VerifyFailure("captured profile does not equal reviewed migration-55 oracle")
    with tempfile.TemporaryDirectory(prefix="fix-cli-codex-a4-") as temp:
        store = build_fixture(Path(temp) / "store")
        env = fixture_env(store)
        before = hash_tree(store["root"])
        first = _json_result(run([str(cli), "list", "--json"], env=env))
        second = _json_result(run([str(cli), "list", "--json"], env=env))
        projection = [(row["summary"], row["repository"]) for row in first]
        expected = [("verify remote newest", "verify/remote"),
                    ("verify local scratch", "local:/verify/local"),
                    ("verify remote older", "verify/remote")]
        if projection != expected or second != first:
            raise VerifyFailure(f"list frozen oracle/two-witness mismatch: {projection!r}")
        archived = _json_result(run(
            [str(cli), "list", "--json", "--include-archived"], env=env))
        if [row["summary"] for row in archived] != [
            "verify remote newest", "verify archived", "verify local scratch",
            "verify remote older",
        ]:
            raise VerifyFailure("archive/guardian filtering differs from frozen oracle")
        repos = _json_result(run([str(cli), "repos", "--json", "--include-local"], env=env))
        repo_projection = [(row["repository"], row["session_count"]) for row in repos["repos"]]
        if repos["count"] != 2 or repo_projection != [("verify/remote", 2),
                                                       ("local:/verify/local", 1)]:
            raise VerifyFailure(f"repos frozen oracle mismatch: {repos!r}")
        if _json_result(run([str(cli), "list", "--json", "--days", "0"], env=env)) != []:
            raise VerifyFailure("list zero-window contract is not []")
        empty_repos = _json_result(run(
            [str(cli), "repos", "--json", "--days", "0"], env=env))
        if empty_repos != {"count": 0, "repos": []}:
            raise VerifyFailure(f"repos zero-window contract differs: {empty_repos!r}")
        after = hash_tree(store["root"])
        if after != before:
            raise VerifyFailure("CLI modified the synthetic fixture store")
    return ["independent-output-oracle=pass", "read-only-hashes=pass", "two-witness=pass"]


def probe_a5() -> list[str]:
    smoke = ROOT / "src/session_recall/providers/codex/verifications/smoke.sh"
    schema = ROOT / "src/session_recall/providers/codex/verifications/verify_schema.sh"
    require(run(["bash", str(smoke), "--self-test"], timeout=120),
            contains='"verdict":"PASS"')
    require(run(["bash", str(schema), "--self-test"], timeout=120),
            contains='"verdict":"PASS"')
    require(run(["bash", str(schema)], timeout=120), contains='"verdict":"PASS"')
    return [*verify_packaged_install(), "shell-self-tests=pass", "schema-shell=pass"]


L1_PROBES = {"A1": probe_a1, "A2": probe_a2_expected_red, "A3": probe_a4,
             "A4": probe_a3, "A5": probe_a5}


def run_l2():
    """Yield probes lazily so a later failure retains completed-case evidence."""
    yield "A1", probe_a1
    yield "A2-tests", probe_a2
    yield "A3", probe_a4
    yield "A4", probe_a3
    yield "A5", probe_a5
