#!/usr/bin/env bash
set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$SCRIPT_DIR"

echo "Installing session-recall..."

if command -v uv >/dev/null 2>&1; then
    echo "Using uv..."
    uv tool install --force --editable .
elif command -v pipx >/dev/null 2>&1; then
    echo "Using pipx..."
    pipx install --force -e .
else
    echo "WARN: uv and pipx not found, falling back to pip --user"
    python3 -m pip install --user --force-reinstall -e .
fi

echo ""
echo "Installed. Verify with:"
echo "  which session-recall"
echo "  session-recall schema-check"
