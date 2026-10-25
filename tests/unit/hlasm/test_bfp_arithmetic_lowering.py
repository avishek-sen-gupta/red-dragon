# pyright: standard
"""BFP arithmetic lowerings: operands read in builtin-argument order, one builtin call, then the trap ladder (suppress, one delivery of the value or the scaled value, flags, inexact trap); static checks abend before any access; compares, test data class and sign forms are IR alone."""

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


@covers(NotLanguageFeature.INFRASTRUCTURE)
def test_ieee_forms_read_operands_in_argument_order_then_call_then_trap():
    traces = {
        "ADBR": trace("ADBR", registers(2, 4)),
        "AEB": trace("AEB", (reg_operand(1), D8)),
        "AXBR": trace("AXBR", registers(0, 4)),
        "MDBR": trace("MDBR", registers(1, 2)),
        "MAEBR": trace("MAEBR", registers(1, 3, 2)),
        "MADB": trace("MADB", (reg_operand(1), reg_operand(3), D8)),
        "MXDBR": trace("MXDBR", registers(4, 2)),
        "CDBR": trace("CDBR", registers(1, 2)),
        "FIEBR": trace("FIEBR", (reg_operand(1), mask_operand(0), reg_operand(2))),
        "FIDBRA": trace(
            "FIDBRA",
            (reg_operand(1), mask_operand(5), reg_operand(2), mask_operand(4)),
        ),
        "DIDBR": trace("DIDBR", (*registers(1, 3, 2), mask_operand(0))),
        "DIEBR": trace("DIEBR", (*registers(1, 3, 2), mask_operand(7))),
        "TCDB": trace("TCDB", (reg_operand(1), D8)),
    }

    assert traces == {
        "ADBR": [
            READ_FPC,
            "read vr 32+8",
            "read vr 64+8",
            "call add_long",
            *ladder("write vr 32+8", CC),
        ],
        "AEB": [
            READ_FPC,
            "read vr 16+4",
            ADDRESS,
            "read storage +4",
            "call add_short",
            *ladder("write vr 16+4", CC),
        ],
        "AXBR": [
            READ_FPC,
            "read vr 0+8",
            "read vr 32+8",
            "read vr 64+8",
            "read vr 96+8",
            "call add_extended",
            *ladder("write vr 0+8", "write vr 32+8", CC),
        ],
        "MDBR": [
            READ_FPC,
            "read vr 16+8",
            "read vr 32+8",
            "call multiply_long",
            *ladder("write vr 16+8"),
        ],
        "MAEBR": [
            READ_FPC,
            "read vr 48+4",
            "read vr 32+4",
            "read vr 16+4",
            "call multiply_add_short",
            *ladder("write vr 16+4"),
        ],
        "MADB": [
            READ_FPC,
            "read vr 48+8",
            ADDRESS,
            "read storage +8",
            "read vr 16+8",
            "call multiply_add_long",
            *ladder("write vr 16+8"),
        ],
        "MXDBR": [
            "read vr 64+8",
            "read vr 32+8",
            "call multiply_lengthened_long",
            *ladder("write vr 64+8", "write vr 96+8"),
        ],
        "CDBR": ["read vr 16+8", "read vr 32+8", *ladder(CC)],
        "FIEBR": [
            READ_FPC,
            "read vr 32+4",
            "call round_to_integral_short",
            *ladder("write vr 16+4"),
        ],
        "FIDBRA": [
            "read vr 32+8",
            "call round_to_integral_long",
            *ladder("write vr 16+8"),
        ],
        "DIDBR": [
            READ_FPC,
            READ_FPC,
            "read vr 16+8",
            "read vr 32+8",
            "call divide_to_integer_long",
            *ladder("write vr 16+8", "write vr 48+8", CC),
        ],
        "DIEBR": [
            READ_FPC,
            "read vr 16+4",
            "read vr 32+4",
            "call divide_to_integer_short",
            *ladder("write vr 16+4", "write vr 48+4", CC),
        ],
        "TCDB": ["read vr 16+8", ADDRESS, CC],
    }


