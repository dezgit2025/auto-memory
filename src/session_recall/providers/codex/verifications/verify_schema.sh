#!/usr/bin/env bash
# verify_schema.sh — codex fixed-schema pre-flight acceptance gate (plan §10.1 + §10.3)
# Script exit codes: 0=pass, 1=test fail, 2=infra/implementation missing, 3=anti-cheat trip, 124=timeout
# CLI exit codes (0/1/2/3/4) are asserted INSIDE checks, never used as script exit codes.
set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/../../../../.." && pwd)"
# shellcheck source=./_verify_lib.sh
source "$SCRIPT_DIR/_verify_lib.sh"

MUTATIONS=(drop_preview rename_history_mode add_threads_column change_item_json_decl
           drop_thread_turns state_migration_52 history_migration_7 failed_migration)

verdict() { # verdict <PASS|FAIL> <checks> <failed-json-array> [reason]
  printf '{"verifier":"verify_schema","verdict":"%s","checks":%d,"failed":%s%s}\n' \
    "$1" "$2" "$3" "${4:+,\"reason\":\"$4\"}"
}

export PYTHONHASHSEED=0 PYTHONDEVMODE=1 PYTHONDONTWRITEBYTECODE=1 LC_ALL=C TZ=UTC
TMP="$(mktemp -d "${TMPDIR:-/tmp}/codex-verify-schema.XXXXXX")"
trap 'rm -rf "$TMP"' EXIT

# ---------- self-test: prove the mutation factory + exact-compare are real ----------
if [[ "${1:-}" == "--self-test" ]]; then
  fails=0; checks=0
  vlib_build_fixture "$TMP/exact" >/dev/null
  checks=$((checks+1))
  vlib_assert_exact "$TMP/exact" >/dev/null || { echo "[self-test] exact fixture mismatched profile" >&2; fails=$((fails+1)); }
  for m in "${MUTATIONS[@]}" extra_unrelated_table; do
    checks=$((checks+1))
    vlib_mutate "$m" "$TMP/mut-$m" >/dev/null
    vlib_assert_drift "$m" "$TMP/mut-$m" >/dev/null || { echo "[self-test] mutation $m NOT observable" >&2; fails=$((fails+1)); }
  done
  # anti-cheat: assert_exact must REJECT a mutated copy (known-bad must fail)
  checks=$((checks+1))
  if vlib_assert_exact "$TMP/mut-drop_preview" >/dev/null 2>&1; then
    echo "[self-test] exact-compare accepted a mutated schema — detector inputs unreal" >&2
    verdict FAIL "$checks" '["exact_compare_accepts_bad"]' "selftest_anticheat"; exit 3
  fi
  if [[ $fails -gt 0 ]]; then verdict FAIL "$checks" '["mutation_factory"]' "selftest"; exit 3; fi
  verdict PASS "$checks" '[]'; exit 0
fi

# ---------- main gate ----------
if ! vlib_impl_present; then
  verdict FAIL 0 '[]' "implementation_missing"; exit 2
fi

cd "$REPO_ROOT"
failed=(); checks=0

# 0) pytest module first (per verifier rules)
checks=$((checks+1))
if ! python3 -m pytest src/session_recall/providers/codex/tests/test_schema.py \
     -q -p no:cacheprovider --import-mode=importlib >&2; then
  failed+=('"pytest_schema"')
fi

envset() { # point CLI at a fixture dir
  export SESSION_RECALL_CODEX_STATE_DB="$1/state_5.sqlite"
  export SESSION_RECALL_CODEX_HISTORY_DB="$1/thread_history_1.sqlite"
  export SESSION_RECALL_CODEX_SESSIONS_ROOT="$1/sessions"
}

# 1) exact fixture passes; second fresh-process witness; run-twice idempotency
vlib_build_fixture "$TMP/exact" >/dev/null
envset "$TMP/exact"
for round in 1 2 3; do
  checks=$((checks+1))
  out="$(vlib_run session-recall-codex schema-check --json)"
  rc="${out##*RC:}"
  [[ "$rc" == "0" ]] || failed+=("\"exact_pass_round$round\"")
done

# 2) every §10.3 mutation must fail: CLI exit 2 + query_executed:false
for m in "${MUTATIONS[@]}"; do
  checks=$((checks+1))
  vlib_mutate "$m" "$TMP/m-$m" >/dev/null
  mkdir -p "$TMP/m-$m/sessions"
  envset "$TMP/m-$m"
  out="$(vlib_run session-recall-codex schema-check --json)"
  rc="${out##*RC:}"
  body="${out%RC:*}"
  if [[ "$rc" != "2" ]] || ! grep -q '"query_executed": *false' <<<"$body"; then
    failed+=("\"drift_$m\"")
  fi
done

# 3) additive unrelated table: diagnostic-only, still passes
checks=$((checks+1))
vlib_mutate "extra_unrelated_table" "$TMP/m-extra" >/dev/null
mkdir -p "$TMP/m-extra/sessions"
envset "$TMP/m-extra"
out="$(vlib_run session-recall-codex schema-check --json)"
rc="${out##*RC:}"
[[ "$rc" == "0" ]] || failed+=('"extra_table_should_pass"')

# 4) missing DB → CLI exit 4
checks=$((checks+1))
envset "$TMP/nonexistent"
out="$(vlib_run session-recall-codex schema-check --json)"
rc="${out##*RC:}"
[[ "$rc" == "4" ]] || failed+=('"missing_db_exit4"')

if [[ ${#failed[@]} -gt 0 ]]; then
  verdict FAIL "$checks" "[$(IFS=,; echo "${failed[*]}")]"; exit 1
fi
verdict PASS "$checks" '[]'; exit 0
