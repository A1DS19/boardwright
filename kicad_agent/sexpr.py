"""
Generic S-expression tokenizer, parser, and navigation helpers.

Pure Python — no KiCad-specific knowledge. All .kicad_sch-aware code lives
in `schematic_io.py`, which builds on this module.
"""

from __future__ import annotations

from typing import List, Union

SExpr = Union[str, List]


def _tokenize_sexpr(text: str) -> list[str]:
    tokens: list[str] = []
    i = 0
    n = len(text)
    while i < n:
        c = text[i]
        if c in ' \t\n\r':
            i += 1
        elif c == '(':
            tokens.append('(')
            i += 1
        elif c == ')':
            tokens.append(')')
            i += 1
        elif c == '"':
            j = i + 1
            while j < n:
                if text[j] == '\\':
                    j += 2
                elif text[j] == '"':
                    break
                else:
                    j += 1
            tokens.append(text[i + 1:j])
            i = j + 1
        else:
            j = i
            while j < n and text[j] not in ' \t\n\r()"':
                j += 1
            tokens.append(text[i:j])
            i = j
    return tokens


def _parse_sexpr(text: str) -> SExpr:
    tokens = _tokenize_sexpr(text)
    pos = [0]

    def _parse_one() -> SExpr:
        if pos[0] >= len(tokens):
            raise ValueError("Unexpected end of S-expression")
        tok = tokens[pos[0]]
        if tok == '(':
            pos[0] += 1
            items: list = []
            while pos[0] < len(tokens) and tokens[pos[0]] != ')':
                items.append(_parse_one())
            pos[0] += 1  # consume ')'
            return items
        else:
            pos[0] += 1
            return tok

    return _parse_one()


def _sx_find(node: SExpr, key: str) -> SExpr | None:
    """Return first direct child list whose first element == key."""
    if not isinstance(node, list):
        return None
    for child in node:
        if isinstance(child, list) and child and child[0] == key:
            return child
    return None


def _sx_findall(node: SExpr, key: str) -> list[SExpr]:
    """Return all direct child lists whose first element == key."""
    if not isinstance(node, list):
        return []
    return [c for c in node if isinstance(c, list) and c and c[0] == key]


def _sx_get_property(sym_node: SExpr, prop_name: str) -> str | None:
    """Return the value of a (property "NAME" "VALUE" ...) child."""
    for child in _sx_findall(sym_node, "property"):
        if len(child) >= 3 and child[1] == prop_name:
            return child[2]
    return None
