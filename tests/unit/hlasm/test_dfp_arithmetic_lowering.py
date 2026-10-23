# pyright: standard
"""DFP lowerings: each operand is read and decoded by the format's IR function in builtin-argument order, one builtin call, then the trap ladder with the result encoded before its store; the A forms' modifier replaces the FPC read; invalid pairs abend before any access; no SYMBOLIC."""

from collections.abc import Mapping

from hlasm_asg.program.operand import Operand
from interpreter.instructions import Symbolic
from tests.covers import NotLanguageFeature, covers
from tests.unit.hlasm.fp_trace import (
    ADDRESS,
    CC,
    D8,
    READ_FPC,
    SPECIFICATION,
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


@covers(NotLanguageFeature.INFRASTRUCTURE)
def test_builtin_forms_decode_in_argument_order_then_call_then_trap_and_encode():
    traces = {
        "ADTR": trace("ADTR", registers(1, 2, 3)),
        "ADTRA": trace("ADTRA", (*registers(1, 2, 3), mask_operand(1))),
        "SXTR": trace("SXTR", registers(0, 4, 8)),
        "DDTRA": trace("DDTRA", (*registers(1, 2, 3), mask_operand(0))),
        "CDTR": trace("CDTR", registers(1, 2)),
        "RRDTR": trace("RRDTR", (*registers(1, 3, 2), mask_operand(0))),
    }

    assert traces == {
        "ADTR": [
            READ_FPC,
            "read fpr 16+8",
            DECODE_LONG,
            "read fpr 24+8",
            DECODE_LONG,
            "call dfp add_long",
            *ladder(ENCODE_LONG, "write fpr 8+8", CC),
        ],
        "ADTRA": [
            "read fpr 16+8",
            DECODE_LONG,
            "read fpr 24+8",
            DECODE_LONG,
            "call dfp add_long",
            *ladder(ENCODE_LONG, "write fpr 8+8", CC),
        ],
        "SXTR": [
            READ_FPC,
            "read fpr 32+8",
            "read fpr 48+8",
            DECODE_EXTENDED,
            "read fpr 64+8",
            "read fpr 80+8",
            DECODE_EXTENDED,
            "call dfp subtract_extended",
            *ladder(ENCODE_EXTENDED, "write fpr 0+8", "write fpr 16+8", CC),
        ],
        "DDTRA": [
            READ_FPC,
            "read fpr 16+8",
            DECODE_LONG,
            "read fpr 24+8",
            DECODE_LONG,
            "call dfp divide_long",
            *ladder(ENCODE_LONG, "write fpr 8+8"),
        ],
        "CDTR": [
            "read fpr 8+8",
            DECODE_LONG,
            "read fpr 16+8",
            DECODE_LONG,
            "call dfp compare_long",
            *ladder(CC),
        ],
        "RRDTR": [
            READ_FPC,
            "read fpr 24+8",
            DECODE_LONG,
            "read gpr 16+8",
            "call dfp reround_long",
            *ladder(ENCODE_LONG, "write fpr 8+8"),
        ],
    }


@covers(NotLanguageFeature.INFRASTRUCTURE)
def test_field_forms_decode_and_compute_in_ir():
    traces = {
        "CEDTR": trace("CEDTR", registers(1, 2)),
        "LTDTR": trace("LTDTR", registers(1, 2)),
        "EEDTR": trace("EEDTR", registers(1, 2)),
        "IEXTR": trace("IEXTR", registers(4, 1, 2)),
        "SLDT": trace("SLDT", (reg_operand(1), reg_operand(3), D8)),
        "TDCET": trace("TDCET", (reg_operand(1), D8)),
        "TDGXT": trace("TDGXT", (reg_operand(4), D8)),
    }

    assert traces == {
        "CEDTR": ["read fpr 8+8", DECODE_LONG, "read fpr 16+8", DECODE_LONG, CC],
        "LTDTR": [
            "read fpr 16+8",
            DECODE_LONG,
            *ladder(ENCODE_LONG, "write fpr 8+8", CC),
        ],
        "EEDTR": ["read fpr 16+8", DECODE_LONG, "write gpr 8+8"],
        "IEXTR": [
            "read gpr 16+8",
            "read fpr 8+8",
            "read fpr 24+8",
            DECODE_EXTENDED,
            ENCODE_EXTENDED,
            "write fpr 32+8",
            "write fpr 48+8",
        ],
        "SLDT": [ADDRESS, "read fpr 24+8", DECODE_LONG, ENCODE_LONG, "write fpr 8+8"],
        "TDCET": [ADDRESS, "read fpr 8+4", "call dfp decode_short", CC],
        "TDGXT": [ADDRESS, "read fpr 32+8", "read fpr 48+8", DECODE_EXTENDED, CC],
    }


@covers(NotLanguageFeature.INFRASTRUCTURE)
def test_invalid_pairs_abend_before_any_access():
    traces = [
        trace("AXTR", registers(2, 4, 8)),
        trace("MXTRA", (*registers(0, 6, 8), mask_operand(1))),
        trace("DXTR", registers(0, 4, 14)),
        trace("CXTR", registers(1, 2)),
        trace("LTXTR", registers(0, 6)),
        trace("EEXTR", registers(2, 2)),
        trace("IEXTR", registers(2, 1, 4)),
        trace(
            "FIXTR", (reg_operand(0), mask_operand(0), reg_operand(6), mask_operand(0))
        ),
        trace("QAXTR", (*registers(0, 4, 10), mask_operand(0))),
        trace("RRXTR", (*registers(4, 2, 1), mask_operand(0))),
        trace("SLXT", (reg_operand(0), reg_operand(2), D8)),
        trace("SRXT", (reg_operand(6), reg_operand(4), D8)),
        trace("TDCXT", (reg_operand(2), D8)),
        trace("TDGXT", (reg_operand(3), D8)),
    ]

    assert traces == [[SPECIFICATION]] * 14


FAMILIES: Mapping[str, tuple[Operand, ...]] = {
    "ADTR AXTR SDTR SXTR MDTR MXTR DDTR DXTR": registers(0, 4, 8),
    "ADTRA AXTRA SDTRA SXTRA MDTRA MXTRA DDTRA DXTRA": (
        *registers(0, 4, 8),
        mask_operand(3),
    ),
    "CDTR CXTR KDTR KXTR CEDTR CEXTR LTDTR LTXTR": registers(0, 4),
    "EEDTR EEXTR ESDTR ESXTR": registers(2, 4),
    "IEDTR IEXTR": registers(0, 4, 2),
    "FIDTR FIXTR": (reg_operand(0), mask_operand(1), reg_operand(4), mask_operand(4)),
    "QADTR QAXTR RRDTR RRXTR": (*registers(0, 4, 1), mask_operand(3)),
    "SLDT SLXT SRDT SRXT": (reg_operand(0), reg_operand(4), D8),
    "TDCET TDCDT TDCXT TDGET TDGDT TDGXT": (reg_operand(0), D8),
}


@covers(NotLanguageFeature.INFRASTRUCTURE)
def test_every_mnemonic_lowers_without_symbolic():
    lowered = {
        m: lowered_ir(m, operands)
        for names, operands in FAMILIES.items()
        for m in names.split()
    }

    assert len(lowered) == 46
    assert [
        m for m, ir in lowered.items() if any(isinstance(i, Symbolic) for i in ir)
    ] == []
