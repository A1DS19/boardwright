"""Tool handler modules, one per PCB-design phase.

Each module exports:
  - HANDLERS: dict[str, Callable]  — tool name → handler function
  - TOOL_SCHEMAS: list[dict]       — JSON schemas (name, description, input_schema)

dispatcher.py merges these into the single TOOLS list and dispatch table.
"""
