"""Force-directed placement solver tests.

These exercise the solver as a pure data-in/data-out function — no PCB file,
no kipy, no kicad-cli. Same level the kicad-mcp-pro upstream tests it.
"""

from __future__ import annotations

import math

import pytest

from boardwright import placement as pl


def _config(**overrides):
    base = dict(iterations=200, board_w=80.0, board_h=60.0, max_seconds=5.0)
    base.update(overrides)
    return pl.ForceDirectedConfig(**base)


# ─────────────────────────────────────────────────────────────────────────────
# Sanity / contract
# ─────────────────────────────────────────────────────────────────────────────


def test_empty_input_returns_empty():
    out = pl.force_directed_placement([], [], _config())
    assert out == []


def test_single_component_does_not_crash():
    comps = [pl.PlacementComponent("R1", x=10.0, y=10.0)]
    out = pl.force_directed_placement(comps, [], _config())
    assert len(out) == 1
    assert out[0].ref == "R1"


def test_solver_returns_copies_not_mutating_input():
    comps = [pl.PlacementComponent("R1", x=5.0, y=5.0), pl.PlacementComponent("R2", x=10.0, y=10.0)]
    original_x = comps[0].x
    pl.force_directed_placement(comps, [], _config())
    assert comps[0].x == original_x  # input not mutated


# ─────────────────────────────────────────────────────────────────────────────
# Force behavior
# ─────────────────────────────────────────────────────────────────────────────


def test_repulsion_separates_overlapping_components():
    # Two components placed on top of each other should end up apart.
    comps = [
        pl.PlacementComponent("R1", x=20.0, y=20.0, w=4.0, h=4.0),
        pl.PlacementComponent("R2", x=20.0, y=20.0, w=4.0, h=4.0),
    ]
    out = pl.force_directed_placement(comps, [], _config())
    dist = math.hypot(out[0].x - out[1].x, out[0].y - out[1].y)
    assert dist > 4.0, f"Expected components to be pushed apart; ended {dist:.2f}mm apart"


def test_attraction_brings_connected_components_closer():
    """Two unconnected components should drift further than two on the same net."""
    cfg = _config()

    free = [
        pl.PlacementComponent("A", x=10.0, y=20.0),
        pl.PlacementComponent("B", x=70.0, y=20.0),
    ]
    free_out = pl.force_directed_placement(free, [], cfg)
    free_dist = math.hypot(free_out[0].x - free_out[1].x, free_out[0].y - free_out[1].y)

    bonded = [
        pl.PlacementComponent("A", x=10.0, y=20.0),
        pl.PlacementComponent("B", x=70.0, y=20.0),
    ]
    nets = [pl.PlacementNet("NET1", refs=["A", "B"], weight=2.0)]
    bonded_out = pl.force_directed_placement(bonded, nets, cfg)
    bonded_dist = math.hypot(bonded_out[0].x - bonded_out[1].x, bonded_out[0].y - bonded_out[1].y)

    assert bonded_dist < free_dist, (
        f"Connected components ({bonded_dist:.2f}mm) should be closer than unconnected "
        f"({free_dist:.2f}mm)"
    )


def test_fixed_components_do_not_move():
    cfg = _config()
    comps = [
        pl.PlacementComponent("J1", x=10.0, y=10.0, fixed=True),
        pl.PlacementComponent("U1", x=15.0, y=15.0),
    ]
    out = pl.force_directed_placement(comps, [], cfg)
    j1 = next(c for c in out if c.ref == "J1")
    assert j1.x == 10.0
    assert j1.y == 10.0


def test_solver_keeps_components_inside_board():
    cfg = _config(board_w=50.0, board_h=40.0, k_repel=200.0)  # strong repulsion
    comps = [
        pl.PlacementComponent(f"R{i}", x=25.0, y=20.0, w=3.0, h=3.0)
        for i in range(8)
    ]
    out = pl.force_directed_placement(comps, [], cfg)
    for c in out:
        assert -0.01 <= c.x <= cfg.board_w + 0.01, f"{c.ref} x={c.x} out of board"
        assert -0.01 <= c.y <= cfg.board_h + 0.01, f"{c.ref} y={c.y} out of board"


