#!/usr/bin/env bash
# install-claude-sidecar.sh — cross-platform installer for the session-recall
# Claude Code pre-warm sidecar. Mirrors deploy/install-claude-code.md §7a/§7b.
#
# Canonical Label: com.session-recall-cc.sidecar
set -euo pipefail

LABEL="com.session-recall-cc.sidecar"
PLIST_PATH="$HOME/Library/LaunchAgents/${LABEL}.plist"
LOG_PATH="$HOME/.claude/.sr-sidecar.log"
ERR_PATH="$HOME/.claude/.sr-sidecar.err.log"
CRON_MARKER="session_recall.providers.claude_code.sidecar"

ACTION="install"
SCHEDULER="auto"
INTERVAL=300
DRY_RUN=0
ASSUME_YES=0

usage() {
    cat <<EOF
Usage: install-claude-sidecar.sh [--install|--uninstall|--status] [options]

Installs the session-recall Claude Code pre-warm sidecar under the canonical
launchd Label "${LABEL}" (macOS) or a marked crontab line (Linux).

Actions:
  --install          (default) install the scheduler entry
  --uninstall        remove the scheduler entry and log files
  --status           report current install state (always exits 0)

Options:
  --scheduler MODE   launchd | cron | auto (default: auto)
  --interval SECS    pre-warm interval in seconds (default: 300)
  --dry-run          print what would change, do not mutate
  -y, --yes          skip the confirmation prompt
  -h, --help         show this help

Windows: use the PowerShell snippet in deploy/install-claude-code.md §7c.
EOF
}

log() { printf '%s\n' "$*" >&2; }
die() { log "error: $*"; exit 1; }

emit_verdict() {
    local verdict="$1" exit_code="$2" sched="${3:-none}"
    printf '{"verdict":"%s","action":"%s","scheduler":"%s","exit":%s}\n' \
        "$verdict" "$ACTION" "$sched" "$exit_code"
    exit "$exit_code"
}

# ---------- arg parsing ----------
while [[ $# -gt 0 ]]; do
    case "$1" in
        --install)   ACTION="install" ;;
        --uninstall) ACTION="uninstall" ;;
        --status)    ACTION="status" ;;
        --scheduler) SCHEDULER="${2:?}"; shift ;;
        --interval)  INTERVAL="${2:?}"; shift ;;
        --dry-run)   DRY_RUN=1 ;;
        -y|--yes)    ASSUME_YES=1 ;;
        -h|--help)   usage; exit 0 ;;
        *) die "unknown arg: $1 (try --help)" ;;
    esac
    shift
done

case "$SCHEDULER" in launchd|cron|auto) ;; *) die "--scheduler must be launchd|cron|auto" ;; esac
[[ "$INTERVAL" =~ ^[0-9]+$ ]] || die "--interval must be a positive integer"
(( INTERVAL >= 30 )) || die "--interval must be >= 30 seconds"

# ---------- OS detection ----------
UNAME="$(uname -s)"
case "$UNAME" in
    Darwin) OS="macos" ;;
    Linux)  OS="linux" ;;
    MINGW*|MSYS*|CYGWIN*)
        log "Windows detected. This bash installer does not support Windows."
        log "See deploy/install-claude-code.md §7c for the PowerShell snippet."
        emit_verdict "pass" 0 "none"
        ;;
    *) die "unsupported OS: $UNAME" ;;
esac

if [[ "$SCHEDULER" == "auto" ]]; then
    [[ "$OS" == "macos" ]] && SCHEDULER="launchd" || SCHEDULER="cron"
fi
[[ "$SCHEDULER" == "launchd" && "$OS" != "macos" ]] && die "launchd is macOS-only"

# ---------- pre-flight (read-only) ----------
preflight() {
    command -v python3 >/dev/null 2>&1 || die "python3 not found on PATH"
    local ver
    ver="$(python3 -c 'import sys;print(f"{sys.version_info[0]}.{sys.version_info[1]}")')"
    python3 -c 'import sys;sys.exit(0 if sys.version_info>=(3,10) else 1)' \
        || die "python3 >= 3.10 required (found $ver)"
    python3 -c 'import session_recall.providers.claude_code.sidecar' 2>/dev/null \
        || die "session_recall package not importable — run: pip install -e ."
    [[ -d "$HOME/.claude" ]] || die "$HOME/.claude does not exist (Claude Code not set up?)"
}

