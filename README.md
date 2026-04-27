# Boardwright

**AI-native KiCad.** An MCP server that gives Claude 41 KiCad design tools across the full PCB workflow — research, schematic, layout, copper pours, routing, validation, and fab outputs. Describe a board in plain English; Claude drives your local KiCad install to design it.

- **Local-first.** Your KiCad, your libraries, your fab presets. Files never leave your machine.
- **Open core.** MIT-licensed. No telemetry. BYO LLM.
- **Indie-maker first.** Built for the person who already opens KiCad on weekends.

> Status: pre-1.0. Working and used daily, but the validation gate ([docs/PROJECT.md](docs/PROJECT.md#validation-gate-hard)) hasn't passed yet.

---

## Install

```bash
git clone https://github.com/A1DS19/boardwright
cd boardwright
./setup.sh
```

`setup.sh` installs the package in editable mode and registers the MCP server with Claude Code at user scope, so it's available from any directory.

PyPI release is on the milestone list — see [docs/PROJECT.md](docs/PROJECT.md#next-milestones-in-order).

---

## Quickstart

Open Claude Code from anywhere:

```bash
claude
```

Verify Boardwright is connected:

```
/mcp
```

You should see `boardwright` listed as an active server. Then just describe what you want to build:

```
Design a USB-C rechargeable LED controller for 4 channels of RGB LED strips,
controlled via smartphone over BLE.
```

```
Industrial temperature and humidity data logger. Battery powered with
2-year life target. LoRaWAN sync. IP67 enclosure, -20°C to 60°C.
```

```
Review my MCU schematic in mcu/ and finish the wiring —
read the datasheets in mcu/datasheets/ first.
```

Three working example projects live in [`examples/`](examples/).

---

## Prerequisites

- **Python 3.10+**
- **Claude Code** ([install](https://claude.com/claude-code))
- **KiCad 9.0+** with the IPC API enabled:
  Preferences → Plugins → check **"Enable KiCad API"**, then restart KiCad.
- The PCB Editor must be **open** for live PCB tools (`place_footprint`, `route_trace`, `fill_zones`, etc.) to work — launching the project manager alone is not enough.
- Optional: `MOUSER_API_KEY` in `.env` for `search_components`. Without it, component search returns a graceful error instead of crashing.

For autorouting via Freerouting, see [docs/troubleshooting.md](docs/troubleshooting.md) — Java 21 specifically is required; Java 25 silently produces a 0-byte session file.

---

## Tools

| Phase | Tools |
|-------|-------|
| Project | `set_project`, `get_capabilities`, `set_drc_severity`, `add_drc_exclusion` |
| Research | `search_components`, `get_datasheet`, `verify_kicad_footprint`, `generate_custom_footprint`, `impedance_calc` |
| Schematic | `create_schematic_sheet`, `add_symbol`, `add_power_symbol`, `connect_pins`, `add_net_label`, `add_no_connect`, `remove_no_connect`, `get_pin_positions`, `move_symbol`, `move_label`, `assign_footprint`, `run_erc` |
| PCB Layout | `set_board_outline`, `add_mounting_holes`, `place_footprint`, `get_ratsnest`, `add_keepout_zone`, `auto_arrange`, `fit_board_outline` |
| Copper Pours | `add_zone`, `fill_zones` |
| Routing | `route_trace`, `route_differential_pair`, `add_via`, `autoroute_pcb` |
| Validation | `run_drc`, `add_silkscreen_text`, `add_test_point` |
| Fab Outputs | `generate_gerbers`, `generate_drill_files`, `generate_bom`, `generate_position_file`, `generate_3d_model` |
| Filesystem | `list_directory`, `read_file` |

To keep Claude's tool-list context clean, 16 commonly-used tools are exposed directly and 25 advanced tools are routed through 5 meta-tools (`project_admin`, `research`, `schematic_advanced`, `pcb_layout_advanced`, `routing_advanced`). Both surfaces are reachable through `execute_tool`.

Call `get_capabilities` first in a session to see which backends are live on the current machine.

---

## Compared to other KiCad MCP servers

The OSS-MCP-for-KiCad space is real and growing. Here's a fair-minded look at the closest neighbours, so you can pick the right tool for your workflow.

| Project | License | Tools | Editing | DFM presets | Product framing |
|---------|---------|-------|---------|-------------|-----------------|
| **Boardwright** (this) | **MIT** | 41 (16 direct + 25 routed) | full schematic + PCB | JLC/PCBWay/OSH on roadmap | indie-maker, open-core, paid Studio tier |
| [`oaslananka/kicad-mcp-pro`](https://github.com/oaslananka/kicad-mcp-pro) | MIT | 100+ across 11 categories | full | **bundled today** | tool, no product wrapper |
| [`Seeed-Studio/kicad-mcp-server`](https://github.com/Seeed-Studio/kicad-mcp-server) | none declared | 39 | analysis prod, **editing experimental** | no | tool, Seeed brand backing |
| [`bunnyf/pcb-mcp`](https://github.com/bunnyf/pcb-mcp) | **GPL-3.0** | 22 | PCB only | JLCPCB export bundle | tool |
| [`nickleassdimebutt/kicad-claude-toolkit`](https://github.com/nickleassdimebutt/kicad-claude-toolkit) | none declared | 16 Claude Skills + IPC bridge | full (KiCad 10) | no | different shape — **Skills, not MCP** |

**Where Boardwright fits:** if you want **MIT licensing** (so you can ship downstream), **working schematic editing** (Seeed marks theirs experimental), and a **product story for indie makers** (paid Studio tier, landing page, validation gate), Boardwright is the right choice. If you want the **largest tool surface today**, `oaslananka/kicad-mcp-pro` is ahead of us — we're closing the gap (DFM profiles are next on the milestone list) but we're not pretending they don't exist.

We're tracking `kicad-claude-toolkit`'s Skills shape as a real architectural alternative to MCP and plan to ship a Boardwright Skills pack alongside the MCP server in Phase 2 — same backend, two surfaces.

See [`docs/PROJECT.md`](docs/PROJECT.md#2026-04-27-revision--the-oss-field-after-looking-properly) for the full competitive scan.

---

## Project structure

```
boardwright/
├── boardwright/                # the Python package
│   ├── server.py               # MCP server entry point
│   ├── dispatcher.py           # tool registry and arg coercion
│   ├── router.py               # direct/routed tool taxonomy
│   ├── backends.py             # kipy / kicad-cli / file-write fallbacks
│   ├── schematic_io.py         # .kicad_sch S-expression parser/serializer
│   ├── sexpr.py                # minimal S-expression tokenizer
│   ├── state.py                # shared project state
│   └── tools/                  # 8 domain modules: project, filesystem,
│                               # research, schematic, pcb_layout,
│                               # routing, pcb_checks, fabrication
├── tests/                      # pytest suite (runs without KiCad)
├── examples/                   # three real KiCad projects
├── docs/
│   ├── PROJECT.md              # strategy, ICP, validation gate
│   └── troubleshooting.md      # Freerouting / Java / KiCad gotchas
├── boardwright_system_prompt.txt   # PCB-engineer context for the agent
├── setup.sh                    # one-shot install + MCP registration
└── pyproject.toml
```

---

## How the backends fit together

`boardwright/backends.py` picks the right strategy per tool:

- **`kipy` IPC** (`kicad-python`) — live PCB operations: `place_footprint`, `route_trace`, `fill_zones`, `add_via`, `get_ratsnest`. Requires KiCad's PCB Editor open with the API enabled.
- **`kicad-cli` subprocess** — ERC, DRC, Gerber/drill/BOM/position/3D outputs.
- **Direct S-expression file editing** — schematic operations (`.kicad_sch` doesn't have full IPC coverage in KiCad 9).
- **Stub fallback** — when a real backend isn't available, tools return a structured error instead of crashing. This is also what makes the test suite runnable on machines without KiCad.

Every tool returns a JSON-serializable dict: `{"status": "ok", ...}` on success, `{"status": "error", "message": "..."}` on failure.

---

## Development

```bash
pip install -e ".[dev]"
pytest tests/                    # 93 tests, no KiCad required
ruff check boardwright/
mypy boardwright/
```

---

## Roadmap

See [docs/PROJECT.md](docs/PROJECT.md) for the full strategic plan: ICP, competitive landscape, validation gate, phased architecture, and decision journal.

---

## License

MIT. See [LICENSE](LICENSE).
