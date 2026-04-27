"""Boardwright MCP server.

Exposes the Boardwright KiCad tool catalog over the Model Context Protocol.
Wired into Claude Code via `claude mcp add`; not invoked manually.
"""

from __future__ import annotations

import asyncio
import json
import logging

import mcp.types as types
from mcp.server import Server
from mcp.server.stdio import stdio_server

from boardwright import TOOLS, dispatch_tool

log = logging.getLogger("boardwright.server")

server = Server("boardwright")


def _relax_scalars(schema: dict) -> dict:
    """Broaden scalar property types to also accept strings.

    Some MCP harnesses (XML-param transports) serialize numbers and booleans
    as strings. The dispatcher coerces them back before invoking the handler;
    this just keeps schema validation from rejecting them at the wire.
    """
    props = (schema or {}).get("properties") or {}
    for spec in props.values():
        if not isinstance(spec, dict):
            continue
        t = spec.get("type")
        if isinstance(t, str) and t in ("number", "integer", "boolean"):
            spec["type"] = [t, "string"]
    return schema


@server.list_tools()
async def list_tools() -> list[types.Tool]:
    return [
        types.Tool(
            name=t["name"],
            description=t["description"],
            inputSchema=_relax_scalars(json.loads(json.dumps(t["input_schema"]))),
        )
        for t in TOOLS
    ]


@server.call_tool()
async def call_tool(name: str, arguments: dict) -> list[types.TextContent]:
    result = dispatch_tool(name, arguments or {})
    return [types.TextContent(type="text", text=json.dumps(result, indent=2))]


async def _run() -> None:
    async with stdio_server() as (read, write):
        await server.run(read, write, server.create_initialization_options())


def main() -> None:
    """Console-script entry point: `boardwright-mcp`."""
    logging.basicConfig(level=logging.INFO, format="%(name)s: %(message)s")
    asyncio.run(_run())


if __name__ == "__main__":
    main()
