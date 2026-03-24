"""
KiCad AI Design Agent — Main Loop

Drives Claude through the 8-phase PCB design workflow defined in the system
prompt, dispatching every tool call to the KiCad IPC bridge in dispatcher.py.
"""

from __future__ import annotations

import json
import os
import pathlib
import time
from collections.abc import Callable
from typing import Any

import anthropic

from .tools import TOOLS
from .dispatcher import dispatch_tool

# Path to the system prompt shipped alongside this package
_SYSTEM_PROMPT_PATH = pathlib.Path(__file__).parent.parent / "kicad_agent_system_prompt.txt"

# Safety cap — prevents runaway billing from infinite loops
_DEFAULT_MAX_TOOL_CALLS = 500

# Model to use
_MODEL = "claude-opus-4-6"


def _load_system_prompt() -> str:
    try:
        return _SYSTEM_PROMPT_PATH.read_text(encoding="utf-8")
    except FileNotFoundError as exc:
        raise FileNotFoundError(
            f"System prompt not found at {_SYSTEM_PROMPT_PATH}. "
            "Ensure kicad_agent_system_prompt.txt is in the project root."
        ) from exc


def run_kicad_agent(
    product_description: str,
    log: Callable[[str], None] = print,
    max_tool_calls: int = _DEFAULT_MAX_TOOL_CALLS,
    api_key: str | None = None,
) -> str | None:
    """
    Run the KiCad AI Design Agent end-to-end.

    Parameters
    ----------
    product_description : str
        Free-form natural language description of the product to design.
        Examples are provided in the module docstring and README.
    log : callable, optional
        Logging function. Defaults to print(). Pass a custom logger for
        integration into larger applications.
    max_tool_calls : int, optional
        Hard limit on total tool invocations to prevent runaway loops.
        Default 500.
    api_key : str, optional
        Anthropic API key. Defaults to the ANTHROPIC_API_KEY env variable.

    Returns
    -------
    str | None
        The final text response from the agent, or None if the loop was
        terminated early due to hitting the tool call limit.
    """
    client = anthropic.Anthropic(
        api_key=api_key or os.environ.get("ANTHROPIC_API_KEY")
    )

    cwd = os.getcwd()
    system_prompt = _load_system_prompt() + f"\n\nCURRENT WORKING DIRECTORY: {cwd}\nAll relative file paths the user mentions are relative to this directory."

    messages: list[dict[str, Any]] = [
        {"role": "user", "content": product_description}
    ]

    total_tool_calls = 0
    final_text: str | None = None

    log("=" * 60)
    log("KiCad AI Design Agent — starting")
    log(f"Model : {_MODEL}")
    log(f"Input : {product_description[:120]}{'...' if len(product_description) > 120 else ''}")
    log("=" * 60)

    while True:
        response = _create_with_retry(client, system_prompt, messages, log)

        # Append assistant turn to history
        messages.append({"role": "assistant", "content": response.content})

        # Collect any text blocks for the final result
        for block in response.content:
            if hasattr(block, "type") and block.type == "text":
                final_text = block.text

        # ── Done ──────────────────────────────────────────────────────────
        if response.stop_reason == "end_turn":
            log("\n✅ Design complete.")
            break

        # ── Print any thinking/text blocks as status ──────────────────────
        for block in response.content:
            if hasattr(block, "type") and block.type == "text" and block.text.strip():
                # Print first line of text as a status hint
                first_line = block.text.strip().splitlines()[0][:120]
                log(f"\n  {first_line}")

        # ── Tool use ──────────────────────────────────────────────────────
        if response.stop_reason == "tool_use":
            tool_results = []
            for block in response.content:
                if not (hasattr(block, "type") and block.type == "tool_use"):
                    continue

                total_tool_calls += 1
                tool_name = block.name
                tool_input = block.input

                log(_format_tool_log(tool_name, tool_input))

                result = dispatch_tool(tool_name, tool_input)
                if result.get("status") == "error":
                    log(f"  ⚠  {result.get('message', 'error')}")

                tool_results.append({
                    "type": "tool_result",
                    "tool_use_id": block.id,
                    "content": json.dumps(result),
                })

            messages.append({"role": "user", "content": tool_results})

        # ── Safety limit ──────────────────────────────────────────────────
        if total_tool_calls >= max_tool_calls:
            log(
                f"\n⚠️  Tool call limit reached ({max_tool_calls}). "
                "Halting to avoid runaway loop."
            )
            break

        # ── Max tokens — continue the response ───────────────────────────
        if response.stop_reason == "max_tokens":
            log("\n↩  max_tokens reached — continuing...")
            messages.append({"role": "user", "content": "Continue."})
            continue

        # ── Unexpected stop reason ────────────────────────────────────────
        if response.stop_reason not in ("tool_use", "end_turn"):
            log(f"\n⚠️  Unexpected stop_reason='{response.stop_reason}'. Halting.")
            break

    log(f"\nTotal tool calls: {total_tool_calls}")
    return final_text


