# pyright: standard
"""An assembled program's sections hold its constants, literals and relocated addresses after the binder's start-up."""

from __future__ import annotations

from pathlib import Path

import pytest

from hlasm_asg.hlasm_bridge_parser import make_hlasm_parser
from hlasm_asg.program.hlasm_program import HlasmProgram
from hlasm_asg.program.reloc_symbol import RelocSymbol
from interpreter.hlasm.assembled_module import object_module
from interpreter.hlasm.binder import Binder
from interpreter.hlasm.binder_start_up import bound_start_up
from interpreter.hlasm.dc_value_out_of_range import DcValueOutOfRange
from interpreter.hlasm.hlasm_constants import STUBS_LOW_VAR
from interpreter.hlasm.image_module import ImageModule
from interpreter.hlasm.section_variable import section_var
from interpreter.instructions import InstructionBase
from interpreter.vm.vm_types import VMState
from tests.covers import NotLanguageFeature, covers
from tests.integration.hlasm.hlasm_helpers import BARE_ASSEMBLY
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
         CCW0  X'02',FIELD,X'20',4
FIELD    DC    F'0'
         CCW1  3,=A(FIELD),0,8
         END   TEST
"""


OUT_OF_RANGE_SOURCE = b"""\
TEST     CSECT
         BR    14
         DC    H'1',F'2147483648'
         END   TEST
"""

OUT_OF_RANGE_LITERAL_SOURCE = b"""\
TEST     CSECT
         USING TEST,15
         LH    1,=H'40000'
         BR    14
         END   TEST
"""

LITERAL_STAR_SOURCE = b"""\
TEST     CSECT
         USING TEST,15
         BR    14
         L     1,=2A(*)
         END   TEST
"""


EXTERNAL_CHANNEL_COMMAND_SOURCE = b"""\
TEST     CSECT
         EXTRN EXT
         BR    14
         CCW   2,EXT,0,4
         END   TEST
"""

DSECT_ADDRESS_SOURCE = b"""\
MAIN     CSECT
         USING MAIN,15
         L     15,ADDR
         BR    14
ADDR     DC    A(FLD),AL2(FLD+2)
D        DSECT
         DS    F
FLD      DS    F
         END   MAIN
"""

S_LITERAL_SOURCE = b"""\
TEST     CSECT
         USING TEST,12
         L     1,=S(FLD)
         DROP  12
         USING TEST,11
         LTORG
FLD      DC    F'0'
         END   TEST
"""


def _assemble(source: bytes, tmp_path: Path) -> HlasmProgram:
    parser = make_hlasm_parser()
    return parser.read(
        parser.parse_to_file(
            source, "src/hello.asm", tmp_path / "program.json", BARE_ASSEMBLY
        )
    )


def _start_up(program: HlasmProgram) -> tuple[InstructionBase, ...]:
    return bound_start_up(Binder((ImageModule("M", "M", object_module(program)),)))


def _start(program: HlasmProgram) -> VMState:
    return run_straight_line(_start_up(program), {})


def _base(vm: VMState, section: str) -> int:
    return vm.current_frame.local_vars[section_var("M", section)].value


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
    assert section_var("M", "WORK") not in vm.current_frame.local_vars


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
def test_channel_command_words_hold_their_relocated_addresses(tmp_path: Path):
    program = _assemble(CHANNEL_COMMAND_SOURCE, tmp_path)
    vm = _start(program)
    base = _base(vm, "TEST")
    field, literal = base + 24, base + 40

    assert vm.load(base + 8, 36) == [
        *[0x02, 0x20, 0x00, 0x04],
        *field.to_bytes(4, "big"),
        *[0x02],
        *(field % (1 << 24)).to_bytes(3, "big"),
        *[0x20, 0x00, 0x00, 0x04],
        *[0, 0, 0, 0],
        *[0, 0, 0, 0],
        *[0x03, 0x00, 0x00, 0x08],
        *literal.to_bytes(4, "big"),
        *field.to_bytes(4, "big"),
    ]


@covers(NotLanguageFeature.INFRASTRUCTURE)
def test_org_overlay_pieces_get_distinct_registers_and_the_later_piece_wins(
    tmp_path: Path,
):
    program = _assemble(OVERLAY_SOURCE, tmp_path)
    ir = _start_up(program)
    results = [i.result_reg for i in ir if i.result_reg.is_present()]
    vm = _start(program)

    assert len(results) == len(set(results))
    assert vm.load(_base(vm, "TEST") + 4, 4) == [0, 0, 0, 2]


@covers(NotLanguageFeature.INFRASTRUCTURE)
def test_v_type_constant_holds_the_named_section_address(tmp_path: Path):
    program = _assemble(EXTERNAL_SOURCE, tmp_path)
    vm = _start(program)

    assert vm.load(_base(vm, "HELLO") + 4, 4) == list(
        _base(vm, "OTHER").to_bytes(4, "big")
    )


@covers(NotLanguageFeature.INFRASTRUCTURE)
@pytest.mark.parametrize(
    ("source", "message"),
    [
        (
            OUT_OF_RANGE_SOURCE,
            "F'2147483648' at line 3 of src/hello.asm does not fit its length — ASMA072E",
        ),
        (
            OUT_OF_RANGE_LITERAL_SOURCE,
            "H'40000' at line 3 of src/hello.asm does not fit its length — ASMA072E",
        ),
    ],
)
def test_a_value_outside_its_length_refuses_naming_the_statement(
    source: bytes, message: str, tmp_path: Path
):
    program = _assemble(source, tmp_path)

    with pytest.raises(DcValueOutOfRange) as refused:
        object_module(program)

    assert str(refused.value) == message


@covers(NotLanguageFeature.INFRASTRUCTURE)
def test_star_in_a_duplicated_literal_is_the_instruction_address_in_every_copy(
    tmp_path: Path,
):
    program = _assemble(LITERAL_STAR_SOURCE, tmp_path)
    vm = _start(program)
    base = _base(vm, "TEST")

    assert vm.load(base + 8, 8) == list((base + 2).to_bytes(4, "big")) * 2


@covers(NotLanguageFeature.INFRASTRUCTURE)
def test_a_channel_command_word_naming_an_unresolved_symbol_holds_its_stub(
    tmp_path: Path,
):
    program = _assemble(EXTERNAL_CHANNEL_COMMAND_SOURCE, tmp_path)
    vm = _start(program)
    stub = vm.current_frame.local_vars[STUBS_LOW_VAR].value

    assert vm.load(_base(vm, "TEST") + 8, 8) == [
        0x02,
        *(stub % (1 << 24)).to_bytes(3, "big"),
        *[0x00, 0x00, 0x00, 0x04],
    ]


@covers(NotLanguageFeature.INFRASTRUCTURE)
def test_an_s_type_literal_resolves_through_the_using_at_its_pool(tmp_path: Path):
    program = _assemble(S_LITERAL_SOURCE, tmp_path)
    vm = _start(program)

    assert vm.load(_base(vm, "TEST") + 8, 2) == [0xB0, 0x0C]


@covers(NotLanguageFeature.INFRASTRUCTURE)
def test_an_address_in_a_dsect_is_its_offset(tmp_path: Path):
    program = _assemble(DSECT_ADDRESS_SOURCE, tmp_path)
    vm = _start(program)

    assert object_module(program).relocations == ()
    assert vm.load(_base(vm, "MAIN") + 8, 6) == [0, 0, 0, 4, 0, 6]