PYTHON3=""
resolve_python() { PYTHON3="$(command -v python3)"; }

# ---------- detection ----------
launchd_installed() { [[ -f "$PLIST_PATH" ]] && launchctl list 2>/dev/null | grep -q "[[:space:]]${LABEL}\$"; }
launchd_present()   { [[ -f "$PLIST_PATH" ]]; }
cron_installed()    { crontab -l 2>/dev/null | grep -Fq "$CRON_MARKER"; }

current_state() {
    local s_lp="no" s_cr="no"
    launchd_present && s_lp="yes"
    cron_installed && s_cr="yes"
    if launchd_installed; then echo "installed-launchd"
    elif [[ "$s_lp" == "yes" ]]; then echo "installed-but-broken"
    elif [[ "$s_cr" == "yes" ]]; then echo "installed-cron"
    else echo "not-installed"; fi
}

next_run_iso() {
    if command -v python3 >/dev/null 2>&1; then
        python3 -c "import datetime as d;print((d.datetime.now(d.timezone.utc)+d.timedelta(seconds=$INTERVAL)).isoformat(timespec='seconds'))"
    else echo "unknown"; fi
}

print_status_block() {
    local sched="$1" path="$2" installed="$3"
    cat <<EOF
installed=${installed} scheduler=${sched} plist_or_crontab=${path} log=${LOG_PATH} next_run=$(next_run_iso)
EOF
}

confirm() {
    [[ $ASSUME_YES -eq 1 ]] && return 0
    [[ $DRY_RUN -eq 1 ]] && return 0
    printf 'Proceed? [y/N] ' >&2
    local ans=""; read -r ans || true
    [[ "$ans" =~ ^[Yy]$ ]]
}

# ---------- launchd install ----------
write_plist() {
    cat > "$PLIST_PATH" <<EOF
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>Label</key>
    <string>${LABEL}</string>
    <key>ProgramArguments</key>
    <array>
        <string>${PYTHON3}</string>
        <string>-m</string>
        <string>session_recall.providers.claude_code.sidecar</string>
        <string>--once</string>
    </array>
    <key>EnvironmentVariables</key>
    <dict>
        <key>SESSION_RECALL_ENABLE_CLAUDE_BACKEND</key>
        <string>1</string>
        <key>PATH</key>
        <string>/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin</string>
    </dict>
    <key>StartInterval</key>
    <integer>${INTERVAL}</integer>
    <key>RunAtLoad</key>
    <true/>
    <key>StandardOutPath</key>
    <string>${LOG_PATH}</string>
    <key>StandardErrorPath</key>
    <string>${ERR_PATH}</string>
    <key>WorkingDirectory</key>
    <string>${HOME}</string>
    <key>ProcessType</key>
    <string>Background</string>
</dict>
</plist>
EOF
}

install_launchd() {
    resolve_python
    log "Plan: write ${PLIST_PATH} (StartInterval=${INTERVAL}s) and launchctl load -w"
    confirm || { log "aborted"; emit_verdict "fail" 1 "launchd"; }
    if [[ $DRY_RUN -eq 1 ]]; then log "(dry-run) no changes made"; emit_verdict "pass" 0 "launchd"; fi

    mkdir -p "$HOME/Library/LaunchAgents" "$HOME/.claude"
    write_plist
    plutil -lint "$PLIST_PATH" >/dev/null
    launchctl unload "$PLIST_PATH" 2>/dev/null || true
    launchctl load -w "$PLIST_PATH"

    if ! launchd_installed; then
        log "verify failed: ${LABEL} not registered with launchctl"
        print_status_block "launchd" "$PLIST_PATH" "NO"
        emit_verdict "fail" 2 "launchd"
    fi
    sleep 4
    [[ -f "$LOG_PATH" ]] && tail -3 "$LOG_PATH" >&2 || true
    print_status_block "launchd" "$PLIST_PATH" "YES"
    emit_verdict "pass" 0 "launchd"
}

