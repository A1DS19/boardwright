"""
KiCad AI Design Agent — Tool Definitions

All tools used by the agent across every design phase.
Replace the stub dispatcher in dispatcher.py with your real KiCad IPC bridge.
"""

TOOLS = [

    # ═══════════════════════════════════════════════════════
    # FILESYSTEM — read local project files
    # ═══════════════════════════════════════════════════════

    {
        "name": "list_directory",
        "description": (
            "List files and subdirectories at a given path. "
            "Use this to explore the user's project folder before reading files."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "path": {
                    "type": "string",
                    "description": "Absolute or relative directory path, e.g. 'mcu/' or '/home/dev/projects/medi-pal/pcbs/mcu'"
                }
            },
            "required": ["path"]
        }
    },

    {
        "name": "read_file",
        "description": (
            "Read the contents of a local file. Use for KiCad schematic files "
            "(.kicad_sch), PCB files (.kicad_pcb), datasheets (.pdf text layer), "
            "text notes, netlists, or any other project file."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "path": {
                    "type": "string",
                    "description": "Absolute or relative file path"
                },
                "max_bytes": {
                    "type": "integer",
                    "default": 65536,
                    "description": "Maximum bytes to read (default 64KB). Increase for large files."
                }
            },
            "required": ["path"]
        }
    },

    # ═══════════════════════════════════════════════════════
    # PHASE 0-1: RESEARCH & VALIDATION
    # ═══════════════════════════════════════════════════════

    {
        "name": "search_components",
        "description": (
            "Search Octopart and Mouser for real, in-stock components matching a "
            "functional description. Returns MPN, manufacturer, package, price, "
            "availability, and KiCad footprint hint. Use to build the BOM."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "Functional description, e.g. '3.3V LDO 500mA SOT-23-5'"
                },
                "package": {
                    "type": "string",
                    "description": "Preferred package, e.g. 'SOT-23', '0402', 'QFN-16'"
                },
                "max_results": {"type": "integer", "default": 5},
                "in_stock_only": {"type": "boolean", "default": True},
                "preferred_distributors": {
                    "type": "array",
                    "items": {"type": "string"},
                    "default": ["Mouser", "Digi-Key"]
                }
            },
            "required": ["query"]
        }
    },

    {
        "name": "get_datasheet",
        "description": (
            "Fetch and parse the datasheet for a given MPN. Returns: pin diagram, "
            "application schematic, recommended footprint, absolute max ratings, "
            "and any layout recommendations from the datasheet."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "mpn": {"type": "string"},
                "manufacturer": {"type": "string"}
            },
            "required": ["mpn"]
        }
    },

    {
        "name": "verify_kicad_footprint",
        "description": (
            "Check if a footprint exists in the installed KiCad standard libraries "
            "or project-local library. Returns the full library path if found, "
            "or a list of close matches if exact match not found."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "library": {"type": "string", "description": "e.g. 'Package_SO'"},
                "footprint": {"type": "string", "description": "e.g. 'SOIC-8_3.9x4.9mm_P1.27mm'"}
            },
            "required": ["library", "footprint"]
        }
    },

    {
        "name": "generate_custom_footprint",
        "description": (
            "Generate a KiCad footprint (.kicad_mod) from datasheet land pattern "
            "dimensions. Use when verify_kicad_footprint returns no match."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "reference": {"type": "string"},
                "package_type": {
                    "type": "string",
                    "enum": ["SMD", "THT", "QFN", "BGA", "DFN", "SOT", "SOIC", "TO", "custom"]
                },
                "pad_count": {"type": "integer"},
                "pitch_mm": {"type": "number"},
                "body_width_mm": {"type": "number"},
                "body_height_mm": {"type": "number"},
                "pad_width_mm": {"type": "number"},
                "pad_height_mm": {"type": "number"},
                "courtyard_margin_mm": {"type": "number", "default": 0.5}
            },
            "required": ["reference", "package_type", "pad_count"]
        }
    },

    {
        "name": "impedance_calc",
        "description": (
            "Calculate trace width for a target impedance given the PCB stackup. "
            "Use for USB (90Ω diff), RF (50Ω single-ended), or any controlled-impedance trace."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "target_impedance_ohm": {"type": "number"},
                "trace_type": {
                    "type": "string",
                    "enum": ["microstrip", "stripline", "coplanar_waveguide", "differential"]
                },
                "layer": {"type": "string", "description": "e.g. 'F.Cu', 'In1.Cu'"},
                "dielectric_thickness_mm": {"type": "number", "default": 0.2},
                "dielectric_constant": {"type": "number", "default": 4.5},
                "copper_thickness_mm": {"type": "number", "default": 0.035}
            },
            "required": ["target_impedance_ohm", "trace_type"]
        }
    },

    # ═══════════════════════════════════════════════════════
    # PHASE 2: SCHEMATIC
    # ═══════════════════════════════════════════════════════

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

    # ═══════════════════════════════════════════════════════
    # PHASE 4: PCB LAYOUT
    # ═══════════════════════════════════════════════════════

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

    # ═══════════════════════════════════════════════════════
    # PHASE 5: COPPER POURS
    # ═══════════════════════════════════════════════════════

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

    # ═══════════════════════════════════════════════════════
    # PHASE 6: ROUTING
    # ═══════════════════════════════════════════════════════

    {
        "name": "route_trace",
        "description": "Route a copper trace segment between two pads or points.",
        "input_schema": {
            "type": "object",
            "properties": {
                "net_name":  {"type": "string"},
                "from_pad":  {"type": "string", "description": "e.g. 'U1:VCC' or coordinate"},
                "to_pad":    {"type": "string"},
                "width_mm":  {"type": "number"},
                "layer":     {
                    "type": "string",
                    "enum": ["F.Cu", "B.Cu", "In1.Cu", "In2.Cu"]
                },
                "via_at":    {
                    "type": "array",
                    "description": "Optional: add a via at this [x, y] midpoint to change layers",
                    "items": {"type": "number"}
                }
            },
            "required": ["net_name", "from_pad", "to_pad", "width_mm", "layer"]
        }
    },

    {
        "name": "route_differential_pair",
        "description": "Route a differential pair with matched length and controlled spacing.",
        "input_schema": {
            "type": "object",
            "properties": {
                "net_positive":  {"type": "string"},
                "net_negative":  {"type": "string"},
                "from_ref":      {"type": "string"},
                "to_ref":        {"type": "string"},
                "width_mm":      {"type": "number"},
                "spacing_mm":    {"type": "number"},
                "layer":         {"type": "string"},
                "max_skew_mm":   {"type": "number", "default": 0.1}
            },
            "required": [
                "net_positive", "net_negative",
                "from_ref", "to_ref",
                "width_mm", "spacing_mm"
            ]
        }
    },

    {
        "name": "add_via",
        "description": "Add a via to transition a net between layers.",
        "input_schema": {
            "type": "object",
            "properties": {
                "net_name":   {"type": "string"},
                "x_mm":       {"type": "number"},
                "y_mm":       {"type": "number"},
                "drill_mm":   {"type": "number", "default": 0.4},
                "pad_mm":     {"type": "number", "default": 0.8},
                "from_layer": {"type": "string"},
                "to_layer":   {"type": "string"}
            },
            "required": ["net_name", "x_mm", "y_mm"]
        }
    },

    # ═══════════════════════════════════════════════════════
    # PHASE 7: VALIDATION
    # ═══════════════════════════════════════════════════════

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

    # ═══════════════════════════════════════════════════════
    # PHASE 8: FABRICATION OUTPUTS
    # ═══════════════════════════════════════════════════════

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
