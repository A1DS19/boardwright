"""PCB layout tools (Phase 4) + copper pour zones (Phase 5)."""

from __future__ import annotations

import json
import math
import tempfile
from pathlib import Path

from ..backends import _kicad, _run_cli, _try_kipy
from ..state import _pcb_file, _project_state


def set_board_outline(
    width_mm: float,
    height_mm: float,
    corner_radius_mm: float = 1.0,
    origin_x_mm: float = 0,
    origin_y_mm: float = 0,
) -> dict:
    try:
        kicad = _kicad()
        from kipy import board_types as bt
        from kipy.geometry import Vector2
        import math

        board = kicad.get_board()
        edge = bt.BoardLayer.BL_Edge_Cuts

        ox, oy = origin_x_mm, origin_y_mm
        w, h, r = width_mm, height_mm, max(0.0, corner_radius_mm)
        r = min(r, w / 2, h / 2)

        def seg(x1, y1, x2, y2):
            s = bt.BoardSegment()
            s.start = Vector2.from_xy_mm(x1, y1)
            s.end = Vector2.from_xy_mm(x2, y2)
            s.layer = edge
            return s

        def arc(cx, cy, sx, sy, ex, ey):
            # mid at 45° between start-angle and end-angle around center
            a1 = math.atan2(sy - cy, sx - cx)
            a2 = math.atan2(ey - cy, ex - cx)
            # pick shorter sweep
            d = a2 - a1
            while d > math.pi: d -= 2 * math.pi
            while d < -math.pi: d += 2 * math.pi
            am = a1 + d / 2
            a = bt.BoardArc()
            a.start = Vector2.from_xy_mm(sx, sy)
            a.mid = Vector2.from_xy_mm(cx + r * math.cos(am), cy + r * math.sin(am))
            a.end = Vector2.from_xy_mm(ex, ey)
            a.layer = edge
            return a

        items = []
        if r == 0:
            items += [
                seg(ox, oy,     ox + w, oy),
                seg(ox + w, oy, ox + w, oy + h),
                seg(ox + w, oy + h, ox, oy + h),
                seg(ox, oy + h, ox, oy),
            ]
        else:
            items += [
                seg(ox + r, oy,         ox + w - r, oy),
                seg(ox + w, oy + r,     ox + w,     oy + h - r),
                seg(ox + w - r, oy + h, ox + r,     oy + h),
                seg(ox, oy + h - r,     ox,         oy + r),
                arc(ox + w - r, oy + r,       ox + w - r, oy,        ox + w, oy + r),
                arc(ox + w - r, oy + h - r,   ox + w, oy + h - r,    ox + w - r, oy + h),
                arc(ox + r, oy + h - r,       ox + r, oy + h,        ox, oy + h - r),
                arc(ox + r, oy + r,           ox, oy + r,            ox + r, oy),
            ]

        board.create_items(items)
        board.save()

        _project_state["board_outline"] = {
            "width": w, "height": h, "corner_radius": r,
            "origin_x": ox, "origin_y": oy,
        }
        return {
            "status": "ok", "source": "kipy",
            "board_area_mm2": round(w * h, 2),
            "segments_created": len(items),
            "note": "Outline added to Edge.Cuts. Re-calling stacks extra shapes — delete existing outline in pcbnew first.",
        }

    except ImportError:
        pass
    except Exception as e:
        # Fall through to file-write fallback on any kipy error — pcbnew may be
        # closed, or the API version mismatch ("no handler available"), or the
        # PCB Editor window isn't open.
        pass

    # File-write fallback — pcbnew must be closed on this file.
    pcb = _pcb_file()
    if pcb:
        from . import _pcb_writer as pw
        n = pw.append_rounded_rect_outline(
            pcb, width_mm, height_mm, corner_radius_mm,
            origin_x_mm, origin_y_mm,
        )
        _project_state["board_outline"] = {
            "width": width_mm, "height": height_mm,
            "corner_radius": corner_radius_mm,
            "origin_x": origin_x_mm, "origin_y": origin_y_mm,
        }
        return {
            "status": "ok", "source": "file",
            "board_area_mm2": round(width_mm * height_mm, 2),
            "segments_created": n,
            "note": "Wrote Edge.Cuts directly to .kicad_pcb. Ensure pcbnew is closed — otherwise it will overwrite on next save. Re-call to stack extra shapes; use strip_edge_cuts first to reset.",
        }

    _project_state["board_outline"] = {
        "width": width_mm, "height": height_mm,
        "corner_radius": corner_radius_mm,
        "origin_x": origin_x_mm, "origin_y": origin_y_mm,
    }
    return {
        "status": "ok", "source": "stub",
        "board_area_mm2": round(width_mm * height_mm, 2),
        "outline": _project_state["board_outline"],
    }


