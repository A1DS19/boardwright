"""
.kicad_sch-aware helpers: parse placed symbols, resolve pin endpoints,
build wire / label / no-connect S-expressions, and append them to files.

Depends only on the generic `sexpr` module.
"""

from __future__ import annotations

import math
import os
import re
import uuid
from pathlib import Path

from .sexpr import SExpr, _parse_sexpr, _sx_find, _sx_findall, _sx_get_property
from .state import _kicad_lib_search_paths


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


def _lib_sym_pins(lib_sym: SExpr, lib_syms: "dict[str, SExpr] | None" = None) -> list[dict]:
    """
    Collect all (pin ...) entries from a lib symbol (including sub-symbol units).
    Returns list of {name, number, x, y, angle}.
    The (at x y angle) in a pin definition gives the *connection endpoint*
    in symbol space (KiCad convention: Y is up in symbol space).

    If lib_syms is provided, resolves KiCad's (extends "ParentName") inheritance
    so that variant symbols (e.g. ATmega48PB-A extending ATmega48PB) return pins
    from their parent when they carry none of their own.
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

    # If no pins found, check for (extends "ParentName") and resolve from parent.
    if not pins and lib_syms is not None:
        extends_node = _sx_find(lib_sym, "extends")
        if extends_node and len(extends_node) > 1:
            parent_name = extends_node[1]
            # lib_syms keys are "Library:SymbolName"; match by bare symbol name
            parent_sym = next(
                (v for k, v in lib_syms.items() if k.split(":")[-1] == parent_name),
                None,
            )
            if parent_sym is not None:
                pins = _lib_sym_pins(parent_sym, lib_syms)

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

    pins = _lib_sym_pins(lib_sym, lib_syms)
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


def _find_matching_paren(text: str, open_idx: int) -> int:
    """Given an index pointing at '(', return index of the matching ')'. -1 on mismatch."""
    depth = 0
    i = open_idx
    in_str = False
    while i < len(text):
        c = text[i]
        if c == '"' and text[i - 1] != "\\":
            in_str = not in_str
        elif not in_str:
            if c == "(":
                depth += 1
            elif c == ")":
                depth -= 1
                if depth == 0:
                    return i
        i += 1
    return -1


def _remove_placed_symbol(sch_file: str, reference: str) -> tuple[bool, str | None]:
    """
    Remove the top-level (symbol ...) instance whose Reference property matches.
    Also removes the matching (symbol "LIB:NAME" ...) from (lib_symbols ...) if
    no other instance references it. Creates a .bak before writing.
    Returns (removed_instance, removed_lib_id_or_None).
    """
    path = Path(sch_file)
    text = path.read_text(encoding="utf-8")

    # Find every top-level "(symbol " occurrence outside lib_symbols.
    lib_block_start = text.find("(lib_symbols")
    lib_block_end = _find_matching_paren(text, lib_block_start) if lib_block_start != -1 else -1

    target_start = target_end = -1
    target_lib_id: str | None = None
    search = 0
    pat = re.compile(r'\(symbol\s')
    for m in pat.finditer(text):
        s = m.start()
        # Skip anything inside (lib_symbols ...)
        if lib_block_start != -1 and lib_block_start < s < lib_block_end:
            continue
        e = _find_matching_paren(text, s)
        if e == -1:
            continue
        block = text[s:e + 1]
        ref_m = re.search(r'\(property\s+"Reference"\s+"([^"]+)"', block)
        if ref_m and ref_m.group(1) == reference:
            lib_m = re.search(r'\(lib_id\s+"([^"]+)"\)', block)
            target_lib_id = lib_m.group(1) if lib_m else None
            target_start, target_end = s, e
            break

    if target_start == -1:
        return False, None

    # Drop the symbol instance (and the newline/whitespace before it, for tidiness).
    pre = text[:target_start]
    # Trim trailing whitespace (tab/newline) before the block so we don't leave blank lines
    pre = re.sub(r'[\t ]*\n?$', '', pre)
    post = text[target_end + 1:]
    new_text = pre + "\n" + post.lstrip("\n")

    # Decide whether to also drop the lib_symbols entry: only if no other placed
    # instance uses the same lib_id.
    removed_lib_id = None
    if target_lib_id and f'(lib_id "{target_lib_id}")' not in new_text:
        # Locate the (symbol "LIB:NAME" ...) inside (lib_symbols ...) in new_text.
        new_lib_start = new_text.find("(lib_symbols")
        new_lib_end = _find_matching_paren(new_text, new_lib_start) if new_lib_start != -1 else -1
        if new_lib_start != -1 and new_lib_end != -1:
            lib_region = new_text[new_lib_start:new_lib_end + 1]
            entry_pat = re.compile(
                r'\(symbol\s+"' + re.escape(target_lib_id) + r'"'
            )
            em = entry_pat.search(lib_region)
            if em:
                entry_abs_start = new_lib_start + em.start()
                entry_abs_end = _find_matching_paren(new_text, entry_abs_start)
                if entry_abs_end != -1:
                    lib_pre = re.sub(r'[\t ]*\n?$', '', new_text[:entry_abs_start])
                    lib_post = new_text[entry_abs_end + 1:].lstrip("\n")
                    new_text = lib_pre + "\n" + lib_post
                    removed_lib_id = target_lib_id

    path.with_suffix(".kicad_sch.bak").write_text(text, encoding="utf-8")
    path.write_text(new_text, encoding="utf-8")
    return True, removed_lib_id


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


# ─────────────────────────────────────────────────────────────────────────────
# Library symbol embedding (for add_symbol writing to disk)
# ─────────────────────────────────────────────────────────────────────────────

_DOWNLOAD_HINT = (
    "Please download the KiCad symbol (.kicad_sym) from one of: "
    "https://www.snapeda.com, https://componentsearchengine.com, or https://www.ultralibrarian.com. "
    "Save the file into the project's 'symbols/' folder, then tell me: "
    "(1) the filename you saved it as (without .kicad_sym) — this is the library name; "
    "(2) the symbol name inside the file (usually shown in the download page or visible "
    "when you open the file in a text editor as the value after '(symbol \"')."
)

_FOOTPRINT_DOWNLOAD_HINT = (
    "Please download the KiCad footprint (.kicad_mod) from one of: "
    "https://www.snapeda.com, https://componentsearchengine.com, or https://www.ultralibrarian.com. "
    "Save the file into the project's 'footprints/' folder, then tell me: "
    "(1) the filename you saved it as (without .kicad_mod) — this is the footprint name; "
    "(2) the footprint name inside the file if it differs (visible after '(footprint \"' "
    "at the top of the file)."
)


def _kicad_sym_search_paths(project_dir: "Path | None" = None) -> list[Path]:
    """Return candidate directories to search for .kicad_sym library files."""
    return _kicad_lib_search_paths("symbols", "KICAD_SYMBOLS", project_dir)


def _find_lib_file(library: str, project_dir: "Path | None" = None) -> Path | None:
    """Find {library}.kicad_sym in the standard KiCad library search paths."""
    for search_dir in _kicad_sym_search_paths(project_dir):
        candidate = search_dir / f"{library}.kicad_sym"
        if candidate.is_file():
            return candidate
    return None


def _extract_raw_symbol(lib_text: str, symbol_name: str) -> str | None:
    """
    Extract the raw S-expression text for a named top-level symbol from a .kicad_sym file.
    Uses paren-counting so nested sub-symbols are included correctly.
    Returns None if the symbol is not found.
    """
    marker = f'(symbol "{symbol_name}"'
    start = lib_text.find(marker)
    if start == -1:
        return None
    depth = 0
    i = start
    while i < len(lib_text):
        c = lib_text[i]
        if c == '(':
            depth += 1
        elif c == ')':
            depth -= 1
            if depth == 0:
                return lib_text[start:i + 1]
        i += 1
    return None


def _prefix_symbol_names(raw_text: str, sym_name: str, lib_name: str) -> str:
    """
    Prefix the top-level (symbol "NAME") entry and any (extends "NAME") reference
    with lib_name:. Sub-unit entries like (symbol "NAME_0_1") are left unchanged.
    KiCad requires both declarations and extends references to use "lib:name" form
    when embedded in a schematic's lib_symbols block.
    """
    sym_pattern = re.compile(r'\(symbol "(' + re.escape(sym_name) + r')"')
    result = sym_pattern.sub(lambda m: f'(symbol "{lib_name}:{m.group(1)}"', raw_text)
    ext_pattern = re.compile(r'\(extends "(' + re.escape(sym_name) + r')"')
    result = ext_pattern.sub(lambda m: f'(extends "{lib_name}:{m.group(1)}"', result)
    return result


def _top_level_property_blocks(raw_sym: str) -> list[tuple[str, str]]:
    """
    Return [(property_name, full_block_text)] for every (property "Name" ...) block
    at depth 1 of the outer (symbol ...) definition. Sub-unit properties are skipped.
    """
    start = raw_sym.find("(")
    if start == -1:
        return []
    # Scan children of the outer symbol node at depth 1.
    depth = 0
    i = 0
    props: list[tuple[str, str]] = []
    while i < len(raw_sym):
        c = raw_sym[i]
        if c == "(":
            if depth == 1 and raw_sym.startswith('(property "', i):
                end = _find_matching_paren(raw_sym, i)
                name_m = re.match(r'\(property\s+"([^"]+)"', raw_sym[i:end + 1])
                if name_m:
                    props.append((name_m.group(1), raw_sym[i:end + 1]))
                i = end + 1
                continue
            depth += 1
        elif c == ")":
            depth -= 1
        i += 1
    return props


def _apply_property_overrides(raw_sym: str, overrides: list[tuple[str, str]]) -> str:
    """
    For each (name, block) in overrides, replace a matching top-level property block
    by name; if none exists, insert before the first sub-unit symbol (or at end).
    """
    out = raw_sym
    for name, new_block in overrides:
        pat = re.compile(
            r'\(property\s+"' + re.escape(name) + r'"\s', re.MULTILINE
        )
        m = pat.search(out)
        if m:
            s = m.start()
            e = _find_matching_paren(out, s)
            if e != -1:
                out = out[:s] + new_block + out[e + 1:]
                continue
        # Insert: find outer symbol's "(symbol ..." opening, place after first newline
        # before any nested (symbol "X_0_1" sub-unit, or before closing paren.
        subunit_m = re.search(r'\n\s*\(symbol\s+"[^"]+_\d', out)
        insert_pos = subunit_m.start() if subunit_m else out.rfind(")")
        out = out[:insert_pos] + "\n\t\t" + new_block + out[insert_pos:]
    return out


def _flatten_extends(raw_sym: str, lib_text: str, depth: int = 0) -> tuple[str, str | None]:
    """
    If raw_sym has (extends "parent"), inline the parent's definition, rename
    parent + sub-units to the child's name, and overlay child's override
    properties. Recurses for chained inheritance. Returns (flat_text, error_or_None).
    """
    if depth > 5:
        return raw_sym, "extends chain too deep (>5 levels)"

    ext_m = re.search(r'\(extends\s+"([^"]+)"\s*\)', raw_sym)
    if not ext_m:
        return raw_sym, None

    parent_name = ext_m.group(1)
    top_m = re.match(r'\s*\(symbol\s+"([^"]+)"', raw_sym)
    if not top_m:
        return raw_sym, "cannot find outer symbol name for extends flatten"
    child_name = top_m.group(1)

    parent_raw = _extract_raw_symbol(lib_text, parent_name)
    if parent_raw is None:
        return raw_sym, (
            f"parent symbol '{parent_name}' referenced by (extends) not found in library"
        )

    # Chained: parent may itself extend something.
    parent_raw, err = _flatten_extends(parent_raw, lib_text, depth + 1)
    if err:
        return raw_sym, err

    # Rename parent + sub-units ("Parent", "Parent_0_1", ...) to child's name.
    renamed = re.sub(
        r'\(symbol\s+"' + re.escape(parent_name) + r'(_[^"]*)?"',
        lambda mm: f'(symbol "{child_name}{mm.group(1) or ""}"',
        parent_raw,
    )

    overrides = _top_level_property_blocks(raw_sym)
    return _apply_property_overrides(renamed, overrides), None


def _sch_top_uuid(sch_file: str) -> str:
    """Return the top-level (uuid "...") value from a schematic file."""
    content = Path(sch_file).read_text(encoding="utf-8")
    m = re.search(r'^\s*\(uuid\s+"([^"]+)"', content, re.MULTILINE)
    return m.group(1) if m else "00000000-0000-0000-0000-000000000000"


def _ensure_lib_symbol_embedded(sch_file: str, library: str, symbol: str) -> str | None:
    """
    Ensure the symbol definition for library:symbol is present in the schematic's
    lib_symbols block, extracting it from the .kicad_sym file if needed.
    Returns None on success, an error string on failure.
    """
    lib_id = f"{library}:{symbol}"
    path = Path(sch_file)
    project_dir = path.parent
    content = path.read_text(encoding="utf-8")

    if f'(symbol "{lib_id}"' in content:
        return None  # already embedded

    lib_file = _find_lib_file(library, project_dir)
    if lib_file is None:
        search_dirs = [str(p) for p in _kicad_sym_search_paths(project_dir)]
        return (
            f"Library '{library}' not found in: {search_dirs}. "
            f"{_DOWNLOAD_HINT}"
        )

    lib_text = lib_file.read_text(encoding="utf-8")
    raw_sym = _extract_raw_symbol(lib_text, symbol)
    if raw_sym is None:
        return (
            f"Symbol '{symbol}' not found in library '{library}' ({lib_file}). "
            f"{_DOWNLOAD_HINT}"
        )

    # If this symbol extends a parent, flatten the definition by inlining the
    # parent's graphics/pins and overlaying the child's overriding properties.
    # lib_symbols entries are expected to be self-contained.
    flat_sym, flat_err = _flatten_extends(raw_sym, lib_text)
    if flat_err:
        return flat_err

    # Prefix ALL symbol names (top-level and sub-units) with "library:"
    prefixed = _prefix_symbol_names(flat_sym, symbol, library)

    ls_start = content.find("(lib_symbols")
    if ls_start == -1:
        # No lib_symbols block — insert one before the final closing paren
        idx = content.rfind(')')
        insert_block = f'\t(lib_symbols\n\t{prefixed}\n\t)\n'
        new_content = content[:idx] + insert_block + content[idx:]
    else:
        # Find the matching closing paren of the lib_symbols block
        depth = 0
        i = ls_start
        while i < len(content):
            if content[i] == '(':
                depth += 1
            elif content[i] == ')':
                depth -= 1
                if depth == 0:
                    break
            i += 1
        # Insert before the closing paren of lib_symbols
        new_content = content[:i] + f'\n\t{prefixed}\n\t' + content[i:]

    path.with_suffix(".kicad_sch.bak").write_text(content, encoding="utf-8")
    path.write_text(new_content, encoding="utf-8")
    return None


def _symbol_instance_sexp(
    lib_id: str,
    reference: str,
    value: str,
    x: float,
    y: float,
    rotation: float,
    mirror_x: bool,
    sch_uuid: str,
    project_name: str,
    footprint: str = "",
) -> str:
    """Generate the S-expression for a placed symbol instance."""
    mirror_line = '\n\t\t(mirror x)' if mirror_x else ''
    ref_y = round(y - 2.54, 4)
    val_y = round(y + 2.54, 4)
    sym_uuid = _gen_uuid()
    return (
        f'\t(symbol\n'
        f'\t\t(lib_id "{lib_id}")\n'
        f'\t\t(at {x} {y} {int(rotation)}){mirror_line}\n'
        f'\t\t(unit 1)\n'
        f'\t\t(exclude_from_sim no)\n'
        f'\t\t(in_bom yes)\n'
        f'\t\t(on_board yes)\n'
        f'\t\t(dnp no)\n'
        f'\t\t(uuid "{sym_uuid}")\n'
        f'\t\t(property "Reference" "{reference}"\n'
        f'\t\t\t(at {x} {ref_y} 0)\n'
        f'\t\t\t(effects (font (size 1.27 1.27)))\n'
        f'\t\t)\n'
        f'\t\t(property "Value" "{value}"\n'
        f'\t\t\t(at {x} {val_y} 0)\n'
        f'\t\t\t(effects (font (size 1.27 1.27)))\n'
        f'\t\t)\n'
        f'\t\t(property "Footprint" "{footprint}"\n'
        f'\t\t\t(at {x} {y} 0)\n'
        f'\t\t\t(effects (font (size 1.27 1.27)) (hide yes))\n'
        f'\t\t)\n'
        f'\t\t(property "Datasheet" ""\n'
        f'\t\t\t(at {x} {y} 0)\n'
        f'\t\t\t(effects (font (size 1.27 1.27)) (hide yes))\n'
        f'\t\t)\n'
        f'\t\t(instances\n'
        f'\t\t\t(project "{project_name}"\n'
        f'\t\t\t\t(path "/{sch_uuid}"\n'
        f'\t\t\t\t\t(reference "{reference}")\n'
        f'\t\t\t\t\t(unit 1)\n'
        f'\t\t\t\t)\n'
        f'\t\t\t)\n'
        f'\t\t)\n'
        f'\t)\n'
    )


def _place_symbol(
    sch_file: str,
    library: str,
    symbol: str,
    reference: str,
    value: str,
    x: float,
    y: float,
    rotation: float,
    mirror_x: bool,
    footprint: str = "",
) -> str | None:
    """
    Write a placed symbol instance into sch_file, embedding the lib definition
    into lib_symbols first if it isn't already there.
    Returns None on success, an error string on failure.
    """
    err = _ensure_lib_symbol_embedded(sch_file, library, symbol)
    if err:
        return err
    sch_uuid = _sch_top_uuid(sch_file)
    project_name = Path(sch_file).stem
    lib_id = f"{library}:{symbol}"
    sexp = _symbol_instance_sexp(
        lib_id, reference, value, x, y, rotation, mirror_x, sch_uuid, project_name,
        footprint=footprint,
    )
    _append_to_sch(sch_file, sexp)
    return None


def _blank_sch_template() -> str:
    """Return the S-expression text for a minimal valid .kicad_sch file."""
    sheet_uuid = _gen_uuid()
    return (
        f'(kicad_sch\n'
        f'\t(version 20250114)\n'
        f'\t(generator "eeschema")\n'
        f'\t(generator_version "9.0")\n'
        f'\t(uuid "{sheet_uuid}")\n'
        f'\t(paper "A4")\n'
        f'\t(lib_symbols\n'
        f'\t)\n'
        f')\n'
    )
