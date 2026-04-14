"""Schematic-capture tools (Phase 2) + ERC validation.

ERC lives here because it reads from _sch_file() and shares _stub_erc with
the schematic in-memory state. Conceptually it's validation, but structurally
it's coupled to schematic state.
"""

from __future__ import annotations

import json
import tempfile
from pathlib import Path

from ..backends import _cli_error, _run_cli
from ..schematic_io import (
    _append_to_sch,
    _label_sexp,
    _lib_sym_pins,
    _no_connect_sexp,
    _parse_sch_file,
    _place_symbol,
    _resolve_pin_endpoint,
    _sch_lib_symbols,
    _sch_placed_symbols,
    _transform_pin,
    _wire_sexp,
)
from ..state import _project_state, _sch_file


def create_schematic_sheet(
    sheet_name: str,
    sheet_number: int,
    title: str,
    revision: str = "v1.0",
) -> dict:
    _project_state["sheets"][sheet_name] = {
        "number": sheet_number,
        "title": title,
        "revision": revision,
        "symbols": [],
        "wires": [],
        "labels": [],
        "no_connects": [],
    }
    return {"status": "ok", "sheet_name": sheet_name, "sheet_number": sheet_number}


def add_symbol(
    library: str,
    symbol: str,
    reference: str,
    value: str,
    x: float,
    y: float,
    sheet: str,
    rotation: float = 0,
    mirror_x: bool = False,
) -> dict:
    sch = _sch_file()
    if sch:
        err = _place_symbol(sch, library, symbol, reference, value, x, y, rotation, mirror_x)
        if err:
            return {"status": "error", "message": err}
        _project_state["bom"][reference] = {"value": value, "library": library, "symbol": symbol}
        return {
            "status": "ok",
            "source": "kicad_sch",
            "reference": reference,
            "lib_id": f"{library}:{symbol}",
            "sheet": sheet,
        }

    # In-memory fallback when no sch_file is set
    if sheet not in _project_state["sheets"]:
        return {"status": "error", "message": f"Sheet '{sheet}' not found. Create it first."}
    _project_state["sheets"][sheet]["symbols"].append({
        "library": library, "symbol": symbol,
        "reference": reference, "value": value,
        "x": x, "y": y, "rotation": rotation, "mirror_x": mirror_x,
    })
    _project_state["bom"][reference] = {"value": value, "library": library, "symbol": symbol}
    return {"status": "ok", "source": "stub", "reference": reference, "sheet": sheet}


def add_power_symbol(net_name: str, x: float, y: float, sheet: str) -> dict:
    if sheet not in _project_state["sheets"]:
        return {"status": "error", "message": f"Sheet '{sheet}' not found."}
    _project_state["sheets"][sheet]["symbols"].append({
        "library": "power", "symbol": net_name,
        "reference": f"#{net_name}", "value": net_name,
        "x": x, "y": y, "rotation": 0, "mirror_x": False,
    })
    return {"status": "ok", "net_name": net_name, "sheet": sheet}


