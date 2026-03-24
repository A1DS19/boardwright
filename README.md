# KiCad AI Project Creator

An agentic PCB design assistant powered by Claude. Give it a plain-language product
description and it drives the full KiCad workflow — from project brief to Gerber files.
It can also read existing KiCad projects, review schematics, and pick up mid-design.

## How it works

The agent follows 8 structured phases:

| Phase | Name | What happens |
|-------|------|--------------|
| 0 | Project Analysis | Parses the description, selects board class (A/B/C), lists assumptions |
| 1 | Component Selection | Searches for real parts, verifies KiCad footprints, builds BOM |
| 2 | Schematic Generation | Creates sheets, places symbols, wires nets, runs ERC |
| 3 | Footprint Assignment | Maps every schematic symbol to a verified PCB footprint |
| 4 | PCB Layout | Sets board outline, places components in priority order |
| 5 | Copper Pours | Adds GND/PWR planes, fills zones |
| 6 | Trace Routing | Routes in priority order: diff pairs → power → analog → digital |
| 7 | DRC & Sign-off | Runs DRC, verifies checklist, adds silkscreen / test points |
| 8 | Fab Outputs | Generates Gerbers, drill files, BOM CSV, pick-and-place, STEP |

The agent can also read files from your local project directory — schematics,
datasheets, KiCad files, notes — so you can point it at an existing project and
it will review and continue from where you left off.

---

## Global Install

Install once, use from any directory:

```bash
git clone https://github.com/your-username/kicad-ai-project-creator
cd kicad-ai-project-creator
pip install -e .
```

Add your Anthropic API key to your shell profile (`~/.zshrc` or `~/.bashrc`):

```bash
export ANTHROPIC_API_KEY="sk-ant-..."
```

Reload:

```bash
source ~/.zshrc   # or source ~/.bashrc
```

Verify:

```bash
kicad-ai --help
```

---

## Usage

```bash
# New design from a description
kicad-ai "USB-C rechargeable LED controller for 4 channels of RGB LED strips,
          controlled via smartphone over BLE."

# Review and continue an existing project
cd /your/kicad/project/
kicad-ai "review my schematic in mcu/ and finish the wiring"

# Built-in examples
kicad-ai --example minimal
kicad-ai --example medium
kicad-ai --example complex

# From stdin
echo "Your product description" | kicad-ai -

# Limit tool calls (safety cap, default 500)
kicad-ai --max-tool-calls 100 "Your description"
```

The agent resolves all relative paths from your **current working directory**, so
`cd` into your project folder before running.

---

## Quickstart (without global install)

```bash
pip install -r requirements.txt
export ANTHROPIC_API_KEY="sk-ant-..."
python main.py --example minimal
```

---

## Project structure

```
kicad-ai-project-creator/
├── kicad_agent_system_prompt.txt   # Expert PCB engineer system prompt
├── main.py                         # Local entry point (python main.py ...)
├── pyproject.toml                  # Package definition (kicad-ai command)
├── requirements.txt
└── kicad_agent/
    ├── __init__.py
    ├── agent.py        # run_kicad_agent() — the agentic loop
    ├── cli.py          # CLI entry point for the installed kicad-ai command
    ├── tools.py        # 33 tool definitions across phases 0–8
    └── dispatcher.py   # Tool router + implementations
```

---

## Connecting to real KiCad

`dispatcher.py` ships with stub implementations that keep state in memory and
return `"note": "STUB"` in their responses. The agent reads these and proceeds —
useful for testing the agent's reasoning without a live KiCad instance.

To connect to a real KiCad project, replace each stub with a call to:

- **KiCad IPC API** (KiCad 8+): `https://dev-docs.kicad.org/en/ipc/`
- **pcbnew Python API**: `import pcbnew` (available in KiCad's scripting console)
- **Your own automation layer** (custom IPC socket, FreeCAD, etc.)

Each dispatcher function receives keyword arguments matching its `input_schema`
and must return a JSON-serialisable `dict` with at least `{"status": "ok"}` on
success or `{"status": "error", "message": "..."}` on failure.

---

## Example descriptions

```
# Minimal
"USB-C rechargeable LED controller for 4 channels of RGB LED strips,
 controlled via smartphone over BLE."

# Medium complexity
"Industrial temperature and humidity data logger. Battery powered with
 2-year life target. Logs to onboard flash every 5 minutes.
 Syncs over LoRaWAN when in range. IP67 enclosure, -20°C to 60°C."

# High complexity
"Stereo audio DAC board for Raspberry Pi. I2S input, PCM5122 DAC,
 Class-D amplifier output, headphone jack with detection,
 volume control via rotary encoder, OLED display for level meters."

# Review existing project
"Review my MCU schematic in mcu/ and finish the wiring — read the
 datasheets in mcu/datasheets/ first."
```

---

## Using as a library

```python
from kicad_agent import run_kicad_agent

result = run_kicad_agent(
    product_description="Your product here",
    log=print,            # custom logger
    max_tool_calls=500,   # safety cap
)
print(result)
```
