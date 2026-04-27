"""
Direct .kicad_pcb s-expression writers.

Purpose: provide file-write fallbacks so tools still work when pcbnew is not
running (kipy IPC unavailable). All helpers read the current .kicad_pcb text,
mutate it, and write back.

Safety: the caller is responsible for ensuring pcbnew is NOT open on the same
file — otherwise pcbnew will overwrite these edits when it next saves.
"""

from __future__ import annotations

import math
import re
import uuid
from pathlib import Path


def _read(pcb_path: str) -> str:
    return Path(pcb_path).read_text()


def _write(pcb_path: str, text: str) -> None:
    Path(pcb_path).write_text(text)


def _u() -> str:
    return str(uuid.uuid4())


def _insert_before_final_paren(text: str, block: str) -> str:
    """Insert block just before the final closing paren of the (kicad_pcb ...) form."""
    text = text.rstrip()
    assert text.endswith(")"), "malformed .kicad_pcb: missing final )"
    return text[:-1].rstrip() + "\n" + block.rstrip() + "\n)\n"


# ─── Edge cuts ──────────────────────────────────────────────────────────────

def append_rounded_rect_outline(
    pcb_path: str,
    width_mm: float,
    height_mm: float,
    corner_radius_mm: float = 2.0,
    origin_x_mm: float = 0.0,
    origin_y_mm: float = 0.0,
    line_width_mm: float = 0.05,
) -> int:
    """Add a rounded-rect outline on Edge.Cuts. Returns number of items added."""
    text = _read(pcb_path)
    ox, oy = origin_x_mm, origin_y_mm
    w, h, r = width_mm, height_mm, max(0.0, corner_radius_mm)
    r = min(r, w / 2, h / 2)
    lw = line_width_mm

    def line(x1, y1, x2, y2):
        return (f'\t(gr_line (start {x1} {y1}) (end {x2} {y2}) '
                f'(stroke (width {lw}) (type solid)) (layer "Edge.Cuts") (uuid "{_u()}"))')

    def arc(cx, cy, sx, sy, ex, ey):
        a1 = math.atan2(sy - cy, sx - cx)
        a2 = math.atan2(ey - cy, ex - cx)
        d = a2 - a1
        while d > math.pi: d -= 2 * math.pi
        while d < -math.pi: d += 2 * math.pi
        am = a1 + d / 2
        mx, my = cx + r * math.cos(am), cy + r * math.sin(am)
        return (f'\t(gr_arc (start {sx} {sy}) (mid {mx:.6f} {my:.6f}) (end {ex} {ey}) '
                f'(stroke (width {lw}) (type solid)) (layer "Edge.Cuts") (uuid "{_u()}"))')

    items = []
    if r == 0:
        items += [
            line(ox, oy, ox + w, oy),
            line(ox + w, oy, ox + w, oy + h),
            line(ox + w, oy + h, ox, oy + h),
            line(ox, oy + h, ox, oy),
        ]
    else:
        items += [
            line(ox + r, oy, ox + w - r, oy),
            line(ox + w, oy + r, ox + w, oy + h - r),
            line(ox + w - r, oy + h, ox + r, oy + h),
            line(ox, oy + h - r, ox, oy + r),
            arc(ox + w - r, oy + r, ox + w - r, oy, ox + w, oy + r),
            arc(ox + w - r, oy + h - r, ox + w, oy + h - r, ox + w - r, oy + h),
            arc(ox + r, oy + h - r, ox + r, oy + h, ox, oy + h - r),
            arc(ox + r, oy + r, ox, oy + r, ox + r, oy),
        ]

    text = _insert_before_final_paren(text, "\n".join(items))
    _write(pcb_path, text)
    return len(items)


def strip_edge_cuts(pcb_path: str) -> int:
    """Remove all (gr_line / gr_arc) entries on Edge.Cuts. Returns count removed."""
    text = _read(pcb_path)
    orig = text
    text = re.sub(r'\n\t\(gr_line [^\n]*?"Edge\.Cuts"[^\n]*\)', '', text)
    text = re.sub(r'\n\t\(gr_arc [^\n]*?"Edge\.Cuts"[^\n]*\)', '', text)
    _write(pcb_path, text)
    return orig.count("Edge.Cuts") - text.count("Edge.Cuts")


# ─── Nets ───────────────────────────────────────────────────────────────────

def read_nets(pcb_path: str) -> dict[str, int]:
    """Map net_name -> net_code by parsing (net N "name") entries (excluding the ones
    inside pad declarations — we only want the top-level declarations)."""
    text = _read(pcb_path)
    # Top-level (net N "name") lines appear at tab-indent level 1 (`\t(net `)
    nets: dict[str, int] = {}
    for m in re.finditer(r'\n\t\(net (\d+) "([^"]*)"\)', text):
        code = int(m.group(1))
        name = m.group(2)
        if name:
            nets[name] = code
            # Also key by leading '/' form
            if not name.startswith("/"):
                nets["/" + name] = code
            else:
                nets[name.lstrip("/")] = code
    return nets


