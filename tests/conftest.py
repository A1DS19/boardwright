"""
Pytest configuration: fake-backend fixture, state reset, minimal sch fixture.

Every test runs with KICAD_MCP_FAKE_BACKEND=1 so that kipy is never imported
and kicad-cli is never invoked. This keeps the suite runnable without KiCad
installed (CI-friendly).
"""

from __future__ import annotations

import shutil

import pytest


MINIMAL_SCH_FIXTURE = """\
(kicad_sch
\t(version 20231120)
\t(generator "eeschema")
\t(uuid "00000000-0000-0000-0000-000000000001")
\t(paper "A4")
\t(lib_symbols
\t\t(symbol "Device:R"
\t\t\t(pin passive line
\t\t\t\t(at 0 3.81 270)
\t\t\t\t(length 1.27)
\t\t\t\t(name "~" (effects (font (size 1.27 1.27))))
\t\t\t\t(number "1" (effects (font (size 1.27 1.27))))
\t\t\t)
\t\t\t(pin passive line
\t\t\t\t(at 0 -3.81 90)
\t\t\t\t(length 1.27)
\t\t\t\t(name "~" (effects (font (size 1.27 1.27))))
\t\t\t\t(number "2" (effects (font (size 1.27 1.27))))
\t\t\t)
\t\t)
\t)
\t(symbol
\t\t(lib_id "Device:R")
\t\t(at 100 50 0)
\t\t(unit 1)
\t\t(uuid "11111111-1111-1111-1111-111111111111")
\t\t(property "Reference" "R1" (at 100 45 0))
\t\t(property "Value" "10k" (at 100 55 0))
\t)
)
"""


@pytest.fixture(autouse=True)
def fake_backend(monkeypatch):
    """
    Gate every test through the fake backend:
      - KICAD_MCP_FAKE_BACKEND=1 makes backends._kicad() raise and
        backends._run_cli() return (1, "", "fake backend...").
      - shutil.which is stubbed so get_capabilities can't see kicad-cli.
      - _project_state is reset between tests via reset_state().
    """
    monkeypatch.setenv("KICAD_MCP_FAKE_BACKEND", "1")
    monkeypatch.setattr(shutil, "which", lambda name: None)

    from boardwright import state
    state.reset_state()
    yield
    state.reset_state()


@pytest.fixture
def tmp_sch(tmp_path):
    """Write MINIMAL_SCH_FIXTURE to a tmp file and return its path."""
    sch = tmp_path / "test.kicad_sch"
    sch.write_text(MINIMAL_SCH_FIXTURE)
    return sch
