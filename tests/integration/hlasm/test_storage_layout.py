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
from interpreter.hlasm.unsupported_data_type import UnsupportedDataType
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


OVERLAY_SOURCE = b"""\
TEST     CSECT
         BR    14
         DC    F'1'
         ORG   TEST+4
         DC    F'2'
         END   TEST
"""

LOCATION_COUNTER_SOURCE = b"""\
TEST     CSECT
         BR    14
         DC    0F
         DC    A(0),A(*)
         DC    2A(*),A(*,*),2A(*,*+2)
         END   TEST
"""

CHANNEL_COMMAND_SOURCE = b"""\
TEST     CSECT
         BR    14
         CCW1  X'02',FIELD,X'20',4
FIELD    DC    F'0'
         END   TEST
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


@covers(NotLanguageFeature.INFRASTRUCTURE)
def test_star_is_the_address_of_each_constant_after_an_empty_fullword(
    tmp_path: Path,
):
    program = _assemble(LOCATION_COUNTER_SOURCE, tmp_path)
    vm = _start(program)
    base = _base(vm, "TEST")

    words = [base + offset for offset in (8, 12, 16, 20, 24, 28, 34, 36, 42)]

    assert vm.load(base + 4, 40) == [
        *[0, 0, 0, 0],
        *(byte for word in words for byte in word.to_bytes(4, "big")),
    ]


@covers(NotLanguageFeature.INFRASTRUCTURE)
def test_channel_command_words_refuse_until_they_are_encoded(tmp_path: Path):
    program = _assemble(CHANNEL_COMMAND_SOURCE, tmp_path)

    with pytest.raises(UnsupportedDataType) as refused:
        section_allocation(program)

    assert str(refused.value) == (
        "DC type CCW1 is not supported yet — red-dragon-6uyp.93"
    )


@covers(NotLanguageFeature.INFRASTRUCTURE)
def test_org_overlay_pieces_get_distinct_registers_and_the_later_piece_wins(
    tmp_path: Path,
):
    program = _assemble(OVERLAY_SOURCE, tmp_path)
    ir = section_allocation(program)
    results = [i.result_reg for i in ir if i.result_reg.is_present()]
    vm = _start(program)

    assert len(results) == len(set(results))
    assert vm.load(_base(vm, "TEST") + 4, 4) == [0, 0, 0, 2]


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
