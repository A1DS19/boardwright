#!/usr/bin/env python3
"""
KiCad MCP Server

Exposes all KiCad design tools to Claude Code via the Model Context Protocol.
Claude Code connects to this server and can call any KiCad tool directly.

Run via setup.sh — do not invoke manually.
"""

import asyncio
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from mcp.server import Server
from mcp.server.stdio import stdio_server
import mcp.types as types

from kicad_agent import TOOLS, dispatch_tool

server = Server("kicad")


@server.list_tools()
async def list_tools() -> list[types.Tool]:
    return [
        types.Tool(
            name=t["name"],
            description=t["description"],
            inputSchema=t["input_schema"],
        )
        for t in TOOLS
    ]


@server.call_tool()
async def call_tool(name: str, arguments: dict) -> list[types.TextContent]:
    result = dispatch_tool(name, arguments or {})
    return [types.TextContent(type="text", text=json.dumps(result, indent=2))]


async def main():
    async with stdio_server() as (read, write):
        await server.run(read, write, server.create_initialization_options())


if __name__ == "__main__":
    asyncio.run(main())