def add_mounting_holes(
    drill_mm: float = 3.2,
    pad_mm: float = 6.0,
    positions: str = "corners",
    corner_offset_mm: float = 3.5,
) -> dict:
    outline = _project_state.get("board_outline")
    if not outline:
        return {"status": "error", "message": "Set board outline before adding mounting holes."}
    w, h = outline["width"], outline["height"]
    d = corner_offset_mm
    hole_positions = [
        {"ref": "H1", "x": d,   "y": d},
        {"ref": "H2", "x": w-d, "y": d},
        {"ref": "H3", "x": w-d, "y": h-d},
        {"ref": "H4", "x": d,   "y": h-d},
    ]
    for hp in hole_positions:
        _project_state["placements"][hp["ref"]] = {
            "x": hp["x"], "y": hp["y"],
            "rotation": 0, "layer": "F.Cu",
            "drill_mm": drill_mm, "pad_mm": pad_mm,
        }
    return {"status": "ok", "holes_added": 4, "positions": hole_positions}


def place_footprint(
    reference: str,
    x_mm: float,
    y_mm: float,
    rotation_deg: float = 0,
    layer: str = "F.Cu",
) -> dict:
    """
    Move a footprint to the given position via kipy IPC.
    KiCad must be running with the PCB open. Falls back to in-memory stub if not.
    """
    def _kipy_place():
        kicad = _kicad()
        from kipy.geometry import Vector2, Angle
        from kipy.board_types import BoardLayer

        board = kicad.get_board()
        fps = board.get_footprints()
        fp = next(
            (f for f in fps if f.reference_field.text.value == reference),
            None,
        )
        if fp is None:
            return {"status": "error", "message": f"Footprint '{reference}' not found on board."}

        old_pos = fp.position
        fp.position = Vector2.from_xy_mm(x_mm, y_mm)
        fp.orientation = Angle.from_degrees(rotation_deg)
        fp.layer = BoardLayer.BL_B_Cu if layer == "B.Cu" else BoardLayer.BL_F_Cu

        board.update_items(fp)
        board.save()
        return {
            "status": "ok",
            "source": "kipy",
            "reference": reference,
            "x_mm": x_mm,
            "y_mm": y_mm,
            "rotation_deg": rotation_deg,
            "layer": layer,
            "from": {
                "x_mm": old_pos.x / 1_000_000,
                "y_mm": old_pos.y / 1_000_000,
            },
        }

    result = _try_kipy(_kipy_place)
    if result is not None:
        return result

    # File-write fallback
    pcb = _pcb_file()
    if pcb:
        from . import _pcb_writer as pw
        hit = pw.move_footprint(pcb, reference, x_mm, y_mm, rotation_deg)
        if not hit:
            return {"status": "error",
                    "message": f"Footprint '{reference}' not found in .kicad_pcb."}
        _project_state["placements"][reference] = {
            "x": x_mm, "y": y_mm, "rotation": rotation_deg, "layer": layer,
        }
        return {
            "status": "ok", "source": "file",
            "reference": reference, "x_mm": x_mm, "y_mm": y_mm,
            "rotation_deg": rotation_deg, "layer": layer,
            "note": "Wrote placement to .kicad_pcb. Ensure pcbnew is closed.",
        }

    _project_state["placements"][reference] = {
        "x": x_mm, "y": y_mm, "rotation": rotation_deg, "layer": layer,
    }
    return {
        "status": "ok", "source": "stub",
        "note": "No pcb_file set — call set_project first.",
        "reference": reference, "x_mm": x_mm, "y_mm": y_mm,
    }


def get_ratsnest(net_filter: str | None = None) -> dict:
    """Return nets and unconnected count via kipy IPC."""
    def _kipy_ratsnest():
        kicad = _kicad()
        board = kicad.get_board()
        nets = board.get_nets()

        net_list = [
            {"name": n.name, "net_code": n.net_code}
            for n in nets
            if not net_filter or net_filter.lower() in n.name.lower()
        ]

        unconnected_count = None
        pcb = _pcb_file()
        if pcb:
            with tempfile.NamedTemporaryFile(suffix=".json", delete=False) as f:
                out = f.name
            rc, _, _ = _run_cli("pcb", "drc", "--format", "json",
                                 "--severity-error", "--output", out, pcb)
            try:
                raw = json.loads(Path(out).read_text())
                unconnected_count = len(raw.get("unconnected_items", []))
            except (json.JSONDecodeError, OSError):
                pass
            finally:
                Path(out).unlink(missing_ok=True)

        return {
            "status": "ok",
            "source": "kipy",
            "net_count": len(net_list),
            "unconnected_count": unconnected_count,
            "nets": net_list,
        }

    result = _try_kipy(_kipy_ratsnest)
    if result is not None:
        return result

    # Stub fallback
    placed = set(_project_state["placements"].keys())
    unplaced = set(_project_state["bom"].keys()) - placed
    return {
        "status": "ok",
        "source": "stub",
        "note": "KiCad not running — open PCB in KiCad for live ratsnest",
        "unconnected_count": None,
        "unplaced_components": list(unplaced),
        "nets": [],
    }


def add_keepout_zone(
    outline_mm: list[list[float]],
    no_copper: bool = True,
    no_vias: bool = True,
    no_footprints: bool = False,
    reason: str = "",
) -> dict:
    _project_state["zones"].append({
        "type": "keepout",
        "outline_mm": outline_mm,
        "no_copper": no_copper,
        "no_vias": no_vias,
        "no_footprints": no_footprints,
        "reason": reason,
    })
    return {"status": "ok", "reason": reason}