# ─── Zones ──────────────────────────────────────────────────────────────────

def append_zone(
    pcb_path: str,
    net_name: str,
    layer: str,
    polygon_pts: list[tuple[float, float]],
    clearance_mm: float = 0.3,
    min_width_mm: float = 0.25,
    thermal_gap_mm: float = 0.5,
    thermal_bridge_width_mm: float = 0.5,
    name: str = "",
) -> dict:
    """Append a copper pour zone. net_name should match a net on the board (e.g. 'GND' or '/GND')."""
    text = _read(pcb_path)
    nets = read_nets(pcb_path)
    # Accept either with or without leading '/'
    net_code = nets.get(net_name) or nets.get("/" + net_name.lstrip("/"))
    if net_code is None:
        return {"status": "error",
                "message": f"Net '{net_name}' not found on board. Known: {sorted(nets.keys())[:10]}"}

    pts_s = " ".join(f"(xy {x} {y})" for x, y in polygon_pts)
    zname = name or f"{net_name}_pour"
    display_net = net_name if net_name.startswith("/") else "/" + net_name
    block = (
        f'\t(zone (net {net_code}) (net_name "{display_net}") (layer "{layer}") '
        f'(uuid "{_u()}") (name "{zname}")\n'
        f'\t\t(hatch edge 0.5) (connect_pads (clearance {clearance_mm})) '
        f'(min_thickness {min_width_mm})\n'
        f'\t\t(fill yes (thermal_gap {thermal_gap_mm}) '
        f'(thermal_bridge_width {thermal_bridge_width_mm}))\n'
        f'\t\t(polygon (pts {pts_s}))\n'
        f'\t)'
    )
    text = _insert_before_final_paren(text, block)
    _write(pcb_path, text)
    return {"status": "ok", "net": net_name, "net_code": net_code,
            "layer": layer, "vertices": len(polygon_pts)}


def strip_zones(pcb_path: str) -> int:
    """Remove all (zone ...) blocks. Returns count removed."""
    text = _read(pcb_path)
    removed = 0
    out = []
    i = 0
    while i < len(text):
        idx = text.find("(zone", i)
        if idx < 0:
            out.append(text[i:]); break
        out.append(text[i:idx])
        depth = 0
        for j in range(idx, len(text)):
            c = text[j]
            if c == "(":
                depth += 1
            elif c == ")":
                depth -= 1
                if depth == 0:
                    # Trim trailing whitespace accumulated before the zone
                    while out and out[-1] and out[-1][-1] in " \t\n":
                        out[-1] = out[-1][:-1]
                    removed += 1
                    i = j + 1
                    while i < len(text) and text[i] in " \t":
                        i += 1
                    break
        else:
            break
    _write(pcb_path, "".join(out))
    return removed


# ─── Footprints & pads ─────────────────────────────────────────────────────

def _iter_footprint_blocks(text: str):
    """Yield (start, end, block_text) for each top-level (footprint ...) form."""
    i = 0
    while True:
        idx = text.find("\n\t(footprint ", i)
        if idx < 0:
            return
        idx += 1  # skip leading newline
        depth = 0
        for j in range(idx, len(text)):
            c = text[j]
            if c == "(":
                depth += 1
            elif c == ")":
                depth -= 1
                if depth == 0:
                    yield idx, j + 1, text[idx:j + 1]
                    i = j + 1
                    break
        else:
            return


def move_footprint(pcb_path: str, reference: str, x_mm: float, y_mm: float,
                   rotation_deg: float = 0.0) -> bool:
    """Set a footprint's top-level (at X Y [rot]). Returns True if updated."""
    text = _read(pcb_path)
    pieces = re.split(r'(\n\t\(footprint )', text)
    out = [pieces[0]]
    hit = False
    i = 1
    while i < len(pieces):
        body = pieces[i + 1] if i + 1 < len(pieces) else ""
        ref_m = re.search(r'\(property "Reference" "([^"]+)"', body)
        if ref_m and ref_m.group(1) == reference:
            rot_str = f" {rotation_deg}" if rotation_deg else ""
            body = re.sub(
                r'\(at [\d.\-]+\s+[\d.\-]+(?:\s+[\d.\-]+)?\)',
                f'(at {x_mm} {y_mm}{rot_str})',
                body, count=1,
            )
            hit = True
        out.append(pieces[i])
        out.append(body)
        i += 2
    if hit:
        _write(pcb_path, "".join(out))
    return hit


