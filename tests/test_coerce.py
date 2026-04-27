"""Tests for schema-driven input coercion in the dispatcher."""

from __future__ import annotations

from boardwright.dispatcher import _coerce_input, _coerce_scalar


def _schema(props: dict) -> dict:
    return {"input_schema": {"type": "object", "properties": props}}


def test_coerce_scalar_int():
    assert _coerce_scalar("150", "integer") == 150
    assert _coerce_scalar("  42 ", "integer") == 42


def test_coerce_scalar_number():
    assert _coerce_scalar("1.5", "number") == 1.5


def test_coerce_scalar_bool():
    assert _coerce_scalar("true", "boolean") is True
    assert _coerce_scalar("False", "boolean") is False
    assert _coerce_scalar("1", "boolean") is True
    assert _coerce_scalar("0", "boolean") is False


def test_coerce_scalar_passthrough_on_bad_input():
    # Non-string stays untouched
    assert _coerce_scalar(123, "integer") == 123
    assert _coerce_scalar(True, "boolean") is True
    # Unparseable string is left alone so the handler sees the real value
    assert _coerce_scalar("abc", "integer") == "abc"
    assert _coerce_scalar("maybe", "boolean") == "maybe"


def test_coerce_input_mixed_fields():
    schema = _schema({
        "x":        {"type": "number"},
        "count":    {"type": "integer"},
        "enabled":  {"type": "boolean"},
        "name":     {"type": "string"},
    })
    out = _coerce_input(
        {"x": "1.5", "count": "3", "enabled": "true", "name": "R1"},
        schema,
    )
    assert out == {"x": 1.5, "count": 3, "enabled": True, "name": "R1"}


def test_coerce_input_leaves_correctly_typed_values_alone():
    schema = _schema({"x": {"type": "number"}, "enabled": {"type": "boolean"}})
    inp = {"x": 2.0, "enabled": False}
    assert _coerce_input(inp, schema) == inp


def test_coerce_input_unknown_fields_passthrough():
    schema = _schema({"x": {"type": "number"}})
    out = _coerce_input({"x": "3", "extra": "untouched"}, schema)
    assert out == {"x": 3.0, "extra": "untouched"}


def test_coerce_input_no_schema_is_noop():
    inp = {"x": "1", "y": "true"}
    assert _coerce_input(inp, None) == inp
    assert _coerce_input(inp, {}) == inp