def add_zone(
    net_name: str,
    layer: str,
    outline_mm: list[list[float]],
    clearance_mm: float = 0.3,
    min_width_mm: float = 0.25,
    fill_mode: str = "solid",
    priority: int = 0,
) -> dict:
    """Add a copper pour zone. Writes directly to .kicad_pcb (pcbnew must be closed)."""
    pcb = _pcb_file()
    if pcb:
        from . import _pcb_writer as pw
        pts = [(float(p[0]), float(p[1])) for p in outline_mm]
        r = pw.append_zone(pcb, net_name, layer, pts,
                           clearance_mm=clearance_mm, min_width_mm=min_width_mm)
        if r.get("status") == "ok":
            r["source"] = "file"
            r["note"] = "Wrote zone to .kicad_pcb. Open in pcbnew and press B to fill."
            _project_state["zones"].append({
                "type": "copper", "net_name": net_name, "layer": layer,
                "outline_mm": outline_mm, "clearance_mm": clearance_mm,
                "min_width_mm": min_width_mm, "fill_mode": fill_mode,
                "priority": priority, "filled": False,
            })
            return r
        return r

    _project_state["zones"].append({
        "type": "copper", "net_name": net_name, "layer": layer,
        "outline_mm": outline_mm, "clearance_mm": clearance_mm,
        "min_width_mm": min_width_mm, "fill_mode": fill_mode,
        "priority": priority, "filled": False,
    })
    return {"status": "ok", "source": "stub", "net_name": net_name, "layer": layer}


def fill_zones() -> dict:
    """Refill all copper zones via kipy IPC."""
    def _kipy_fill():
        kicad = _kicad()
        board = kicad.get_board()
        board.refill_zones()
        board.save()
        zone_count = len(board.get_zones())
        return {"status": "ok", "source": "kipy", "zones_filled": zone_count}

    result = _try_kipy(_kipy_fill)
    if result is not None:
        return result

    # Stub fallback
    filled = sum(1 for z in _project_state["zones"] if z.get("type") == "copper")
    for z in _project_state["zones"]:
        if z.get("type") == "copper":
            z["filled"] = True
    return {"status": "ok", "source": "stub",
            "note": "KiCad not running — zone fill recorded in memory only",
            "zones_filled": filled}


def sync_pcb_from_schematic() -> dict:
    """
    Trigger "Update PCB from Schematic" in the open PCB Editor via kipy.run_action.
    Equivalent to pressing F8 in pcbnew. Requires the PCB Editor window to be open.
    Uses kipy's unstable run_action API — action name may change across KiCad versions.
    """
    try:
        kicad = _kicad()
        result = kicad.run_action("pcbnew.EditorControl.updatePcbFromSchematic")
        return {"status": "ok", "source": "kipy", "run_action_result": str(result),
                "note": "KiCad may show a confirmation dialog that requires manual acknowledgement."}
    except ImportError:
        return {"status": "error", "message": "kipy not installed."}
    except Exception as e:
        if "connect" in str(e).lower() or "socket" in str(e).lower():
            return {"status": "error",
                    "message": "KiCad IPC unavailable. Ensure: (1) KiCad main app is open, (2) the .kicad_pcb is open in the PCB Editor window, (3) Preferences → Plugins → 'Enable KiCad API' is checked (restart KiCad if you just enabled it)."}
        return {"status": "error",
                "message": f"run_action failed: {e}. Fallback: press F8 in pcbnew manually."}


def save_board() -> dict:
    """Save the currently open PCB via kipy IPC."""
    try:
        kicad = _kicad()
        board = kicad.get_board()
        board.save()
        return {"status": "ok", "source": "kipy"}
    except ImportError:
        return {"status": "error", "message": "kipy not installed — cannot save board."}
    except Exception as e:
        if "connect" in str(e).lower() or "socket" in str(e).lower():
            return {"status": "error",
                    "message": "KiCad IPC unavailable. Ensure: (1) KiCad main app is open, (2) the .kicad_pcb is open in the PCB Editor window, (3) Preferences → Plugins → 'Enable KiCad API' is checked (restart KiCad if you just enabled it)."}
        return {"status": "error", "message": f"kipy error: {e}"}


def get_pad_positions(reference: str) -> dict:
    """Return absolute pad positions for a placed footprint on the PCB."""
    try:
        kicad = _kicad()
        import math
        board = kicad.get_board()
        fp = next((f for f in board.get_footprints()
                   if f.reference_field.text.value == reference), None)
        if fp is None:
            return {"status": "error", "message": f"Footprint '{reference}' not found on board."}

        theta = fp.orientation.degrees * math.pi / 180.0
        cos_t, sin_t = math.cos(theta), math.sin(theta)
        fp_x, fp_y = fp.position.x, fp.position.y

        pads = []
        for pad in fp.pads:
            lx, ly = pad.position.x, pad.position.y
            ax = fp_x + (lx * cos_t - ly * sin_t)
            ay = fp_y + (lx * sin_t + ly * cos_t)
            pads.append({
                "number": pad.number,
                "net": pad.net.name if pad.net else "",
                "x_mm": round(ax / 1_000_000, 4),
                "y_mm": round(ay / 1_000_000, 4),
            })

        return {
            "status": "ok", "source": "kipy",
            "reference": reference,
            "footprint_position_mm": {
                "x": round(fp_x / 1_000_000, 4),
                "y": round(fp_y / 1_000_000, 4),
                "rotation_deg": fp.orientation.degrees,
            },
            "pads": pads,
        }

    except ImportError:
        pass
    except Exception as e:
        if "connect" not in str(e).lower() and "socket" not in str(e).lower():
            return {"status": "error", "message": f"kipy error: {e}"}

    # File-read fallback
    pcb = _pcb_file()
    if not pcb:
        return {"status": "error", "message": "No pcb_file set. Call set_project first."}
    from . import _pcb_writer as pw
    place = pw.read_footprint_placement(pcb, reference)
    if place is None:
        return {"status": "error", "message": f"Footprint '{reference}' not found in .kicad_pcb."}
    pads = pw.read_pad_positions(pcb, reference)
    return {
        "status": "ok", "source": "file",
        "reference": reference,
        "footprint_position_mm": {
            "x": place["x"], "y": place["y"], "rotation_deg": place["rotation"],
        },
        "pads": pads,
    }


