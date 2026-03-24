# KiCad AI Project Creator

An agentic PCB design assistant that takes a plain-language product description
and drives Claude through every phase of a KiCad design — from project brief to
Gerber files.

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

## Quickstart

```bash
# Install dependencies
pip install -r requirements.txt

# Set your API key
export ANTHROPIC_API_KEY="sk-ant-..."

# Run with a description
python main.py "USB-C rechargeable LED controller for 4 channels of RGB LED
               strips, controlled via smartphone over BLE."

# Or use a built-in example
python main.py --example minimal
python main.py --example medium
python main.py --example complex

# Pipe a description from stdin
echo "Your product description" | python main.py -
```

## Project structure

```
kicad-ai-project-creator/
├── kicad_agent_system_prompt.txt   # Expert PCB engineer system prompt
├── main.py                         # CLI entry point
├── requirements.txt
└── kicad_agent/
    ├── __init__.py
    ├── agent.py        # run_kicad_agent() — the agentic loop
    ├── tools.py        # TOOLS — 31 tool definitions (phases 0–8)
    └── dispatcher.py   # Tool dispatcher + stub implementations
```

## Connecting to real KiCad

`dispatcher.py` ships with stub implementations that keep state in memory and
return `"note": "STUB"` in their responses. The agent reads these responses and
proceeds with the design — useful for testing the agent's reasoning without a
live KiCad instance.

To connect to a real KiCad project, replace each stub function with a call to:

- **KiCad IPC API** (KiCad 8+): `https://dev-docs.kicad.org/en/ipc/`
- **pcbnew Python API**: `import pcbnew` (available inside KiCad's scripting console)
- **Your own automation layer** (FreeCAD, custom IPC socket, etc.)

The dispatcher contract is simple: each function receives keyword arguments
matching its `input_schema` and must return a JSON-serialisable `dict` with at
least `{"status": "ok"}` on success or `{"status": "error", "message": "..."}` on
failure.

## Example descriptions

```python
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
```

## Using as a library

```python
from kicad_agent import run_kicad_agent

result = run_kicad_agent(
    product_description="Your product here",
    log=print,               # custom logger
    max_tool_calls=500,      # safety cap
)
print(result)
```
