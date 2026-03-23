"""Resource handler implementations for the RedDragon MCP server."""

from __future__ import annotations

import json

import mcp_server.session as session_module


def handle_source_resource() -> str:
    """Return the loaded program's source code."""
    current = session_module._current_session
    if current is None:
        return "No program loaded. Call load_program first."
    return current.source


def handle_ir_resource() -> str:
    """Return the full IR listing."""
    current = session_module._current_session
    if current is None:
        return "No program loaded. Call load_program first."

    lines = []
    for label, block in current.cfg.blocks.items():
        lines.append(f"{label}:  → {', '.join(str(s) for s in block.successors)}")
        for inst in block.instructions:
            lines.append(f"  {inst}")
        lines.append("")
    return "\n".join(lines)


def handle_cfg_resource() -> str:
    """Return the CFG structure as JSON."""
    current = session_module._current_session
    if current is None:
        return json.dumps({"error": "No program loaded. Call load_program first."})

    blocks = [
        {
            "label": str(label),
            "successors": [str(s) for s in block.successors],
            "instruction_count": len(block.instructions),
        }
        for label, block in current.cfg.blocks.items()
    ]
    return json.dumps({"blocks": blocks}, indent=2)
