"""Shared helpers for COBOL integration tests (ProLeap bridge → IR → CFG → VM).

Centralizes the ProLeap bridge JAR path fixture (``bridge_jar``) and the small
decode/format helpers used across the COBOL integration test modules so they are
defined exactly once.
"""

from __future__ import annotations

import os
from decimal import Decimal

import pytest

from interpreter.run import run

_AREA_A = "       "  # 7 spaces: cols 1-6 (seq) + col 7 (indicator = space)
_COMMENT = "      *"  # col 7 = * for comment line


def to_fixed(lines: list[str]) -> str:
    """Convert short-form COBOL lines to FIXED format (columns 1-80).

    Each input line is treated as starting at column 8 (Area A): 6 spaces for
    the sequence area + 1 space for the indicator area are prepended.

    A line starting with ``*`` is emitted as a COBOL comment line (the ``*``
    goes in the column-7 indicator area); the rest of the line follows.
    """
    formatted = [
        _COMMENT + line[1:] if line.startswith("*") else _AREA_A + line
        for line in lines
    ]
    return "\n".join(formatted) + "\n"


def decode_zoned_unsigned(region: bytearray, offset: int, length: int) -> int:
    """Decode unsigned zoned decimal from a memory region.

    Each byte is EBCDIC zoned: 0xF0=0, 0xF1=1, ..., 0xF9=9.
    The digit is in the low nibble (b & 0x0F).
    """
    digits = [region[offset + i] & 0x0F for i in range(length)]
    return sum(d * (10 ** (length - 1 - i)) for i, d in enumerate(digits))


def decode_zoned_with_decimal(
    region: bytearray, offset: int, integer_digits: int, decimal_digits: int
) -> Decimal:
    """Decode zoned decimal with fixed-point (integer.fractional) parts.

    Extracts (integer_digits + decimal_digits) zoned decimal bytes, then
    divides by 10^decimal_digits to place the decimal point.
    E.g., 3 integer + 2 decimal digits reads 5 bytes and divides by 100.
    """
    n = integer_digits + decimal_digits
    digits = [region[offset + i] & 0x0F for i in range(n)]
    raw = sum(d * (10 ** (n - 1 - i)) for i, d in enumerate(digits))
    return Decimal(raw) / Decimal(10**decimal_digits)


def run_cobol(lines: list[str], max_steps: int = 1000):
    """Run short-form COBOL lines through the full pipeline; return the VMState."""
    source = to_fixed(lines)
    return run(source=source, language="cobol", max_steps=max_steps)


def run_cobol_programs(
    main: list[str], subprograms: dict[str, list[str]], max_steps: int = 500_000
):
    """Run a main program plus named subprograms through the full pipeline.

    Entry is by FUNCTION, not top level: ``EntryPoint.top_level()`` executes only
    the per-module init blocks (each ends in ``branch __after_<pid>_0``), so the
    PROCEDURE DIVISION never runs and every assertion would read nothing but the
    VALUE clauses. This mirrors how jackal enters a COBOL step.
    """
    from cobol_asg.cobol_parser import make_cobol_parser
    from interpreter.project.cobol_compile import compile_cobol
    from interpreter.run import EntryPoint, initial_vm_state, run_linked

    main_id = _program_id(main)
    _, linked = compile_cobol(
        to_fixed(main).encode(),
        parser=make_cobol_parser(),
        extra_subprogram_sources={
            name: to_fixed(lines).encode() for name, lines in subprograms.items()
        },
    )
    entry = f"func_{main_id.lower()}_0"
    return run_linked(
        linked,
        entry_point=EntryPoint.function(lambda f: str(f.name) == entry),
        max_steps=max_steps,
        initial_vm=initial_vm_state(),
    )


def _program_id(lines: list[str]) -> str:
    for line in lines:
        stripped = line.strip().upper()
        if stripped.startswith("PROGRAM-ID."):
            return stripped[len("PROGRAM-ID.") :].strip().rstrip(".")
    raise ValueError("No PROGRAM-ID. found in source lines")


def ws_region(vm, program_id: str) -> bytearray:
    """Return one program's WORKING-STORAGE bytes, found via its program singleton.

    ``first_region`` cannot serve a multi-program run: which region comes first is
    module link order, not the program under test. The singleton is identified by
    the ``run`` entry point it publishes, which is stable across link orders.
    """
    from interpreter.address import Address
    from interpreter.field_name import FieldName

    wanted = f"func_{program_id.lower()}_0"
    for _addr, obj in vm.heap_items():
        run_field = obj.fields.get(FieldName("run"))
        if run_field is None or str(run_field.value.func_ref.name) != wanted:
            continue
        handle = obj.fields[FieldName("ws_handle")]
        return vm.region_get(Address(str(handle.value)))
    raise KeyError(f"No singleton for program {program_id!r} in this VMState")


def return_code_of(vm, program_id: str) -> int:
    """Decode one named program's own RETURN-CODE special register."""
    from interpreter.address import Address
    from interpreter.cobol.binary import decode_binary
    from interpreter.cobol.special_registers import (
        RETURN_CODE_HANDLE,
        RETURN_CODE_NAME,
        SPECIAL_REGISTERS_LAYOUT,
    )
    from interpreter.field_name import FieldName

    wanted = f"func_{program_id.lower()}_0"
    for _addr, obj in vm.heap_items():
        run_field = obj.fields.get(FieldName("run"))
        if run_field is None or str(run_field.value.func_ref.name) != wanted:
            continue
        handle = obj.fields[RETURN_CODE_HANDLE]
        region = vm.region_get(Address(str(handle.value)))
        fl = SPECIAL_REGISTERS_LAYOUT.lookup_or_raise(RETURN_CODE_NAME)
        raw = bytes(region[fl.offset : fl.offset + fl.byte_length])
        descriptor = fl.type_descriptor
        return int(decode_binary(raw, descriptor.decimal_digits, descriptor.signed))
    raise KeyError(f"No singleton for program {program_id!r} in this VMState")


def first_region(vm):
    """Return the first memory region from the VM state."""
    return vm.region_get(list(vm.region_keys())[0])


def all_field_names(fields) -> set[str]:
    """Recursively collect all field names from a list of CobolFields."""
    names: set[str] = set()
    for f in fields:
        names.add(f.name)
        names |= all_field_names(f.children)
    return names


@pytest.fixture
def bridge_jar() -> str:
    """The ProLeap bridge JAR path — the single source of the JAR config, read from
    the required PROLEAP_BRIDGE_JAR env. No default, no skip: if it's unset, a test
    that needs the JAR fails loudly (KeyError) instead of silently skipping or
    guessing a path. Fixtures/tests that build a parser take this and use the
    returned path; run()/compile_directory read the same env var themselves.
    """
    return os.environ["PROLEAP_BRIDGE_JAR"]