def connect_pins(
    from_ref: str, from_pin: str,
    to_ref: str, to_pin: str,
    sheet: str,
) -> dict:
    sch = _sch_file()
    if sch:
        try:
            p1 = _resolve_pin_endpoint(sch, from_ref, from_pin)
            if p1 is None:
                return {
                    "status": "error",
                    "message": f"Pin '{from_pin}' not found on '{from_ref}'. "
                               "Use get_pin_positions to verify pin names/numbers.",
                }
            p2 = _resolve_pin_endpoint(sch, to_ref, to_pin)
            if p2 is None:
                return {
                    "status": "error",
                    "message": f"Pin '{to_pin}' not found on '{to_ref}'. "
                               "Use get_pin_positions to verify pin names/numbers.",
                }
            x1, y1 = p1
            x2, y2 = p2
            sexp = ""
            if abs(x1 - x2) < 0.001:
                sexp = _wire_sexp(x1, y1, x2, y2)
            elif abs(y1 - y2) < 0.001:
                sexp = _wire_sexp(x1, y1, x2, y2)
            else:
                sexp = _wire_sexp(x1, y1, x2, y1) + _wire_sexp(x2, y1, x2, y2)
            _append_to_sch(sch, sexp)
            return {
                "status": "ok",
                "source": "kicad_sch",
                "from": {"ref": from_ref, "pin": from_pin, "x": x1, "y": y1},
                "to":   {"ref": to_ref,   "pin": to_pin,   "x": x2, "y": y2},
                "segments_written": 1 if abs(x1 - x2) < 0.001 or abs(y1 - y2) < 0.001 else 2,
            }
        except (OSError, ValueError) as e:
            return {"status": "error", "message": f"Failed to write wire: {e}"}

    # In-memory fallback (no sch_file set)
    if sheet not in _project_state["sheets"]:
        return {"status": "error", "message": f"Sheet '{sheet}' not found."}
    _project_state["sheets"][sheet]["wires"].append({
        "from_ref": from_ref, "from_pin": from_pin,
        "to_ref": to_ref, "to_pin": to_pin,
    })
    return {"status": "ok", "source": "stub",
            "note": "Set sch_file via set_project() to write wires to disk."}


def add_net_label(
    net_name: str,
    sheet: str,
    snap_to_ref: str | None = None,
    snap_to_pin: str | None = None,
    x: float | None = None,
    y: float | None = None,
    rotation: float = 0,
) -> dict:
    sch = _sch_file()

    lx, ly = x, y
    if snap_to_ref and snap_to_pin:
        if sch:
            pos = _resolve_pin_endpoint(sch, snap_to_ref, snap_to_pin)
            if pos is None:
                return {
                    "status": "error",
                    "message": f"Pin '{snap_to_pin}' not found on '{snap_to_ref}'. "
                               "Use get_pin_positions to check available pins.",
                }
            lx, ly = pos
        else:
            if sheet not in _project_state["sheets"]:
                return {"status": "error", "message": f"Sheet '{sheet}' not found."}
            _project_state["sheets"][sheet]["labels"].append(
                {"net_name": net_name, "snap_to_ref": snap_to_ref,
                 "snap_to_pin": snap_to_pin, "rotation": rotation}
            )
            return {
                "status": "ok", "source": "stub",
                "note": "Set sch_file via set_project() to snap to real pin coordinates.",
                "snapped_to": f"{snap_to_ref}:{snap_to_pin}",
            }

    if lx is None or ly is None:
        return {"status": "error", "message": "Provide either snap_to_ref+snap_to_pin or explicit x,y."}

    if sch:
        try:
            _append_to_sch(sch, _label_sexp(net_name, lx, ly, rotation))
        except (OSError, ValueError) as e:
            return {"status": "error", "message": f"Failed to write label: {e}"}
        return {"status": "ok", "source": "kicad_sch",
                "net_name": net_name, "x": lx, "y": ly, "rotation": rotation}

    if sheet not in _project_state["sheets"]:
        return {"status": "error", "message": f"Sheet '{sheet}' not found."}
    _project_state["sheets"][sheet]["labels"].append(
        {"net_name": net_name, "x": lx, "y": ly, "rotation": rotation}
    )
    return {"status": "ok", "source": "stub",
            "net_name": net_name, "x": lx, "y": ly}


def add_no_connect(reference: str, pin: str, sheet: str) -> dict:
    sch = _sch_file()
    if sch:
        pos = _resolve_pin_endpoint(sch, reference, pin)
        if pos is None:
            return {
                "status": "error",
                "message": f"Pin '{pin}' not found on '{reference}'. "
                           "Use get_pin_positions to check available pins.",
            }
        try:
            _append_to_sch(sch, _no_connect_sexp(pos[0], pos[1]))
        except (OSError, ValueError) as e:
            return {"status": "error", "message": f"Failed to write no-connect: {e}"}
        return {"status": "ok", "source": "kicad_sch",
                "reference": reference, "pin": pin, "x": pos[0], "y": pos[1]}

    if sheet not in _project_state["sheets"]:
        return {"status": "error", "message": f"Sheet '{sheet}' not found."}
    _project_state["sheets"][sheet]["no_connects"].append(
        {"reference": reference, "pin": pin}
    )
    return {"status": "ok", "source": "stub",
            "note": "Set sch_file via set_project() to write no-connect to disk."}


