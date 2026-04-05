"""
Tool router pattern (ported from KiCAD-MCP-Server's TypeScript implementation).

Goal: reduce the MCP `list_tools` response to ~20 schemas instead of 41, by
hiding less-frequently-used tools behind four meta-tools. Hidden tools are
never registered with the MCP client but are still reachable via `execute_tool`.

Split rationale:
- **Direct (16 tools)**: enough to complete a full project lifecycle
  (setup → research → schematic → PCB → validate → export) without ever
  needing to call the router.
- **Routed (25 tools)**: the long tail — advanced variants, fab-specific
  exports, drc tuning.

Late-bound import note: `execute_tool` imports `ALL_HANDLERS` from
`dispatcher` at call time, not module top. This is deliberate to break the
`dispatcher ↔ router` dependency cycle — dispatcher imports router to merge
the 4 router handlers into ALL_HANDLERS.
"""

from __future__ import annotations

from typing import Any

# ─────────────────────────────────────────────────────────────────────────────
# Direct / routed taxonomy
# ─────────────────────────────────────────────────────────────────────────────

DIRECT_TOOL_NAMES: set[str] = {
    "set_project",
    "get_capabilities",
    "list_directory",
    "read_file",
    "search_components",
    "create_schematic_sheet",
    "add_symbol",
    "connect_pins",
    "add_net_label",
    "get_pin_positions",
    "run_erc",
    "set_board_outline",
    "place_footprint",
    "route_trace",
    "run_drc",
    "generate_gerbers",
}


TOOL_CATEGORIES: list[dict[str, Any]] = [
    {
        "name": "project_admin",
        "description": "DRC rule tuning and exclusion management.",
        "tools": ["set_drc_severity", "add_drc_exclusion"],
    },
    {
        "name": "research",
        "description": "Datasheet lookup, footprint verification, impedance calculations.",
        "tools": [
            "get_datasheet",
            "verify_kicad_footprint",
            "generate_custom_footprint",
            "impedance_calc",
        ],
    },
    {
        "name": "schematic_advanced",
        "description": "Less-common schematic operations: power symbols, no-connects, moves, footprint assignment.",
        "tools": [
            "add_power_symbol",
            "add_no_connect",
            "remove_no_connect",
            "move_symbol",
            "move_label",
            "assign_footprint",
        ],
    },
    {
        "name": "pcb_layout_advanced",
        "description": "Mounting holes, ratsnest queries, keep-out and copper zones.",
        "tools": [
            "add_mounting_holes",
            "get_ratsnest",
            "add_keepout_zone",
            "add_zone",
            "fill_zones",
        ],
    },
    {
        "name": "routing_advanced",
        "description": "Differential pair routing and vias.",
        "tools": ["route_differential_pair", "add_via"],
    },
    {
        "name": "pcb_checks",
        "description": "Silkscreen text and test points.",
        "tools": ["add_silkscreen_text", "add_test_point"],
    },
    {
        "name": "fabrication",
        "description": "Drill files, BOM, pick-and-place, and 3D model exports.",
        "tools": [
            "generate_drill_files",
            "generate_bom",
            "generate_position_file",
            "generate_3d_model",
        ],
    },
]


ROUTER_TOOL_NAMES: set[str] = {
    "list_tool_categories",
    "get_category_tools",
    "search_tools",
    "execute_tool",
}


def _routed_tool_names() -> set[str]:
    names: set[str] = set()
    for cat in TOOL_CATEGORIES:
        names.update(cat["tools"])
    return names


def _category_of(tool_name: str) -> str | None:
    for cat in TOOL_CATEGORIES:
        if tool_name in cat["tools"]:
            return cat["name"]
    return None


# ─────────────────────────────────────────────────────────────────────────────
# The 4 router tools
# ─────────────────────────────────────────────────────────────────────────────

def list_tool_categories() -> dict:
    """Discovery entry point: returns all categories + tool counts."""
    return {
        "status": "ok",
        "total_direct_tools": len(DIRECT_TOOL_NAMES),
        "total_routed_tools": sum(len(c["tools"]) for c in TOOL_CATEGORIES),
        "total_categories": len(TOOL_CATEGORIES),
        "categories": [
            {
                "name": c["name"],
                "description": c["description"],
                "tool_count": len(c["tools"]),
            }
            for c in TOOL_CATEGORIES
        ],
        "note": (
            "Direct tools are always visible. Use get_category_tools to see "
            "what's inside a category, then execute_tool to run a routed tool."
        ),
    }


