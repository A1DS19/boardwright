"""
Registry invariants: every schema has a handler, every name is unique, the
direct/routed taxonomy is a clean partition, and each schema validates against
the JSON Schema meta-schema.
"""

from __future__ import annotations

import jsonschema

from boardwright import dispatcher, router


def test_every_schema_has_a_handler():
    missing = set(dispatcher.ALL_SCHEMAS) - set(dispatcher.ALL_HANDLERS)
    assert not missing, f"Schemas without handlers: {missing}"


def test_every_handler_has_a_schema():
    missing = set(dispatcher.ALL_HANDLERS) - set(dispatcher.ALL_SCHEMAS)
    assert not missing, f"Handlers without schemas: {missing}"


def test_direct_and_routed_are_disjoint():
    routed = router._routed_tool_names()
    overlap = router.DIRECT_TOOL_NAMES & routed
    assert not overlap, f"Tool is both direct and routed: {overlap}"


def test_router_tools_not_in_direct_or_routed():
    routed = router._routed_tool_names()
    assert not (router.ROUTER_TOOL_NAMES & router.DIRECT_TOOL_NAMES)
    assert not (router.ROUTER_TOOL_NAMES & routed)


def test_visible_tools_count():
    # 16 direct + 4 router = 20
    assert len(dispatcher.TOOLS) == len(router.DIRECT_TOOL_NAMES) + len(router.ROUTER_TOOL_NAMES)


def test_all_handlers_count_matches_union():
    direct = router.DIRECT_TOOL_NAMES
    routed = router._routed_tool_names()
    union = direct | routed | router.ROUTER_TOOL_NAMES
    assert set(dispatcher.ALL_HANDLERS) == union, (
        f"ALL_HANDLERS differs from direct+routed+router union: "
        f"only in handlers: {set(dispatcher.ALL_HANDLERS) - union}, "
        f"only in union: {union - set(dispatcher.ALL_HANDLERS)}"
    )


def test_every_schema_is_valid_json_schema():
    validator = jsonschema.Draft202012Validator
    for name, schema in dispatcher.ALL_SCHEMAS.items():
        assert "name" in schema, f"{name}: missing 'name' key"
        assert "description" in schema, f"{name}: missing 'description' key"
        assert "input_schema" in schema, f"{name}: missing 'input_schema' key"
        # The input_schema must itself be a valid JSON Schema.
        validator.check_schema(schema["input_schema"])


def test_no_duplicate_names_in_visible_tools():
    names = [t["name"] for t in dispatcher.TOOLS]
    assert len(names) == len(set(names)), "Duplicate name in TOOLS"