def read_footprint_placement(pcb_path: str, reference: str):
    """Return {'x': mm, 'y': mm, 'rotation': deg} or None."""
    text = _read(pcb_path)
    for _s, _e, block in _iter_footprint_blocks(text):
        ref = re.search(r'\(property "Reference" "([^"]+)"', block)
        if not ref or ref.group(1) != reference:
            continue
        at = re.search(r'\A[^\n]*\n\s*\(layer[^\n]*\n\s*\(uuid[^\n]*\n\s*\(at '
                       r'([\d.\-]+)\s+([\d.\-]+)(?:\s+([\d.\-]+))?\)', block)
        if at:
            return {"x": float(at.group(1)), "y": float(at.group(2)),
                    "rotation": float(at.group(3) or 0)}
    return None


def read_pad_positions(pcb_path: str, reference: str) -> list[dict]:
    """
    Parse pads for `reference`. Returns list of
    {'number': str, 'net': str, 'x_mm': float, 'y_mm': float}
    in absolute board coords (footprint rotation applied).
    """
    text = _read(pcb_path)
    for _s, _e, block in _iter_footprint_blocks(text):
        ref = re.search(r'\(property "Reference" "([^"]+)"', block)
        if not ref or ref.group(1) != reference:
            continue
        fp_at = re.search(r'\A[^\n]*\n\s*\(layer[^\n]*\n\s*\(uuid[^\n]*\n\s*\(at '
                          r'([\d.\-]+)\s+([\d.\-]+)(?:\s+([\d.\-]+))?\)', block)
        if not fp_at:
            return []
        fx = float(fp_at.group(1))
        fy = float(fp_at.group(2))
        frot = float(fp_at.group(3) or 0)
        cos_t = math.cos(math.radians(frot))
        sin_t = math.sin(math.radians(frot))

        pads = []
        # Split block into individual (pad ...) regions by tracking paren balance
        # starting at each '(pad "' occurrence.
        i = 0
        while True:
            idx = block.find('(pad "', i)
            if idx < 0:
                break
            depth = 0
            for j in range(idx, len(block)):
                c = block[j]
                if c == '(':
                    depth += 1
                elif c == ')':
                    depth -= 1
                    if depth == 0:
                        pad_text = block[idx:j + 1]
                        i = j + 1
                        break
            else:
                break

            num_m = re.match(r'\(pad "([^"]*)"', pad_text)
            # Footprint-level (at X Y [rot]) for the pad
            at_m = re.search(r'\(at ([\d.\-]+)\s+([\d.\-]+)(?:\s+([\d.\-]+))?\)', pad_text)
            net_m = re.search(r'\(net (\d+) "([^"]*)"\)', pad_text)
            if not num_m or not at_m:
                continue
            num = num_m.group(1)
            lx = float(at_m.group(1))
            ly = float(at_m.group(2))
            ax = fx + (lx * cos_t - ly * sin_t)
            ay = fy + (lx * sin_t + ly * cos_t)
            pads.append({
                "number": num,
                "net": net_m.group(2) if net_m else "",
                "x_mm": round(ax, 4),
                "y_mm": round(ay, 4),
            })
        return pads
    return []


# ─── Bulk footprint reader ─────────────────────────────────────────────────

def read_all_footprints(pcb_path: str) -> list[dict]:
    """Read every footprint in one pass. Returns list of dicts:
    {reference, footprint_lib, x, y, rotation, pads: [{number, net, local_x, local_y, pad_w, pad_h}]}
    Pad coords are footprint-local (before rotation). Use for bounding-box and connectivity analysis.
    """
    text = _read(pcb_path)
    results = []
    for _s, _e, block in _iter_footprint_blocks(text):
        ref_m = re.search(r'\(property "Reference" "([^"]+)"', block)
        if not ref_m:
            continue
        reference = ref_m.group(1)

        # Footprint library name from first line
        lib_m = re.match(r'\(footprint "([^"]*)"', block)
        lib_name = lib_m.group(1) if lib_m else ""

        # Position
        at_m = re.search(
            r'\A[^\n]*\n\s*\(layer[^\n]*\n\s*\(uuid[^\n]*\n\s*'
            r'\(at ([\d.\-]+)\s+([\d.\-]+)(?:\s+([\d.\-]+))?\)', block)
        if not at_m:
            continue
        fx, fy = float(at_m.group(1)), float(at_m.group(2))
        frot = float(at_m.group(3) or 0)

        # Parse pads
        pads = []
        i = 0
        while True:
            idx = block.find('(pad "', i)
            if idx < 0:
                break
            depth = 0
            for j in range(idx, len(block)):
                if block[j] == '(':
                    depth += 1
                elif block[j] == ')':
                    depth -= 1
                    if depth == 0:
                        pad_text = block[idx:j + 1]
                        i = j + 1
                        break
            else:
                break

            num_m = re.match(r'\(pad "([^"]*)"', pad_text)
            at_p = re.search(r'\(at ([\d.\-]+)\s+([\d.\-]+)(?:\s+([\d.\-]+))?\)', pad_text)
            net_m = re.search(r'\(net \d+ "([^"]*)"\)', pad_text)
            size_m = re.search(r'\(size ([\d.\-]+)\s+([\d.\-]+)\)', pad_text)
            if not num_m or not at_p:
                continue
            pads.append({
                "number": num_m.group(1),
                "net": net_m.group(1) if net_m else "",
                "local_x": float(at_p.group(1)),
                "local_y": float(at_p.group(2)),
                "pad_w": float(size_m.group(1)) if size_m else 1.0,
                "pad_h": float(size_m.group(2)) if size_m else 1.0,
            })

        results.append({
            "reference": reference,
            "footprint_lib": lib_name,
            "x": fx, "y": fy, "rotation": frot,
            "pads": pads,
        })
    return results


