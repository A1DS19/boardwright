"""
Shared in-memory project state + file path accessors.

INVARIANT: every tools/*.py module imports the same `_project_state` object
and mutates it in place. Do not rebind it; only mutate its keys. Tests reset
it between runs via `INITIAL_STATE`.

This module has ZERO internal package imports, so every other module can
import from it freely without risking circular imports.
"""

from __future__ import annotations

import copy
from typing import Any


def _fresh_state() -> dict[str, Any]:
    return {
        "pcb_file":      None,   # path to .kicad_pcb
        "sch_file":      None,   # path to .kicad_sch
        "sheets":        {},     # sheet_name → {components, nets, labels}
        "footprints":    {},     # reference → footprint_path
        "placements":    {},     # reference → {x, y, rotation, layer}
        "zones":         [],     # list of zone dicts
        "traces":        [],     # list of trace dicts
        "vias":          [],     # list of via dicts
        "board_outline": None,   # {width, height, corner_radius}
        "bom":           {},     # reference → component info
    }


# Reference template used by tests to reset state between runs.
INITIAL_STATE: dict[str, Any] = _fresh_state()

# The live mutable state shared across every tool module.
_project_state: dict[str, Any] = copy.deepcopy(INITIAL_STATE)


def reset_state() -> None:
    """Reset _project_state to its initial values. Used by test fixtures."""
    _project_state.clear()
    _project_state.update(copy.deepcopy(INITIAL_STATE))


def _pcb_file(override: str | None = None) -> str | None:
    return override or _project_state.get("pcb_file")


def _sch_file(override: str | None = None) -> str | None:
    return override or _project_state.get("sch_file")


def get_project_state() -> dict:
    """Return a snapshot of the current in-memory project state (for debugging)."""
    return _project_state