# ---------- cron install ----------
cron_schedule() {
    local mins=$(( INTERVAL / 60 ))
    (( mins < 1 )) && mins=1
    if (( INTERVAL == 60 )); then echo "* * * * *"
    else echo "*/${mins} * * * *"; fi
}

install_cron() {
    resolve_python
    local sched line
    sched="$(cron_schedule)"
    line="${sched} env SESSION_RECALL_ENABLE_CLAUDE_BACKEND=1 ${PYTHON3} -m session_recall.providers.claude_code.sidecar --once >> ${LOG_PATH} 2>&1"
    log "Plan: replace any existing '${CRON_MARKER}' crontab line with:"
    log "  ${line}"
    confirm || { log "aborted"; emit_verdict "fail" 1 "cron"; }
    if [[ $DRY_RUN -eq 1 ]]; then log "(dry-run) no changes made"; emit_verdict "pass" 0 "cron"; fi

    mkdir -p "$HOME/.claude"
    { crontab -l 2>/dev/null | grep -Fv "$CRON_MARKER" || true; echo "$line"; } | crontab -
    if ! cron_installed; then
        log "verify failed: cron entry not found"
        print_status_block "cron" "(crontab)" "NO"
        emit_verdict "fail" 2 "cron"
    fi
    print_status_block "cron" "(crontab)" "YES"
    emit_verdict "pass" 0 "cron"
}

# ---------- uninstall ----------
do_uninstall() {
    log "Plan: remove canonical Label '${LABEL}' (launchd) and any '${CRON_MARKER}' crontab line; delete logs."
    log "Note: this only touches the canonical handle. Other labels (e.g. com.dez.*) are left alone."
    confirm || { log "aborted"; emit_verdict "fail" 1 "none"; }
    if [[ $DRY_RUN -eq 1 ]]; then log "(dry-run) no changes made"; emit_verdict "pass" 0 "none"; fi

    if [[ -f "$PLIST_PATH" ]]; then
        launchctl unload -w "$PLIST_PATH" 2>/dev/null || true
        rm -f "$PLIST_PATH"
    fi
    if cron_installed; then
        crontab -l 2>/dev/null | grep -Fv "$CRON_MARKER" | crontab - || true
    fi
    rm -f "$LOG_PATH" "$ERR_PATH"

    if launchd_installed || cron_installed; then
        log "verify failed: residue still present"
        emit_verdict "fail" 2 "none"
    fi
    log "uninstalled cleanly"
    print_status_block "none" "-" "NO"
    emit_verdict "pass" 0 "none"
}

# ---------- status ----------
do_status() {
    local state sched="none" path="-" installed="NO"
    state="$(current_state)"
    case "$state" in
        installed-launchd)     sched="launchd"; path="$PLIST_PATH"; installed="YES" ;;
        installed-cron)        sched="cron";    path="(crontab)";   installed="YES" ;;
        installed-but-broken)  sched="launchd"; path="$PLIST_PATH"; installed="BROKEN" ;;
        not-installed)         : ;;
    esac
    log "state: ${state} (canonical Label: ${LABEL})"
    if [[ "$state" == "not-installed" ]]; then
        local other
        other="$(launchctl list 2>/dev/null | grep -i 'session-recall' | grep -v "${LABEL}\$" || true)"
        [[ -n "$other" ]] && log "note: other session-recall labels present (left untouched):" && log "$other"
    fi
    print_status_block "$sched" "$path" "$installed"
    emit_verdict "pass" 0 "$sched"
}

# ---------- dispatch ----------
case "$ACTION" in
    status)    do_status ;;
    install)
        preflight
        existing="$(current_state)"
        case "$existing" in
            installed-launchd|installed-cron|installed-but-broken)
                log "existing install detected (${existing}); will replace idempotently."
                ;;
        esac
        case "$SCHEDULER" in
            launchd) install_launchd ;;
            cron)    install_cron ;;
        esac
        ;;
    uninstall) do_uninstall ;;
esac
