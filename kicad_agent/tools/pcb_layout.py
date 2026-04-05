"""PCB layout tools (Phase 4) + copper pour zones (Phase 5)."""

from __future__ import annotations

import json
import tempfile
from pathlib import Path

from ..backends import _kicad, _run_cli
from ..state import _pcb_file, _project_state


def set_board_outline(
    width_mm: float,
    height_mm: float,
    corner_radius_mm: float = 1.0,
    origin_x_mm: float = 0,
    origin_y_mm: float = 0,
) -> dict:
    _project_state["board_outline"] = {
        "width": width_mm, "height": height_mm,
        "corner_radius": corner_radius_mm,
        "origin_x": origin_x_mm, "origin_y": origin_y_mm,
    }
    return {
        "status": "ok",
        "board_area_mm2": round(width_mm * height_mm, 2),
        "outline": _project_state["board_outline"],
    }


def add_mounting_holes(
    drill_mm: float = 3.2,
    pad_mm: float = 6.0,
    positions: str = "corners",
    corner_offset_mm: float = 3.5,
) -> dict:
    outline = _project_state.get("board_outline")
    if not outline:
        return {"status": "error", "message": "Set board outline before adding mounting holes."}
    w, h = outline["width"], outline["height"]
    d = corner_offset_mm
    hole_positions = [
        {"ref": "H1", "x": d,   "y": d},
        {"ref": "H2", "x": w-d, "y": d},
        {"ref": "H3", "x": w-d, "y": h-d},
        {"ref": "H4", "x": d,   "y": h-d},
    ]
    for hp in hole_positions:
        _project_state["placements"][hp["ref"]] = {
            "x": hp["x"], "y": hp["y"],
            "rotation": 0, "layer": "F.Cu",
            "drill_mm": drill_mm, "pad_mm": pad_mm,
        }
    return {"status": "ok", "holes_added": 4, "positions": hole_positions}


def place_footprint(
    reference: str,
    x_mm: float,
    y_mm: float,
    rotation_deg: float = 0,
    layer: str = "F.Cu",
) -> dict:
    """
    Move a footprint to the given position via kipy IPC.
    KiCad must be running with the PCB open. Falls back to in-memory stub if not.
    """
    try:
        kicad = _kicad()
        from kipy.geometry import Vector2, Angle
        from kipy.board_types import BoardLayer

        board = kicad.get_board()

        fps = board.get_footprints()
        fp = next(
            (f for f in fps if f.reference_field.text.value == reference),
            None,
        )
        if fp is None:
            return {"status": "error", "message": f"Footprint '{reference}' not found on board."}

        old_pos = fp.position
        fp.position = Vector2.from_xy_mm(x_mm, y_mm)
        fp.orientation = Angle.from_degrees(rotation_deg)
        fp.layer = BoardLayer.BL_B_Cu if layer == "B.Cu" else BoardLayer.BL_F_Cu

        board.update_items(fp)
        board.save()

        return {
            "status": "ok",
            "source": "kipy",
            "reference": reference,
            "x_mm": x_mm,
            "y_mm": y_mm,
            "rotation_deg": rotation_deg,
            "layer": layer,
            "from": {
                "x_mm": old_pos.x / 1_000_000,
                "y_mm": old_pos.y / 1_000_000,
            },
        }

    except ImportError:
        pass
    except Exception as e:
        if "connect" in str(e).lower() or "socket" in str(e).lower():
            return {
                "status": "error",
                "message": "KiCad is not running. Open the PCB in KiCad then retry.",
            }
        return {"status": "error", "message": f"kipy error: {e}"}

    # Stub fallback
    _project_state["placements"][reference] = {
        "x": x_mm, "y": y_mm, "rotation": rotation_deg, "layer": layer,
    }
    return {
        "status": "ok",
        "source": "stub",
        "note": "KiCad not running — open PCB in KiCad for live placement",
        "reference": reference,
        "x_mm": x_mm,
        "y_mm": y_mm,
    }