def strip_edge_cuts() -> dict:
    """Remove all Edge.Cuts outlines from the PCB (file write). Returns count removed."""
    pcb = _pcb_file()
    if not pcb:
        return {"status": "error", "message": "No pcb_file set."}
    from . import _pcb_writer as pw
    n = pw.strip_edge_cuts(pcb)
    return {"status": "ok", "removed": n}


def strip_zones() -> dict:
    """Remove all copper pour zones from the PCB (file write). Returns count removed."""
    pcb = _pcb_file()
    if not pcb:
        return {"status": "error", "message": "No pcb_file set."}
    from . import _pcb_writer as pw
    n = pw.strip_zones(pcb)
    return {"status": "ok", "removed": n}


def strip_tracks() -> dict:
    """Remove all track segments, arcs, and vias from the PCB (file write). Returns count removed."""
    pcb = _pcb_file()
    if not pcb:
        return {"status": "error", "message": "No pcb_file set."}
    from . import _pcb_writer as pw
    n = pw.strip_tracks(pcb)
    return {"status": "ok", "removed": n}


# ─── Power net heuristic ───────────────────────────────────────────────────

_POWER_PATTERNS = {"GND", "VCC", "VDD", "VSS", "VBUS", "VBAT", "VIN"}


def _is_power_net(name: str) -> bool:
    """Return True for nets that are power/ground (not useful for grouping)."""
    n = name.lstrip("/").upper()
    if n in _POWER_PATTERNS:
        return True
    # +3V3, +5V, +12V, +3.3V, etc.
    if n.startswith("+") and any(c.isdigit() for c in n):
        return True
    return False


# ─── Bounding box from footprint pad data ──────────────────────────────────

def _footprint_bbox(fp: dict) -> tuple[float, float, float, float]:
    """Return (half_w, half_h, abs_min_x, abs_min_y, abs_max_x, abs_max_y)
    for a footprint dict from read_all_footprints. Accounts for rotation."""
    pads = fp["pads"]
    if not pads:
        return 1.0, 1.0  # minimum fallback

    rot = math.radians(fp["rotation"])
    cos_t, sin_t = math.cos(rot), math.sin(rot)

    xs, ys = [], []
    for p in pads:
        lx, ly = p["local_x"], p["local_y"]
        pw, ph = p["pad_w"] / 2, p["pad_h"] / 2
        # Rotated corners of pad extent
        ax = fp["x"] + (lx * cos_t - ly * sin_t)
        ay = fp["y"] + (lx * sin_t + ly * cos_t)
        xs.extend([ax - pw, ax + pw])
        ys.extend([ay - ph, ay + ph])

    return min(xs), min(ys), max(xs), max(ys)


def _bbox_size(fp: dict) -> tuple[float, float]:
    """Return (width, height) of footprint bounding box."""
    x1, y1, x2, y2 = _footprint_bbox(fp)
    return x2 - x1, y2 - y1


def _bboxes_overlap(a: tuple, b: tuple) -> bool:
    """Check if two (x1,y1,x2,y2) bounding boxes overlap."""
    return a[0] < b[2] and a[2] > b[0] and a[1] < b[3] and a[3] > b[1]


# ─── Auto-arrange ─────────────────────────────────────────────────────────

def _compute_arrangement(
    footprints: list[dict], margin_mm: float, strategy: str,
) -> list[dict]:
    """Pure logic: returns list of {reference, x, y, rotation} placements."""
    if strategy == "grid":
        return _grid_arrange(footprints, margin_mm)
    return _connectivity_arrange(footprints, margin_mm)


def _grid_arrange(footprints: list[dict], margin: float) -> list[dict]:
    """Simple grid layout sorted by category then reference."""
    def sort_key(fp):
        ref = fp["reference"]
        prefix = "".join(c for c in ref if c.isalpha())
        num = "".join(c for c in ref if c.isdigit())
        order = {"U": 0, "J": 1, "Y": 2, "D": 3, "Q": 4,
                 "L": 5, "C": 6, "R": 7}
        return (order.get(prefix, 8), int(num) if num else 0)

    sorted_fps = sorted(footprints, key=sort_key)
    placements = []
    x, y = margin, margin
    row_height = 0.0
    max_row_width = 90.0  # reasonable default max width

    for fp in sorted_fps:
        w, h = _bbox_size(fp)
        w += margin
        h += margin

        if x + w > max_row_width and x > margin:
            x = margin
            y += row_height
            row_height = 0.0

        placements.append({
            "reference": fp["reference"],
            "x": round(x + w / 2, 2),
            "y": round(y + h / 2, 2),
            "rotation": fp["rotation"],
        })
        x += w
        row_height = max(row_height, h)

    return placements


