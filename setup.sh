#!/usr/bin/env bash
# KiCad MCP Server — setup script
# Installs dependencies and registers the MCP server with Claude Code.

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SERVER="$SCRIPT_DIR/kicad_mcp_server.py"

if command -v python3 >/dev/null 2>&1; then
  PYTHON="$(command -v python3)"
elif command -v python >/dev/null 2>&1; then
  PYTHON="$(command -v python)"
else
  echo "Error: Python is not installed or not on PATH." >&2
  exit 1
fi

if ! command -v claude >/dev/null 2>&1; then
  echo "Error: 'claude' CLI is not installed or not on PATH." >&2
  exit 1
fi

echo "==> Installing Python dependencies..."
"$PYTHON" -m pip install --upgrade pip
"$PYTHON" -m pip install -e "$SCRIPT_DIR"

echo "==> Registering KiCad MCP server with Claude Code..."
cd "$SCRIPT_DIR"
claude mcp add --scope user kicad "$PYTHON" "$SERVER"

echo ""
echo "Done. Run 'claude' from any directory — the KiCad tools will be available."
