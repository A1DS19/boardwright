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
import os
from pathlib import Path
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


# ── KiCad library search paths ──────────────────────────────────────────

_SYSTEM_LIB_BASES: list[Path] = [
    Path("/usr/share/kicad"),
    Path("/usr/local/share/kicad"),
    Path.home() / ".local" / "share" / "kicad",
    Path("/Applications/KiCad/KiCad.app/Contents/SharedSupport"),
]


def _kicad_lib_search_paths(
    subfolder: str,
    env_var: str,
    project_dir: Path | None = None,
) -> list[Path]:
    """Return candidate directories for a KiCad library type.

    *subfolder* is e.g. ``"symbols"`` or ``"footprints"``.
    *env_var* is the environment variable override (e.g. ``"KICAD_SYMBOLS"``).
    Project-local folder is checked first so local overrides take precedence.
    """
    candidates: list[Path] = []
    if project_dir is not None:
        candidates.append(project_dir / subfolder)
    env = os.environ.get(env_var)
    if env:
        candidates.append(Path(env))
    candidates += [base / subfolder for base in _SYSTEM_LIB_BASES]
    return [p for p in candidates if p.is_dir()]
