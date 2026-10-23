# pyright: standard
"""DFP conversion lowerings: the rounding forms read the mode and the operand, call one builtin and run the trap ladder; invalid pairs abend before any access; no SYMBOLIC."""

from collections.abc import Mapping

from hlasm_asg.program.operand import Operand
from interpreter.instructions import Symbolic
from tests.covers import NotLanguageFeature, covers
from tests.unit.hlasm.fp_trace import (
    CC,
    DATA,
    READ_FPC,
    SPECIFICATION,
    WRITE_FPC,
    ladder,
    lowered_ir,
    registers,
    trace,
)
from tests.unit.hlasm.lowering_helpers import mask_operand, reg_operand

DECODE_LONG = "call dfp decode_long"
DECODE_EXTENDED = "call dfp decode_extended"
ENCODE_LONG = "call dfp encode_long"
ENCODE_EXTENDED = "call dfp encode_extended"


def _rrfe(r1: int, m3: int, r2: int, m4: int) -> tuple[Operand, ...]:
    return (reg_operand(r1), mask_operand(m3), reg_operand(r2), mask_operand(m4))


def _rrf(r1: int, m3: int, r2: int) -> tuple[Operand, ...]:
    return (reg_operand(r1), mask_operand(m3), reg_operand(r2))


@covers(NotLanguageFeature.INFRASTRUCTURE)
def test_fixed_point_forms_call_the_builtin_then_store_through_the_ladder():
    assert {
        "CGDTR": trace("CGDTR", _rrf(2, 0, 1)),
        "CLFXTR": trace("CLFXTR", _rrfe(2, 1, 4, 0)),
        "CDGTR": trace("CDGTR", registers(1, 2)),
        "CXLFTR": trace("CXLFTR", _rrfe(4, 0, 2, 0)),
        "CDLGTR": trace("CDLGTR", _rrfe(1, 5, 2, 4)),
    } == {
        "CGDTR": [
            READ_FPC,
            "read fpr 8+8",
            DECODE_LONG,
            "call dfp to_fixed_64_long",
            *ladder("write gpr 16+8", CC),
        ],
        "CLFXTR": [
            "read fpr 32+8",
            "read fpr 48+8",
            DECODE_EXTENDED,
            "call dfp to_logical_32_extended",
            *ladder("write gpr 20+4", CC),
        ],
        "CDGTR": [
            READ_FPC,
            "read gpr 16+8",
            "call dfp from_fixed_long",
            *ladder(ENCODE_LONG, "write fpr 8+8"),
        ],
        "CXLFTR": [
            READ_FPC,
            "read gpr 20+4",
            "call dfp from_fixed_extended",
            *ladder(ENCODE_EXTENDED, "write fpr 32+8", "write fpr 48+8"),
        ],
        "CDLGTR": [
            "read gpr 16+8",
            "call dfp from_fixed_long",
            *ladder(ENCODE_LONG, "write fpr 8+8"),
        ],
    }


@covers(NotLanguageFeature.INFRASTRUCTURE)
def test_lengthening_is_ir_and_rounding_merges_into_the_source_format_register():
    assert {
        "LDETR": trace("LDETR", (*registers(1, 2), mask_operand(0))),
        "LXDTR": trace("LXDTR", (*registers(4, 1), mask_operand(8))),
        "LEDTR": trace("LEDTR", _rrfe(1, 0, 2, 0)),
    } == {
        "LDETR": [
            "read fpr 16+4",
            "call dfp decode_short",
            *ladder(ENCODE_LONG, "write fpr 8+8"),
        ],
        "LXDTR": [
            "read fpr 8+8",
            DECODE_LONG,
            *ladder(ENCODE_EXTENDED, "write fpr 32+8", "write fpr 48+8"),
        ],
        "LEDTR": [
            READ_FPC,
            "read fpr 16+8",
            DECODE_LONG,
            "call dfp load_rounded_long",
            *ladder(
                "call dfp encode_short", ENCODE_LONG, "read fpr 8+8", "write fpr 8+8"
            ),
        ],
    }


