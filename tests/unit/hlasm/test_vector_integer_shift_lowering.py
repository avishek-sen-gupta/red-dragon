# pyright: standard
"""Vector integer shift and rotate lowerings: each form reads its source registers whole (and the D2(B2) address for a count) and writes V1 whole, VERIM reads V1 before writing it, VSLDB ignores I4 bits 0-3, an element size past doubleword or a set VSLD/VSRD I4 bit 0-4 abends S0C6 before any access; no SYMBOLIC in any of the 18 at any allowed size."""

from hlasm_asg.program.operand import Operand
from interpreter.hlasm.opcodes.vector_integer_shift import (
    VECTOR_INTEGER_SHIFT_LOWERINGS,
)
from interpreter.instructions import Symbolic
from tests.covers import NotLanguageFeature, covers
from tests.unit.hlasm.fp_trace import ADDRESS, D8, SPECIFICATION, lowered_ir, trace
from tests.unit.hlasm.lowering_helpers import imm_operand, mask_operand
from tests.unit.hlasm.lowering_helpers import vec_reg_operand as vr

READ_V1 = "read vr 16+16"
READ_V2 = "read vr 32+16"
READ_V3 = "read vr 48+16"
WRITE_V1 = "write vr 16+16"
BY_ADDRESS = ("VERLL", "VESL", "VESRA", "VESRL")
BY_VECTOR = ("VERLLV", "VESLV", "VESRAV", "VESRLV")
WHOLE = ("VSL", "VSLB", "VSRA", "VSRAB", "VSRL", "VSRLB")
DOUBLE = ("VSLD", "VSLDB", "VSRD")
SIZES = range(4)


def _forms(size: int, i4: int) -> dict[str, tuple[Operand, ...]]:
    return {
        **{m: (vr(1), vr(3), D8, mask_operand(size)) for m in BY_ADDRESS},
        **{m: (vr(1), vr(2), vr(3), mask_operand(size)) for m in BY_VECTOR},
        "VERIM": (vr(1), vr(2), vr(3), imm_operand(i4), mask_operand(size)),
        **{m: (vr(1), vr(2), vr(3)) for m in WHOLE},
        **{m: (vr(1), vr(2), vr(3), imm_operand(i4)) for m in DOUBLE},
    }


@covers(NotLanguageFeature.INFRASTRUCTURE)
def test_shift_and_rotate_forms_read_their_sources_whole_and_write_v1_whole():
    assert {m: trace(m, operands) for m, operands in _forms(2, 7).items()} == {
        **{m: [READ_V3, ADDRESS, WRITE_V1] for m in BY_ADDRESS},
        **{m: [READ_V2, READ_V3, WRITE_V1] for m in BY_VECTOR},
        "VERIM": [READ_V2, READ_V3, READ_V1, WRITE_V1],
        **{m: [READ_V2, READ_V3, WRITE_V1] for m in WHOLE},
        **{m: [READ_V2, READ_V3, WRITE_V1] for m in DOUBLE},
    }


@covers(NotLanguageFeature.INFRASTRUCTURE)
def test_an_invalid_element_size_or_double_shift_count_abends_s0c6_before_any_access():
    sized = ("VERIM", *BY_ADDRESS, *BY_VECTOR)
    invalid = [
        *((m, operands) for m, operands in _forms(4, 7).items() if m in sized),
        *((m, operands) for m, operands in _forms(5, 7).items() if m in sized),
        *(
            (m, _forms(0, i4)[m])
            for m in ("VSLD", "VSRD")
            for i4 in (8, 0x80, 0xF8, -1, 264)
        ),
    ]

    assert [trace(m, operands) for m, operands in invalid] == [
        [SPECIFICATION] for _ in invalid
    ]


@covers(NotLanguageFeature.INFRASTRUCTURE)
def test_every_vector_integer_shift_instruction_lowers_without_symbolic():
    lowered = {
        (m, size, i4): lowered_ir(m, operands)
        for size in SIZES
        for i4 in (0, 7, 256)
        for m, operands in _forms(size, i4).items()
    }

    assert (
        sorted({form[0] for form in lowered}),
        len(VECTOR_INTEGER_SHIFT_LOWERINGS),
        [k for k, ir in lowered.items() if any(isinstance(i, Symbolic) for i in ir)],
        [
            (m, size, i4)
            for m, size, i4 in lowered
            if trace(m, _forms(size, i4)[m]) == [SPECIFICATION]
        ],
    ) == (sorted(VECTOR_INTEGER_SHIFT_LOWERINGS), 18, [], [])


@covers(NotLanguageFeature.INFRASTRUCTURE)
def test_vsldb_takes_its_byte_index_from_i4_bits_4_to_7_only():
    def shown(i4: int) -> list[str]:
        return [str(i) for i in lowered_ir("VSLDB", _forms(0, i4)["VSLDB"])]

    assert (shown(0x13), shown(0xF9), shown(-13)) == (shown(3), shown(9), shown(3))