def get_ratsnest(net_filter: str | None = None) -> dict:
    """Return nets and unconnected count via kipy IPC."""
    try:
        kicad = _kicad()
        board = kicad.get_board()
        nets = board.get_nets()

        net_list = [
            {"name": n.name, "net_code": n.net_code}
            for n in nets
            if not net_filter or net_filter.lower() in n.name.lower()
        ]

        unconnected_count = None
        pcb = _pcb_file()
        if pcb:
            with tempfile.NamedTemporaryFile(suffix=".json", delete=False) as f:
                out = f.name
            rc, _, _ = _run_cli("pcb", "drc", "--format", "json",
                                 "--severity-error", "--output", out, pcb)
            try:
                raw = json.loads(Path(out).read_text())
                unconnected_count = len(raw.get("unconnected_items", []))
            except Exception:
                pass
            finally:
                Path(out).unlink(missing_ok=True)

        return {
            "status": "ok",
            "source": "kipy",
            "net_count": len(net_list),
            "unconnected_count": unconnected_count,
            "nets": net_list,
        }

    except ImportError:
        pass
    except Exception as e:
        if "connect" in str(e).lower() or "socket" in str(e).lower():
            return {
                "status": "error",
                "message": "KiCad is not running. Open the PCB in KiCad then retry.",
            }
        return {"status": "error", "message": f"kipy error: {e}"}

    # Stub fallback
    placed = set(_project_state["placements"].keys())
    unplaced = set(_project_state["bom"].keys()) - placed
    return {
        "status": "ok",
        "source": "stub",
        "note": "KiCad not running — open PCB in KiCad for live ratsnest",
        "unconnected_count": None,
        "unplaced_components": list(unplaced),
        "nets": [],
    }


def add_keepout_zone(
    outline_mm: list[list[float]],
    no_copper: bool = True,
    no_vias: bool = True,
    no_footprints: bool = False,
    reason: str = "",
) -> dict:
    _project_state["zones"].append({
        "type": "keepout",
        "outline_mm": outline_mm,
        "no_copper": no_copper,
        "no_vias": no_vias,
        "no_footprints": no_footprints,
        "reason": reason,
    })
    return {"status": "ok", "reason": reason}


def add_zone(
    net_name: str,
    layer: str,
    outline_mm: list[list[float]],
    clearance_mm: float = 0.3,
    min_width_mm: float = 0.25,
    fill_mode: str = "solid",
    priority: int = 0,
) -> dict:
    _project_state["zones"].append({
        "type": "copper",
        "net_name": net_name,
        "layer": layer,
        "outline_mm": outline_mm,
        "clearance_mm": clearance_mm,
        "min_width_mm": min_width_mm,
        "fill_mode": fill_mode,
        "priority": priority,
        "filled": False,
    })
    return {"status": "ok", "net_name": net_name, "layer": layer}


def fill_zones() -> dict:
    """Refill all copper zones via kipy IPC."""
    try:
        kicad = _kicad()
        board = kicad.get_board()
        board.refill_zones()
        board.save()

        zone_count = len(board.get_zones())
        return {"status": "ok", "source": "kipy", "zones_filled": zone_count}

    except ImportError:
        pass
    except Exception as e:
        if "connect" in str(e).lower() or "socket" in str(e).lower():
            return {
                "status": "error",
                "message": "KiCad is not running. Open the PCB in KiCad then retry.",
            }
        return {"status": "error", "message": f"kipy error: {e}"}

    # Stub fallback
    filled = sum(1 for z in _project_state["zones"] if z.get("type") == "copper")
    for z in _project_state["zones"]:
        if z.get("type") == "copper":
            z["filled"] = True
    return {"status": "ok", "source": "stub",
            "note": "KiCad not running — zone fill recorded in memory only",
            "zones_filled": filled}


