#!/usr/bin/env bash
# smoke.sh — session-recall-codex hermetic end-to-end smoke gate (plan §9)
# Script exit codes: 0=pass, 1=fail, 2=infra/implementation missing, 3=anti-cheat trip, 124=timeout
# CLI exit codes (0/1/2/3/4) are asserted INSIDE checks, never used as script exit codes.
set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=./_verify_lib.sh
source "$SCRIPT_DIR/_verify_lib.sh"

verdict() { # verdict <PASS|FAIL> <checks> <failed-json-array> [reason]
  printf '{"verifier":"smoke","verdict":"%s","checks":%d,"failed":%s%s}\n' \
    "$1" "$2" "$3" "${4:+,\"reason\":\"$4\"}"
}

export PYTHONHASHSEED=0 PYTHONDEVMODE=1 PYTHONDONTWRITEBYTECODE=1 LC_ALL=C TZ=UTC
TMP="$(mktemp -d "${TMPDIR:-/tmp}/codex-smoke.XXXXXX")"
trap 'vlib_safe_cleanup "$TMP" "codex-smoke."' EXIT

# Held-out literal: fresh random token per run so hard-coded output can never pass.
SEED="${RANDOM}${RANDOM}"
export HELD_OUT_LITERAL="heldout-$(python3 -c "import random,sys; random.seed(int(sys.argv[1])); print('%08x' % random.getrandbits(32))" "$SEED")"
export BAND_TERM="bandterm-$(python3 -c "import random,sys; random.seed(int(sys.argv[1])+1); print('%08x' % random.getrandbits(32))" "$SEED")"
echo "[smoke] seed=$SEED held_out=$HELD_OUT_LITERAL band=$BAND_TERM" >&2

# ---------- self-test: drift generator + hash tripwire are real ----------
if [[ "${1:-}" == "--self-test" ]]; then
  checks=0; fails=0
  checks=$((checks+1))
  vlib_mutate "state_migration_56" "$TMP/drift" >/dev/null
  vlib_assert_drift "state_migration_56" "$TMP/drift" >/dev/null || fails=$((fails+1))
  # hash-snapshot machinery must detect a deliberate 1-byte mutation
  checks=$((checks+1))
  vlib_build_fixture "$TMP/hash" >/dev/null
  before="$(vlib_hash_dir "$TMP/hash")"
  printf '\x00' >> "$TMP/hash/state_5.sqlite"
  after="$(vlib_hash_dir "$TMP/hash")"
  if [[ "$before" == "$after" ]]; then
    echo "[self-test] hash snapshot did NOT detect 1-byte mutation" >&2
    verdict FAIL "$checks" '["hash_tripwire"]' "selftest_anticheat"; exit 3
  fi
  [[ $fails -eq 0 ]] || { verdict FAIL "$checks" '["drift_generator"]' "selftest"; exit 3; }
  verdict PASS "$checks" '[]'; exit 0
fi

MODE="full"
[[ "${1:-}" == "--trial" ]] && MODE="trial"

if ! vlib_impl_present; then
  verdict FAIL 0 '[]' "implementation_missing"; exit 2
fi

run_suite() { # run_suite FIXDIR OUTFILE MODE — one normalized assertion sweep
  local fix="$1" outf="$2" mode="$3"
  export SESSION_RECALL_CODEX_STATE_DB="$fix/state_5.sqlite"
  export SESSION_RECALL_CODEX_HISTORY_DB="$fix/thread_history_1.sqlite"
  export SESSION_RECALL_CODEX_SESSIONS_ROOT="$fix/sessions"
  vlib_safe_truncate "$TMP" "$outf" "codex-smoke."
  local name cmd rc out
  check() { # check NAME EXPECT_RC GREP_PATTERN CMD...
    name="$1"; local want_rc="$2" pat="$3"; shift 3
    out="$(vlib_run "$@")"; rc="${out##*RC:}"
    local body="${out%RC:*}" ok="ok"
    [[ "$rc" == "$want_rc" ]] || ok="rc=$rc"
    if [[ -n "$pat" && "$ok" == "ok" ]] && ! grep -Eq "$pat" <<<"$body"; then ok="pattern"; fi
    echo "$name:$ok" >> "$outf"
  }
  check_stderr() { # check_stderr NAME EXPECT_RC GREP_PATTERN CMD...
    name="$1"; local want_rc="$2" pat="$3"; shift 3
    out="$(vlib_run_stderr "$@")"; rc="${out##*RC:}"
    local body="${out%RC:*}" ok="ok"
    [[ "$rc" == "$want_rc" ]] || ok="rc=$rc"
    if [[ -n "$pat" && "$ok" == "ok" ]] && ! grep -Eq "$pat" <<<"$body"; then ok="pattern"; fi
    echo "$name:$ok" >> "$outf"
  }
  check help 0 "" session-recall-codex --help
  check version 0 "" session-recall-codex --version
  check schema_check 0 "codex-state-v5-migration-55" session-recall-codex schema-check --json
  check schema_check2 0 "codex-thread-history-v1-migration-6" session-recall-codex schema-check --json
  check list 0 '"alpha' session-recall-codex list --json --limit 10
  check list_excludes_guardian 0 "" session-recall-codex list --json --limit 10
  out="$(vlib_run session-recall-codex list --json --limit 10)"
  grep -q "guardian" <<<"${out%RC:*}" && echo "guardian_leak:LEAKED" >> "$outf" || echo "guardian_leak:ok" >> "$outf"
  check repos 0 "repo-a" session-recall-codex repos --json
  if [[ "$mode" == "trial" ]]; then
    check list_archived 0 '"summary": *"archived"' session-recall-codex list --json --include-archived
    check repos_local 0 "local:/tmp/repo-b" session-recall-codex repos --json --include-local
    check_stderr deferred_show 2 "invalid choice" session-recall-codex show 01aa1111 --json
    check_stderr deferred_search 2 "invalid choice" session-recall-codex search "$HELD_OUT_LITERAL" --json
    check_stderr deferred_files 2 "invalid choice" session-recall-codex files --json
    check_stderr deferred_health 2 "invalid choice" session-recall-codex health --json
  else
    check show 0 "found it" session-recall-codex show 01aa1111 --json
    check search_heldout 0 "$HELD_OUT_LITERAL" session-recall-codex search "$HELD_OUT_LITERAL" --json
    check search_band 0 '"window_used": *30' session-recall-codex search "$BAND_TERM" --json
    check files 0 "target.py" session-recall-codex files --json
    check health 0 "" session-recall-codex health --json
  fi
}

