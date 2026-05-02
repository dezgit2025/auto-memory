#!/usr/bin/env bash
# scripts/v04-merge-and-test.sh
# Idempotent autonomous merge for the v0.4 two-track plan split.
# Safe to run from either Plan A or Plan B pane after their .completed marker is written.
# Reference: plans/v04-CONTRACT.md §7

set -euo pipefail

REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$REPO_ROOT"

INDEXER_DONE="plans/v04-indexer/.completed"
INSTALL_DONE="plans/v04-install/.completed"
MERGE_DIR="plans/v04-merge"
LOCK="$MERGE_DIR/.in-progress"
PASS="$MERGE_DIR/.tests-pass"

mkdir -p "$MERGE_DIR"

# Are both plans done?
if [ ! -f "$INDEXER_DONE" ] || [ ! -f "$INSTALL_DONE" ]; then
    echo "[merge] waiting for both .completed files (have: indexer=$([ -f "$INDEXER_DONE" ] && echo yes || echo no), install=$([ -f "$INSTALL_DONE" ] && echo yes || echo no))"
    exit 0
fi

# Already passed?
if [ -f "$PASS" ]; then
    echo "[merge] integration already complete and tests passed: $(cat "$PASS")"
    exit 0
fi

# Take lock (clear stale lock > 10 min old)
if [ -f "$LOCK" ]; then
    LOCK_AGE=$(( $(date +%s) - $(stat -f %m "$LOCK" 2>/dev/null || stat -c %Y "$LOCK") ))
    if [ "$LOCK_AGE" -gt 600 ]; then
        echo "[merge] stale lock detected (${LOCK_AGE}s old) — clearing"
        rm -f "$LOCK"
    else
        echo "[merge] another merge in progress (lock ${LOCK_AGE}s old) — exiting"
        exit 0
    fi
fi
echo "$$ $(date)" > "$LOCK"
trap 'rm -f "$LOCK"' EXIT

echo "[merge] starting integration: v0.4-indexer + v0.4-install"

git fetch origin
git checkout main
git pull --rebase

# Create or reset integration branch
git branch -D v0.4-integration 2>/dev/null || true
git checkout -b v0.4-integration

# Merge indexer
echo "[merge] merging v0.4-indexer..."
if ! git merge --no-ff origin/v0.4-indexer -m "merge: Plan A (indexer track)"; then
    echo "[merge] CONFLICT in indexer merge"
    cat > "plans/v04-blockers/$(date +%s)-MERGE-CONFLICT.md" <<EOF
BLOCKED: merge conflict integrating v0.4-indexer
CONTEXT: Auto-merge into v0.4-integration failed.
OPTIONS: A) Manually resolve conflict; B) Restart from a clean branch.
RECOMMEND: human investigation required
EOF
    git add plans/v04-blockers/ && git commit -m "BLOCKER: merge conflict" || true
    git push origin v0.4-integration || true
    exit 2
fi

# Merge install
echo "[merge] merging v0.4-install..."
if ! git merge --no-ff origin/v0.4-install -m "merge: Plan B (install/hook track)"; then
    echo "[merge] CONFLICT in install merge"
    cat > "plans/v04-blockers/$(date +%s)-MERGE-CONFLICT.md" <<EOF
BLOCKED: merge conflict integrating v0.4-install
CONTEXT: Auto-merge into v0.4-integration failed after indexer merged cleanly.
OPTIONS: A) Manually resolve conflict; B) Restart from a clean branch.
RECOMMEND: human investigation required
EOF
    git add plans/v04-blockers/ && git commit -m "BLOCKER: merge conflict" || true
    git push origin v0.4-integration || true
    exit 2
fi

# Write the doctor.py joiner per CONTRACT §5
DOCTOR_PATH="src/session_recall/providers/claude_code/doctor.py"
if [ ! -f "$DOCTOR_PATH" ]; then
    echo "[merge] writing doctor.py joiner"
    cat > "$DOCTOR_PATH" <<'PYEOF'
"""Doctor entrypoint — joins Plan A's doctor_db and Plan B's doctor_hooks.

Per plans/v04-CONTRACT.md §5.
"""
from .doctor_db import (
    check_db_integrity,
    check_schema,
    check_lockfile,
    check_corpus,
    check_symlink_refusal,
)
from .doctor_hooks import (
    check_hooks,
    check_orphans,
    check_logs,
    check_audit,
)


def run(fix: bool = False) -> dict:
    """Run all Claude Code provider doctor checks. Returns {check_name: result_dict}."""
    results = {}
    checks = (
        check_db_integrity,
        check_schema,
        check_lockfile,
        check_corpus,
        check_symlink_refusal,
        check_hooks,
        check_orphans,
        check_logs,
        check_audit,
    )
    for fn in checks:
        try:
            argc = fn.__code__.co_argcount
            results[fn.__name__] = fn(fix) if argc else fn()
        except Exception as exc:
            results[fn.__name__] = {
                "name": fn.__name__,
                "status": "error",
                "details": str(exc),
            }
    return results
PYEOF
    git add "$DOCTOR_PATH"
    git commit -m "merge: add doctor.py joiner per CONTRACT §5"
fi

# Run full test suite
echo "[merge] running full test suite..."
if ! pytest src/ -q --maxfail=5; then
    echo "[merge] TESTS FAILED on integration branch"
    cat > "plans/v04-blockers/$(date +%s)-INTEGRATION-TESTS-FAIL.md" <<EOF
BLOCKED: integration test suite failed on v0.4-integration
CONTEXT: Both plans merged cleanly but pytest failed. See pytest output above.
OPTIONS: A) fix on integration branch; B) revert to last green
RECOMMEND: human investigation required
EOF
    git add plans/v04-blockers/ && git commit -m "BLOCKER: integration tests failed" || true
    git push origin v0.4-integration || true
    exit 3
fi

# Mark integration complete
date -u +%Y-%m-%dT%H:%M:%SZ > "$PASS"
git add "$PASS"
git commit -m "merge: integration tests pass — ready for §22 verification"
git push origin v0.4-integration

echo ""
echo "════════════════════════════════════════════════════════════════════"
echo "  AUTONOMOUS PHASE COMPLETE"
echo "  Branch: v0.4-integration"
echo "  Tests: $(cat "$PASS")"
echo ""
echo "  Next step: human runs §22 V1–V9 verification on v0.4-integration"
echo "  See: plans/claude-code-pr8.md §22 + §22.7 sign-off"
echo "════════════════════════════════════════════════════════════════════"