def get_category_tools(category: str) -> dict:
    """Return the list of tools in a category, with their descriptions."""
    # Late import to avoid cycle: dispatcher imports router.
    from . import dispatcher

    cat = next((c for c in TOOL_CATEGORIES if c["name"] == category), None)
    if cat is None:
        return {
            "status": "error",
            "message": f"Unknown category '{category}'.",
            "available_categories": [c["name"] for c in TOOL_CATEGORIES],
        }

    tools_out = []
    for tool_name in cat["tools"]:
        schema = dispatcher.ALL_SCHEMAS.get(tool_name, {})
        tools_out.append({
            "name": tool_name,
            "description": schema.get("description", ""),
        })

    return {
        "status": "ok",
        "category": category,
        "description": cat["description"],
        "tool_count": len(tools_out),
        "tools": tools_out,
    }


def search_tools(query: str) -> dict:
    """Case-insensitive search across tool name, description, and category name."""
    from . import dispatcher

    q = (query or "").lower().strip()
    if not q:
        return {"status": "error", "message": "Empty query."}

    matches: list[dict] = []
    for cat in TOOL_CATEGORIES:
        for tool_name in cat["tools"]:
            schema = dispatcher.ALL_SCHEMAS.get(tool_name, {})
            desc = schema.get("description", "")
            if (q in tool_name.lower()
                    or q in desc.lower()
                    or q in cat["name"].lower()):
                matches.append({
                    "category": cat["name"],
                    "name": tool_name,
                    "description": desc,
                })

    # Also search direct tools so users can find them via search too.
    for tool_name in DIRECT_TOOL_NAMES:
        schema = dispatcher.ALL_SCHEMAS.get(tool_name, {})
        desc = schema.get("description", "")
        if q in tool_name.lower() or q in desc.lower():
            matches.append({
                "category": "direct",
                "name": tool_name,
                "description": desc,
            })

    return {
        "status": "ok",
        "query": query,
        "count": len(matches),
        "matches": matches[:20],
        "note": "Direct tools can be called by name without execute_tool.",
    }


def execute_tool(tool_name: str, params: dict | None = None) -> dict:
    """Run a routed tool by name."""
    from . import dispatcher  # late import to break cycle

    if tool_name in ROUTER_TOOL_NAMES:
        return {
            "status": "error",
            "message": f"'{tool_name}' is a router tool — call it directly instead of via execute_tool.",
        }

    if tool_name in DIRECT_TOOL_NAMES:
        # Still run it — but warn the agent that wrapping is unnecessary.
        fn = dispatcher.ALL_HANDLERS.get(tool_name)
        if fn is None:
            return {"status": "error", "message": f"Unknown tool: {tool_name}"}
        try:
            result = fn(**(params or {}))
            if isinstance(result, dict):
                result.setdefault("note", f"'{tool_name}' is a direct tool; you can call it by name without execute_tool.")
            return result
        except TypeError as e:
            return {"status": "error", "message": f"Invalid arguments for {tool_name}: {e}"}

    fn = dispatcher.ALL_HANDLERS.get(tool_name)
    if fn is None:
        return {
            "status": "error",
            "message": f"Unknown tool: {tool_name}",
            "hint": "Use list_tool_categories or search_tools to discover available tools.",
        }

    try:
        return fn(**(params or {}))
    except TypeError as e:
        return {"status": "error", "message": f"Invalid arguments for {tool_name}: {e}"}
    except Exception as e:  # noqa: BLE001
        return {"status": "error", "message": f"{tool_name} raised {type(e).__name__}: {e}"}


HANDLERS = {
    "list_tool_categories": list_tool_categories,
    "get_category_tools":   get_category_tools,
    "search_tools":         search_tools,
    "execute_tool":         execute_tool,
}


TOOL_SCHEMAS = [
    {
        "name": "list_tool_categories",
        "description": (
            "List all routed tool categories with descriptions and tool counts. "
            "Use this first to discover what categories of tools are available "
            "beyond the direct tools visible in this tool list."
        ),
        "input_schema": {"type": "object", "properties": {}},
    },
    {
        "name": "get_category_tools",
        "description": (
            "List the tools inside a specific routed category, with their descriptions. "
            "Use after list_tool_categories to drill into a category before executing a tool."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "category": {
                    "type": "string",
                    "description": "Category name from list_tool_categories (e.g. 'fabrication')",
                },
            },
            "required": ["category"],
        },
    },
    {
        "name": "search_tools",
        "description": (
            "Search all tools (direct and routed) by name, description, or category. "
            "Case-insensitive substring match. Returns up to 20 matches."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "Free-text search term, e.g. 'gerber', 'differential', 'zone'",
                },
            },
            "required": ["query"],
        },
    },
    {
        "name": "execute_tool",
        "description": (
            "Execute a routed tool by name with the given parameters. "
            "Use this for any tool returned by get_category_tools or search_tools that is NOT "
            "already visible in the direct tool list."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "tool_name": {
                    "type": "string",
                    "description": "Exact tool name as returned by get_category_tools",
                },
                "params": {
                    "type": "object",
                    "description": "Parameters to pass to the tool (matches that tool's own input_schema)",
                },
            },
            "required": ["tool_name"],
        },
    },
]
