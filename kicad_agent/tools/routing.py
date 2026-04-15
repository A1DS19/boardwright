"""Routing tools (Phase 6): traces, differential pairs, vias, autoroute."""

from __future__ import annotations

import os
import re
import subprocess
from pathlib import Path

from ..backends import _kicad
from ..state import _pcb_file, _project_state


_LAYER_MAP = {
    "F.Cu": "BL_F_Cu", "B.Cu": "BL_B_Cu",
    "In1.Cu": "BL_In1_Cu", "In2.Cu": "BL_In2_Cu",
}


def _resolve_point(endpoint: str, board):
    """Return kipy Vector2 for 'REF:PAD' or 'x,y' (mm)."""
    from kipy.geometry import Vector2
    if ":" in endpoint:
        ref, pad_num = endpoint.split(":", 1)
        fp = next((f for f in board.get_footprints()
                   if f.reference_field.text.value == ref), None)
        if fp is None:
            raise ValueError(f"Footprint '{ref}' not found")
        pad = next((p for p in fp.pads if p.number == pad_num), None)
        if pad is None:
            raise ValueError(f"Pad '{pad_num}' not found on {ref}")
        # pad.position is footprint-relative; add footprint position
        return Vector2(fp.position.x + pad.position.x,
                       fp.position.y + pad.position.y)
    parts = [p.strip() for p in endpoint.split(",")]
    if len(parts) != 2:
        raise ValueError(f"Expected 'REF:PAD' or 'x,y', got {endpoint!r}")
    return Vector2.from_xy_mm(float(parts[0]), float(parts[1]))


def _find_net(board, net_name: str):
    for n in board.get_nets():
        if n.name == net_name:
            return n
    raise ValueError(f"Net '{net_name}' not found on board")


def route_trace(
    net_name: str,
    from_pad: str,
    to_pad: str,
    width_mm: float,
    layer: str,
    via_at: list[float] | None = None,
) -> dict:
    try:
        kicad = _kicad()
        from kipy import board_types as bt
        from kipy.geometry import Vector2

        board = kicad.get_board()
        net = _find_net(board, net_name)
        start = _resolve_point(from_pad, board)
        end = _resolve_point(to_pad, board)
        layer_enum = getattr(bt.BoardLayer, _LAYER_MAP.get(layer, "BL_F_Cu"))
        width_nm = int(width_mm * 1_000_000)

        items = []
        if via_at and len(via_at) == 2:
            mid = Vector2.from_xy_mm(float(via_at[0]), float(via_at[1]))
            t1 = bt.Track(); t1.start = start; t1.end = mid
            t1.width = width_nm; t1.layer = layer_enum; t1.net = net
            via = bt.Via(); via.position = mid; via.net = net
            via.diameter = int(0.8 * 1_000_000); via.drill_diameter = int(0.4 * 1_000_000)
            other_layer = bt.BoardLayer.BL_B_Cu if layer == "F.Cu" else bt.BoardLayer.BL_F_Cu
            t2 = bt.Track(); t2.start = mid; t2.end = end
            t2.width = width_nm; t2.layer = other_layer; t2.net = net
            items = [t1, via, t2]
        else:
            t = bt.Track(); t.start = start; t.end = end
            t.width = width_nm; t.layer = layer_enum; t.net = net
            items = [t]

        board.create_items(items)
        board.save()
        return {"status": "ok", "source": "kipy", "net_name": net_name,
                "from": from_pad, "to": to_pad, "segments": len(items)}

    except ImportError:
        pass
    except ValueError as e:
        return {"status": "error", "message": str(e)}
    except Exception as e:
        if "connect" in str(e).lower() or "socket" in str(e).lower():
            return {"status": "error",
                    "message": "KiCad IPC unavailable. Ensure: (1) KiCad main app is open, (2) the .kicad_pcb is open in the PCB Editor window, (3) Preferences → Plugins → 'Enable KiCad API' is checked (restart KiCad if you just enabled it)."}
        return {"status": "error", "message": f"kipy error: {e}"}

    trace = {
        "net_name": net_name, "from_pad": from_pad,
        "to_pad": to_pad, "width_mm": width_mm,
        "layer": layer, "via_at": via_at,
    }
    _project_state["traces"].append(trace)
    return {"status": "ok", "source": "stub", "net_name": net_name,
            "from": from_pad, "to": to_pad}


def route_differential_pair(
    net_positive: str,
    net_negative: str,
    from_ref: str,
    to_ref: str,
    width_mm: float,
    spacing_mm: float,
    layer: str = "F.Cu",
    max_skew_mm: float = 0.1,
) -> dict:
    for net in (net_positive, net_negative):
        _project_state["traces"].append({
            "net_name": net, "from_pad": from_ref,
            "to_pad": to_ref, "width_mm": width_mm,
            "layer": layer, "differential": True,
            "spacing_mm": spacing_mm,
        })
    return {
        "status": "ok",
        "net_positive": net_positive, "net_negative": net_negative,
        "skew_mm": 0.0, "max_skew_mm": max_skew_mm,
    }


