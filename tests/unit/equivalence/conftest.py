"""Shared helpers for cross-language IR equivalence tests."""

import logging

from interpreter.cfg import extract_function_instructions
from interpreter.ir import IRInstruction, Opcode

from tests.unit.rosetta.conftest import parse_for_language

logger = logging.getLogger(__name__)


def function_opcode_sequence(
    language: str, source: str, func_name: str
) -> list[Opcode]:
    """Lower source, extract function body, return opcode sequence (no LABELs)."""
    instructions = parse_for_language(language, source)
    body = extract_function_instructions(instructions, func_name)
    return [inst.opcode for inst in body if inst.opcode != Opcode.LABEL]
