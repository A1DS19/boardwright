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
    try:
        kicad = _kicad()
        from kipy import board_types as bt
        from kipy.geometry import Vector2
        import math

        board = kicad.get_board()
        edge = bt.BoardLayer.BL_Edge_Cuts

        ox, oy = origin_x_mm, origin_y_mm
        w, h, r = width_mm, height_mm, max(0.0, corner_radius_mm)
        r = min(r, w / 2, h / 2)

        def seg(x1, y1, x2, y2):
            s = bt.BoardSegment()
            s.start = Vector2.from_xy_mm(x1, y1)
            s.end = Vector2.from_xy_mm(x2, y2)
            s.layer = edge
            return s

        def arc(cx, cy, sx, sy, ex, ey):
            # mid at 45° between start-angle and end-angle around center
            a1 = math.atan2(sy - cy, sx - cx)
            a2 = math.atan2(ey - cy, ex - cx)
            # pick shorter sweep
            d = a2 - a1
            while d > math.pi: d -= 2 * math.pi
            while d < -math.pi: d += 2 * math.pi
            am = a1 + d / 2
            a = bt.BoardArc()
            a.start = Vector2.from_xy_mm(sx, sy)
            a.mid = Vector2.from_xy_mm(cx + r * math.cos(am), cy + r * math.sin(am))
            a.end = Vector2.from_xy_mm(ex, ey)
            a.layer = edge
            return a

        items = []
        if r == 0:
            items += [
                seg(ox, oy,     ox + w, oy),
                seg(ox + w, oy, ox + w, oy + h),
                seg(ox + w, oy + h, ox, oy + h),
                seg(ox, oy + h, ox, oy),
            ]
        else:
            items += [
                seg(ox + r, oy,         ox + w - r, oy),
                seg(ox + w, oy + r,     ox + w,     oy + h - r),
                seg(ox + w - r, oy + h, ox + r,     oy + h),
                seg(ox, oy + h - r,     ox,         oy + r),
                arc(ox + w - r, oy + r,       ox + w - r, oy,        ox + w, oy + r),
                arc(ox + w - r, oy + h - r,   ox + w, oy + h - r,    ox + w - r, oy + h),
                arc(ox + r, oy + h - r,       ox + r, oy + h,        ox, oy + h - r),
                arc(ox + r, oy + r,           ox, oy + r,            ox + r, oy),
            ]

        board.create_items(items)
        board.save()

        _project_state["board_outline"] = {
            "width": w, "height": h, "corner_radius": r,
            "origin_x": ox, "origin_y": oy,
        }
        return {
            "status": "ok", "source": "kipy",
            "board_area_mm2": round(w * h, 2),
            "segments_created": len(items),
            "note": "Outline added to Edge.Cuts. Re-calling stacks extra shapes — delete existing outline in pcbnew first.",
        }

    except ImportError:
        pass
    except Exception as e:
        if "connect" in str(e).lower() or "socket" in str(e).lower():
            return {"status": "error",
                    "message": "KiCad IPC unavailable. Ensure: (1) KiCad main app is open, (2) the .kicad_pcb is open in the PCB Editor window, (3) Preferences → Plugins → 'Enable KiCad API' is checked (restart KiCad if you just enabled it)."}
        return {"status": "error", "message": f"kipy error: {e}"}

    _project_state["board_outline"] = {
        "width": width_mm, "height": height_mm,
        "corner_radius": corner_radius_mm,
        "origin_x": origin_x_mm, "origin_y": origin_y_mm,
    }
    return {
        "status": "ok", "source": "stub",
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
                "message": "KiCad IPC unavailable. Ensure: (1) KiCad main app is open, (2) the .kicad_pcb is open in the PCB Editor window, (3) Preferences → Plugins → 'Enable KiCad API' is checked (restart KiCad if you just enabled it).",
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
                "message": "KiCad IPC unavailable. Ensure: (1) KiCad main app is open, (2) the .kicad_pcb is open in the PCB Editor window, (3) Preferences → Plugins → 'Enable KiCad API' is checked (restart KiCad if you just enabled it).",
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
                "message": "KiCad IPC unavailable. Ensure: (1) KiCad main app is open, (2) the .kicad_pcb is open in the PCB Editor window, (3) Preferences → Plugins → 'Enable KiCad API' is checked (restart KiCad if you just enabled it).",
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


def sync_pcb_from_schematic() -> dict:
    """
    Trigger "Update PCB from Schematic" in the open PCB Editor via kipy.run_action.
    Equivalent to pressing F8 in pcbnew. Requires the PCB Editor window to be open.
    Uses kipy's unstable run_action API — action name may change across KiCad versions.
    """
    try:
        kicad = _kicad()
        result = kicad.run_action("pcbnew.EditorControl.updatePcbFromSchematic")
        return {"status": "ok", "source": "kipy", "run_action_result": str(result),
                "note": "KiCad may show a confirmation dialog that requires manual acknowledgement."}
    except ImportError:
        return {"status": "error", "message": "kipy not installed."}
    except Exception as e:
        if "connect" in str(e).lower() or "socket" in str(e).lower():
            return {"status": "error",
                    "message": "KiCad IPC unavailable. Ensure: (1) KiCad main app is open, (2) the .kicad_pcb is open in the PCB Editor window, (3) Preferences → Plugins → 'Enable KiCad API' is checked (restart KiCad if you just enabled it)."}
        return {"status": "error",
                "message": f"run_action failed: {e}. Fallback: press F8 in pcbnew manually."}


def save_board() -> dict:
    """Save the currently open PCB via kipy IPC."""
    try:
        kicad = _kicad()
        board = kicad.get_board()
        board.save()
        return {"status": "ok", "source": "kipy"}
    except ImportError:
        return {"status": "error", "message": "kipy not installed — cannot save board."}
    except Exception as e:
        if "connect" in str(e).lower() or "socket" in str(e).lower():
            return {"status": "error",
                    "message": "KiCad IPC unavailable. Ensure: (1) KiCad main app is open, (2) the .kicad_pcb is open in the PCB Editor window, (3) Preferences → Plugins → 'Enable KiCad API' is checked (restart KiCad if you just enabled it)."}
        return {"status": "error", "message": f"kipy error: {e}"}


def get_pad_positions(reference: str) -> dict:
    """Return absolute pad positions for a placed footprint on the PCB."""
    try:
        kicad = _kicad()
        import math
        board = kicad.get_board()
        fp = next((f for f in board.get_footprints()
                   if f.reference_field.text.value == reference), None)
        if fp is None:
            return {"status": "error", "message": f"Footprint '{reference}' not found on board."}

        theta = fp.orientation.degrees * math.pi / 180.0
        cos_t, sin_t = math.cos(theta), math.sin(theta)
        fp_x, fp_y = fp.position.x, fp.position.y

        pads = []
        for pad in fp.pads:
            lx, ly = pad.position.x, pad.position.y
            ax = fp_x + (lx * cos_t - ly * sin_t)
            ay = fp_y + (lx * sin_t + ly * cos_t)
            pads.append({
                "number": pad.number,
                "net": pad.net.name if pad.net else "",
                "x_mm": round(ax / 1_000_000, 4),
                "y_mm": round(ay / 1_000_000, 4),
            })

        return {
            "status": "ok", "source": "kipy",
            "reference": reference,
            "footprint_position_mm": {
                "x": round(fp_x / 1_000_000, 4),
                "y": round(fp_y / 1_000_000, 4),
                "rotation_deg": fp.orientation.degrees,
            },
            "pads": pads,
        }

    except ImportError:
        return {"status": "error", "message": "kipy not installed."}
    except Exception as e:
        if "connect" in str(e).lower() or "socket" in str(e).lower():
            return {"status": "error",
                    "message": "KiCad IPC unavailable. Ensure: (1) KiCad main app is open, (2) the .kicad_pcb is open in the PCB Editor window, (3) Preferences → Plugins → 'Enable KiCad API' is checked (restart KiCad if you just enabled it)."}
        return {"status": "error", "message": f"kipy error: {e}"}


HANDLERS = {
    "set_board_outline":  set_board_outline,
    "add_mounting_holes": add_mounting_holes,
    "place_footprint":    place_footprint,
    "get_ratsnest":       get_ratsnest,
    "add_keepout_zone":   add_keepout_zone,
    "add_zone":           add_zone,
    "fill_zones":         fill_zones,
    "save_board":         save_board,
    "get_pad_positions":  get_pad_positions,
    "sync_pcb_from_schematic": sync_pcb_from_schematic,
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
    {
        "name": "save_board",
        "description": "Save the currently open PCB to disk via KiCad IPC. Use after placements/routes to persist changes.",
        "input_schema": {"type": "object", "properties": {}}
    },
    {
        "name": "sync_pcb_from_schematic",
        "description": "Push schematic netlist to the open PCB (equivalent to pressing F8 in pcbnew). Uses kipy run_action — KiCad may show a dialog. Call before place_footprint when footprints/nets are missing.",
        "input_schema": {"type": "object", "properties": {}}
    },
    {
        "name": "get_pad_positions",
        "description": "Return absolute pad positions (x_mm, y_mm) and connected net for every pad of a footprint on the PCB. Accounts for footprint rotation. Use before route_trace to get real coordinates.",
        "input_schema": {
            "type": "object",
            "properties": {
                "reference": {"type": "string", "description": "e.g. R1, U3, BT1"}
            },
            "required": ["reference"]
        }
    },
]
