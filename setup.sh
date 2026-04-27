#!/usr/bin/env bash
# Boardwright — local install + Claude Code registration.
# Installs the package in editable mode and registers the MCP server globally.

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

if command -v python3 >/dev/null 2>&1; then
  PYTHON="$(command -v python3)"
elif command -v python >/dev/null 2>&1; then
  PYTHON="$(command -v python)"
else
  echo "error: python is not installed or not on PATH" >&2
  exit 1
fi

if ! command -v claude >/dev/null 2>&1; then
  echo "error: 'claude' CLI is not installed or not on PATH" >&2
  echo "       install Claude Code first: https://claude.com/claude-code" >&2
  exit 1
fi

echo "==> installing boardwright (editable)..."
"$PYTHON" -m pip install --upgrade pip
"$PYTHON" -m pip install -e "$SCRIPT_DIR"

echo "==> registering boardwright with Claude Code (user scope)..."
claude mcp add --scope user boardwright "$PYTHON" -m boardwright.server

echo
echo "done. open Claude Code from any directory and run /mcp to verify."