HANDLERS = {
    "set_board_outline":  set_board_outline,
    "add_mounting_holes": add_mounting_holes,
    "place_footprint":    place_footprint,
    "get_ratsnest":       get_ratsnest,
    "add_keepout_zone":   add_keepout_zone,
    "add_zone":           add_zone,
    "fill_zones":         fill_zones,
}


TOOL_SCHEMAS = [
    {
        "name": "set_board_outline",
        "description": "Define the PCB board outline (Edge.Cuts layer).",
        "input_schema": {
            "type": "object",
            "properties": {
                "width_mm":             {"type": "number"},
                "height_mm":            {"type": "number"},
                "corner_radius_mm":     {"type": "number", "default": 1.0},
                "origin_x_mm":          {"type": "number", "default": 0},
                "origin_y_mm":          {"type": "number", "default": 0}
            },
            "required": ["width_mm", "height_mm"]
        }
    },
    {
        "name": "add_mounting_holes",
        "description": "Add mounting holes at standard positions (corners or custom).",
        "input_schema": {
            "type": "object",
            "properties": {
                "drill_mm":         {"type": "number", "default": 3.2},
                "pad_mm":           {"type": "number", "default": 6.0},
                "positions":        {
                    "type": "string",
                    "enum": ["corners", "custom"],
                    "default": "corners"
                },
                "corner_offset_mm": {"type": "number", "default": 3.5}
            }
        }
    },
    {
        "name": "place_footprint",
        "description": "Place a component footprint at exact coordinates on the PCB.",
        "input_schema": {
            "type": "object",
            "properties": {
                "reference":    {"type": "string"},
                "x_mm":         {"type": "number"},
                "y_mm":         {"type": "number"},
                "rotation_deg": {"type": "number", "default": 0},
                "layer":        {"type": "string", "enum": ["F.Cu", "B.Cu"], "default": "F.Cu"}
            },
            "required": ["reference", "x_mm", "y_mm"]
        }
    },
    {
        "name": "get_ratsnest",
        "description": (
            "Return the current ratsnest (list of unconnected nets with their endpoints). "
            "Use to plan routing order and check completeness."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "net_filter": {
                    "type": "string",
                    "description": "Optional: filter by net name pattern"
                }
            }
        }
    },
    {
        "name": "add_keepout_zone",
        "description": "Add a keep-out zone (no copper, no vias, no components).",
        "input_schema": {
            "type": "object",
            "properties": {
                "outline_mm": {
                    "type": "array",
                    "description": "List of [x, y] corner coordinates in mm",
                    "items": {"type": "array", "items": {"type": "number"}}
                },
                "no_copper":     {"type": "boolean", "default": True},
                "no_vias":       {"type": "boolean", "default": True},
                "no_footprints": {"type": "boolean", "default": False},
                "reason":        {
                    "type": "string",
                    "description": "e.g. 'Antenna keep-out', 'Mechanical clearance'"
                }
            },
            "required": ["outline_mm"]
        }
    },
    {
        "name": "add_zone",
        "description": "Add a copper pour zone on a specific layer.",
        "input_schema": {
            "type": "object",
            "properties": {
                "net_name":     {"type": "string"},
                "layer":        {
                    "type": "string",
                    "enum": ["F.Cu", "B.Cu", "In1.Cu", "In2.Cu"]
                },
                "outline_mm":   {
                    "type": "array",
                    "description": (
                        "Corner coordinates. "
                        "Pass [[0,0],[w,0],[w,h],[0,h]] for full board."
                    ),
                    "items": {"type": "array", "items": {"type": "number"}}
                },
                "clearance_mm": {"type": "number", "default": 0.3},
                "min_width_mm": {"type": "number", "default": 0.25},
                "fill_mode":    {"type": "string", "enum": ["solid", "hatched"], "default": "solid"},
                "priority":     {"type": "integer", "default": 0}
            },
            "required": ["net_name", "layer", "outline_mm"]
        }
    },
    {
        "name": "fill_zones",
        "description": "Execute copper pour fill on all defined zones.",
        "input_schema": {"type": "object", "properties": {}}
    },
]