@covers(NotLanguageFeature.INFRASTRUCTURE)
def test_register_decimal_forms_check_then_combine_or_spread_the_digits():
    assert {
        "CDSTR": trace("CDSTR", registers(1, 2)),
        "CXUTR": trace("CXUTR", registers(4, 6)),
        "CSDTR": trace("CSDTR", (*registers(2, 1), mask_operand(1))),
        "CUXTR": trace("CUXTR", registers(6, 4)),
    } == {
        "CDSTR": [
            "read gpr 16+8",
            READ_FPC,
            WRITE_FPC,
            DATA,
            "call decimal value_4_18",
            ENCODE_LONG,
            "write fpr 8+8",
        ],
        "CXUTR": [
            "read gpr 48+8",
            "read gpr 56+8",
            READ_FPC,
            WRITE_FPC,
            DATA,
            "call decimal value_4_36",
            ENCODE_EXTENDED,
            "write fpr 32+8",
            "write fpr 48+8",
        ],
        "CSDTR": [
            "read fpr 8+8",
            DECODE_LONG,
            "call decimal lanes_4_16",
            "write gpr 16+8",
        ],
        "CUXTR": [
            "read fpr 32+8",
            "read fpr 48+8",
            DECODE_EXTENDED,
            "call decimal lanes_4_34",
            "write gpr 48+8",
            "write gpr 56+8",
        ],
    }


@covers(NotLanguageFeature.INFRASTRUCTURE)
def test_invalid_pairs_abend_before_any_access():
    traces = [
        trace("CXFTR", _rrfe(2, 0, 1, 0)),
        trace("CXGTR", registers(6, 1)),
        trace("CXLGTR", _rrfe(3, 0, 1, 0)),
        trace("CFXTR", _rrfe(1, 0, 2, 0)),
        trace("CGXTRA", _rrfe(1, 0, 6, 0)),
        trace("CLGXTR", _rrfe(1, 0, 3, 0)),
        trace("LXDTR", (*registers(2, 1), mask_operand(0))),
        trace("LDXTR", _rrfe(1, 0, 6, 0)),
        trace("LDXTR", _rrfe(3, 0, 4, 0)),
        trace("CXSTR", registers(2, 4)),
        trace("CXSTR", registers(4, 5)),
        trace("CXUTR", registers(1, 3)),
        trace("CSXTR", (*registers(4, 2), mask_operand(0))),
        trace("CSXTR", (*registers(3, 4), mask_operand(0))),
        trace("CUXTR", registers(4, 6)),
    ]

    assert traces == [[SPECIFICATION]] * 15


FAMILIES: Mapping[str, tuple[Operand, ...]] = {
    "CDGTR CXGTR": registers(0, 4),
    "CDGTRA CXGTRA CDFTR CXFTR CDLFTR CXLFTR CDLGTR CXLGTR": _rrfe(0, 1, 4, 4),
    "CGDTR CGXTR": _rrf(4, 1, 0),
    "CFDTR CFXTR CGDTRA CGXTRA CLFDTR CLFXTR CLGDTR CLGXTR": _rrfe(4, 1, 0, 4),
    "LDETR LXDTR": (*registers(0, 4), mask_operand(8)),
    "LEDTR LDXTR": _rrfe(0, 1, 4, 12),
    "CDSTR CXSTR CDUTR CXUTR CUDTR CUXTR": registers(4, 8),
    "CSDTR CSXTR": (*registers(6, 4), mask_operand(1)),
}


@covers(NotLanguageFeature.INFRASTRUCTURE)
def test_every_mnemonic_lowers_without_symbolic():
    lowered = {
        m: lowered_ir(m, operands)
        for names, operands in FAMILIES.items()
        for m in names.split()
    }

    assert len(lowered) == 32
    assert [
        m for m, ir in lowered.items() if any(isinstance(i, Symbolic) for i in ir)
    ] == []
