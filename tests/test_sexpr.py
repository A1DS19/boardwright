"""
S-expression parser + pin-transform math. These are the numeric-correctness
guards — if the rotation/mirror math drifts, wiring will silently point at
the wrong coordinates and nothing else catches it.
"""

from __future__ import annotations

import math

from kicad_agent.schematic_io import (
    _resolve_pin_endpoint,
    _sch_lib_symbols,
    _sch_placed_symbols,
    _transform_pin,
)
from kicad_agent.sexpr import (
    _parse_sexpr,
    _sx_find,
    _sx_findall,
    _sx_get_property,
    _tokenize_sexpr,
)


def test_tokenize_handles_quoted_strings():
    tokens = _tokenize_sexpr('(foo "hello world" 42)')
    assert tokens == ["(", "foo", "hello world", "42", ")"]


def test_parse_nested():
    tree = _parse_sexpr('(a (b 1 2) (c "x"))')
    assert tree[0] == "a"
    assert _sx_find(tree, "b") == ["b", "1", "2"]
    assert _sx_find(tree, "c") == ["c", "x"]


def test_sx_findall_returns_all_matches():
    tree = _parse_sexpr('(root (child 1) (child 2) (other 3))')
    children = _sx_findall(tree, "child")
    assert len(children) == 2


def test_sx_get_property():
    tree = _parse_sexpr('(symbol (property "Reference" "R1") (property "Value" "10k"))')
    assert _sx_get_property(tree, "Reference") == "R1"
    assert _sx_get_property(tree, "Value") == "10k"
    assert _sx_get_property(tree, "Missing") is None


def test_transform_pin_identity():
    # No rotation, no mirror: pin just gets translated, Y is inverted.
    x, y = _transform_pin(1.0, 2.0, 100.0, 50.0, 0.0, False, False)
    assert x == 101.0
    assert y == 48.0  # 50 - 2


def test_transform_pin_rotation_90():
    # 90° CCW of (1, 0) → (0, 1). After Y-invert: (place_x + 0, place_y - 1).
    x, y = _transform_pin(1.0, 0.0, 100.0, 50.0, 90.0, False, False)
    assert math.isclose(x, 100.0, abs_tol=1e-3)
    assert math.isclose(y, 49.0, abs_tol=1e-3)


def test_transform_pin_mirror_x():
    x, y = _transform_pin(1.0, 2.0, 100.0, 50.0, 0.0, mirror_x=True, mirror_y=False)
    assert x == 99.0   # 100 + (-1)
    assert y == 48.0


def test_resolve_pin_endpoint_from_fixture(tmp_sch):
    # From MINIMAL_SCH_FIXTURE in conftest: R1 placed at (100, 50, 0°),
    # pin "1" at symbol-space (0, 3.81) → schematic (100, 50 - 3.81) = (100, 46.19).
    pos = _resolve_pin_endpoint(str(tmp_sch), "R1", "1")
    assert pos is not None
    assert math.isclose(pos[0], 100.0, abs_tol=1e-3)
    assert math.isclose(pos[1], 46.19, abs_tol=1e-3)


def test_parse_placed_and_lib_symbols(tmp_sch):
    from kicad_agent.schematic_io import _parse_sch_file
    tree = _parse_sch_file(str(tmp_sch))
    placed = _sch_placed_symbols(tree)
    assert "R1" in placed
    assert placed["R1"]["lib_id"] == "Device:R"
    assert placed["R1"]["x"] == 100.0
    lib = _sch_lib_symbols(tree)
    assert "Device:R" in lib