def _connectivity_arrange(footprints: list[dict], margin: float) -> list[dict]:
    """Place components grouped by netlist connectivity."""
    fp_map = {fp["reference"]: fp for fp in footprints}

    # Build connectivity: ref -> set of connected refs (signal nets only)
    net_to_refs: dict[str, set[str]] = {}
    for fp in footprints:
        for pad in fp["pads"]:
            net = pad["net"]
            if net and not _is_power_net(net):
                net_to_refs.setdefault(net, set()).add(fp["reference"])

    connectivity: dict[str, set[str]] = {ref: set() for ref in fp_map}
    for refs in net_to_refs.values():
        for r in refs:
            connectivity[r] |= refs - {r}

    # Also track power connections for decoupling cap detection
    power_net_to_refs: dict[str, set[str]] = {}
    for fp in footprints:
        for pad in fp["pads"]:
            net = pad["net"]
            if net and _is_power_net(net):
                power_net_to_refs.setdefault(net, set()).add(fp["reference"])

    # Classify components
    ics = [r for r in fp_map if r[0] == "U"]
    connectors = [r for r in fp_map if r[0] == "J"]
    crystals = [r for r in fp_map if r[0] in ("Y", "X")]
    switches = [r for r in fp_map if r.startswith("SW")]

    # Find decoupling caps: C* that shares a power net with an IC.
    # Each cap is assigned to at most one IC (the one it shares the most nets with).
    decoupling: dict[str, list[str]] = {ic: [] for ic in ics}
    caps = [r for r in fp_map if r[0] == "C"]
    assigned = set()
    # Sort ICs by signal connection count (main IC first) so it gets priority
    sorted_ics = sorted(ics, key=lambda r: len(connectivity.get(r, set())), reverse=True)
    for ic in sorted_ics:
        for cap in caps:
            if cap in assigned:
                continue
            shares_power = any(
                ic in refs and cap in refs
                for refs in power_net_to_refs.values()
            )
            if not shares_power:
                continue
            shares_signal = cap in connectivity.get(ic, set())
            cap_nets = {p["net"] for p in fp_map[cap]["pads"] if p["net"]}
            all_power = all(_is_power_net(n) for n in cap_nets)
            if shares_signal or all_power:
                decoupling[ic].append(cap)
                assigned.add(cap)

    remaining = [
        r for r in fp_map
        if r not in set(ics) | set(connectors) | set(crystals) | set(switches) | assigned
    ]

    # Placement state
    placements: list[dict] = []
    placed_bboxes: list[tuple[float, float, float, float]] = []
    placed_positions: dict[str, tuple[float, float]] = {}

    def _place(ref: str, cx: float, cy: float, rot: float | None = None):
        fp = fp_map[ref]
        r = rot if rot is not None else fp["rotation"]
        # Temporarily update fp position for bbox calculation
        old_x, old_y = fp["x"], fp["y"]
        fp["x"], fp["y"] = cx, cy
        bbox = _footprint_bbox(fp)
        fp["x"], fp["y"] = old_x, old_y

        # Check collisions and nudge
        cx, cy, bbox = _find_free_spot(cx, cy, bbox, placed_bboxes, margin)

        placements.append({"reference": ref, "x": round(cx, 2),
                           "y": round(cy, 2), "rotation": r})
        placed_bboxes.append(bbox)
        placed_positions[ref] = (cx, cy)

    def _find_free_spot(cx, cy, bbox, existing, m):
        """Nudge position until no overlap with existing bboxes."""
        w = bbox[2] - bbox[0]
        h = bbox[3] - bbox[1]
        for attempt in range(50):
            test_bbox = (cx - w / 2, cy - h / 2, cx + w / 2, cy + h / 2)
            collision = False
            for eb in existing:
                eb_padded = (eb[0] - m, eb[1] - m, eb[2] + m, eb[3] + m)
                if _bboxes_overlap(test_bbox, eb_padded):
                    collision = True
                    # Nudge away from collision
                    dx = (test_bbox[2] + test_bbox[0]) / 2 - (eb[2] + eb[0]) / 2
                    dy = (test_bbox[3] + test_bbox[1]) / 2 - (eb[3] + eb[1]) / 2
                    dist = math.hypot(dx, dy) or 1.0
                    nudge = max(w, h) * 0.5 + m
                    cx += dx / dist * nudge
                    cy += dy / dist * nudge
                    break
            if not collision:
                break
        final_bbox = (cx - w / 2, cy - h / 2, cx + w / 2, cy + h / 2)
        return cx, cy, final_bbox

    # Phase A: Place main IC at center (50, 35 is a reasonable starting point)
    center_x, center_y = 45.0, 35.0
    if ics:
        # Pick IC with most signal connections
        main_ic = max(ics, key=lambda r: len(connectivity.get(r, set())))
        _place(main_ic, center_x, center_y)
        other_ics = [r for r in ics if r != main_ic]
    else:
        main_ic = None
        other_ics = []

    # Phase B: Place decoupling caps around their IC
    if main_ic and decoupling.get(main_ic):
        ic_w, ic_h = _bbox_size(fp_map[main_ic])
        cap_list = decoupling[main_ic]
        angles = [i * 2 * math.pi / max(len(cap_list), 1) for i in range(len(cap_list))]
        radius = max(ic_w, ic_h) / 2 + margin + 2.0
        for cap_ref, angle in zip(cap_list, angles):
            cx = placed_positions[main_ic][0] + radius * math.cos(angle)
            cy = placed_positions[main_ic][1] + radius * math.sin(angle)
            _place(cap_ref, cx, cy)

    # Phase C: Place crystals near their connected IC
    for crystal in crystals:
        target_ic = None
        for ic in ics:
            if ic in connectivity.get(crystal, set()):
                target_ic = ic
                break
        if target_ic and target_ic in placed_positions:
            ix, iy = placed_positions[target_ic]
            ic_w, ic_h = _bbox_size(fp_map[target_ic])
            _place(crystal, ix - ic_w / 2 - margin - 3, iy + ic_h / 2 + margin)
        else:
            _place(crystal, center_x - 15, center_y + 10)

    # Phase D: Place other ICs
    for i, ic in enumerate(other_ics):
        offset = (i + 1) * 25
        _place(ic, center_x + offset, center_y)
        # Place their decoupling caps
        if decoupling.get(ic):
            ic_w, ic_h = _bbox_size(fp_map[ic])
            cap_list = decoupling[ic]
            angles = [j * 2 * math.pi / max(len(cap_list), 1) for j in range(len(cap_list))]
            radius = max(ic_w, ic_h) / 2 + margin + 2.0
            for cap_ref, angle in zip(cap_list, angles):
                cx = placed_positions[ic][0] + radius * math.cos(angle)
                cy = placed_positions[ic][1] + radius * math.sin(angle)
                _place(cap_ref, cx, cy)

    # Phase E: Place connectors along edges
    conn_y = margin + 5
    for i, conn in enumerate(connectors):
        conn_w, conn_h = _bbox_size(fp_map[conn])
        _place(conn, margin + conn_w / 2 + 2, conn_y)
        conn_y += conn_h + margin + 2

    # Phase F: Place switches
    for i, sw in enumerate(switches):
        target = None
        for neighbor in connectivity.get(sw, set()):
            if neighbor in placed_positions:
                target = neighbor
                break
        if target:
            tx, ty = placed_positions[target]
            _place(sw, tx, ty + 20 + i * 10)
        else:
            _place(sw, center_x + i * 15, center_y + 25)

    # Phase G: Place remaining passives near their most-connected placed neighbor
    remain_offset = 0
    for ref in remaining:
        best = None
        best_score = -1
        for neighbor in connectivity.get(ref, set()):
            if neighbor in placed_positions:
                score = len(connectivity.get(ref, set()) & connectivity.get(neighbor, set()))
                if score > best_score:
                    best = neighbor
                    best_score = score
        if best:
            bx, by = placed_positions[best]
            # Spread around the neighbor using angle offset
            angle = remain_offset * math.pi / 3
            radius = margin + 5
            _place(ref, bx + radius * math.cos(angle), by + radius * math.sin(angle))
        else:
            _place(ref, center_x + 20 + remain_offset * 6, center_y + 20)
        remain_offset += 1

    # Post-process: shift everything so nothing is at negative coordinates
    if placements:
        min_x = min(p["x"] for p in placements) - margin
        min_y = min(p["y"] for p in placements) - margin
        shift_x = max(0, margin - min_x)
        shift_y = max(0, margin - min_y)
        if shift_x > 0 or shift_y > 0:
            for p in placements:
                p["x"] = round(p["x"] + shift_x, 2)
                p["y"] = round(p["y"] + shift_y, 2)

    return placements


