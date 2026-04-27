"""PCB-side validation tools (Phase 7): DRC, DFM profiles, silkscreen, test points."""

from __future__ import annotations

import json
import tempfile
from pathlib import Path
from typing import Any

from ..backends import _cli_error, _run_cli
from ..state import _pcb_file, _project_state


# ─────────────────────────────────────────────────────────────────────────────
# DFM (Design For Manufacturing) profiles
# ─────────────────────────────────────────────────────────────────────────────
#
# Each profile is a mapping of KiCad design-rule field names (as they appear
# under board.design_settings.rules in the .kicad_pro JSON) to the values that
# fab house enforces at its standard service tier. All distances are in mm.
#
# Sources (refresh annually — fabs change capabilities):
#   JLCPCB    https://jlcpcb.com/capabilities/pcb-capabilities
#   PCBWay    https://www.pcbway.com/capabilities.html
#   OSH Park  https://docs.oshpark.com/services/two-layer/
#
# These are deliberately the *standard* tier values — the cheap-and-fast
# default service. Advanced tiers (3.5 mil traces on JLC, 4 mil on PCBWay)
# are exposed via the `advanced=True` argument on each tool.

DFM_PROFILES: dict[str, dict[str, Any]] = {
    "jlcpcb": {
        "fab": "JLCPCB",
        "tier": "standard (2-layer or 4-layer)",
        "url": "https://jlcpcb.com/capabilities/pcb-capabilities",
        "rules": {
            "min_track_width": 0.127,                # 5 mil
            "min_clearance": 0.127,                  # 5 mil
            "min_via_diameter": 0.5,                 # 0.5 mm pad
            "min_through_hole_diameter": 0.3,        # 0.3 mm hole
            "min_via_annular_width": 0.13,           # 5 mil ring
            "min_copper_edge_clearance": 0.4,
            "min_hole_clearance": 0.25,
            "min_hole_to_hole": 0.5,
            "min_silk_clearance": 0.15,
            "solder_mask_to_copper_clearance": 0.1,
            "min_text_height": 0.8,
            "min_text_thickness": 0.15,
        },
    },
    "jlcpcb_advanced": {
        "fab": "JLCPCB",
        "tier": "advanced (3.5 mil)",
        "url": "https://jlcpcb.com/capabilities/pcb-capabilities",
        "rules": {
            "min_track_width": 0.0889,               # 3.5 mil
            "min_clearance": 0.0889,                 # 3.5 mil
            "min_via_diameter": 0.4,
            "min_through_hole_diameter": 0.2,
            "min_via_annular_width": 0.1,
            "min_copper_edge_clearance": 0.4,
            "min_hole_clearance": 0.2,
            "min_hole_to_hole": 0.4,
            "min_silk_clearance": 0.15,
            "solder_mask_to_copper_clearance": 0.1,
            "min_text_height": 0.8,
            "min_text_thickness": 0.15,
        },
    },
    "pcbway": {
        "fab": "PCBWay",
        "tier": "standard (6 mil)",
        "url": "https://www.pcbway.com/capabilities.html",
        "rules": {
            "min_track_width": 0.1524,               # 6 mil
            "min_clearance": 0.1524,                 # 6 mil
            "min_via_diameter": 0.4,
            "min_through_hole_diameter": 0.3,
            "min_via_annular_width": 0.13,
            "min_copper_edge_clearance": 0.5,
            "min_hole_clearance": 0.25,
            "min_hole_to_hole": 0.5,
            "min_silk_clearance": 0.15,
            "solder_mask_to_copper_clearance": 0.1,
            "min_text_height": 1.0,
            "min_text_thickness": 0.15,
        },
    },
    "pcbway_advanced": {
        "fab": "PCBWay",
        "tier": "advanced (4 mil)",
        "url": "https://www.pcbway.com/capabilities.html",
        "rules": {
            "min_track_width": 0.1016,               # 4 mil
            "min_clearance": 0.1016,
            "min_via_diameter": 0.3,
            "min_through_hole_diameter": 0.15,
            "min_via_annular_width": 0.1,
            "min_copper_edge_clearance": 0.5,
            "min_hole_clearance": 0.2,
            "min_hole_to_hole": 0.4,
            "min_silk_clearance": 0.15,
            "solder_mask_to_copper_clearance": 0.1,
            "min_text_height": 1.0,
            "min_text_thickness": 0.15,
        },
    },
    "oshpark": {
        "fab": "OSH Park",
        "tier": "two-layer service (6 mil)",
        "url": "https://docs.oshpark.com/services/two-layer/",
        "rules": {
            "min_track_width": 0.1524,               # 6 mil
            "min_clearance": 0.1524,                 # 6 mil
            "min_via_diameter": 0.61,                # 24 mil pad
            "min_through_hole_diameter": 0.33,       # 13 mil drill
            "min_via_annular_width": 0.18,           # 7 mil ring
            "min_copper_edge_clearance": 0.508,      # 20 mil
            "min_hole_clearance": 0.33,
            "min_hole_to_hole": 0.5,
            "min_silk_clearance": 0.15,
            "solder_mask_to_copper_clearance": 0.1,
            "min_text_height": 1.0,
            "min_text_thickness": 0.15,
        },
    },
    "oshpark_4layer": {
        "fab": "OSH Park",
        "tier": "four-layer service (5 mil)",
        "url": "https://docs.oshpark.com/services/four-layer/",
        "rules": {
            "min_track_width": 0.127,                # 5 mil
            "min_clearance": 0.127,                  # 5 mil
            "min_via_diameter": 0.508,               # 20 mil pad
            "min_through_hole_diameter": 0.254,      # 10 mil drill
            "min_via_annular_width": 0.127,          # 5 mil ring
            "min_copper_edge_clearance": 0.508,
            "min_hole_clearance": 0.254,
            "min_hole_to_hole": 0.4,
            "min_silk_clearance": 0.127,
            "solder_mask_to_copper_clearance": 0.1,
            "min_text_height": 1.0,
            "min_text_thickness": 0.15,
        },
    },
}