def test_keepout_region_is_avoided():
    cfg = _config(
        board_w=60.0,
        board_h=60.0,
        keepout_regions=[(20.0, 20.0, 40.0, 40.0)],  # central forbidden box
    )
    # Drop a component inside the keepout — solver must move it out.
    comps = [pl.PlacementComponent("R1", x=30.0, y=30.0, w=2.0, h=2.0)]
    out = pl.force_directed_placement(comps, [], cfg)
    c = out[0]
    eps = 1e-6
    overlaps_keepout = (
        c.x + c.w / 2 > 20.0 + eps and c.x - c.w / 2 < 40.0 - eps
        and c.y + c.h / 2 > 20.0 + eps and c.y - c.h / 2 < 40.0 - eps
    )
    assert not overlaps_keepout, f"Component overlaps keep-out at ({c.x}, {c.y})"


# ─────────────────────────────────────────────────────────────────────────────
# Quality metric: total wirelength should not get worse
# ─────────────────────────────────────────────────────────────────────────────


def test_wirelength_decreases_for_chain_topology():
    """Linear chain A-B-C-D-E in random order should fold tighter after solving."""
    refs = ["A", "B", "C", "D", "E"]
    # Scattered initial positions
    initial = [
        pl.PlacementComponent("A", x=70.0, y=10.0),
        pl.PlacementComponent("B", x=10.0, y=50.0),
        pl.PlacementComponent("C", x=70.0, y=50.0),
        pl.PlacementComponent("D", x=10.0, y=10.0),
        pl.PlacementComponent("E", x=40.0, y=30.0),
    ]
    nets = [pl.PlacementNet(f"N{i}", refs=[refs[i], refs[i + 1]], weight=2.0)
            for i in range(len(refs) - 1)]

    before = pl.total_wire_length(initial, nets)
    out = pl.force_directed_placement(initial, nets, _config(iterations=400))
    after = pl.total_wire_length(out, nets)

    assert after < before, f"Solver made wirelength worse: {before:.1f} → {after:.1f}"


def test_grid_snap_applied_to_final_positions():
    cfg = _config(grid_mm=0.5, iterations=100)
    comps = [pl.PlacementComponent(f"R{i}", x=10.0 + i * 4.0, y=10.0) for i in range(4)]
    out = pl.force_directed_placement(comps, [], cfg)
    for c in out:
        # 0.5mm grid → x and y must be multiples of 0.5
        assert abs(round(c.x * 2) - c.x * 2) < 1e-6, f"{c.ref} x={c.x} not on 0.5mm grid"
        assert abs(round(c.y * 2) - c.y * 2) < 1e-6, f"{c.ref} y={c.y} not on 0.5mm grid"


# ─────────────────────────────────────────────────────────────────────────────
# Tool integration
# ─────────────────────────────────────────────────────────────────────────────


def test_auto_arrange_schema_exposes_force_directed():
    from boardwright import dispatcher
    schema = dispatcher.ALL_SCHEMAS["auto_arrange"]
    enum = schema["input_schema"]["properties"]["strategy"]["enum"]
    assert "force_directed" in enum
    assert "connectivity" in enum
    assert "grid" in enum


def test_auto_arrange_returns_error_without_project():
    from boardwright.tools import pcb_layout
    out = pcb_layout.auto_arrange(strategy="force_directed")
    assert out["status"] == "error"
    assert "set_project" in out["message"].lower()


def test_total_wire_length_zero_for_no_nets():
    comps = [pl.PlacementComponent("A", x=0, y=0), pl.PlacementComponent("B", x=10, y=10)]
    assert pl.total_wire_length(comps, []) == 0.0