def auto_arrange(
    margin_mm: float = 3.0,
    strategy: str = "connectivity",
) -> dict:
    """Automatically arrange all footprints on the PCB based on netlist connectivity."""
    pcb = _pcb_file()
    if not pcb:
        return {"status": "error", "message": "No pcb_file set. Call set_project first."}

    from . import _pcb_writer as pw
    footprints = pw.read_all_footprints(pcb)
    if not footprints:
        return {"status": "error", "message": "No footprints found in PCB."}

    placements = _compute_arrangement(footprints, margin_mm, strategy)

    for p in placements:
        pw.move_footprint(pcb, p["reference"], p["x"], p["y"], p["rotation"])

    # Compute final bounding box
    all_x = [p["x"] for p in placements]
    all_y = [p["y"] for p in placements]

    return {
        "status": "ok",
        "source": "file",
        "strategy": strategy,
        "components_placed": len(placements),
        "bounding_box": {
            "x_min": round(min(all_x) - 5, 1),
            "y_min": round(min(all_y) - 5, 1),
            "x_max": round(max(all_x) + 5, 1),
            "y_max": round(max(all_y) + 5, 1),
        },
        "placements": placements,
        "note": "Wrote placements to .kicad_pcb. Ensure pcbnew is closed.",
    }


# ─── Fit board outline ────────────────────────────────────────────────────