def _apply_dfm_profile(profile_name: str) -> dict:
    """Write a fab's design rules into the active project's .kicad_pro file.

    Returns a structured diff (old → new for each rule) so the caller can show
    the user exactly what changed. Idempotent: re-running with the same profile
    is a no-op-equivalent (writes the same values back).
    """
    pcb = _pcb_file()
    if not pcb:
        return {"status": "error", "message": "Call set_project(pcb_file=...) first."}

    profile = DFM_PROFILES.get(profile_name)
    if profile is None:
        return {
            "status": "error",
            "message": f"Unknown DFM profile {profile_name!r}.",
            "available_profiles": sorted(DFM_PROFILES),
        }

    pro_file = Path(pcb).with_suffix(".kicad_pro")
    if not pro_file.exists():
        return {"status": "error", "message": f"Project file not found: {pro_file}"}

    try:
        data = json.loads(pro_file.read_text())
    except (OSError, json.JSONDecodeError) as e:
        return {"status": "error", "message": f"Failed to parse {pro_file}: {e}"}

    rules = (
        data.setdefault("board", {})
            .setdefault("design_settings", {})
            .setdefault("rules", {})
    )

    diff: dict[str, dict[str, Any]] = {}
    for key, value in profile["rules"].items():
        old = rules.get(key, "not set")
        if old != value:
            rules[key] = value
            diff[key] = {"old": old, "new": value}

    try:
        pro_file.write_text(json.dumps(data, indent=2))
    except OSError as e:
        return {"status": "error", "message": f"Failed to write {pro_file}: {e}"}

    return {
        "status": "ok",
        "profile": profile_name,
        "fab": profile["fab"],
        "tier": profile["tier"],
        "url": profile["url"],
        "rules_changed": diff,
        "rules_unchanged_count": len(profile["rules"]) - len(diff),
        "file": str(pro_file),
        "note": (
            "Reload the PCB in KiCad and run run_drc to validate the design "
            "against the new rules. Existing tracks and vias that violate "
            "the tighter limits will surface as DRC errors."
        ),
    }


def dfm_apply_jlcpcb(advanced: bool = False) -> dict:
    """Apply JLCPCB DFM rules to the active project."""
    return _apply_dfm_profile("jlcpcb_advanced" if advanced else "jlcpcb")


def dfm_apply_pcbway(advanced: bool = False) -> dict:
    """Apply PCBWay DFM rules to the active project."""
    return _apply_dfm_profile("pcbway_advanced" if advanced else "pcbway")