checks=0; failed=()

# 1) build fixture, snapshot hashes
vlib_build_fixture "$TMP/fix" >/dev/null
HASH_BEFORE="$(vlib_hash_dir "$TMP/fix")"

# 2) full sweep, twice — verdicts must be identical (idempotency)
run_suite "$TMP/fix" "$TMP/run1.txt" "$MODE"
run_suite "$TMP/fix" "$TMP/run2.txt" "$MODE"
checks=$((checks+1))
cmp -s "$TMP/run1.txt" "$TMP/run2.txt" || failed+=('"idempotency"')
while IFS=: read -r name status; do
  checks=$((checks+1))
  [[ "$status" == "ok" ]] || failed+=("\"$name\"")
done < "$TMP/run1.txt"

# 3) read-only proof: fixture hashes unchanged after both sweeps
checks=$((checks+1))
HASH_AFTER="$(vlib_hash_dir "$TMP/fix")"
[[ "$HASH_BEFORE" == "$HASH_AFTER" ]] || failed+=('"fixture_mutated"')

# 4) drifted copy: CLI exit 2, schema_drift, query_executed:false
checks=$((checks+1))
vlib_mutate "state_migration_56" "$TMP/drifted" >/dev/null
mkdir -p "$TMP/drifted/sessions"
export SESSION_RECALL_CODEX_STATE_DB="$TMP/drifted/state_5.sqlite"
export SESSION_RECALL_CODEX_HISTORY_DB="$TMP/drifted/thread_history_1.sqlite"
export SESSION_RECALL_CODEX_SESSIONS_ROOT="$TMP/drifted/sessions"
out="$(vlib_run session-recall-codex list --json)"
rc="${out##*RC:}"; body="${out%RC:*}"
if [[ "$rc" != "2" ]] || ! grep -q "schema_drift" <<<"$body" || ! grep -q '"query_executed": *false' <<<"$body"; then
  failed+=('"drifted_copy"')
fi

# 5) optional live read-only mode (maintainer): guarded schema-check/list/health
if [[ "${1:-}" == "--live-readonly" ]]; then
  LIVE="$HOME/.codex"
  if [[ -f "$LIVE/state_5.sqlite" ]]; then
    checks=$((checks+1))
    unset SESSION_RECALL_CODEX_STATE_DB SESSION_RECALL_CODEX_HISTORY_DB SESSION_RECALL_CODEX_SESSIONS_ROOT
    live_before="$(shasum -a 256 "$LIVE/state_5.sqlite" "$LIVE/thread_history_1.sqlite" 2>/dev/null)"
    vlib_run session-recall-codex schema-check --json >/dev/null
    vlib_run session-recall-codex list --json --limit 1 >/dev/null
    if [[ "$MODE" == "full" ]]; then
      vlib_run session-recall-codex health --json >/dev/null
    fi
    live_after="$(shasum -a 256 "$LIVE/state_5.sqlite" "$LIVE/thread_history_1.sqlite" 2>/dev/null)"
    if [[ "$live_before" != "$live_after" ]]; then
      echo "[live] NOTE: store hashes changed — check whether live Codex was writing concurrently" >&2
      failed+=('"live_hash_changed"')
    fi
  else
    echo "[live] no live Codex store found — skipping" >&2
  fi
fi

if [[ ${#failed[@]} -gt 0 ]]; then
  verdict FAIL "$checks" "[$(IFS=,; echo "${failed[*]}")]"; exit 1
fi
verdict PASS "$checks" '[]'; exit 0
