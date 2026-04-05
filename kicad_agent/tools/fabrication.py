"""Fabrication output tools (Phase 8): Gerbers, drill files, BOM, pick-and-place, 3D."""

from __future__ import annotations

from pathlib import Path

from ..backends import _cli_error, _run_cli
from ..state import _pcb_file, _sch_file


def generate_gerbers(
    output_dir: str = "./gerbers",
    layer_count: int | None = None,
    format: str = "gerber_x2",
) -> dict:
    """Generate Gerber files via kicad-cli. Requires set_project(pcb_file=...)."""
    pcb = _pcb_file()
    if not pcb:
        return {"status": "error", "message": "Call set_project(pcb_file=...) first."}

    Path(output_dir).mkdir(parents=True, exist_ok=True)

    layers = "F.Cu,B.Cu,F.SilkS,B.SilkS,F.Mask,B.Mask,F.Paste,B.Paste,Edge.Cuts,F.Fab,B.Fab,F.Courtyard,B.Courtyard"
    if layer_count and layer_count >= 4:
        layers = "F.Cu,In1.Cu,In2.Cu,B.Cu,F.SilkS,B.SilkS,F.Mask,B.Mask,F.Paste,B.Paste,Edge.Cuts,F.Fab,B.Fab"

    args = ["pcb", "export", "gerbers", "--output", output_dir, "--layers", layers]
    if format == "gerber_x1":
        args.append("--no-x2")
    args.append(pcb)

    rc, stdout, stderr = _run_cli(*args)
    if rc != 0:
        return _cli_error(stderr, rc)

    files = [f.name for f in Path(output_dir).iterdir() if f.suffix in (".gbr", ".gtl", ".gbl")]
    return {
        "status": "ok",
        "source": "kicad-cli",
        "output_dir": str(Path(output_dir).resolve()),
        "files_written": len(files),
        "files": sorted(files),
    }


def generate_drill_files(
    output_dir: str = "./gerbers",
    format: str = "excellon",
    merge_pth_npth: bool = False,
) -> dict:
    """Generate drill files via kicad-cli. Requires set_project(pcb_file=...)."""
    pcb = _pcb_file()
    if not pcb:
        return {"status": "error", "message": "Call set_project(pcb_file=...) first."}

    Path(output_dir).mkdir(parents=True, exist_ok=True)

    args = ["pcb", "export", "drill", "--output", output_dir, "--format", format]
    if not merge_pth_npth:
        args.append("--excellon-separate-th")
    args.append(pcb)

    rc, stdout, stderr = _run_cli(*args)
    if rc != 0:
        return _cli_error(stderr, rc)

    files = [f.name for f in Path(output_dir).iterdir() if f.suffix in (".drl", ".xln")]
    return {
        "status": "ok",
        "source": "kicad-cli",
        "output_dir": str(Path(output_dir).resolve()),
        "files_written": len(files),
        "files": sorted(files),
    }


def generate_bom(
    output_path: str | None = None,
    include_prices: bool = True,
    quantity_for_price: int = 10,
    distributors: list[str] | None = None,
) -> dict:
    """Generate BOM via kicad-cli sch export bom. Requires set_project(sch_file=...)."""
    sch = _sch_file()
    if not sch:
        return {"status": "error", "message": "Call set_project(sch_file=...) first."}

    out = output_path or str(Path(sch).parent / "bom.csv")

    rc, stdout, stderr = _run_cli(
        "sch", "export", "bom",
        "--output", out,
        "--fields", "Reference,Value,Footprint,${QUANTITY},Manufacturer,MPN,${DNP}",
        "--labels", "Refs,Value,Footprint,Qty,Manufacturer,MPN,DNP",
        "--group-by", "Value,Footprint",
        "--sort-field", "Reference",
        "--exclude-dnp",
        sch,
    )
    if rc != 0:
        return _cli_error(stderr, rc)

    return {
        "status": "ok",
        "source": "kicad-cli",
        "output_path": out,
        "note": "Pricing/MPN data must be filled in the schematic fields or via a distributor API.",
    }