def dfm_apply_oshpark(four_layer: bool = False) -> dict:
    """Apply OSH Park DFM rules to the active project."""
    return _apply_dfm_profile("oshpark_4layer" if four_layer else "oshpark")


# ─────────────────────────────────────────────────────────────────────────────
# DRC (now wired to honor `rules_preset` for fab-aware checks)
# ─────────────────────────────────────────────────────────────────────────────

_FAB_PRESETS = {"jlcpcb", "pcbway", "oshpark"}


def run_drc(rules_preset: str = "default") -> dict:
    """Run DRC via kicad-cli. Returns structured violations.

    If `rules_preset` matches a fab profile, the corresponding DFM rules are
    applied to the .kicad_pro file *before* running DRC, so violations reflect
    that fab's capabilities.
    """
    pcb = _pcb_file()
    if not pcb:
        return _stub_drc()

    applied_profile: dict | None = None
    if rules_preset in _FAB_PRESETS:
        applied_profile = _apply_dfm_profile(rules_preset)
        if applied_profile.get("status") != "ok":
            return applied_profile

    with tempfile.NamedTemporaryFile(suffix=".json", delete=False) as f:
        out = f.name

    rc, _stdout, stderr = _run_cli(
        "pcb", "drc",
        "--format", "json",
        "--severity-all",
        "--schematic-parity",
        "--output", out,
        pcb,
    )

    try:
        raw = json.loads(Path(out).read_text())
    except (json.JSONDecodeError, OSError):
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

    result = {
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
    if applied_profile is not None:
        result["dfm_profile_applied"] = {
            "fab": applied_profile["fab"],
            "tier": applied_profile["tier"],
            "rules_changed": applied_profile["rules_changed"],
        }
    return result


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
    "dfm_apply_jlcpcb":    dfm_apply_jlcpcb,
    "dfm_apply_pcbway":    dfm_apply_pcbway,
    "dfm_apply_oshpark":   dfm_apply_oshpark,
}


TOOL_SCHEMAS = [
    {
        "name": "run_drc",
        "description": (
            "Run Design Rule Check. Returns all violations with type (clearance, "
            "unconnected, courtyard, silkscreen, drill), location, and net names. "
            "When rules_preset is a fab name (jlcpcb / pcbway / oshpark), the fab's "
            "DFM rules are applied to the project before DRC runs, so violations "
            "reflect that fab's manufacturing capabilities."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "rules_preset": {
                    "type": "string",
                    "enum": ["default", "jlcpcb", "pcbway", "oshpark"],
                    "default": "default",
                    "description": "Apply fab-specific DFM rules before DRC, or 'default' to use the project's existing rules"
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
    {
        "name": "dfm_apply_jlcpcb",
        "description": (
            "Apply JLCPCB Design-For-Manufacturing rules to the active project's "
            ".kicad_pro file. Sets minimum trace/space, via, drill, annular ring, "
            "and edge-clearance values to JLCPCB's standard service tier. "
            "Use advanced=true for the 3.5 mil tier. Run run_drc afterwards to "
            "validate the existing design against the new rules."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "advanced": {
                    "type": "boolean",
                    "default": False,
                    "description": "Use advanced tier (3.5 mil traces) instead of standard (5 mil)."
                }
            }
        }
    },
    {
        "name": "dfm_apply_pcbway",
        "description": (
            "Apply PCBWay Design-For-Manufacturing rules to the active project's "
            ".kicad_pro file. Sets minimum trace/space, via, drill, annular ring, "
            "and edge-clearance values to PCBWay's standard tier (6 mil). Use "
            "advanced=true for the 4 mil tier. Run run_drc afterwards to validate."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "advanced": {
                    "type": "boolean",
                    "default": False,
                    "description": "Use advanced tier (4 mil traces) instead of standard (6 mil)."
                }
            }
        }
    },
    {
        "name": "dfm_apply_oshpark",
        "description": (
            "Apply OSH Park Design-For-Manufacturing rules to the active project's "
            ".kicad_pro file. Defaults to the two-layer service (6 mil traces, "
            "13 mil drill, 7 mil annular ring). Use four_layer=true for the "
            "four-layer service (5 mil). Run run_drc afterwards to validate."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "four_layer": {
                    "type": "boolean",
                    "default": False,
                    "description": "Use the four-layer service rules (5 mil) instead of two-layer (6 mil)."
                }
            }
        }
    },
]
