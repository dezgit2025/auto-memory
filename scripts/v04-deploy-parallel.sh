#!/usr/bin/env bash
# scripts/v04-deploy-parallel.sh
# Launches the v0.4 two-track parallel execution OR runs a smoke test.
# See plans/deploy-parallel-plan.md for full doc.

set -euo pipefail

REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$REPO_ROOT"

MODE="${1:---help}"
MODEL="claude-opus-4.6-1m"
EFFORT="medium"
SESSION="v04"
SMOKE_SESSION="v04-smoke"

usage() {
    cat <<EOF
Usage: $(basename "$0") [--smoke | --launch | --status | --help]

  --smoke    Run a 60-sec harmless smoke test of tmux + copilot CLI mechanics
  --launch   Real launch: create branches, spawn 2-pane tmux, start agents
  --status   Show progress (blockers, completion markers, recent commits)
  --help     This message
EOF
}

preflight() {
    echo "[preflight] checking environment..."

    # Verify copilot CLI is installed and the model is available
    if ! command -v copilot >/dev/null; then
        echo "❌ copilot CLI not found on PATH"
        return 1
    fi

    # Verify required plan files exist
    local missing=0
    for f in \
        "plans/claude-code-pr8.md" \
        "plans/v04-CONTRACT.md" \
        "plans/v04-indexer/plan.md" "plans/v04-indexer/progress.md" \
        "plans/v04-install/plan.md" "plans/v04-install/progress.md" \
        "scripts/v04-merge-and-test.sh"
    do
        if [ ! -f "$f" ]; then
            echo "❌ missing: $f"
            missing=1
        fi
    done
    [ "$missing" -eq 0 ] || return 1

    # Verify merge script is executable
    [ -x "scripts/v04-merge-and-test.sh" ] || { echo "❌ scripts/v04-merge-and-test.sh not executable"; return 1; }

    # Verify clean tree
    if [ -n "$(git status --porcelain)" ]; then
        echo "⚠️  uncommitted changes in working tree:"
        git status --short
        echo "    (script will stash + restore around branch creation)"
    fi

    echo "[preflight] ✅ all checks passed"
}

smoke() {
    echo "[smoke] starting smoke test of model + tmux..."

    # Test 1: model is reachable
    echo "[smoke] testing model $MODEL..."
    local out
    out="$(copilot -p "Reply with just the word READY and nothing else." --model "$MODEL" --effort low --yolo 2>&1 | head -5)"
    if echo "$out" | grep -qi "ready"; then
        echo "[smoke] ✅ model $MODEL responded"
    else
        echo "[smoke] ❌ model test failed. Output:"
        echo "$out"
        return 1
    fi

    # Test 2: tmux 2-pane spawning
    echo "[smoke] testing tmux 2-pane setup..."
    tmux kill-session -t "$SMOKE_SESSION" 2>/dev/null || true
    tmux new-session -d -s "$SMOKE_SESSION" -c "$REPO_ROOT" -x 220 -y 60
    tmux split-window -h -t "$SMOKE_SESSION" -c "$REPO_ROOT"
    sleep 0.5
    tmux send-keys -t "$SMOKE_SESSION.0" "echo SMOKE_PANE_0_OK_\$(pwd)" Enter
    tmux send-keys -t "$SMOKE_SESSION.1" "echo SMOKE_PANE_1_OK_\$(pwd)" Enter
    sleep 2

    local p0 p1
    p0="$(tmux capture-pane -t "$SMOKE_SESSION.0" -p | grep -c SMOKE_PANE_0_OK || true)"
    p1="$(tmux capture-pane -t "$SMOKE_SESSION.1" -p | grep -c SMOKE_PANE_1_OK || true)"

    tmux kill-session -t "$SMOKE_SESSION"

    if [ "$p0" -ge 1 ] && [ "$p1" -ge 1 ]; then
        echo "[smoke] ✅ both panes worked"
    else
        echo "[smoke] ❌ pane test failed (pane0_hits=$p0 pane1_hits=$p1)"
        return 1
    fi

    echo ""
    echo "════════════════════════════════════════"
    echo "  SMOKE TEST PASSED"
    echo "  Ready for: $(basename "$0") --launch"
    echo "════════════════════════════════════════"
}

write_prompts() {
    cat > /tmp/v04-prompt-A.txt <<'PROMPT'
You are an autonomous coding agent executing Plan A — the Indexer Track for auto-memory v0.4. REQUIRED READING IN ORDER: 1) plans/claude-code-pr8.md sections 19 through 33 (North Star section 29), 2) plans/v04-CONTRACT.md fully, 3) plans/v04-indexer/plan.md, 4) CLAUDE.md. THEN read plans/v04-indexer/progress.md and update it after each item completes. RULES: honor section 29 North Star (do not over-engineer); use sub-agents for parallel items (A12d, A12e, A12g, A12j, A12o, A12p); Item A1 must be committed and pushed within 30 minutes (Plan B blocks on it); after each item run pytest, commit, push to v0.4-indexer, update progress.md to done with date; on TRUE blocker write plans/v04-blockers/$(date +%s)-PLANA.md per CONTRACT section 8 then PIVOT to non-blocked item; when all items pass and pytest src/session_recall/providers/claude_code/ -q is green, write plans/v04-indexer/.completed and run ./scripts/v04-merge-and-test.sh; YOLO mode is on, do not ask for permissions. Begin Item A0 now.
PROMPT

    cat > /tmp/v04-prompt-B.txt <<'PROMPT'
