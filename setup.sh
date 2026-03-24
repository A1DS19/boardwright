#!/usr/bin/env bash
# KiCad MCP Server — setup script
# Installs dependencies and registers the MCP server with Claude Code.

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SERVER="$SCRIPT_DIR/kicad_mcp_server.py"
PYTHON="$(which python)"

echo "==> Installing Python dependencies..."
pip install mcp

echo "==> Registering KiCad MCP server with Claude Code..."
cd "$SCRIPT_DIR"
claude mcp add --scope user kicad "$PYTHON" "$SERVER"

echo ""
echo "Done. Run 'claude' in this directory — the KiCad tools will be available."