def remove_no_connect(reference: str, pin: str, sheet: str) -> dict:
    if sheet not in _project_state["sheets"]:
        return {"status": "error", "message": f"Sheet '{sheet}' not found."}
    nc_list = _project_state["sheets"][sheet]["no_connects"]
    before = len(nc_list)
    _project_state["sheets"][sheet]["no_connects"] = [
        nc for nc in nc_list
        if not (nc["reference"] == reference and nc["pin"] == pin)
    ]
    removed = before - len(_project_state["sheets"][sheet]["no_connects"])
    if removed == 0:
        return {"status": "error", "message": f"No no-connect marker found for {reference}:{pin}."}
    return {"status": "ok", "removed": removed, "reference": reference, "pin": pin}


def get_pin_positions(reference: str, sheet: str) -> dict:
    """
    Return all pin endpoints in schematic coordinates.
    """
    sch = _sch_file()
    if sch:
        try:
            tree = _parse_sch_file(sch)
            placed = _sch_placed_symbols(tree)
            lib_syms = _sch_lib_symbols(tree)

            sym_info = placed.get(reference)
            if not sym_info:
                return {"status": "error", "message": f"Symbol '{reference}' not found in {sch}."}
            lib_sym = lib_syms.get(sym_info["lib_id"])
            if not lib_sym:
                return {
                    "status": "error",
                    "message": (
                        f"Lib symbol '{sym_info['lib_id']}' not found in lib_symbols. "
                        "It may be defined in an external .kicad_sym file."
                    ),
                }

            raw_pins = _lib_sym_pins(lib_sym, lib_syms)
            pins_out = []
            for p in raw_pins:
                sx, sy = _transform_pin(
                    p["x"], p["y"],
                    sym_info["x"], sym_info["y"],
                    sym_info["rotation"],
                    sym_info["mirror_x"], sym_info["mirror_y"],
                )
                pins_out.append({
                    "pin_name": p["name"],
                    "pin_number": p["number"],
                    "sch_x": sx,
                    "sch_y": sy,
                })
            return {
                "status": "ok",
                "source": "kicad_sch",
                "reference": reference,
                "placement": {
                    "x": sym_info["x"], "y": sym_info["y"],
                    "rotation": sym_info["rotation"],
                    "mirror_x": sym_info["mirror_x"],
                    "mirror_y": sym_info["mirror_y"],
                },
                "coordinate_space": "schematic (Y-inversion applied)",
                "pins": pins_out,
            }
        except (OSError, ValueError) as e:
            return {"status": "error", "message": f"Failed to read schematic: {e}"}

    # In-memory fallback
    sheet_data = _project_state["sheets"].get(sheet)
    if not sheet_data:
        return {"status": "error", "message": f"Sheet '{sheet}' not found."}
    symbol = next(
        (s for s in sheet_data["symbols"] if s["reference"] == reference), None
    )
    if not symbol:
        return {"status": "error", "message": f"Symbol '{reference}' not found on sheet '{sheet}'."}
    return {
        "status": "ok",
        "source": "stub",
        "note": "Set sch_file via set_project() for real pin positions.",
        "reference": reference,
        "placement": {"x": symbol["x"], "y": symbol["y"], "rotation": symbol.get("rotation", 0)},
        "coordinate_space": "schematic (Y-inversion applied)",
        "pins": [],
    }


def move_symbol(
    reference: str,
    x: float,
    y: float,
    sheet: str,
    rotation: float | None = None,
) -> dict:
    sheet_data = _project_state["sheets"].get(sheet)
    if not sheet_data:
        return {"status": "error", "message": f"Sheet '{sheet}' not found."}
    symbol = next(
        (s for s in sheet_data["symbols"] if s["reference"] == reference), None
    )
    if not symbol:
        return {"status": "error", "message": f"Symbol '{reference}' not found on sheet '{sheet}'."}
    old = {"x": symbol["x"], "y": symbol["y"], "rotation": symbol.get("rotation", 0)}
    symbol["x"] = x
    symbol["y"] = y
    if rotation is not None:
        symbol["rotation"] = rotation
    return {"status": "ok", "reference": reference, "from": old, "to": {"x": x, "y": y}}


