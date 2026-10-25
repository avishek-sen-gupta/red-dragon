# pyright: standard
"""The variable a program's entry is registered under, which COBOL's CALL shares: the entry prefix and the name uppercased, as z/OS load-module names are, built at lowering time or in IR from a name read at run time."""

from interpreter.hlasm.hlasm_constants import (
    PROGRAM_ENTRY_PREFIX,
    STRING_CONCAT_PAIR,
    STRING_UPPER,
)
from interpreter.hlasm.hlasm_emitter import HlasmEmitter
from interpreter.register import Register


def program_entry_name(name: str) -> str:
    return f"{PROGRAM_ENTRY_PREFIX}{name.upper()}"


def emit_program_entry_name(emitter: HlasmEmitter, name: Register) -> Register:
    upper = emitter.call(STRING_UPPER, (name,))
    return emitter.call(STRING_CONCAT_PAIR, (emitter.str_(PROGRAM_ENTRY_PREFIX), upper))
