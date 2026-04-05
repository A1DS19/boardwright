"""Project setup + DRC rule-tuning tools."""

from __future__ import annotations

import json
import os
import shutil
from pathlib import Path

from .. import backends
from ..state import _pcb_file, _project_state


def set_drc_severity(rule_type: str, severity: str) -> dict:
    """
    Change a rule_severities entry in the .kicad_pro file.
    Edits the JSON in place — safe to call multiple times.
    """
    pcb = _pcb_file()
    if not pcb:
        return {"status": "error", "message": "Call set_project(pcb_file=...) first."}

    pro_file = Path(pcb).with_suffix(".kicad_pro")
    if not pro_file.exists():
        return {"status": "error", "message": f"Project file not found: {pro_file}"}

    try:
        data = json.loads(pro_file.read_text())
        severities = data.setdefault("board", {}).setdefault(
            "design_settings", {}
        ).setdefault("rule_severities", {})

        old = severities.get(rule_type, "not set")
        severities[rule_type] = severity
        pro_file.write_text(json.dumps(data, indent=2))

        return {
            "status": "ok",
            "rule_type": rule_type,
            "old_severity": old,
            "new_severity": severity,
            "file": str(pro_file),
        }
    except Exception as e:
        return {"status": "error", "message": str(e)}


def add_drc_exclusion(
    reference: str,
    rule_types: list[str],
    reason: str = "",
) -> dict:
    """
    Write a custom rule to the .kicad_dru file that ignores specific DRC
    checks for a named footprint reference.
    """
    pcb = _pcb_file()
    if not pcb:
        return {"status": "error", "message": "Call set_project(pcb_file=...) first."}

    dru_file = Path(pcb).with_suffix(".kicad_dru")

    lines = []
    if reason:
        lines.append(f"# {reason}")
    for rule_type in rule_types:
        rule_name = f"exclude_{rule_type}_{reference}".replace(" ", "_")
        lines.append(f"(rule \"{rule_name}\"")
        lines.append(f"  (severity ignore)")
        lines.append(f"  (condition \"A.Reference == '{reference}' || B.Reference == '{reference}'\")")
        lines.append(f"  (constraint {rule_type})")
        lines.append(f")")
        lines.append("")

    block = "\n".join(lines)

    try:
        existing = dru_file.read_text() if dru_file.exists() else ""
        dru_file.write_text(existing + ("\n" if existing and not existing.endswith("\n") else "") + block)
        return {
            "status": "ok",
            "reference": reference,
            "rule_types": rule_types,
            "dru_file": str(dru_file),
            "note": "Reload the PCB in KiCad (or run DRC again) to apply.",
        }
    except Exception as e:
        return {"status": "error", "message": str(e)}


def set_project(
    pcb_file: str | None = None,
    sch_file: str | None = None,
) -> dict:
    """Store the active project file paths for this session."""
    if pcb_file:
        p = Path(pcb_file).expanduser().resolve()
        if not p.exists():
            return {"status": "error", "message": f"PCB file not found: {p}"}
        _project_state["pcb_file"] = str(p)
    if sch_file:
        s = Path(sch_file).expanduser().resolve()
        if not s.exists():
            return {"status": "error", "message": f"Schematic file not found: {s}"}
        _project_state["sch_file"] = str(s)
    return {
        "status": "ok",
        "pcb_file": _project_state["pcb_file"],
        "sch_file": _project_state["sch_file"],
    }


def get_capabilities() -> dict:
    """Report runtime capabilities and current project context."""
    # kicad-cli probe honours FAKE_BACKENDS by hiding the binary
    kicad_cli_path = None if backends._fake_backends() else shutil.which("kicad-cli")

    kipy_available, kipy_import_error = backends._probe_kipy()

    pcb_file = _project_state.get("pcb_file")
    sch_file = _project_state.get("sch_file")

    return {
        "status": "ok",
        "server": "kicad",
        "active_project": {
            "pcb_file": pcb_file,
            "sch_file": sch_file,
            "pcb_file_exists": bool(pcb_file and Path(pcb_file).exists()),
            "sch_file_exists": bool(sch_file and Path(sch_file).exists()),
        },
        "backends": {
            "kicad_cli": {
                "available": bool(kicad_cli_path),
                "path": kicad_cli_path,
                "used_for": ["run_erc", "run_drc", "generate_* exports"],
            },
            "kipy_ipc": {
                "available": kipy_available,
                "socket_env": os.environ.get("KICAD_API_SOCKET"),
                "used_for": ["place_footprint", "get_ratsnest", "fill_zones"],
                "import_error": kipy_import_error,
            },
            "schematic_file_editing": {
                "available": bool(sch_file and Path(sch_file).exists()),
                "used_for": ["connect_pins", "add_net_label", "add_no_connect", "get_pin_positions"],
            },
            "stub_fallback": {
                "available": True,
                "note": "Used when real backend is unavailable for a tool.",
            },
        },
    }


HANDLERS = {
    "set_project":       set_project,
    "get_capabilities":  get_capabilities,
    "set_drc_severity":  set_drc_severity,
    "add_drc_exclusion": add_drc_exclusion,
}


TOOL_SCHEMAS = [
    {
        "name": "set_project",
        "description": (
            "Set the active KiCad project files for this session. "
            "Must be called before any tool that reads or writes a real KiCad file. "
            "Accepts paths to the .kicad_pcb and/or .kicad_sch files."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "pcb_file": {
                    "type": "string",
                    "description": "Absolute path to the .kicad_pcb file"
                },
                "sch_file": {
                    "type": "string",
                    "description": "Absolute path to the root .kicad_sch file"
                }
            }
        }
    },
    {
        "name": "get_capabilities",
        "description": (
            "Report runtime capabilities and active project context. "
            "Use this first to see which backends are available (kicad-cli, kipy IPC), "
            "and whether pcb_file/sch_file are set."
        ),
        "input_schema": {
            "type": "object",
            "properties": {}
        }
    },
    {
        "name": "set_drc_severity",
        "description": (
            "Change the severity of a DRC rule type in the project's .kicad_pro file. "
            "Use to suppress false positives from module footprints (e.g. castellated "
            "ESP32 pads triggering solder_mask_bridge or drill_out_of_range). "
            "Valid severities: error, warning, ignore. "
            "Valid rule types match KiCad's rule_severities keys, e.g.: "
            "solder_mask_bridge, clearance, drill_out_of_range, annular_width, "
            "footprint_symbol_mismatch, missing_courtyard, silk_over_copper."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "rule_type": {
                    "type": "string",
                    "description": "DRC rule name, e.g. 'solder_mask_bridge'"
                },
                "severity": {
                    "type": "string",
                    "enum": ["error", "warning", "ignore"],
                    "description": "New severity level"
                }
            },
            "required": ["rule_type", "severity"]
        }
    },
    {
        "name": "add_drc_exclusion",
        "description": (
            "Add a custom design rule to the project's .kicad_dru file that exempts "
            "a specific footprint reference from one or more DRC checks. "
            "Use for known false positives scoped to a single component "
            "(e.g. U1 ESP32 module internal geometry). "
            "More precise than set_drc_severity since it applies only to the named reference."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "reference": {
                    "type": "string",
                    "description": "Footprint reference to exclude, e.g. 'U1'"
                },
                "rule_types": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "List of DRC rule types to ignore for this reference, e.g. ['solder_mask_bridge', 'drill_out_of_range']"
                },
                "reason": {
                    "type": "string",
                    "description": "Human-readable reason, written as a comment in the .kicad_dru file"
                }
            },
            "required": ["reference", "rule_types"]
        }
    },
]