def move_label(
    net_name: str,
    sheet: str,
    snap_to_ref: str | None = None,
    snap_to_pin: str | None = None,
    x: float | None = None,
    y: float | None = None,
    rotation: float | None = None,
) -> dict:
    sheet_data = _project_state["sheets"].get(sheet)
    if not sheet_data:
        return {"status": "error", "message": f"Sheet '{sheet}' not found."}
    label = next(
        (lb for lb in sheet_data["labels"] if lb["net_name"] == net_name), None
    )
    if not label:
        return {"status": "error", "message": f"Label '{net_name}' not found on sheet '{sheet}'."}

    if snap_to_ref and snap_to_pin:
        label["snap_to_ref"] = snap_to_ref
        label["snap_to_pin"] = snap_to_pin
        if rotation is not None:
            label["rotation"] = rotation
        return {
            "status": "ok", "net_name": net_name,
            "snapped_to": f"{snap_to_ref}:{snap_to_pin}",
            "note": "STUB — pin endpoint will be resolved in real implementation",
        }

    if x is None or y is None:
        return {"status": "error", "message": "Provide either snap_to_ref+snap_to_pin or explicit x,y."}

    label["x"] = x
    label["y"] = y
    if rotation is not None:
        label["rotation"] = rotation
    return {"status": "ok", "net_name": net_name, "x": x, "y": y}


def assign_footprint(reference: str, footprint_path: str) -> dict:
    _project_state["footprints"][reference] = footprint_path
    if reference in _project_state["bom"]:
        _project_state["bom"][reference]["footprint"] = footprint_path
    return {"status": "ok", "reference": reference, "footprint": footprint_path}


