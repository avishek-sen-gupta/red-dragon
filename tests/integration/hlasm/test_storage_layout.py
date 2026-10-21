# pyright: standard
"""An assembled program's sections hold its constants and literals after start-up."""

from __future__ import annotations

from pathlib import Path

import pytest

from hlasm_asg.hlasm_bridge_parser import make_hlasm_parser
from hlasm_asg.program.hlasm_program import HlasmProgram
from hlasm_asg.program.reloc_symbol import RelocSymbol
from interpreter.hlasm.machine import machine_allocation
from interpreter.hlasm.storage_layout import section_allocation, section_var
from interpreter.vm.vm_types import VMState
from tests.covers import NotLanguageFeature, covers
from tests.unit.hlasm.straight_line_vm import run_straight_line

CONSTANTS_SOURCE = b"""\
HELLO    CSECT
         USING HELLO,15
         L     1,=F'5'
         BR    14
FIELD    DC    F'7'
AFIELD   DC    A(FIELD)
MIX      DC    C'A',F'-2'
HALF     DC    Y(FIELD)
SPACE    DS    CL3
         LTORG
WORK     DSECT
WFIELD   DC    F'1'
         END   HELLO
"""

EXTERNAL_SOURCE = b"""\
HELLO    CSECT
         BR    14
VOTHER   DC    V(OTHER)
OTHER    CSECT
         DC    F'9'
         END   HELLO
"""


def _assemble(source: bytes, tmp_path: Path) -> HlasmProgram:
    parser = make_hlasm_parser()
    return parser.read(
        parser.parse_to_file(source, "src/hello.asm", tmp_path / "program.json")
    )


def _start(program: HlasmProgram) -> VMState:
    return run_straight_line((*machine_allocation(), *section_allocation(program)), {})


def _base(vm: VMState, section: str) -> int:
    return vm.current_frame.local_vars[section_var(section)].value


def _offset(program: HlasmProgram, name: str) -> int:
    (symbol,) = [
        s for s in program.symbols if isinstance(s, RelocSymbol) and s.name == name
    ]
    return symbol.offset


@covers(NotLanguageFeature.INFRASTRUCTURE)
def test_address_constant_holds_runtime_address(tmp_path: Path):
    program = _assemble(CONSTANTS_SOURCE, tmp_path)
    vm = _start(program)
    base = _base(vm, "HELLO")
    field = base + 8

    assert [_offset(program, "FIELD"), _offset(program, "AFIELD")] == [8, 12]
    assert [(s.name, s.length) for s in program.sections] == [
        ("HELLO", 36),
        ("WORK", 4),
    ]
    assert vm.load(base, 36) == [
        *[0] * 8,
        *[0, 0, 0, 7],
        *field.to_bytes(4, "big"),
        *[0xC1, 0, 0, 0],
        *[0xFF, 0xFF, 0xFF, 0xFE],
        *(field % 0x10000).to_bytes(2, "big"),
        *[0] * 6,
        *[0, 0, 0, 5],
    ]
    assert section_var("WORK") not in vm.current_frame.local_vars


@pytest.mark.xfail(
    reason="V-type constants hold zero until the linkage unit resolves them — red-dragon-6uyp.8",
    strict=True,
)
@covers(NotLanguageFeature.INFRASTRUCTURE)
def test_v_type_constant_holds_the_named_section_address(tmp_path: Path):
    program = _assemble(EXTERNAL_SOURCE, tmp_path)
    vm = _start(program)

    assert vm.load(_base(vm, "HELLO") + 4, 4) == list(
        _base(vm, "OTHER").to_bytes(4, "big")
    )
