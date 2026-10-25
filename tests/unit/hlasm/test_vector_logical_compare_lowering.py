# pyright: standard
"""Vector integer logical, compare, minimum and maximum, complement and count lowerings: each family reads its source registers whole and writes V1 whole, VEC and VECL read the PoO's one element of each operand and VTM both registers and set only the CC, VCEQ, VCH and VCHL call one element function per operation and size and set the CC only with CS, an invalid element size abends S0C6 before any access; no SYMBOLIC in any of the 24."""

from collections.abc import Sequence

from hlasm_asg.program.operand import Operand
from interpreter.hlasm.opcodes.vector_logical_compare import (
    VECTOR_LOGICAL_COMPARE_LOWERINGS,
)
from interpreter.instructions import CallFunction, Symbolic
from tests.covers import NotLanguageFeature, covers
from tests.unit.hlasm.fp_trace import CC, SPECIFICATION, lowered_ir, trace
from tests.unit.hlasm.lowering_helpers import imm_operand, mask_operand
from tests.unit.hlasm.lowering_helpers import vec_reg_operand as vr

READ_V1 = "read vr 16+16"
READ_V2 = "read vr 32+16"
READ_V3 = "read vr 48+16"
READ_V4 = "read vr 64+16"
WRITE_V1 = "write vr 16+16"
SIZE_NAMES = {0: "byte", 1: "halfword", 2: "word", 3: "doubleword", 4: "quadword"}
BITWISE = ("VN", "VNC", "VNN", "VNO", "VNX", "VO", "VOC", "VX")
PAIRWISE = ("VMN", "VMNL", "VMX", "VMXL")
SINGLE = ("VLC", "VLP", "VPOPCT", "VCLZ", "VCTZ")
COMPARES = {"VCEQ": "equal", "VCH": "high", "VCHL": "high_logical"}


def _calls(mnemonic: str, operands: Sequence[Operand]) -> list[str]:
    return [
        str(i.func_name)
        for i in lowered_ir(mnemonic, operands)
        if isinstance(i, CallFunction) and str(i.func_name).startswith("__hlasm_vector")
    ]


@covers(NotLanguageFeature.INFRASTRUCTURE)
def test_logical_compare_forms_read_their_sources_whole_and_write_v1_whole():
    forms = {
        **{m: (vr(1), vr(2), vr(3)) for m in BITWISE},
        "VEVAL": (vr(1), vr(2), vr(3), vr(4), imm_operand(0x96)),
        **{m: (vr(1), vr(2), vr(3), mask_operand(4)) for m in PAIRWISE},
        **{m: (vr(1), vr(2), mask_operand(3)) for m in SINGLE},
    }

    assert {m: trace(m, operands) for m, operands in forms.items()} == {
        **{m: [READ_V2, READ_V3, WRITE_V1] for m in BITWISE},
        "VEVAL": [READ_V2, READ_V3, READ_V4, WRITE_V1],
        **{m: [READ_V2, READ_V3, WRITE_V1] for m in PAIRWISE},
        **{m: [READ_V2, WRITE_V1] for m in SINGLE},
    }


@covers(NotLanguageFeature.INFRASTRUCTURE)
def test_element_compare_and_test_under_mask_read_their_operands_and_set_only_the_cc():
    elements = {
        code: trace("VEC", (vr(1), vr(2), mask_operand(code))) for code in SIZE_NAMES
    }

    assert (
        elements,
        trace("VECL", (vr(1), vr(2), mask_operand(2))),
        trace("VTM", (vr(1), vr(2))),
    ) == (
        {
            0: ["read vr 23+1", "read vr 39+1", CC],
            1: ["read vr 22+2", "read vr 38+2", CC],
            2: ["read vr 20+4", "read vr 36+4", CC],
            3: ["read vr 16+8", "read vr 32+8", CC],
            4: ["read vr 16+16", "read vr 32+16", CC],
        },
        ["read vr 20+4", "read vr 36+4", CC],
        [READ_V2, READ_V1, CC],
    )


@covers(NotLanguageFeature.INFRASTRUCTURE)
def test_element_compares_call_one_function_per_operation_and_size_and_set_cc_only_with_cs():
    def operands(code: int, cs: int) -> tuple[Operand, ...]:
        return (vr(1), vr(2), vr(3), mask_operand(code), mask_operand(cs))

    assert (
        {
            (m, code): _calls(m, operands(code, 1))
            for m in COMPARES
            for code in SIZE_NAMES
        },
        trace("VCEQ", operands(0, 1)),
        trace("VCH", operands(4, 0)),
        trace("VCHL", operands(2, 0b1110)),
    ) == (
        {
            (m, code): [f"__hlasm_vector_compare_{kind}_{name}"]
            for m, kind in COMPARES.items()
            for code, name in SIZE_NAMES.items()
        },
        [READ_V2, READ_V3, WRITE_V1, CC],
        [READ_V2, READ_V3, WRITE_V1],
        [READ_V2, READ_V3, WRITE_V1],
    )


@covers(NotLanguageFeature.INFRASTRUCTURE)
def test_an_invalid_element_size_abends_s0c6_before_any_access():
    invalid = {
        **{
            m: (vr(1), vr(2), vr(3), mask_operand(5), mask_operand(1)) for m in COMPARES
        },
        **{m: (vr(1), vr(2), mask_operand(5)) for m in ("VEC", "VECL")},
        **{m: (vr(1), vr(2), vr(3), mask_operand(5)) for m in PAIRWISE},
        **{m: (vr(1), vr(2), mask_operand(5)) for m in SINGLE},
        "VPOPCT": (vr(1), vr(2), mask_operand(4)),
    }

    assert {m: trace(m, operands) for m, operands in invalid.items()} == {
        m: [SPECIFICATION] for m in invalid
    }


@covers(NotLanguageFeature.INFRASTRUCTURE)
def test_every_vector_logical_compare_instruction_lowers_without_symbolic():
    forms = {
        **{m: (vr(1), vr(2), vr(3)) for m in BITWISE},
        "VEVAL": (vr(1), vr(2), vr(3), vr(4), imm_operand(0xFF)),
        **{
            m: (vr(1), vr(2), vr(3), mask_operand(4), mask_operand(1)) for m in COMPARES
        },
        **{m: (vr(1), vr(2), mask_operand(4)) for m in ("VEC", "VECL")},
        **{m: (vr(1), vr(2), vr(3), mask_operand(4)) for m in PAIRWISE},
        "VTM": (vr(1), vr(2)),
        **{m: (vr(1), vr(2), mask_operand(3)) for m in SINGLE},
    }
    lowered = {m: lowered_ir(m, operands) for m, operands in forms.items()}

    assert (
        sorted(lowered),
        len(VECTOR_LOGICAL_COMPARE_LOWERINGS),
        [m for m, ir in lowered.items() if any(isinstance(i, Symbolic) for i in ir)],
        [m for m, ir in lowered.items() if trace(m, forms[m]) == [SPECIFICATION]],
    ) == (sorted(VECTOR_LOGICAL_COMPARE_LOWERINGS), 24, [], [])
