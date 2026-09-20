#!/usr/bin/env bash
# Synced to deploy/install.md — see that file for the full agent-runnable flow
# AI agents: use a reasoning model (Sonnet 4.6, GPT-5.4) — mini models may skip confirmation gates
set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$SCRIPT_DIR"

echo "Installing session-recall..."
VENV_FALLBACK=false

if command -v pipx >/dev/null 2>&1; then
    echo "Using pipx..."
    pipx install --force -e .
elif command -v uv >/dev/null 2>&1; then
    echo "Using uv..."
    uv tool install --force --editable .
else
    echo "WARN: pipx and uv not found; installing into the project .venv"
    VENV_FALLBACK=true
    python3 -m venv "$SCRIPT_DIR/.venv"
    "$SCRIPT_DIR/.venv/bin/python" -m pip install --force-reinstall -e .
fi

echo ""
echo "Installed. Verify with:"
if [[ "$VENV_FALLBACK" == true ]]; then
    echo "  export PATH=\"$SCRIPT_DIR/.venv/bin:\$PATH\""
fi
echo "  command -v session-recall"
echo "  session-recall schema-check"