You are an autonomous coding agent executing Plan B — the Hook+Install Track for auto-memory v0.4. REQUIRED READING IN ORDER: 1) plans/claude-code-pr8.md sections 19 through 33 (North Star section 29), 2) plans/v04-CONTRACT.md fully, 3) plans/v04-install/plan.md, 4) CLAUDE.md. THEN read plans/v04-install/progress.md and update it after each item. RULES: honor section 29 North Star; Item B0 polls for src/session_recall/providers/claude_code/_paths.py (run its loop verbatim); while waiting, re-read contract and draft B6 install.py mentally (Spicy item, TDD it); use sub-agents for parallel B12* tests; Item B6 install.py is SPICY (TDD against fixtures FIRST); after each item run pytest, commit, push to v0.4-install, update progress.md to done with date; race tests B12f must pass pytest --count=20; latency tests B12b use HARD-FAIL assertions; on TRUE blocker write plans/v04-blockers/$(date +%s)-PLANB.md per CONTRACT section 8 then PIVOT; when all items pass and race tests pass --count=20, write plans/v04-install/.completed and run ./scripts/v04-merge-and-test.sh; YOLO is on, do not ask permissions. Begin Item B0 now.
PROMPT
}

launch() {
    preflight || return 1

    echo "[launch] creating branches..."
    local needs_stash=0
    if [ -n "$(git status --porcelain)" ]; then
        git stash push --include-untracked -m "v04-deploy auto-stash"
        needs_stash=1
    fi
    git checkout main
    git pull --rebase 2>/dev/null || true
    git checkout -B v0.4-indexer
    git checkout main
    git checkout -B v0.4-install
    git checkout main
    [ "$needs_stash" = "1" ] && git stash pop || true

    echo "[launch] writing kickoff prompts..."
    write_prompts

    echo "[launch] killing any existing $SESSION session..."
    tmux kill-session -t "$SESSION" 2>/dev/null || true

    echo "[launch] creating tmux session $SESSION with 2 panes..."
    tmux new-session -d -s "$SESSION" -c "$REPO_ROOT" -x 220 -y 60
    tmux split-window -h -t "$SESSION" -c "$REPO_ROOT"

    echo "[launch] starting Plan A in pane 0..."
    tmux send-keys -t "$SESSION.0" "git checkout v0.4-indexer" Enter
    sleep 1
    tmux send-keys -t "$SESSION.0" "copilot --model $MODEL --effort $EFFORT --yolo" Enter
    sleep 5
    tmux send-keys -t "$SESSION.0" -l "$(cat /tmp/v04-prompt-A.txt)"
    sleep 0.5
    tmux send-keys -t "$SESSION.0" Enter

    echo "[launch] starting Plan B in pane 1..."
    tmux send-keys -t "$SESSION.1" "git checkout v0.4-install" Enter
    sleep 1
    tmux send-keys -t "$SESSION.1" "copilot --model $MODEL --effort $EFFORT --yolo" Enter
    sleep 5
    tmux send-keys -t "$SESSION.1" -l "$(cat /tmp/v04-prompt-B.txt)"
    sleep 0.5
    tmux send-keys -t "$SESSION.1" Enter

    echo ""
    echo "════════════════════════════════════════════════════════════════════"
    echo "  LAUNCHED"
    echo "  Session: $SESSION (2 panes)"
    echo "  Pane 0: Plan A (Indexer) on branch v0.4-indexer"
    echo "  Pane 1: Plan B (Install) on branch v0.4-install"
    echo "  Model: $MODEL  Effort: $EFFORT  Permissions: yolo"
    echo ""
    echo "  Attach:   tmux attach -t $SESSION"
    echo "  Status:   $(basename "$0") --status"
    echo "  Pause:    tmux send-keys -t $SESSION.0 C-c   (and .1)"
    echo "  Abort:    tmux kill-session -t $SESSION"
    echo "════════════════════════════════════════════════════════════════════"
}

status() {
    echo "════════════ v0.4 PARALLEL EXECUTION STATUS ════════════"
    echo ""
    echo "Tmux session:"
    tmux ls 2>/dev/null | grep -E "^$SESSION:" || echo "  (no $SESSION session active)"
    echo ""
    echo "Completion markers:"
    for f in plans/v04-indexer/.completed plans/v04-install/.completed plans/v04-merge/.tests-pass; do
        if [ -f "$f" ]; then
            echo "  ✅ $f  ($(cat "$f"))"
        else
            echo "  ⏳ $f  (not yet)"
        fi
    done
    echo ""
    echo "Blocker files:"
    if [ -d plans/v04-blockers ] && [ -n "$(ls -A plans/v04-blockers 2>/dev/null)" ]; then
        ls -la plans/v04-blockers/
    else
        echo "  (none)"
    fi
    echo ""
    echo "Recent commits on v0.4-indexer (vs main):"
    git log --oneline v0.4-indexer ^main 2>/dev/null | head -10 || echo "  (branch doesn't exist yet)"
    echo ""
    echo "Recent commits on v0.4-install (vs main):"
    git log --oneline v0.4-install ^main 2>/dev/null | head -10 || echo "  (branch doesn't exist yet)"
    echo ""
    echo "Progress: Plan A"
    grep -E "^\| A[0-9]" plans/v04-indexer/progress.md 2>/dev/null | head -20 || true
    echo ""
    echo "Progress: Plan B"
    grep -E "^\| B[0-9]" plans/v04-install/progress.md 2>/dev/null | head -20 || true
}

case "$MODE" in
    --smoke)  smoke ;;
    --launch) launch ;;
    --status) status ;;
    --help|-h|*) usage ;;
esac