@covers(NotLanguageFeature.INFRASTRUCTURE)
def test_sign_forms_are_ir_and_load_and_test_traps_an_snan():
    traces = {
        "LCDBR": trace("LCDBR", registers(1, 2)),
        "LNEBR": trace("LNEBR", registers(1, 2)),
        "LPXBR": trace("LPXBR", registers(0, 4)),
        "LTDBR": trace("LTDBR", registers(1, 2)),
    }

    assert traces == {
        "LCDBR": ["read vr 32+8", "write vr 16+8", CC],
        "LNEBR": ["read vr 32+4", "write vr 16+4", CC],
        "LPXBR": [
            "read vr 64+8",
            "read vr 96+8",
            "write vr 0+8",
            "write vr 32+8",
            CC,
        ],
        "LTDBR": ["read vr 32+8", *ladder("write vr 16+8", CC)],
    }


@covers(NotLanguageFeature.INFRASTRUCTURE)
def test_invalid_pairs_modifiers_and_registers_abend_before_any_access():
    traces = [
        trace("AXBR", registers(2, 4)),
        trace("SQXBR", registers(0, 6)),
        trace("MXDBR", registers(2, 4)),
        trace("MXDB", (reg_operand(6), D8)),
        trace("TCXB", (reg_operand(2), D8)),
        trace("LTXBR", registers(7, 0)),
        trace("FIEBR", (reg_operand(1), mask_operand(2), reg_operand(2))),
        trace(
            "FIXBRA",
            (reg_operand(1), mask_operand(4), reg_operand(6), mask_operand(0)),
        ),
        trace(
            "FIDBRA",
            (reg_operand(1), mask_operand(8), reg_operand(2), mask_operand(0)),
        ),
        trace("DIEBR", (*registers(1, 3, 2), mask_operand(2))),
        trace("DIDBR", (*registers(1, 1, 2), mask_operand(0))),
        trace("DIEBR", (*registers(1, 3, 3), mask_operand(0))),
        trace("DIDBR", (*registers(2, 3, 2), mask_operand(0))),
    ]

    assert traces == [[SPECIFICATION]] * 13


RR = registers(0, 4)
RX = (reg_operand(0), D8)
FAMILIES: Mapping[str, tuple[Operand, ...]] = {
    "AEBR ADBR AXBR SEBR SDBR SXBR MEEBR MDBR MXBR MDEBR MXDBR DEBR DDBR DXBR": RR,
    "AEB ADB SEB SDB MEEB MDB MDEB MXDB DEB DDB SQEB SQDB TCEB TCDB TCXB": RX,
    "SQEBR SQDBR SQXBR CEBR CDBR CXBR KEBR KDBR KXBR": RR,
    "CEB CDB KEB KDB": RX,
    "LTEBR LTDBR LTXBR LCEBR LCDBR LCXBR LNEBR LNDBR LNXBR LPEBR LPDBR LPXBR": RR,
    "MAEBR MADBR MSEBR MSDBR": registers(1, 3, 2),
    "MAEB MADB MSEB MSDB": (reg_operand(1), reg_operand(3), D8),
    "FIEBR FIDBR FIXBR": (reg_operand(0), mask_operand(0), reg_operand(4)),
    "FIEBRA FIDBRA FIXBRA": (
        reg_operand(0),
        mask_operand(0),
        reg_operand(4),
        mask_operand(4),
    ),
    "DIEBR DIDBR": (*registers(1, 3, 2), mask_operand(4)),
}


@covers(NotLanguageFeature.INFRASTRUCTURE)
def test_every_mnemonic_lowers_without_symbolic():
    lowered = {
        m: lowered_ir(m, operands)
        for names, operands in FAMILIES.items()
        for m in names.split()
    }

    assert len(lowered) == 70
    assert [
        m for m, ir in lowered.items() if any(isinstance(i, Symbolic) for i in ir)
    ] == []


@covers(NotLanguageFeature.INFRASTRUCTURE)
def test_bfp_ladder_carries_no_quantum_step():
    assert {m: len(lowered_ir(m, registers(1, 4))) for m in ("ADBR", "CDBR")} == {
        "ADBR": 164,
        "CDBR": 134,
    }
