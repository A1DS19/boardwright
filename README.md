# KiCad AI Project Creator

An MCP server that gives Claude Code 41 KiCad design tools across the full PCB
workflow. Once installed, the tools are available in every Claude Code session
on your machine — open Claude from any directory and just describe what you want
to build.

No API key needed. Uses Claude Code directly.

## Setup

Clone and run the setup script once:

```bash
git clone https://github.com/your-username/kicad-ai-project-creator
cd kicad-ai-project-creator
./setup.sh
```

This installs project dependencies (`mcp`, `kicad-python`, etc.) and registers the server globally with
Claude Code (`--scope user`), so it's available from any directory.

---

## Running

Open Claude Code from anywhere:

```bash
claude
```

Verify the server is connected:

```
/mcp
```

You should see `kicad` listed as an active server. All 41 tools are then
available in every message — just describe what you want to design.

---

## Usage

Chat naturally from any directory:

```
Design a USB-C rechargeable LED controller for 4 channels of RGB LED strips,
controlled via smartphone over BLE.
```

```
Industrial temperature and humidity data logger. Battery powered with
2-year life target. Logs to onboard flash every 5 minutes.
Syncs over LoRaWAN when in range. IP67 enclosure, -20°C to 60°C.
```

```
Review my MCU schematic in mcu/ and finish the wiring —
read the datasheets in mcu/datasheets/ first.
```

---

## Tools

| Phase | Tools |
|-------|-------|
| Runtime / Project | `set_project`, `get_capabilities`, `set_drc_severity`, `add_drc_exclusion` |
| Research | `search_components`, `get_datasheet`, `verify_kicad_footprint`, `generate_custom_footprint`, `impedance_calc` |
| Schematic | `create_schematic_sheet`, `add_symbol`, `add_power_symbol`, `connect_pins`, `add_net_label`, `add_no_connect`, `remove_no_connect`, `get_pin_positions`, `move_symbol`, `move_label`, `assign_footprint`, `run_erc` |
| PCB Layout | `set_board_outline`, `add_mounting_holes`, `place_footprint`, `get_ratsnest`, `add_keepout_zone` |
| Copper Pours | `add_zone`, `fill_zones` |
| Routing | `route_trace`, `route_differential_pair`, `add_via` |
| Validation | `run_drc`, `add_silkscreen_text`, `add_test_point` |
| Fab Outputs | `generate_gerbers`, `generate_drill_files`, `generate_bom`, `generate_position_file`, `generate_3d_model` |
| Filesystem | `list_directory`, `read_file` |

---

## Project structure

```
kicad-ai-project-creator/
├── kicad_mcp_server.py             # MCP server entry point
├── setup.sh                        # One-shot install + global registration
├── kicad_agent_system_prompt.txt   # PCB engineer context (optional, for reference)
└── kicad_agent/
    ├── tools.py                    # Tool input schemas
    └── dispatcher.py               # Tool implementations
```

---

## Connecting to real KiCad

`dispatcher.py` uses mixed backends and can fall back to in-memory stubs:

- `kicad-cli`: ERC/DRC and fabrication exports
- `kipy` IPC (`kicad-python`): selected live PCB operations
- Direct `.kicad_sch` editing: selected schematic operations
- Stub fallback: used when a real backend is unavailable for a specific tool

Call `get_capabilities` first in a session to see what is available on the current machine and whether `pcb_file`/`sch_file` are set.

Each function must return a JSON-serialisable `dict` with `{"status": "ok"}` on
success or `{"status": "error", "message": "..."}` on failure.
