"""
Router pattern: discovery chain, search, and execute_tool delegation.

The router hides routed tools from list_tools but they stay reachable via
execute_tool. These tests lock that contract in place.
"""

from __future__ import annotations

from kicad_agent import dispatcher, router


def test_list_tool_categories():
    result = dispatcher.dispatch_tool("list_tool_categories", {})
    assert result["status"] == "ok"
    assert result["total_categories"] == len(router.TOOL_CATEGORIES)
    names = {c["name"] for c in result["categories"]}
    assert "fabrication" in names
    assert "research" in names


def test_get_category_tools_known():
    result = dispatcher.dispatch_tool("get_category_tools", {"category": "fabrication"})
    assert result["status"] == "ok"
    tool_names = {t["name"] for t in result["tools"]}
    assert "generate_bom" in tool_names
    assert "generate_drill_files" in tool_names


def test_get_category_tools_unknown():
    result = dispatcher.dispatch_tool("get_category_tools", {"category": "nonsense"})
    assert result["status"] == "error"
    assert "available_categories" in result


def test_search_tools_by_name():
    result = dispatcher.dispatch_tool("search_tools", {"query": "gerber"})
    assert result["status"] == "ok"
    assert result["count"] >= 1
    assert any("gerber" in m["name"].lower() for m in result["matches"])


def test_search_tools_includes_direct():
    # Direct tools should also be discoverable via search (marked category="direct").
    result = dispatcher.dispatch_tool("search_tools", {"query": "set_project"})
    assert result["status"] == "ok"
    assert any(m["category"] == "direct" for m in result["matches"])


def test_execute_tool_delegates_to_routed():
    # generate_bom is routed; execute_tool should reach it.
    result = dispatcher.dispatch_tool(
        "execute_tool",
        {"tool_name": "generate_bom", "params": {}},
    )
    # No project set — should return an error from the handler, not a dispatch failure.
    assert result["status"] == "error"
    assert "set_project" in result["message"]


def test_execute_tool_recursion_guard():
    # Router tools must refuse to be called via execute_tool.
    for router_tool in router.ROUTER_TOOL_NAMES:
        result = dispatcher.dispatch_tool(
            "execute_tool",
            {"tool_name": router_tool, "params": {}},
        )
        assert result["status"] == "error"
        assert "router tool" in result["message"].lower()


def test_execute_tool_direct_tool_still_works():
    # Direct tools are reachable via execute_tool too, with a usage hint.
    result = dispatcher.dispatch_tool(
        "execute_tool",
        {"tool_name": "get_capabilities", "params": {}},
    )
    assert result["status"] == "ok"
    assert "note" in result
    assert "direct tool" in result["note"]


def test_execute_tool_unknown():
    result = dispatcher.dispatch_tool(
        "execute_tool",
        {"tool_name": "does_not_exist", "params": {}},
    )
    assert result["status"] == "error"
    assert "Unknown tool" in result["message"]


def test_routed_tools_hidden_from_visible_list():
    visible_names = {t["name"] for t in dispatcher.TOOLS}
    for routed in router._routed_tool_names():
        assert routed not in visible_names, f"{routed} should be hidden"