def fit_board_outline(
    margin_mm: float = 2.0,
    corner_radius_mm: float = 1.0,
    snap_to_mm: float = 1.0,
) -> dict:
    """Calculate and draw a tight-fitting board outline around all placed components."""
    pcb = _pcb_file()
    if not pcb:
        return {"status": "error", "message": "No pcb_file set. Call set_project first."}

    from . import _pcb_writer as pw
    footprints = pw.read_all_footprints(pcb)
    if not footprints:
        return {"status": "error", "message": "No footprints found in PCB."}

    # Compute global bounding box across all footprints
    global_min_x = float("inf")
    global_min_y = float("inf")
    global_max_x = float("-inf")
    global_max_y = float("-inf")

    for fp in footprints:
        x1, y1, x2, y2 = _footprint_bbox(fp)
        global_min_x = min(global_min_x, x1)
        global_min_y = min(global_min_y, y1)
        global_max_x = max(global_max_x, x2)
        global_max_y = max(global_max_y, y2)

    # Apply margin
    origin_x = global_min_x - margin_mm
    origin_y = global_min_y - margin_mm
    width = global_max_x - global_min_x + 2 * margin_mm
    height = global_max_y - global_min_y + 2 * margin_mm

    # Snap dimensions up
    if snap_to_mm > 0:
        width = math.ceil(width / snap_to_mm) * snap_to_mm
        height = math.ceil(height / snap_to_mm) * snap_to_mm
        # Also snap origin to grid
        origin_x = math.floor(origin_x / snap_to_mm) * snap_to_mm
        origin_y = math.floor(origin_y / snap_to_mm) * snap_to_mm

    # Strip existing outline and write new one
    pw.strip_edge_cuts(pcb)
    segments = pw.append_rounded_rect_outline(
        pcb, width, height, corner_radius_mm, origin_x, origin_y,
    )

    _project_state["board_outline"] = {
        "width": width, "height": height,
        "corner_radius": corner_radius_mm,
        "origin_x": origin_x, "origin_y": origin_y,
    }

    return {
        "status": "ok",
        "source": "file",
        "width_mm": round(width, 2),
        "height_mm": round(height, 2),
        "origin_x_mm": round(origin_x, 2),
        "origin_y_mm": round(origin_y, 2),
        "corner_radius_mm": corner_radius_mm,
        "board_area_mm2": round(width * height, 2),
        "components_enclosed": len(footprints),
        "margin_applied_mm": margin_mm,
        "segments_created": segments,
        "note": "Replaced Edge.Cuts outline in .kicad_pcb. Ensure pcbnew is closed.",
    }


HANDLERS = {
    "set_board_outline":  set_board_outline,
    "add_mounting_holes": add_mounting_holes,
    "place_footprint":    place_footprint,
    "get_ratsnest":       get_ratsnest,
    "add_keepout_zone":   add_keepout_zone,
    "add_zone":           add_zone,
    "fill_zones":         fill_zones,
    "strip_edge_cuts":    strip_edge_cuts,
    "strip_zones":        strip_zones,
    "strip_tracks":       strip_tracks,
    "save_board":         save_board,
    "get_pad_positions":  get_pad_positions,
    "sync_pcb_from_schematic": sync_pcb_from_schematic,
    "auto_arrange":       auto_arrange,
    "fit_board_outline":  fit_board_outline,
}