def _create_with_retry(client, system_prompt, messages, log, max_retries=8):
    delay = 60
    for attempt in range(max_retries):
        try:
            with client.messages.stream(
                model=_MODEL,
                max_tokens=32000,
                thinking={"type": "adaptive"},
                system=[{
                    "type": "text",
                    "text": system_prompt,
                    "cache_control": {"type": "ephemeral"},
                }],
                tools=TOOLS,
                messages=messages,
            ) as stream:
                return stream.get_final_message()
        except anthropic.RateLimitError:
            if attempt == max_retries - 1:
                raise
            log(f"\n⏳ Rate limit hit — waiting {delay}s before retry ({attempt + 1}/{max_retries})...")
            time.sleep(delay)
            delay = min(delay * 2, 300)


_TOOL_LABELS = {
    "list_directory":          ("📂", "Exploring"),
    "read_file":               ("📄", "Reading"),
    "search_components":       ("🔍", "Searching components"),
    "get_datasheet":           ("📑", "Fetching datasheet"),
    "verify_kicad_footprint":  ("✔ ", "Verifying footprint"),
    "generate_custom_footprint": ("🔧", "Generating footprint"),
    "impedance_calc":          ("📐", "Calculating impedance"),
    "create_schematic_sheet":  ("🗒 ", "Creating sheet"),
    "add_symbol":              ("➕", "Adding symbol"),
    "add_power_symbol":        ("⚡", "Adding power symbol"),
    "connect_pins":            ("🔗", "Connecting pins"),
    "add_net_label":           ("🏷 ", "Labelling net"),
    "add_no_connect":          ("✖ ", "Marking no-connect"),
    "assign_footprint":        ("📌", "Assigning footprint"),
    "run_erc":                 ("🔬", "Running ERC"),
    "set_board_outline":       ("⬜", "Setting board outline"),
    "add_mounting_holes":      ("🔩", "Adding mounting holes"),
    "place_footprint":         ("📍", "Placing"),
    "get_ratsnest":            ("🕸 ", "Checking ratsnest"),
    "add_keepout_zone":        ("🚫", "Adding keepout zone"),
    "add_zone":                ("🟦", "Adding copper zone"),
    "fill_zones":              ("🟦", "Filling copper pours"),
    "route_trace":             ("➰", "Routing trace"),
    "route_differential_pair": ("➰", "Routing diff pair"),
    "add_via":                 ("🔘", "Adding via"),
    "run_drc":                 ("🔬", "Running DRC"),
    "add_silkscreen_text":     ("🖊 ", "Adding silkscreen text"),
    "add_test_point":          ("🎯", "Adding test point"),
    "generate_gerbers":        ("📦", "Generating Gerbers"),
    "generate_drill_files":    ("🕳 ", "Generating drill files"),
    "generate_bom":            ("📋", "Generating BOM"),
    "generate_position_file":  ("📋", "Generating position file"),
    "generate_3d_model":       ("🧊", "Generating 3D model"),
}

def _format_tool_log(tool_name: str, tool_input: dict) -> str:
    icon, label = _TOOL_LABELS.get(tool_name, ("⚙ ", tool_name))
    # Pick the most meaningful input field to show as context
    context = (
        tool_input.get("path")
        or tool_input.get("reference")
        or tool_input.get("sheet_name")
        or tool_input.get("net_name")
        or tool_input.get("mpn")
        or tool_input.get("query")
        or tool_input.get("text")
        or ""
    )
    if context:
        return f"  {icon} {label}: {context}"
    return f"  {icon} {label}"


def _truncate(s: str, n: int) -> str:
    return s if len(s) <= n else s[:n] + "…"
