"""
Backend shims: kipy (IPC) + kicad-cli (subprocess).

Both honor the KICAD_MCP_FAKE_BACKEND=1 env var — when set, kipy imports
raise ImportError and kicad-cli returns a synthetic non-zero exit code.
This makes the test suite runnable on machines without KiCad installed.

All kipy imports stay INSIDE functions (never at module top) so that the
env-var guard is the single source of truth for whether real backends are
exercised.
"""

from __future__ import annotations

import os
import subprocess


def _fake_backends() -> bool:
    """Check the env flag at call time — tests may toggle it per-fixture."""
    return os.environ.get("KICAD_MCP_FAKE_BACKEND") == "1"


def _kicad():
    """
    Return a connected kipy.kicad.KiCad instance.
    Raises ImportError when faked or when kicad-python is not installed.
    """
    if _fake_backends():
        raise ImportError("fake backend: kipy disabled")
    from kipy.kicad import KiCad  # pip install kicad-python
    return KiCad()


def _probe_kipy() -> tuple[bool, str | None]:
    """Return (available, import_error_str). Used by get_capabilities."""
    if _fake_backends():
        return False, "fake backend: kipy disabled"
    try:
        from kipy.kicad import KiCad  # noqa: F401
        return True, None
    except Exception as exc:  # noqa: BLE001
        return False, f"{type(exc).__name__}: {exc}"


def _run_cli(*args: str) -> tuple[int, str, str]:
    """Run kicad-cli and return (returncode, stdout, stderr)."""
    if _fake_backends():
        return (1, "", "fake backend: kicad-cli disabled")
    result = subprocess.run(
        ["kicad-cli", *args],
        capture_output=True, text=True,
    )
    return result.returncode, result.stdout, result.stderr


def _cli_error(stderr: str, returncode: int) -> dict:
    return {"status": "error", "message": stderr.strip() or f"kicad-cli exited {returncode}"}
