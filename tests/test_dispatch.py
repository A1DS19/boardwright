"""
Smoke test: call every registered tool via dispatch_tool with empty args.

Goal is not functional correctness — it's to guarantee that
  (a) no handler raises an unhandled exception under the fake backend,
  (b) every handler returns a JSON-serializable dict with a "status" key.

dispatch_tool() catches TypeError and other exceptions and converts them to
{"status": "error", ...}, so missing required args are fine for this smoke pass.
"""

from __future__ import annotations

import json

import pytest

from kicad_agent import dispatcher


@pytest.mark.parametrize("tool_name", sorted(dispatcher.ALL_HANDLERS))
def test_dispatch_smoke(tool_name):
    result = dispatcher.dispatch_tool(tool_name, {})
    assert isinstance(result, dict), f"{tool_name} returned {type(result).__name__}, not dict"
    assert "status" in result, f"{tool_name} response missing 'status': {result}"
    assert result["status"] in ("ok", "error"), (
        f"{tool_name} returned unexpected status: {result['status']}"
    )
    # Must be JSON-serializable so the MCP layer can ship it back.
    json.dumps(result)


def test_unknown_tool_returns_error():
    result = dispatcher.dispatch_tool("this_tool_does_not_exist", {})
    assert result["status"] == "error"
    assert "Unknown tool" in result["message"]


def test_set_project_roundtrip(tmp_path):
    pcb = tmp_path / "x.kicad_pcb"
    pcb.write_text("")
    result = dispatcher.dispatch_tool("set_project", {"pcb_file": str(pcb)})
    assert result["status"] == "ok"

    from kicad_agent import state
    assert state._pcb_file() == str(pcb)
