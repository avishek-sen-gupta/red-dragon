"""Shared helpers for CFG-level unit tests.

Centralizes the small instruction-list and CFG-construction boilerplate used
across the CFG/execution unit test modules so it is defined exactly once.
"""

from __future__ import annotations

from interpreter.cfg import CFG, build_cfg
from interpreter.instructions import InstructionBase
from interpreter.ir import IRInstruction, Opcode
from interpreter.registry import FunctionRegistry, build_registry


def make_instructions(*specs: tuple[Opcode, dict]) -> list[InstructionBase]:
    """Build an IRInstruction list from (opcode, kwargs) tuples."""
    return [IRInstruction(opcode=op, **kw) for op, kw in specs]


def build_simple_cfg(
    instructions: list[InstructionBase],
) -> tuple[CFG, FunctionRegistry]:
    """Build a CFG + registry from an instruction list."""
    cfg = build_cfg(instructions)
    registry = build_registry(instructions, cfg)
    return cfg, registry
