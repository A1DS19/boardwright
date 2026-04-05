"""Routing tools (Phase 6): traces, differential pairs, vias."""

from __future__ import annotations

from ..state import _project_state


def route_trace(
    net_name: str,
    from_pad: str,
    to_pad: str,
    width_mm: float,
    layer: str,
    via_at: list[float] | None = None,
) -> dict:
    trace = {
        "net_name": net_name, "from_pad": from_pad,
        "to_pad": to_pad, "width_mm": width_mm,
        "layer": layer, "via_at": via_at,
    }
    _project_state["traces"].append(trace)
    return {"status": "ok", "net_name": net_name, "from": from_pad, "to": to_pad}


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
    _project_state["vias"].append({
        "net_name": net_name, "x": x_mm, "y": y_mm,
        "drill_mm": drill_mm, "pad_mm": pad_mm,
        "from_layer": from_layer, "to_layer": to_layer,
    })
    return {"status": "ok", "net_name": net_name, "x": x_mm, "y": y_mm}


HANDLERS = {
    "route_trace":             route_trace,
    "route_differential_pair": route_differential_pair,
    "add_via":                 add_via,
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
]
