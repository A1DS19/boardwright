"""Force-directed component placement.

A spring-embedder for PCB component layout:

- Connected components attract each other (Hooke's-law spring).
- All components repel each other (Coulomb-style 1/r²).
- Soft boundary walls push components inward.
- Velocity damping with a cooling temperature for convergence.
- Optional rectangular keep-out regions are honored.

The solver is unit-free; callers pass mm in and get mm out. Pure stdlib —
no NumPy required.

Algorithm adapted from kicad-mcp-pro (MIT, by oaslananka), simplified slightly
and tightened for our tool surface. Same physics; smaller surface area.
"""

from __future__ import annotations

import math
import time
from dataclasses import dataclass, field


@dataclass
class PlacementComponent:
    """A movable item — typically a footprint reference."""

    ref: str
    x: float
    y: float
    w: float = 2.0   # bounding-box width in mm
    h: float = 2.0   # bounding-box height in mm
    fixed: bool = False  # connectors / mounting holes that must not move


@dataclass
class PlacementNet:
    """A net pulls a set of component refs together."""

    name: str
    refs: list[str] = field(default_factory=list)
    weight: float = 1.0  # higher = pulled closer


@dataclass
class ForceDirectedConfig:
    iterations: int = 300
    k_spring: float = 0.4    # attraction coefficient (Hooke)
    k_repel: float = 80.0    # repulsion coefficient (Coulomb)
    k_wall: float = 5.0      # boundary inward push
    damping: float = 0.85    # velocity damping per step
    min_dist: float = 0.5    # numerical floor to avoid div/0
    board_w: float = 100.0   # mm, soft boundary
    board_h: float = 80.0    # mm, soft boundary
    seed: int = 42
    grid_mm: float = 0.5     # final-pass snap grid
    max_seconds: float = 10.0
    keepout_regions: list[tuple[float, float, float, float]] = field(default_factory=list)


# ─────────────────────────────────────────────────────────────────────────────
# Geometry helpers
# ─────────────────────────────────────────────────────────────────────────────


def _snap(value: float, grid_mm: float) -> float:
    if grid_mm <= 0:
        return value
    return round(round(value / grid_mm) * grid_mm, 4)


def _bounds(x: float, y: float, c: PlacementComponent) -> tuple[float, float, float, float]:
    return x - c.w / 2.0, y - c.h / 2.0, x + c.w / 2.0, y + c.h / 2.0


def _inside_board(x: float, y: float, c: PlacementComponent, cfg: ForceDirectedConfig) -> bool:
    left, top, right, bottom = _bounds(x, y, c)
    return left >= 0.0 and top >= 0.0 and right <= cfg.board_w and bottom <= cfg.board_h


def _hits_keepout(x: float, y: float, c: PlacementComponent, cfg: ForceDirectedConfig) -> bool:
    left, top, right, bottom = _bounds(x, y, c)
    for x1, y1, x2, y2 in cfg.keepout_regions:
        kl, kt = min(x1, x2), min(y1, y2)
        kr, kb = max(x1, x2), max(y1, y2)
        if not (right <= kl or left >= kr or bottom <= kt or top >= kb):
            return True
    return False


def _resolve(
    x: float,
    y: float,
    c: PlacementComponent,
    cfg: ForceDirectedConfig,
    *,
    snap_to_grid: bool,
) -> tuple[float, float]:
    """Find the nearest valid position to (x, y) for component c.

    Walks an outward spiral; falls back to a clamped position if the spiral
    exhausts. Optionally snaps to the configured grid.
    """
    def normalize(cx: float, cy: float) -> tuple[float, float]:
        if snap_to_grid:
            return _snap(cx, cfg.grid_mm), _snap(cy, cfg.grid_mm)
        return cx, cy

    candidate = normalize(x, y)
    if _inside_board(*candidate, c, cfg) and not _hits_keepout(*candidate, c, cfg):
        return candidate

    # Step needs to be large enough to clear common keepouts in ~32 rings.
    step = max(cfg.grid_mm, 1.0)
    phase = cfg.seed % 4
    dirs = [(1, 0), (0, 1), (-1, 0), (0, -1)]
    dirs = dirs[phase:] + dirs[:phase]

    for ring in range(1, 65):
        for dx, dy in dirs:
            for offset in range(-ring, ring + 1):
                if dx == 0:
                    candidate = normalize(x + offset * step, y + dy * ring * step)
                else:
                    candidate = normalize(x + dx * ring * step, y + offset * step)
                if _inside_board(*candidate, c, cfg) and not _hits_keepout(*candidate, c, cfg):
                    return candidate

    safe_x = min(max(c.w / 2.0, x), cfg.board_w - c.w / 2.0)
    safe_y = min(max(c.h / 2.0, y), cfg.board_h - c.h / 2.0)
    return normalize(safe_x, safe_y)


# ─────────────────────────────────────────────────────────────────────────────
# Core solver
# ─────────────────────────────────────────────────────────────────────────────


