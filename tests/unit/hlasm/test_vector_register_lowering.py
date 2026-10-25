# pyright: standard
"""Vector register-manipulation lowerings: each family reads its source registers whole and writes V1 whole, VLGV and VLVG touch one element at the run-time index modulo the element count, VPKS and VPKLS call one element function per signedness and size and set the CC only with CS, invalid fields abend S0C6 before any access; no SYMBOLIC in any of the 23."""

from collections.abc import Sequence

from hlasm_asg.program.operand import Operand
from interpreter.hlasm.opcodes.vector_register import VECTOR_REGISTER_LOWERINGS
from interpreter.instructions import Binop, CallFunction, Const, Symbolic
from interpreter.operator_kind import BinopKind
from tests.covers import NotLanguageFeature, covers
from tests.unit.hlasm.fp_trace import ADDRESS, CC, D8, SPECIFICATION, lowered_ir, trace
from tests.unit.hlasm.lowering_helpers import imm_operand, mask_operand, reg_operand
from tests.unit.hlasm.lowering_helpers import vec_reg_operand as vr

READ_V2 = "read vr 32+16"
READ_V3 = "read vr 48+16"
READ_V4 = "read vr 64+16"
WRITE_V1 = "write vr 16+16"
ELEMENT_COUNTS = {0: 16, 1: 8, 2: 4, 3: 2}
SIZE_NAMES = {1: "halfword", 2: "word", 3: "doubleword"}


def _modulus_constants(mnemonic: str, operands: Sequence[Operand]) -> list[int | str]:
    ir = lowered_ir(mnemonic, operands)
    consts = {i.result_reg: i.value for i in ir if isinstance(i, Const)}
    return [
        consts[i.right]
        for i in ir
        if isinstance(i, Binop) and i.operator is BinopKind.MOD
    ]


def _calls(mnemonic: str, operands: Sequence[Operand]) -> list[str]:
    return [
        str(i.func_name)
        for i in lowered_ir(mnemonic, operands)
        if isinstance(i, CallFunction) and str(i.func_name).startswith("__hlasm_vector")
    ]


@covers(NotLanguageFeature.INFRASTRUCTURE)
def test_register_forms_read_their_sources_whole_and_write_v1_whole():
    forms = {
        "VGBM": (vr(1), imm_operand(0xF00F)),
        "VGM": (vr(1), imm_operand(2), imm_operand(5), mask_operand(1)),
        "VGEM": (vr(1), vr(2), mask_operand(4)),
        "VLVGP": (vr(1), reg_operand(2), reg_operand(3)),
        "VMRH": (vr(1), vr(2), vr(3), mask_operand(0)),
        "VMRL": (vr(1), vr(2), vr(3), mask_operand(3)),
        "VPDI": (vr(1), vr(2), vr(3), mask_operand(5)),
        "VPERM": (vr(1), vr(2), vr(3), vr(4)),
        "VBPERM": (vr(1), vr(2), vr(3)),
        "VPK": (vr(1), vr(2), vr(3), mask_operand(2)),
        "VREP": (vr(1), vr(3), imm_operand(2), mask_operand(1)),
        "VREPI": (vr(1), imm_operand(-2), mask_operand(0)),
        "VSEG": (vr(1), vr(2), mask_operand(2)),
        "VSEL": (vr(1), vr(2), vr(3), vr(4)),
        "VBLEND": (vr(1), vr(2), vr(3), vr(4), mask_operand(4)),
        "VUPH": (vr(1), vr(2), mask_operand(3)),
        "VUPLL": (vr(1), vr(2), mask_operand(0)),
    }

    assert {m: trace(m, operands) for m, operands in forms.items()} == {
        "VGBM": [WRITE_V1],
        "VGM": [WRITE_V1],
        "VGEM": [READ_V2, WRITE_V1],
        "VLVGP": ["read gpr 16+8", "read gpr 24+8", WRITE_V1],
        "VMRH": [READ_V2, READ_V3, WRITE_V1],
        "VMRL": [READ_V2, READ_V3, WRITE_V1],
        "VPDI": [READ_V2, READ_V3, WRITE_V1],
        "VPERM": [READ_V2, READ_V3, READ_V4, WRITE_V1],
        "VBPERM": [READ_V2, READ_V3, WRITE_V1],
        "VPK": [READ_V2, READ_V3, WRITE_V1],
        "VREP": ["read vr 52+2", WRITE_V1],
        "VREPI": [WRITE_V1],
        "VSEG": [READ_V2, WRITE_V1],
        "VSEL": [READ_V2, READ_V3, READ_V4, WRITE_V1],
        "VBLEND": [READ_V2, READ_V3, READ_V4, WRITE_V1],
        "VUPH": [READ_V2, WRITE_V1],
        "VUPLL": [READ_V2, WRITE_V1],
    }


