"""
KiCad Tool Dispatcher — thin merger over per-domain tool modules.

Responsibilities:
  1. Collect HANDLERS and TOOL_SCHEMAS from every submodule in `tools/`
     plus the router.
  2. Build:
       ALL_HANDLERS  — every tool name → function (union of everything)
       ALL_SCHEMAS   — every tool name → schema dict
       TOOLS         — list of schemas visible to the MCP client:
                       direct tools + 4 router tools ONLY
  3. Expose `dispatch_tool(name, args)` which looks up ALL_HANDLERS and
     calls the handler with keyword arguments.

Why TOOLS ≠ ALL_SCHEMAS: the router pattern hides routed tools from
`list_tools` to reduce context. They are still reachable by name via
`execute_tool` because they live in ALL_HANDLERS.
"""

from __future__ import annotations

from typing import Any, Callable

from . import router
from .tools import (
    fabrication,
    filesystem,
    pcb_checks,
    pcb_layout,
    project,
    research,
    routing,
    schematic,
)

# Re-export for backward compatibility with anything that imported from dispatcher.
from .state import get_project_state  # noqa: F401

# ─────────────────────────────────────────────────────────────────────────────
# Merge HANDLERS and TOOL_SCHEMAS from every submodule.
# ─────────────────────────────────────────────────────────────────────────────

_TOOL_MODULES = [
    project,
    filesystem,
    research,
    schematic,
    pcb_layout,
    routing,
    pcb_checks,
    fabrication,
]


ALL_HANDLERS: dict[str, Callable[..., dict]] = {}
ALL_SCHEMAS: dict[str, dict[str, Any]] = {}

for _mod in _TOOL_MODULES:
    for _name, _fn in _mod.HANDLERS.items():
        if _name in ALL_HANDLERS:
            raise RuntimeError(f"Duplicate tool handler registered: {_name}")
        ALL_HANDLERS[_name] = _fn
    for _schema in _mod.TOOL_SCHEMAS:
        _name = _schema["name"]
        if _name in ALL_SCHEMAS:
            raise RuntimeError(f"Duplicate tool schema registered: {_name}")
        ALL_SCHEMAS[_name] = _schema

# Router tools are also callable by name through the MCP client.
for _name, _fn in router.HANDLERS.items():
    ALL_HANDLERS[_name] = _fn
for _schema in router.TOOL_SCHEMAS:
    ALL_SCHEMAS[_schema["name"]] = _schema


# ─────────────────────────────────────────────────────────────────────────────
# TOOLS: only direct tools + the 4 router tools are visible to MCP clients.
# ─────────────────────────────────────────────────────────────────────────────

TOOLS: list[dict[str, Any]] = (
    [ALL_SCHEMAS[name] for name in sorted(router.DIRECT_TOOL_NAMES) if name in ALL_SCHEMAS]
    + list(router.TOOL_SCHEMAS)
)


# ─────────────────────────────────────────────────────────────────────────────
# Public dispatch
# ─────────────────────────────────────────────────────────────────────────────

def dispatch_tool(tool_name: str, tool_input: dict) -> dict:
    """
    Route a tool call from the agent to the correct implementation function.

    Parameters
    ----------
    tool_name  : str   — the tool's ``name`` field from the TOOLS list
    tool_input : dict  — the validated input dict from the agent's tool-use block

    Returns
    -------
    dict — JSON-serialisable result forwarded back to the agent as tool_result
    """
    fn = ALL_HANDLERS.get(tool_name)
    if fn is None:
        return {
            "status": "error",
            "message": f"Unknown tool '{tool_name}'. Check TOOLS list.",
        }
    try:
        return fn(**(tool_input or {}))
    except TypeError as exc:
        return {
            "status": "error",
            "message": f"Tool '{tool_name}' called with invalid arguments: {exc}",
        }
    except Exception as exc:  # noqa: BLE001
        return {
            "status": "error",
            "message": f"Tool '{tool_name}' raised an exception: {type(exc).__name__}: {exc}",
        }
