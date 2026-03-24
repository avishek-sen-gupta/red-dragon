"""Shared helpers for cross-language IR equivalence tests."""

import logging

from interpreter.cfg import extract_function_instructions
from interpreter.ir import Opcode

from tests.unit.rosetta.conftest import parse_for_language

logger = logging.getLogger(__name__)


def _normalize_opcode(opcode: Opcode) -> Opcode:
    """Normalize DECL_VAR to STORE_VAR for cross-language equivalence comparison.

    Different languages emit DECL_VAR vs STORE_VAR for the same semantic
    operation (variable initialization), so they must be treated as equivalent.
    """
    return Opcode.STORE_VAR if opcode == Opcode.DECL_VAR else opcode


def function_opcode_sequence(
    language: str, source: str, func_name: str
) -> list[Opcode]:
    """Lower source, extract function body, return normalized opcode sequence (no LABELs)."""
    instructions = parse_for_language(language, source)
    body = extract_function_instructions(instructions, func_name)
    return [
        _normalize_opcode(inst.opcode) for inst in body if inst.opcode != Opcode.LABEL
    ]
