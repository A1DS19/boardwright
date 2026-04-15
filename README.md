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

### Enabling the KiCad IPC API

Live PCB tools (`place_footprint`, `route_trace`, `get_ratsnest`, `fill_zones`, `add_via`, etc.) talk to KiCad over the `kipy` IPC socket. For these to work:

1. **Enable the API once**: KiCad → Preferences → Preferences → Plugins → check **"Enable KiCad API"**, then restart KiCad.
2. **Open the PCB Editor**: launching the KiCad project manager alone is not enough — double-click the `.kicad_pcb` so the PCB Editor window is open.
3. **Set the active project**: call `set_project` with absolute paths to the `.kicad_pcb` / `.kicad_sch`.
4. **Sync footprints before placing**: footprints must exist on the board (Schematic Editor → Tools → *Update PCB from Schematic*, or `assign_footprint` + update) before `place_footprint` can move them.

If a live tool returns `"KiCad is not running"`, the PCB Editor isn't open or the API isn't enabled.

### Freerouting (autorouter) — Fedora setup

KiCad's **Freerouting plugin** (install via *Tools → Plugin and Content Manager*) ships a Java jar that needs **Java 21** specifically. Java 25 runs but silently produces a 0-byte `.ses` file, which KiCad then fails to import with `Expecting '(' in ... offset 1`.

```bash
sudo dnf install java-21-openjdk-headless
```

Launch KiCad with `JAVA_HOME` pointing at 21 so the plugin picks it up:

```bash
JAVA_HOME=/usr/lib/jvm/java-21-openjdk kicad &
```

Make it permanent:

```bash
echo 'export JAVA_HOME=/usr/lib/jvm/java-21-openjdk' >> ~/.zshrc
```

If you want to autoroute manually (skipping the plugin):

```bash
cd <project-dir>
/usr/lib/jvm/java-21-openjdk/bin/java -jar \
  ~/.local/share/kicad/9.0/3rdparty/plugins/app_freerouting_kicad-plugin/jar/freerouting-2.1.0.jar \
  -de freerouting.dsn -do freerouting.ses -mt 1 \
  -host "KiCad's Pcbnew,9.0.8-1.fc43"
```

Use `-mt 1` — Freerouting's multi-threaded optimizer is known to create clearance violations. Then re-import in pcbnew: **File → Import → Specctra Session**.

Each function must return a JSON-serialisable `dict` with `{"status": "ok"}` on
success or `{"status": "error", "message": "..."}` on failure.