@covers(NotLanguageFeature.INFRASTRUCTURE)
def test_vlgv_and_vlvg_take_the_address_modulo_the_element_count():
    loads = {
        code: _modulus_constants(
            "VLGV", (reg_operand(1), vr(3), D8, mask_operand(code))
        )
        for code in ELEMENT_COUNTS
    }
    inserts = {
        code: _modulus_constants(
            "VLVG", (vr(1), reg_operand(3), D8, mask_operand(code))
        )
        for code in ELEMENT_COUNTS
    }

    assert (
        loads,
        inserts,
        trace("VLGV", (reg_operand(1), vr(3), D8, mask_operand(2))),
        trace("VLVG", (vr(1), reg_operand(3), D8, mask_operand(1))),
    ) == (
        {code: [count, 1 << 64] for code, count in ELEMENT_COUNTS.items()},
        {code: [count, 1 << (128 // count)] for code, count in ELEMENT_COUNTS.items()},
        [ADDRESS, "read storage +4", "write gpr 8+8"],
        [ADDRESS, "read gpr 24+8", "write storage +2"],
    )


@covers(NotLanguageFeature.INFRASTRUCTURE)
def test_saturating_packs_call_one_function_per_kind_and_size_and_set_cc_only_with_cs():
    def operands(code: int, cs: int) -> tuple[Operand, ...]:
        return (vr(1), vr(2), vr(3), mask_operand(code), mask_operand(cs))

    assert (
        {
            (m, code): _calls(m, operands(code, 0))
            for m in ("VPKS", "VPKLS")
            for code in SIZE_NAMES
        },
        trace("VPKS", operands(1, 1)),
        trace("VPKLS", operands(3, 0)),
        trace("VPKS", operands(2, 0b1110)),
    ) == (
        {
            **{
                ("VPKS", code): [f"__hlasm_vector_pack_saturate_{name}"]
                for code, name in SIZE_NAMES.items()
            },
            **{
                ("VPKLS", code): [f"__hlasm_vector_pack_logical_saturate_{name}"]
                for code, name in SIZE_NAMES.items()
            },
        },
        [READ_V2, READ_V3, WRITE_V1, CC],
        [READ_V2, READ_V3, WRITE_V1],
        [READ_V2, READ_V3, WRITE_V1],
    )


@covers(NotLanguageFeature.INFRASTRUCTURE)
def test_an_invalid_element_size_or_index_abends_s0c6_before_any_access():
    invalid = {
        "VGM": (vr(1), imm_operand(0), imm_operand(7), mask_operand(4)),
        "VGEM": (vr(1), vr(2), mask_operand(5)),
        "VLGV": (reg_operand(1), vr(3), D8, mask_operand(4)),
        "VLVG": (vr(1), reg_operand(3), D8, mask_operand(4)),
        "VMRH": (vr(1), vr(2), vr(3), mask_operand(4)),
        "VMRL": (vr(1), vr(2), vr(3), mask_operand(4)),
        "VPK": (vr(1), vr(2), vr(3), mask_operand(0)),
        "VPKS": (vr(1), vr(2), vr(3), mask_operand(4), mask_operand(1)),
        "VPKLS": (vr(1), vr(2), vr(3), mask_operand(0), mask_operand(1)),
        "VREP": (vr(1), vr(3), imm_operand(8), mask_operand(1)),
        "VREPI": (vr(1), imm_operand(1), mask_operand(4)),
        "VSEG": (vr(1), vr(2), mask_operand(3)),
        "VBLEND": (vr(1), vr(2), vr(3), vr(4), mask_operand(5)),
        "VUPH": (vr(1), vr(2), mask_operand(4)),
        "VUPL": (vr(1), vr(2), mask_operand(4)),
        "VUPLH": (vr(1), vr(2), mask_operand(4)),
        "VUPLL": (vr(1), vr(2), mask_operand(4)),
    }

    negative = (vr(1), vr(3), imm_operand(-1), mask_operand(1))

    assert (
        {m: trace(m, operands) for m, operands in invalid.items()},
        trace("VREP", negative),
    ) == ({m: [SPECIFICATION] for m in invalid}, [SPECIFICATION])


@covers(NotLanguageFeature.INFRASTRUCTURE)
def test_every_vector_register_instruction_lowers_without_symbolic():
    forms = {
        **{
            m: (vr(1), vr(2), vr(3), mask_operand(1)) for m in VECTOR_REGISTER_LOWERINGS
        },
        "VGBM": (vr(1), imm_operand(0xFFFF)),
        "VGM": (vr(1), imm_operand(3), imm_operand(1), mask_operand(1)),
        "VGEM": (vr(1), vr(2), mask_operand(1)),
        "VLGV": (reg_operand(1), vr(3), D8, mask_operand(1)),
        "VLVG": (vr(1), reg_operand(3), D8, mask_operand(1)),
        "VLVGP": (vr(1), reg_operand(2), reg_operand(3)),
        "VPERM": (vr(1), vr(2), vr(3), vr(4)),
        "VBPERM": (vr(1), vr(2), vr(3)),
        "VPKS": (vr(1), vr(2), vr(3), mask_operand(1), mask_operand(1)),
        "VPKLS": (vr(1), vr(2), vr(3), mask_operand(1), mask_operand(1)),
        "VREP": (vr(1), vr(3), imm_operand(1), mask_operand(1)),
        "VREPI": (vr(1), imm_operand(-7), mask_operand(1)),
        "VSEG": (vr(1), vr(2), mask_operand(1)),
        "VSEL": (vr(1), vr(2), vr(3), vr(4)),
        "VBLEND": (vr(1), vr(2), vr(3), vr(4), mask_operand(1)),
        **{
            m: (vr(1), vr(2), mask_operand(1))
            for m in ("VUPH", "VUPL", "VUPLH", "VUPLL")
        },
    }
    lowered = {m: lowered_ir(m, operands) for m, operands in forms.items()}

    assert (
        len(lowered),
        [m for m, ir in lowered.items() if any(isinstance(i, Symbolic) for i in ir)],
        [m for m, ir in lowered.items() if trace(m, forms[m]) == [SPECIFICATION]],
    ) == (23, [], [])