TOOL_SCHEMAS = [
    {
        "name": "set_board_outline",
        "description": "Define the PCB board outline (Edge.Cuts layer).",
        "input_schema": {
            "type": "object",
            "properties": {
                "width_mm":             {"type": "number"},
                "height_mm":            {"type": "number"},
                "corner_radius_mm":     {"type": "number", "default": 1.0},
                "origin_x_mm":          {"type": "number", "default": 0},
                "origin_y_mm":          {"type": "number", "default": 0}
            },
            "required": ["width_mm", "height_mm"]
        }
    },
    {
        "name": "add_mounting_holes",
        "description": "Add mounting holes at standard positions (corners or custom).",
        "input_schema": {
            "type": "object",
            "properties": {
                "drill_mm":         {"type": "number", "default": 3.2},
                "pad_mm":           {"type": "number", "default": 6.0},
                "positions":        {
                    "type": "string",
                    "enum": ["corners", "custom"],
                    "default": "corners"
                },
                "corner_offset_mm": {"type": "number", "default": 3.5}
            }
        }
    },
    {
        "name": "place_footprint",
        "description": "Place a component footprint at exact coordinates on the PCB.",
        "input_schema": {
            "type": "object",
            "properties": {
                "reference":    {"type": "string"},
                "x_mm":         {"type": "number"},
                "y_mm":         {"type": "number"},
                "rotation_deg": {"type": "number", "default": 0},
                "layer":        {"type": "string", "enum": ["F.Cu", "B.Cu"], "default": "F.Cu"}
            },
            "required": ["reference", "x_mm", "y_mm"]
        }
    },
    {
        "name": "get_ratsnest",
        "description": (
            "Return the current ratsnest (list of unconnected nets with their endpoints). "
            "Use to plan routing order and check completeness."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "net_filter": {
                    "type": "string",
                    "description": "Optional: filter by net name pattern"
                }
            }
        }
    },
    {
        "name": "add_keepout_zone",
        "description": "Add a keep-out zone (no copper, no vias, no components).",
        "input_schema": {
            "type": "object",
            "properties": {
                "outline_mm": {
                    "type": "array",
                    "description": "List of [x, y] corner coordinates in mm",
                    "items": {"type": "array", "items": {"type": "number"}}
                },
                "no_copper":     {"type": "boolean", "default": True},
                "no_vias":       {"type": "boolean", "default": True},
                "no_footprints": {"type": "boolean", "default": False},
                "reason":        {
                    "type": "string",
                    "description": "e.g. 'Antenna keep-out', 'Mechanical clearance'"
                }
            },
            "required": ["outline_mm"]
        }
    },
    {
        "name": "add_zone",
        "description": "Add a copper pour zone on a specific layer.",
        "input_schema": {
            "type": "object",
            "properties": {
                "net_name":     {"type": "string"},
                "layer":        {
                    "type": "string",
                    "enum": ["F.Cu", "B.Cu", "In1.Cu", "In2.Cu"]
                },
                "outline_mm":   {
                    "type": "array",
                    "description": (
                        "Corner coordinates. "
                        "Pass [[0,0],[w,0],[w,h],[0,h]] for full board."
                    ),
                    "items": {"type": "array", "items": {"type": "number"}}
                },
                "clearance_mm": {"type": "number", "default": 0.3},
                "min_width_mm": {"type": "number", "default": 0.25},
                "fill_mode":    {"type": "string", "enum": ["solid", "hatched"], "default": "solid"},
                "priority":     {"type": "integer", "default": 0}
            },
            "required": ["net_name", "layer", "outline_mm"]
        }
    },
    {
        "name": "fill_zones",
        "description": "Execute copper pour fill on all defined zones.",
        "input_schema": {"type": "object", "properties": {}}
    },
    {
        "name": "strip_edge_cuts",
        "description": "Remove all existing Edge.Cuts segments/arcs from the PCB file. Call before re-issuing set_board_outline to avoid stacked outlines.",
        "input_schema": {"type": "object", "properties": {}}
    },
    {
        "name": "strip_zones",
        "description": "Remove all copper pour zones from the PCB file. Call before re-issuing add_zone to reset.",
        "input_schema": {"type": "object", "properties": {}}
    },
    {
        "name": "strip_tracks",
        "description": "Remove all track segments, arcs, and vias from the PCB file. Call before re-running the autorouter so Freerouting does not treat stale traces as fixed pre-routes.",
        "input_schema": {"type": "object", "properties": {}}
    },
    {
        "name": "save_board",
        "description": "Save the currently open PCB to disk via KiCad IPC. Use after placements/routes to persist changes.",
        "input_schema": {"type": "object", "properties": {}}
    },
    {
        "name": "sync_pcb_from_schematic",
        "description": "Push schematic netlist to the open PCB (equivalent to pressing F8 in pcbnew). Uses kipy run_action — KiCad may show a dialog. Call before place_footprint when footprints/nets are missing.",
        "input_schema": {"type": "object", "properties": {}}
    },
    {
        "name": "get_pad_positions",
        "description": "Return absolute pad positions (x_mm, y_mm) and connected net for every pad of a footprint on the PCB. Accounts for footprint rotation. Use before route_trace to get real coordinates.",
        "input_schema": {
            "type": "object",
            "properties": {
                "reference": {"type": "string", "description": "e.g. R1, U3, BT1"}
            },
            "required": ["reference"]
        }
    },
    {
        "name": "auto_arrange",
        "description": "Automatically arrange all footprints on the PCB based on netlist connectivity. Groups decoupling caps near their ICs, places connectors on periphery, crystals near their IC, and spaces components to avoid overlap.",
        "input_schema": {
            "type": "object",
            "properties": {
                "margin_mm": {
                    "type": "number",
                    "default": 3.0,
                    "description": "Minimum spacing between components in mm"
                },
                "strategy": {
                    "type": "string",
                    "enum": ["connectivity", "grid"],
                    "default": "connectivity",
                    "description": "'connectivity' groups by netlist connections, 'grid' uses simple row/column layout"
                }
            }
        }
    },
    {
        "name": "fit_board_outline",
        "description": "Calculate and draw a tight-fitting board outline (Edge.Cuts) around all placed components. Replaces any existing outline. Use after auto_arrange or manual placement.",
        "input_schema": {
            "type": "object",
            "properties": {
                "margin_mm": {
                    "type": "number",
                    "default": 2.0,
                    "description": "Clearance between outermost components and board edge in mm"
                },
                "corner_radius_mm": {
                    "type": "number",
                    "default": 1.0,
                    "description": "Corner rounding radius in mm"
                },
                "snap_to_mm": {
                    "type": "number",
                    "default": 1.0,
                    "description": "Round board dimensions up to nearest multiple of this value (0 to disable)"
                }
            }
        }
    },
]