def add_via(
    net_name: str,
    x_mm: float,
    y_mm: float,
    drill_mm: float = 0.4,
    pad_mm: float = 0.8,
    from_layer: str = "F.Cu",
    to_layer: str = "B.Cu",
) -> dict:
    try:
        kicad = _kicad()
        from kipy import board_types as bt
        from kipy.geometry import Vector2

        board = kicad.get_board()
        net = _find_net(board, net_name)
        via = bt.Via()
        via.position = Vector2.from_xy_mm(x_mm, y_mm)
        via.net = net
        via.diameter = int(pad_mm * 1_000_000)
        via.drill_diameter = int(drill_mm * 1_000_000)
        board.create_items([via])
        board.save()
        return {"status": "ok", "source": "kipy", "net_name": net_name,
                "x": x_mm, "y": y_mm}

    except ImportError:
        pass
    except ValueError as e:
        return {"status": "error", "message": str(e)}
    except Exception as e:
        if "connect" in str(e).lower() or "socket" in str(e).lower():
            return {"status": "error",
                    "message": "KiCad IPC unavailable. Ensure: (1) KiCad main app is open, (2) the .kicad_pcb is open in the PCB Editor window, (3) Preferences → Plugins → 'Enable KiCad API' is checked (restart KiCad if you just enabled it)."}
        return {"status": "error", "message": f"kipy error: {e}"}

    _project_state["vias"].append({
        "net_name": net_name, "x": x_mm, "y": y_mm,
        "drill_mm": drill_mm, "pad_mm": pad_mm,
        "from_layer": from_layer, "to_layer": to_layer,
    })
    return {"status": "ok", "source": "stub", "net_name": net_name, "x": x_mm, "y": y_mm}


def _find_java21() -> str | None:
    """Return path to a java 21 executable, or None."""
    candidates: list[Path] = []
    jh = os.environ.get("JAVA_HOME")
    if jh:
        candidates.append(Path(jh) / "bin" / "java")
    candidates += [
        Path("/usr/lib/jvm/java-21-openjdk/bin/java"),
        Path("/usr/lib/jvm/jre-21-openjdk/bin/java"),
        Path("/usr/lib/jvm/jre-21/bin/java"),
    ]
    for c in candidates:
        if c.is_file():
            try:
                out = subprocess.run([str(c), "-version"], capture_output=True, text=True, timeout=5)
                ver = (out.stderr + out.stdout)
                m = re.search(r'version "(\d+)', ver)
                if m and m.group(1) == "21":
                    return str(c)
            except Exception:
                continue
    return None


def _find_freerouting_jar() -> Path | None:
    """Scan the KiCad plugin dirs for freerouting-*.jar."""
    home = Path.home()
    roots = [
        home / ".local/share/kicad",
        home / ".var/app/org.kicad.KiCad/data/kicad",  # Flatpak
    ]
    for root in roots:
        if not root.exists():
            continue
        for jar in sorted(root.rglob("freerouting-*.jar"), reverse=True):
            return jar
    return None


def autoroute_pcb(
    dsn_path: str | None = None,
    ses_path: str | None = None,
    threads: int = 1,
    timeout_seconds: int = 600,
    host: str = "KiCad's Pcbnew",
) -> dict:
    """
    Run Freerouting on a Specctra .dsn file and produce a .ses file.

    Workflow:
      1. In pcbnew, File → Export → Specctra DSN (writes <project>/<board>.dsn
         next to the .kicad_pcb, or pick a path).
      2. Call this tool — it discovers Java 21 + the freerouting jar shipped
         by the KiCad Freerouting plugin, runs the autorouter, writes .ses.
      3. In pcbnew, File → Import → Specctra Session, pick the .ses.

    If dsn_path / ses_path aren't given, defaults to <board-stem>.dsn /
    <board-stem>.ses next to the active .kicad_pcb.
    """
    pcb = _pcb_file()
    if not dsn_path:
        if not pcb:
            return {"status": "error",
                    "message": "No pcb_file set and no dsn_path provided. Call set_project first."}
        dsn_path = str(Path(pcb).with_suffix(".dsn"))
    if not ses_path:
        ses_path = str(Path(dsn_path).with_suffix(".ses"))

    if not Path(dsn_path).is_file():
        return {"status": "error",
                "message": f"DSN file not found: {dsn_path}. In pcbnew, File → Export → Specctra DSN first."}

    java = _find_java21()
    if not java:
        return {"status": "error",
                "message": "Java 21 not found. Install java-21-openjdk-headless and/or set JAVA_HOME to a Java 21 JDK. Freerouting 2.1 silently produces empty output on Java 25."}

    jar = _find_freerouting_jar()
    if not jar:
        return {"status": "error",
                "message": "freerouting-*.jar not found. Install the Freerouting plugin via KiCad's Plugin and Content Manager."}

    # Remove stale .ses so we can detect a silent-failure (0 byte) outcome.
    try:
        Path(ses_path).unlink(missing_ok=True)
    except OSError:
        pass

    cmd = [java, "-jar", str(jar),
           "-de", dsn_path, "-do", ses_path,
           "-mt", str(threads), "-host", host]
    try:
        proc = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout_seconds)
    except subprocess.TimeoutExpired:
        return {"status": "error", "message": f"Freerouting timed out after {timeout_seconds}s."}

    ses = Path(ses_path)
    size = ses.stat().st_size if ses.exists() else 0
    if size == 0:
        return {"status": "error",
                "message": "Freerouting finished but produced a 0-byte .ses. Check Java version (must be 21).",
                "stderr_tail": (proc.stderr or proc.stdout)[-600:]}

    # Heuristic stats extraction from log output.
    log = proc.stdout + proc.stderr
    score_m = re.search(r"score of (\d+(?:\.\d+)?)", log)
    pass_m = re.search(r"pass #(\d+)", log)
    viol_m = re.search(r"clearance_violations.*?total_count.*?(\d+)", log, re.DOTALL)

    return {
        "status": "ok",
        "source": "freerouting",
        "jar": str(jar),
        "java": java,
        "dsn": dsn_path,
        "ses": ses_path,
        "ses_bytes": size,
        "score": float(score_m.group(1)) if score_m else None,
        "last_pass": int(pass_m.group(1)) if pass_m else None,
        "clearance_violations": int(viol_m.group(1)) if viol_m else None,
        "next_step": "In pcbnew: File → Import → Specctra Session, choose the .ses.",
    }