# ─── Segments (traces) ─────────────────────────────────────────────────────

def append_segments(
    pcb_path: str,
    segments: list[dict],
) -> int:
    """
    segments: list of {'start': (x,y), 'end': (x,y), 'width_mm': float,
                       'layer': 'F.Cu'|'B.Cu'|..., 'net_code': int}
    Returns count written.
    """
    text = _read(pcb_path)
    lines = []
    for s in segments:
        x1, y1 = s["start"]
        x2, y2 = s["end"]
        if (x1, y1) == (x2, y2):
            continue
        w = s["width_mm"]
        layer = s["layer"]
        nc = s["net_code"]
        lines.append(
            f'\t(segment (start {x1} {y1}) (end {x2} {y2}) '
            f'(width {w}) (layer "{layer}") (net {nc}) (uuid "{_u()}"))'
        )
    if not lines:
        return 0
    text = _insert_before_final_paren(text, "\n".join(lines))
    _write(pcb_path, text)
    return len(lines)


def append_via(
    pcb_path: str,
    x_mm: float,
    y_mm: float,
    net_code: int,
    pad_mm: float = 0.8,
    drill_mm: float = 0.4,
) -> None:
    text = _read(pcb_path)
    block = (
        f'\t(via (at {x_mm} {y_mm}) (size {pad_mm}) (drill {drill_mm}) '
        f'(layers "F.Cu" "B.Cu") (net {net_code}) (uuid "{_u()}"))'
    )
    text = _insert_before_final_paren(text, block)
    _write(pcb_path, text)


def strip_tracks(pcb_path: str) -> int:
    """Remove all top-level (segment ...), (via ...), and (arc ...) track blocks.
    Handles both single-line and multi-line formats via paren-balance walking.
    Returns count of blocks removed."""
    text = _read(pcb_path)
    pattern = re.compile(r'\n\t\((?:segment|via|arc)(?=[\s\n\t)])')
    removed = 0
    out: list[str] = []
    i = 0
    n = len(text)
    while i < n:
        m = pattern.search(text, i)
        if not m:
            out.append(text[i:])
            break
        # m.start() points at the '\n' before '\t('; the block itself starts after it.
        block_start = m.start() + 1
        out.append(text[i:block_start])
        depth = 0
        j = block_start
        while j < n:
            c = text[j]
            if c == "(":
                depth += 1
            elif c == ")":
                depth -= 1
                if depth == 0:
                    j += 1
                    break
            j += 1
        # Trim trailing whitespace accumulated before the block.
        while out and out[-1] and out[-1][-1] in " \t\n":
            out[-1] = out[-1][:-1]
        removed += 1
        # Skip trailing whitespace after the closing paren so the file stays tidy.
        while j < n and text[j] in " \t":
            j += 1
        i = j
    _write(pcb_path, "".join(out))
    return removed


# ─── Pad resolution for route_trace 'REF:PIN' syntax ───────────────────────

def resolve_pad_coord(pcb_path: str, endpoint: str) -> tuple[float, float]:
    """Accept 'REF:PIN' or 'x,y' in mm. Returns (x_mm, y_mm)."""
    if ":" in endpoint:
        ref, pin = endpoint.split(":", 1)
        for p in read_pad_positions(pcb_path, ref):
            if p["number"] == pin:
                return p["x_mm"], p["y_mm"]
        raise ValueError(f"Pad '{pin}' of '{ref}' not found")
    parts = [p.strip() for p in endpoint.split(",")]
    if len(parts) != 2:
        raise ValueError(f"Expected 'REF:PIN' or 'x,y', got {endpoint!r}")
    return float(parts[0]), float(parts[1])