def run_erc(scope: str = "all") -> dict:
    """Run ERC via kicad-cli. Returns structured violations with suggested fixes."""
    sch = _sch_file()
    if not sch:
        return _stub_erc(scope)

    with tempfile.NamedTemporaryFile(suffix=".json", delete=False) as f:
        out = f.name

    rc, stdout, stderr = _run_cli(
        "sch", "erc",
        "--format", "json",
        "--severity-all",
        "--output", out,
        sch,
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
        ref = items[0].get("description", "") if items else ""
        pos = items[0].get("pos", {}) if items else {}
        entry = {
            "type": v.get("type", "unknown"),
            "severity": sev,
            "symbol_ref": ref,
            "pin_name": items[1].get("description", "") if len(items) > 1 else None,
            "position_x": pos.get("x"),
            "position_y": pos.get("y"),
            "description": v.get("description", ""),
            "suggested_fix": _erc_suggested_fix(v),
        }
        (errors if sev == "error" else warnings).append(entry)

    return {
        "status": "ok",
        "source": "kicad-cli",
        "sch_file": sch,
        "error_count": len(errors),
        "warning_count": len(warnings),
        "all_clear": len(errors) == 0,
        "errors": errors,
        "warnings": warnings,
    }


def _erc_suggested_fix(v: dict) -> str:
    t = v.get("type", "")
    desc = v.get("description", "")
    if "dangling" in t or "dangling" in desc.lower():
        return "Use snap_label_to_pin or move_label with snap_to_ref+snap_to_pin to connect the label to the nearest pin endpoint."
    if "unconnected" in t:
        return "Add a net label, wire, or no-connect marker to this pin."
    if "power_flag" in t or "PWR_FLAG" in desc:
        return "Add a PWR_FLAG symbol to this power net."
    if "duplicate" in t:
        return "Renumber the duplicate reference designator."
    return desc


def _stub_erc(scope: str) -> dict:
    """In-memory stub ERC used when no sch_file is set."""
    errors, warnings = [], []
    for ref in _project_state["bom"]:
        if ref not in _project_state["footprints"]:
            warnings.append({
                "type": "missing_footprint", "severity": "warning",
                "symbol_ref": ref, "pin_name": None,
                "position_x": None, "position_y": None,
                "suggested_fix": f"Call assign_footprint(reference='{ref}', footprint_path='...')",
            })
    for sheet_data in _project_state["sheets"].values():
        for label in sheet_data.get("labels", []):
            if "snap_to_ref" in label and "x" not in label:
                errors.append({
                    "type": "label_dangling", "severity": "error",
                    "symbol_ref": label.get("snap_to_ref"),
                    "pin_name": label.get("snap_to_pin"),
                    "position_x": None, "position_y": None,
                    "suggested_fix": (
                        f"Resolve pin endpoint for {label['snap_to_ref']}:{label['snap_to_pin']} "
                        f"and snap label '{label['net_name']}' there."
                    ),
                })
    return {
        "status": "ok", "source": "stub",
        "note": "Set sch_file via set_project() to run real ERC",
        "error_count": len(errors), "warning_count": len(warnings),
        "errors": errors, "warnings": warnings,
    }


HANDLERS = {
    "create_schematic_sheet": create_schematic_sheet,
    "add_symbol":             add_symbol,
    "add_power_symbol":       add_power_symbol,
    "connect_pins":           connect_pins,
    "add_net_label":          add_net_label,
    "add_no_connect":         add_no_connect,
    "remove_no_connect":      remove_no_connect,
    "get_pin_positions":      get_pin_positions,
    "move_symbol":            move_symbol,
    "move_label":             move_label,
    "assign_footprint":       assign_footprint,
    "run_erc":                run_erc,
}


TOOL_SCHEMAS = [
    {
        "name": "create_schematic_sheet",
        "description": "Create a new schematic sheet in the KiCad project.",
        "input_schema": {
            "type": "object",
            "properties": {
                "sheet_name": {"type": "string"},
                "sheet_number": {"type": "integer"},
                "title": {"type": "string"},
                "revision": {"type": "string", "default": "v1.0"}
            },
            "required": ["sheet_name", "sheet_number", "title"]
        }
    },
    {
        "name": "add_symbol",
        "description": "Add a schematic symbol to a sheet.",
        "input_schema": {
            "type": "object",
            "properties": {
                "library":    {"type": "string"},
                "symbol":     {"type": "string"},
                "reference":  {"type": "string", "description": "e.g. U1, R5, C12, J3"},
                "value":      {"type": "string"},
                "x":          {"type": "number"},
                "y":          {"type": "number"},
                "rotation":   {"type": "number", "default": 0},
                "mirror_x":   {"type": "boolean", "default": False},
                "sheet":      {"type": "string"}
            },
            "required": ["library", "symbol", "reference", "value", "x", "y", "sheet"]
        }
    },
    {
        "name": "add_power_symbol",
        "description": "Add a power net symbol (VCC, GND, etc.) to the schematic.",
        "input_schema": {
            "type": "object",
            "properties": {
                "net_name": {
                    "type": "string",
                    "description": "e.g. '+3V3', 'GND', '+5V', 'VBUS', 'AGND', 'PGND'"
                },
                "x":     {"type": "number"},
                "y":     {"type": "number"},
                "sheet": {"type": "string"}
            },
            "required": ["net_name", "x", "y", "sheet"]
        }
    },
    {
        "name": "connect_pins",
        "description": "Draw a wire connecting two component pins in the schematic.",
        "input_schema": {
            "type": "object",
            "properties": {
                "from_ref":  {"type": "string"},
                "from_pin":  {"type": "string", "description": "Pin number or name"},
                "to_ref":    {"type": "string"},
                "to_pin":    {"type": "string"},
                "sheet":     {"type": "string"}
            },
            "required": ["from_ref", "from_pin", "to_ref", "to_pin", "sheet"]
        }
    },
    {
        "name": "add_net_label",
        "description": (
            "Add a named net label. Preferred: pass snap_to_ref + snap_to_pin to place "
            "the label exactly at a pin endpoint (no coordinate math needed). "
            "Falls back to explicit x/y when snap targets are not provided."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "net_name":    {"type": "string"},
                "sheet":       {"type": "string"},
                "snap_to_ref": {"type": "string", "description": "Symbol reference to snap to, e.g. 'U2'"},
                "snap_to_pin": {"type": "string", "description": "Pin name or number to snap to, e.g. 'LRCLK'"},
                "x":           {"type": "number", "description": "Explicit X (schematic coords). Used only when snap not provided."},
                "y":           {"type": "number", "description": "Explicit Y (schematic coords). Used only when snap not provided."},
                "rotation":    {"type": "number", "default": 0}
            },
            "required": ["net_name", "sheet"]
        }
    },
    {
        "name": "add_no_connect",
        "description": "Add a no-connect marker (X) to an unconnected pin.",
        "input_schema": {
            "type": "object",
            "properties": {
                "reference": {"type": "string"},
                "pin":       {"type": "string"},
                "sheet":     {"type": "string"}
            },
            "required": ["reference", "pin", "sheet"]
        }
    },
    {
        "name": "remove_no_connect",
        "description": (
            "Remove a no-connect marker from a pin. "
            "Use before connecting a pin that was previously marked no-connect."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "reference": {"type": "string"},
                "pin":       {"type": "string"},
                "sheet":     {"type": "string"}
            },
            "required": ["reference", "pin", "sheet"]
        }
    },
    {
        "name": "get_pin_positions",
        "description": (
            "Return all pin endpoints for a symbol in schematic coordinates. "
            "All positions account for symbol placement, rotation, mirroring, and "
            "the KiCad Y-axis inversion — callers always receive schematic-space coords. "
            "Use this before placing net labels or wires to avoid off-by-grid errors."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "reference": {"type": "string", "description": "Symbol reference, e.g. 'U2'"},
                "sheet":     {"type": "string"}
            },
            "required": ["reference", "sheet"]
        }
    },
    {
        "name": "move_symbol",
        "description": "Move a placed symbol to a new position on the schematic sheet.",
        "input_schema": {
            "type": "object",
            "properties": {
                "reference": {"type": "string"},
                "x":         {"type": "number"},
                "y":         {"type": "number"},
                "sheet":     {"type": "string"},
                "rotation":  {"type": "number", "description": "New rotation in degrees. Omit to keep current."}
            },
            "required": ["reference", "x", "y", "sheet"]
        }
    },
    {
        "name": "move_label",
        "description": (
            "Move an existing net label to a new position or snap it to a pin endpoint. "
            "Preferred: pass snap_to_ref + snap_to_pin to eliminate label_dangling ERC errors."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "net_name":    {"type": "string"},
                "sheet":       {"type": "string"},
                "snap_to_ref": {"type": "string", "description": "Snap to this symbol's pin endpoint"},
                "snap_to_pin": {"type": "string"},
                "x":           {"type": "number", "description": "Explicit X. Used only when snap not provided."},
                "y":           {"type": "number"},
                "rotation":    {"type": "number"}
            },
            "required": ["net_name", "sheet"]
        }
    },
    {
        "name": "assign_footprint",
        "description": "Assign a PCB footprint to a schematic symbol.",
        "input_schema": {
            "type": "object",
            "properties": {
                "reference":      {"type": "string"},
                "footprint_path": {
                    "type": "string",
                    "description": "e.g. 'Package_SO:SOIC-8_3.9x4.9mm_P1.27mm'"
                }
            },
            "required": ["reference", "footprint_path"]
        }
    },
    {
        "name": "run_erc",
        "description": (
            "Run Electrical Rules Check. Returns structured violations: "
            "{type, severity, symbol_ref, pin_name, position_x, position_y, suggested_fix}. "
            "Types include: pin_unconnected, label_dangling, duplicate_ref, missing_power_flag, "
            "bus_entry_conflict. Use suggested_fix to resolve each error programmatically."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "scope": {
                    "type": "string",
                    "enum": ["all", "current_sheet"],
                    "default": "all"
                }
            }
        }
    },
]