def generate_position_file(
    output_path: str | None = None,
    units: str = "mm",
    side: str = "both",
) -> dict:
    """Generate pick-and-place position file via kicad-cli."""
    pcb = _pcb_file()
    if not pcb:
        return {"status": "error", "message": "Call set_project(pcb_file=...) first."}

    out = output_path or str(Path(pcb).parent / "positions.csv")

    rc, stdout, stderr = _run_cli(
        "pcb", "export", "pos",
        "--output", out,
        "--format", "csv",
        "--units", units,
        "--side", side,
        "--exclude-dnp",
        pcb,
    )
    if rc != 0:
        return _cli_error(stderr, rc)

    return {
        "status": "ok",
        "source": "kicad-cli",
        "output_path": out,
        "units": units,
        "side": side,
    }


def generate_3d_model(
    output_path: str | None = None,
    format: str = "step",
) -> dict:
    """Export 3D model via kicad-cli."""
    pcb = _pcb_file()
    if not pcb:
        return {"status": "error", "message": "Call set_project(pcb_file=...) first."}

    out = output_path or str(Path(pcb).with_suffix(f".{format}"))

    subcommand = "vrml" if format == "wrl" else "step"
    rc, stdout, stderr = _run_cli(
        "pcb", "export", subcommand,
        "--output", out,
        "--force",
        pcb,
    )
    if rc != 0:
        return _cli_error(stderr, rc)

    return {
        "status": "ok",
        "source": "kicad-cli",
        "output_path": out,
        "format": format,
    }


HANDLERS = {
    "generate_gerbers":       generate_gerbers,
    "generate_drill_files":   generate_drill_files,
    "generate_bom":           generate_bom,
    "generate_position_file": generate_position_file,
    "generate_3d_model":      generate_3d_model,
}


TOOL_SCHEMAS = [
    {
        "name": "generate_gerbers",
        "description": "Generate all Gerber files for PCB fabrication.",
        "input_schema": {
            "type": "object",
            "properties": {
                "output_dir":  {"type": "string", "default": "./gerbers"},
                "layer_count": {"type": "integer", "enum": [2, 4, 6]},
                "format":      {
                    "type": "string",
                    "enum": ["gerber_x2", "gerber_x1"],
                    "default": "gerber_x2"
                }
            },
            "required": ["output_dir"]
        }
    },
    {
        "name": "generate_drill_files",
        "description": "Generate Excellon drill files (PTH and NPTH).",
        "input_schema": {
            "type": "object",
            "properties": {
                "output_dir":     {"type": "string", "default": "./gerbers"},
                "format":         {
                    "type": "string",
                    "enum": ["excellon", "gerber_x2"],
                    "default": "excellon"
                },
                "merge_pth_npth": {"type": "boolean", "default": False}
            }
        }
    },
    {
        "name": "generate_bom",
        "description": "Generate Bill of Materials CSV with distributor part numbers and pricing.",
        "input_schema": {
            "type": "object",
            "properties": {
                "output_path":        {"type": "string"},
                "include_prices":     {"type": "boolean", "default": True},
                "quantity_for_price": {"type": "integer", "default": 10},
                "distributors":       {
                    "type": "array",
                    "items": {"type": "string"},
                    "default": ["Mouser", "Digi-Key"]
                }
            }
        }
    },
    {
        "name": "generate_position_file",
        "description": "Generate SMT pick-and-place position file.",
        "input_schema": {
            "type": "object",
            "properties": {
                "output_path": {"type": "string"},
                "units":       {"type": "string", "enum": ["mm", "in"], "default": "mm"},
                "side":        {"type": "string", "enum": ["top", "bottom", "both"], "default": "both"}
            }
        }
    },
    {
        "name": "generate_3d_model",
        "description": "Export 3D STEP model of the populated PCB for mechanical review.",
        "input_schema": {
            "type": "object",
            "properties": {
                "output_path": {"type": "string"},
                "format":      {"type": "string", "enum": ["step", "wrl"], "default": "step"}
            }
        }
    },
]
