"""
.kicad_sch-aware helpers: parse placed symbols, resolve pin endpoints,
build wire / label / no-connect S-expressions, and append them to files.

Depends only on the generic `sexpr` module.
"""

from __future__ import annotations

import math
import uuid
from pathlib import Path

from .sexpr import SExpr, _parse_sexpr, _sx_find, _sx_findall, _sx_get_property


def _parse_sch_file(sch_file: str) -> SExpr:
    """Parse a .kicad_sch file and return the top-level S-expression tree."""
    text = Path(sch_file).read_text(encoding="utf-8")
    return _parse_sexpr(text)


def _sch_lib_symbols(sch_tree: SExpr) -> dict[str, SExpr]:
    """Return {lib_id: symbol_node} for all symbols in (lib_symbols ...)."""
    lib_block = _sx_find(sch_tree, "lib_symbols")
    if not lib_block:
        return {}
    result: dict[str, SExpr] = {}
    for child in lib_block:
        if isinstance(child, list) and child and child[0] == "symbol":
            lib_id = child[1] if len(child) > 1 and isinstance(child[1], str) else None
            if lib_id:
                result[lib_id] = child
    return result


def _sch_placed_symbols(sch_tree: SExpr) -> dict[str, dict]:
    """
    Return {reference: {lib_id, x, y, rotation, mirror_x, mirror_y}}
    for every placed symbol instance at the top level of the schematic.
    """
    result: dict[str, dict] = {}
    for child in sch_tree:
        if not (isinstance(child, list) and child and child[0] == "symbol"):
            continue
        lib_id_node = _sx_find(child, "lib_id")
        at_node = _sx_find(child, "at")
        if not lib_id_node or not at_node:
            continue
        lib_id = lib_id_node[1] if len(lib_id_node) > 1 else ""
        try:
            px = float(at_node[1])
            py = float(at_node[2])
            rot = float(at_node[3]) if len(at_node) > 3 else 0.0
        except (IndexError, ValueError):
            continue

        mirror_node = _sx_find(child, "mirror")
        mirror_x = mirror_y = False
        if mirror_node:
            for m in mirror_node[1:]:
                if m == "x":
                    mirror_x = True
                if m == "y":
                    mirror_y = True

        # Reference is in a (property "Reference" "REF" ...) child
        ref = _sx_get_property(child, "Reference")
        if ref and not ref.startswith("#"):
            result[ref] = {
                "lib_id": lib_id,
                "x": px, "y": py, "rotation": rot,
                "mirror_x": mirror_x, "mirror_y": mirror_y,
            }
    return result


def _lib_sym_pins(lib_sym: SExpr) -> list[dict]:
    """
    Collect all (pin ...) entries from a lib symbol (including sub-symbol units).
    Returns list of {name, number, x, y, angle}.
    The (at x y angle) in a pin definition gives the *connection endpoint*
    in symbol space (KiCad convention: Y is up in symbol space).
    """
    pins: list[dict] = []

    def _collect(node: SExpr) -> None:
        if not isinstance(node, list):
            return
        for child in node:
            if not isinstance(child, list) or not child:
                continue
            if child[0] == "pin":
                at_node = _sx_find(child, "at")
                name_node = _sx_find(child, "name")
                num_node = _sx_find(child, "number")
                if at_node and len(at_node) >= 3:
                    try:
                        px = float(at_node[1])
                        py = float(at_node[2])
                        angle = float(at_node[3]) if len(at_node) > 3 else 0.0
                    except ValueError:
                        continue
                    pin_name = name_node[1] if name_node and len(name_node) > 1 else ""
                    pin_num = num_node[1] if num_node and len(num_node) > 1 else ""
                    pins.append({"name": pin_name, "number": pin_num,
                                 "x": px, "y": py, "angle": angle})
            elif child[0] == "symbol":
                _collect(child)

    _collect(lib_sym)
    return pins


