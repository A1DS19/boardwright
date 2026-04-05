"""Filesystem tools — read local project files."""

from __future__ import annotations

from pathlib import Path


def list_directory(path: str) -> dict:
    p = Path(path).expanduser()
    if not p.exists():
        return {"status": "error", "message": f"Path not found: {path}"}
    if not p.is_dir():
        return {"status": "error", "message": f"Not a directory: {path}"}
    entries = []
    for item in sorted(p.iterdir()):
        entries.append({
            "name": item.name,
            "type": "dir" if item.is_dir() else "file",
            "size_bytes": item.stat().st_size if item.is_file() else None,
        })
    return {"status": "ok", "path": str(p.resolve()), "entries": entries}


def read_file(path: str, max_bytes: int = 65536) -> dict:
    p = Path(path).expanduser()
    if not p.exists():
        return {"status": "error", "message": f"File not found: {path}"}
    if not p.is_file():
        return {"status": "error", "message": f"Not a file: {path}"}
    size = p.stat().st_size
    try:
        raw = p.read_bytes()[:max_bytes]
        content = raw.decode("utf-8", errors="replace")
        return {
            "status": "ok",
            "path": str(p.resolve()),
            "size_bytes": size,
            "truncated": size > max_bytes,
            "content": content,
        }
    except Exception as exc:
        return {"status": "error", "message": f"Could not read file: {exc}"}


HANDLERS = {
    "list_directory": list_directory,
    "read_file":      read_file,
}


TOOL_SCHEMAS = [
    {
        "name": "list_directory",
        "description": (
            "List files and subdirectories at a given path. "
            "Use this to explore the user's project folder before reading files."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "path": {
                    "type": "string",
                    "description": "Absolute or relative directory path, e.g. 'mcu/' or '/home/dev/projects/medi-pal/pcbs/mcu'"
                }
            },
            "required": ["path"]
        }
    },
    {
        "name": "read_file",
        "description": (
            "Read the contents of a local file. Use for KiCad schematic files "
            "(.kicad_sch), PCB files (.kicad_pcb), datasheets (.pdf text layer), "
            "text notes, netlists, or any other project file."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "path": {
                    "type": "string",
                    "description": "Absolute or relative file path"
                },
                "max_bytes": {
                    "type": "integer",
                    "default": 65536,
                    "description": "Maximum bytes to read (default 64KB). Increase for large files."
                }
            },
            "required": ["path"]
        }
    },
]
