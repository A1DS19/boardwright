"""PCB-side validation tools (Phase 7): DRC, silkscreen text, test points."""

from __future__ import annotations

import json
import tempfile
from pathlib import Path

from ..backends import _cli_error, _run_cli
from ..state import _pcb_file, _project_state


def run_drc(rules_preset: str = "default") -> dict:
    """Run DRC via kicad-cli. Returns structured violations."""
    pcb = _pcb_file()
    if not pcb:
        return _stub_drc()

    with tempfile.NamedTemporaryFile(suffix=".json", delete=False) as f:
        out = f.name

    rc, stdout, stderr = _run_cli(
        "pcb", "drc",
        "--format", "json",
        "--severity-all",
        "--schematic-parity",
        "--output", out,
        pcb,
    )

    try:
        raw = json.loads(Path(out).read_text())
    except Exception:
        return _cli_error(stderr, rc)
    finally:
        Path(out).unlink(missing_ok=True)

    errors, warnings = [], []
    for v in raw.get("violations", []):
        sev = v.get("severity", "error").lower()
        items = v.get("items", [])
        pos = items[0].get("pos", {}) if items else {}
        entry = {
            "type": v.get("type", "unknown"),
            "severity": sev,
            "description": v.get("description", ""),
            "position_x": pos.get("x"),
            "position_y": pos.get("y"),
            "items": [i.get("description", "") for i in items],
        }
        (errors if sev == "error" else warnings).append(entry)

    unconnected = raw.get("unconnected_items", [])

    return {
        "status": "ok",
        "source": "kicad-cli",
        "pcb_file": pcb,
        "rules_preset": rules_preset,
        "error_count": len(errors),
        "warning_count": len(warnings),
        "unconnected_count": len(unconnected),
        "errors": errors,
        "warnings": warnings,
        "unconnected": unconnected,
        "all_clear": len(errors) == 0 and len(unconnected) == 0,
    }


def _stub_drc() -> dict:
    errors = []
    if not _project_state.get("board_outline"):
        errors.append({"type": "missing_outline", "severity": "error",
                       "description": "No board outline defined."})
    unplaced = set(_project_state["bom"].keys()) - set(_project_state["placements"].keys())
    for ref in unplaced:
        errors.append({"type": "unplaced_component", "severity": "error",
                       "description": f"{ref} has not been placed on the PCB."})
    return {
        "status": "ok", "source": "stub",
        "note": "Set pcb_file via set_project() to run real DRC",
        "error_count": len(errors), "warning_count": 0,
        "errors": errors, "all_clear": len(errors) == 0,
    }


def add_silkscreen_text(
    text: str,
    x_mm: float,
    y_mm: float,
    size_mm: float = 1.0,
    layer: str = "F.SilkS",
) -> dict:
    return {"status": "ok", "text": text, "x": x_mm, "y": y_mm, "layer": layer}


def add_test_point(
    net_name: str,
    x_mm: float,
    y_mm: float,
    layer: str = "F.Cu",
    pad_size_mm: float = 1.5,
) -> dict:
    _project_state["placements"][f"TP_{net_name}"] = {
        "x": x_mm, "y": y_mm, "rotation": 0, "layer": layer,
        "type": "test_point", "net": net_name,
    }
    return {"status": "ok", "net_name": net_name, "x": x_mm, "y": y_mm}


HANDLERS = {
    "run_drc":             run_drc,
    "add_silkscreen_text": add_silkscreen_text,
    "add_test_point":      add_test_point,
}


TOOL_SCHEMAS = [
    {
        "name": "run_drc",
        "description": (
            "Run Design Rule Check. Returns all violations with type (clearance, "
            "unconnected, courtyard, silkscreen, drill), location, and net names."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "rules_preset": {
                    "type": "string",
                    "enum": ["default", "jlcpcb", "pcbway", "oshpark"],
                    "default": "default",
                    "description": "Apply fab-specific DRC rules"
                }
            }
        }
    },
    {
        "name": "add_silkscreen_text",
        "description": "Add text to silkscreen layer (board name, version, date, warnings).",
        "input_schema": {
            "type": "object",
            "properties": {
                "text":    {"type": "string"},
                "x_mm":    {"type": "number"},
                "y_mm":    {"type": "number"},
                "size_mm": {"type": "number", "default": 1.0},
                "layer":   {
                    "type": "string",
                    "enum": ["F.SilkS", "B.SilkS"],
                    "default": "F.SilkS"
                }
            },
            "required": ["text", "x_mm", "y_mm"]
        }
    },
    {
        "name": "add_test_point",
        "description": "Add a test point pad on a net (for debugging and automated testing).",
        "input_schema": {
            "type": "object",
            "properties": {
                "net_name":    {"type": "string"},
                "x_mm":        {"type": "number"},
                "y_mm":        {"type": "number"},
                "layer":       {"type": "string", "enum": ["F.Cu", "B.Cu"], "default": "F.Cu"},
                "pad_size_mm": {"type": "number", "default": 1.5}
            },
            "required": ["net_name", "x_mm", "y_mm"]
        }
    },
]