def _transform_pin(px: float, py: float,
                   place_x: float, place_y: float,
                   rotation: float,
                   mirror_x: bool, mirror_y: bool) -> tuple[float, float]:
    """
    Transform a pin's symbol-space coordinates to schematic space.

    KiCad convention:
      - Symbol space: Y-up (mathematical)
      - Schematic space: Y-down (screen)
      - Transform: apply mirror → rotate (CCW in math space) → Y-invert + translate
    """
    if mirror_x:
        px = -px
    if mirror_y:
        py = -py
    rad = math.radians(rotation)
    rot_x = px * math.cos(rad) - py * math.sin(rad)
    rot_y = px * math.sin(rad) + py * math.cos(rad)
    sch_x = round(place_x + rot_x, 4)
    sch_y = round(place_y - rot_y, 4)
    return sch_x, sch_y


def _resolve_pin_endpoint(
    sch_file: str, reference: str, pin_id: str
) -> tuple[float, float] | None:
    """
    Return the schematic-space (x, y) of a pin endpoint.
    pin_id is matched against pin name OR pin number (case-insensitive).
    Returns None if not found.
    """
    tree = _parse_sch_file(sch_file)
    placed = _sch_placed_symbols(tree)
    lib_syms = _sch_lib_symbols(tree)

    sym_info = placed.get(reference)
    if not sym_info:
        return None
    lib_sym = lib_syms.get(sym_info["lib_id"])
    if not lib_sym:
        return None

    pins = _lib_sym_pins(lib_sym)
    pin_id_lower = pin_id.lower()
    match = next(
        (p for p in pins
         if p["name"].lower() == pin_id_lower or p["number"] == pin_id),
        None,
    )
    if not match:
        return None

    return _transform_pin(
        match["x"], match["y"],
        sym_info["x"], sym_info["y"],
        sym_info["rotation"], sym_info["mirror_x"], sym_info["mirror_y"],
    )


def _gen_uuid() -> str:
    return str(uuid.uuid4())


def _wire_sexp(x1: float, y1: float, x2: float, y2: float) -> str:
    return (
        f'\t(wire\n'
        f'\t\t(pts\n'
        f'\t\t\t(xy {x1} {y1}) (xy {x2} {y2})\n'
        f'\t\t)\n'
        f'\t\t(stroke\n'
        f'\t\t\t(width 0)\n'
        f'\t\t\t(type default)\n'
        f'\t\t)\n'
        f'\t\t(uuid "{_gen_uuid()}")\n'
        f'\t)\n'
    )


def _label_sexp(net_name: str, x: float, y: float, rotation: float = 0) -> str:
    justify = "right bottom" if abs(rotation - 180) < 1 else "left bottom"
    return (
        f'\t(label "{net_name}"\n'
        f'\t\t(at {x} {y} {int(rotation)})\n'
        f'\t\t(effects\n'
        f'\t\t\t(font\n'
        f'\t\t\t\t(size 1.27 1.27)\n'
        f'\t\t\t)\n'
        f'\t\t\t(justify {justify})\n'
        f'\t\t)\n'
        f'\t\t(uuid "{_gen_uuid()}")\n'
        f'\t)\n'
    )


def _no_connect_sexp(x: float, y: float) -> str:
    return (
        f'\t(no_connect\n'
        f'\t\t(at {x} {y})\n'
        f'\t\t(uuid "{_gen_uuid()}")\n'
        f'\t)\n'
    )


def _append_to_sch(sch_file: str, sexp_text: str) -> None:
    """
    Insert sexp_text into the .kicad_sch file just before the final closing paren.
    Creates a backup (.bak) before writing.
    """
    path = Path(sch_file)
    content = path.read_text(encoding="utf-8")
    idx = content.rfind(')')
    if idx == -1:
        raise ValueError(f"No closing ')' found in {sch_file}")
    new_content = content[:idx] + sexp_text + content[idx:]
    path.with_suffix(".kicad_sch.bak").write_text(content, encoding="utf-8")
    path.write_text(new_content, encoding="utf-8")