def force_directed_placement(
    components: list[PlacementComponent],
    nets: list[PlacementNet],
    cfg: ForceDirectedConfig | None = None,
) -> list[PlacementComponent]:
    """Run the spring-embedder and return new component positions.

    Components are returned as fresh copies; the input list is not mutated.
    Fixed components stay where they are but still exert forces on others.
    """
    if cfg is None:
        cfg = ForceDirectedConfig()

    comps = [PlacementComponent(**c.__dict__) for c in components]
    if not comps:
        return comps

    ref_idx = {c.ref: i for i, c in enumerate(comps)}

    # Adjacency built once: ref → list of (neighbor_ref, weight)
    adj: dict[str, list[tuple[str, float]]] = {c.ref: [] for c in comps}
    for net in nets:
        for r1 in net.refs:
            for r2 in net.refs:
                if r1 != r2 and r1 in adj:
                    adj[r1].append((r2, net.weight))

    vx = [0.0] * len(comps)
    vy = [0.0] * len(comps)
    step_size = min(cfg.board_w, cfg.board_h) * 0.05
    started = time.perf_counter()

    for it in range(cfg.iterations):
        if time.perf_counter() - started >= cfg.max_seconds:
            break
        # Cooling: max-displacement shrinks linearly with iterations
        temperature = step_size * (1.0 - it / cfg.iterations) + 0.1

        fx = [0.0] * len(comps)
        fy = [0.0] * len(comps)

        # Repulsion: every pair
        for i in range(len(comps)):
            for j in range(i + 1, len(comps)):
                dx = comps[i].x - comps[j].x
                dy = comps[i].y - comps[j].y
                if math.hypot(dx, dy) < cfg.min_dist:
                    # Coincident or near-coincident: pick a deterministic
                    # nonzero direction so the pair doesn't get stuck.
                    dx = float(i - j) or 1.0
                    dy = float(i + j) * 0.5 + 0.5
                dist = max(math.hypot(dx, dy), cfg.min_dist)
                # If bounding boxes would overlap, ramp up repulsion sharply
                min_clear = (comps[i].w + comps[j].w) * 0.5 + 1.0
                k = cfg.k_repel * ((min_clear / dist) ** 2 if dist < min_clear else 1.0)
                force = k / (dist * dist)
                nx, ny = dx / dist, dy / dist
                fx[i] += force * nx
                fy[i] += force * ny
                fx[j] -= force * nx
                fy[j] -= force * ny

        # Attraction: connected pairs (Hooke)
        for i, comp in enumerate(comps):
            for neighbor_ref, weight in adj[comp.ref]:
                ni = ref_idx.get(neighbor_ref)
                if ni is None:
                    continue
                dx = comps[ni].x - comp.x
                dy = comps[ni].y - comp.y
                dist = max(math.hypot(dx, dy), cfg.min_dist)
                force = cfg.k_spring * weight * dist
                nx, ny = dx / dist, dy / dist
                fx[i] += force * nx
                fy[i] += force * ny

        # Wall pressure (soft boundary)
        for i, comp in enumerate(comps):
            if comp.x < comp.w:
                fx[i] += cfg.k_wall / max(comp.x, 0.01)
            right_gap = cfg.board_w - comp.x - comp.w
            if right_gap < comp.w:
                fx[i] -= cfg.k_wall / max(right_gap, 0.01)
            if comp.y < comp.h:
                fy[i] += cfg.k_wall / max(comp.y, 0.01)
            bottom_gap = cfg.board_h - comp.y - comp.h
            if bottom_gap < comp.h:
                fy[i] -= cfg.k_wall / max(bottom_gap, 0.01)

        # Integrate
        for i, comp in enumerate(comps):
            if comp.fixed:
                vx[i] = vy[i] = 0.0
                continue
            vx[i] = (vx[i] + fx[i]) * cfg.damping
            vy[i] = (vy[i] + fy[i]) * cfg.damping
            speed = math.hypot(vx[i], vy[i])
            if speed > temperature:
                vx[i] *= temperature / speed
                vy[i] *= temperature / speed
            comp.x, comp.y = _resolve(
                comp.x + vx[i],
                comp.y + vy[i],
                comp,
                cfg,
                snap_to_grid=False,
            )

    # Final pass: snap to grid (and resolve any residual keepout overlap)
    for c in comps:
        if not c.fixed:
            c.x, c.y = _resolve(c.x, c.y, c, cfg, snap_to_grid=True)

    return comps


def total_wire_length(comps: list[PlacementComponent], nets: list[PlacementNet]) -> float:
    """Sum of pairwise distances along each net — a useful quality metric for tests."""
    by_ref = {c.ref: c for c in comps}
    total = 0.0
    for net in nets:
        present = [by_ref[r] for r in net.refs if r in by_ref]
        for i in range(len(present)):
            for j in range(i + 1, len(present)):
                total += math.hypot(present[i].x - present[j].x, present[i].y - present[j].y)
    return total
