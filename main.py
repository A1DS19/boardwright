#!/usr/bin/env python3
"""
KiCad AI Project Creator — CLI entry point

Usage
-----
  python main.py "USB-C rechargeable LED controller for 4 channels of RGB LED
                  strips, controlled via smartphone over BLE."

  python main.py --example minimal
  python main.py --example medium
  python main.py --example complex

  echo "Your product description" | python main.py -

Environment
-----------
  ANTHROPIC_API_KEY   Required — your Anthropic API key.
"""

from __future__ import annotations

import argparse
import sys

from dotenv import load_dotenv
load_dotenv()

from kicad_agent import run_kicad_agent

# ── Built-in example descriptions ────────────────────────────────────────────

EXAMPLES = {
    "minimal": (
        "USB-C rechargeable LED controller for 4 channels of RGB LED strips, "
        "controlled via smartphone over BLE."
    ),
    "medium": (
        "Industrial temperature and humidity data logger. Battery powered with "
        "2-year life target. Logs to onboard flash every 5 minutes. "
        "Syncs over LoRaWAN when in range. "
        "IP67 enclosure, -20°C to 60°C operating range."
    ),
    "complex": (
        "Stereo audio DAC board for Raspberry Pi. I2S input, PCM5122 DAC, "
        "Class-D amplifier output, headphone jack with detection, "
        "volume control via rotary encoder, OLED display for level meters."
    ),
}


def main() -> None:
    parser = argparse.ArgumentParser(
        prog="kicad-ai",
        description="Generate a complete KiCad PCB project from a product description.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )

    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument(
        "description",
        nargs="?",
        help=(
            'Free-form product description in quotes, '
            'or "-" to read from stdin.'
        ),
    )
    group.add_argument(
        "--example",
        choices=list(EXAMPLES.keys()),
        metavar=f"{{{','.join(EXAMPLES)}}}",
        help="Run one of the built-in example descriptions.",
    )

    parser.add_argument(
        "--max-tool-calls",
        type=int,
        default=500,
        help="Safety cap on total tool invocations (default: 500).",
    )

    args = parser.parse_args()

    # ── Resolve the product description ──────────────────────────────────────
    if args.example:
        description = EXAMPLES[args.example]
        print(f"Running built-in example: {args.example!r}")
        print(f"Description: {description}\n")
    elif args.description == "-":
        description = sys.stdin.read().strip()
        if not description:
            parser.error("No description provided on stdin.")
    else:
        description = args.description

    # ── Run the agent ─────────────────────────────────────────────────────────
    final = run_kicad_agent(
        product_description=description,
        max_tool_calls=args.max_tool_calls,
    )

    if final:
        print("\n" + "=" * 60)
        print("FINAL AGENT OUTPUT")
        print("=" * 60)
        print(final)


if __name__ == "__main__":
    main()