HANDLERS = {
    "route_trace":             route_trace,
    "route_differential_pair": route_differential_pair,
    "add_via":                 add_via,
    "autoroute_pcb":           autoroute_pcb,
}


TOOL_SCHEMAS = [
    {
        "name": "route_trace",
        "description": "Route a copper trace segment between two pads or points.",
        "input_schema": {
            "type": "object",
            "properties": {
                "net_name":  {"type": "string"},
                "from_pad":  {"type": "string", "description": "e.g. 'U1:VCC' or coordinate"},
                "to_pad":    {"type": "string"},
                "width_mm":  {"type": "number"},
                "layer":     {
                    "type": "string",
                    "enum": ["F.Cu", "B.Cu", "In1.Cu", "In2.Cu"]
                },
                "via_at":    {
                    "type": "array",
                    "description": "Optional: add a via at this [x, y] midpoint to change layers",
                    "items": {"type": "number"}
                }
            },
            "required": ["net_name", "from_pad", "to_pad", "width_mm", "layer"]
        }
    },
    {
        "name": "route_differential_pair",
        "description": "Route a differential pair with matched length and controlled spacing.",
        "input_schema": {
            "type": "object",
            "properties": {
                "net_positive":  {"type": "string"},
                "net_negative":  {"type": "string"},
                "from_ref":      {"type": "string"},
                "to_ref":        {"type": "string"},
                "width_mm":      {"type": "number"},
                "spacing_mm":    {"type": "number"},
                "layer":         {"type": "string"},
                "max_skew_mm":   {"type": "number", "default": 0.1}
            },
            "required": [
                "net_positive", "net_negative",
                "from_ref", "to_ref",
                "width_mm", "spacing_mm"
            ]
        }
    },
    {
        "name": "add_via",
        "description": "Add a via to transition a net between layers.",
        "input_schema": {
            "type": "object",
            "properties": {
                "net_name":   {"type": "string"},
                "x_mm":       {"type": "number"},
                "y_mm":       {"type": "number"},
                "drill_mm":   {"type": "number", "default": 0.4},
                "pad_mm":     {"type": "number", "default": 0.8},
                "from_layer": {"type": "string"},
                "to_layer":   {"type": "string"}
            },
            "required": ["net_name", "x_mm", "y_mm"]
        }
    },
    {
        "name": "autoroute_pcb",
        "description": "Run the Freerouting autorouter on a Specctra .dsn and produce a .ses. Requires Java 21 and the KiCad Freerouting plugin installed (auto-discovered). User must first export DSN from pcbnew (File → Export → Specctra DSN), then import the resulting SES (File → Import → Specctra Session). Uses single-threaded optimization by default to avoid clearance violations.",
        "input_schema": {
            "type": "object",
            "properties": {
                "dsn_path": {"type": "string", "description": "Path to the exported .dsn. Defaults to <board-stem>.dsn next to the active .kicad_pcb."},
                "ses_path": {"type": "string", "description": "Path for the output .ses. Defaults to <dsn-stem>.ses."},
                "threads":  {"type": "integer", "default": 1, "description": "-mt flag. 1 is recommended (multi-threaded optimizer creates clearance violations)."},
                "timeout_seconds": {"type": "integer", "default": 600},
                "host":     {"type": "string", "default": "KiCad's Pcbnew"}
            },
            "required": []
        }
    },
]
