# pyright: standard
"""HFP arithmetic lowerings: operands read in builtin-argument order, one builtin call, then the program-mask ladder (suppressing abends, the store, the CC, the completing abends), holding only the checks the operation can raise; the sign forms are IR alone; invalid pairs abend before any access."""

from collections.abc import Mapping

from hlasm_asg.program.operand import Operand
from interpreter.instructions import Symbolic
from tests.covers import NotLanguageFeature, covers
from tests.unit.hlasm.fp_trace import (
    ADDRESS,
    CC,
    D8,
    READ_PM,
    SPECIFICATION,
    lowered_ir,
    registers,
    trace,
)
from tests.unit.hlasm.lowering_helpers import reg_operand

OVERFLOW, UNDERFLOW, SIGNIFICANCE = (
    f"StoreVar __hlasm_abend {code}" for code in ("S0CC", "S0CD", "S0CE")
)
NORMALIZED = (OVERFLOW, UNDERFLOW, SIGNIFICANCE)
UNNORMALIZED = (OVERFLOW, SIGNIFICANCE)
PRODUCT = (OVERFLOW, UNDERFLOW)


def _ladder(completing: tuple[str, ...], *deliver: str) -> list[str]:
    return [READ_PM, *deliver, *completing]


@covers(NotLanguageFeature.INFRASTRUCTURE)
def test_builtin_forms_read_operands_then_call_then_run_the_program_mask_ladder():
    traces = {
        "ADR": trace("ADR", registers(2, 4)),
        "AU": trace("AU", (reg_operand(1), D8)),
        "AXR": trace("AXR", registers(0, 4)),
        "CDR": trace("CDR", registers(1, 2)),
        "CE": trace("CE", (reg_operand(1), D8)),
        "MDER": trace("MDER", registers(1, 2)),
        "MXD": trace("MXD", (reg_operand(4), D8)),
        "DDR": trace("DDR", registers(1, 2)),
        "SQER": trace("SQER", registers(1, 2)),
        "HDR": trace("HDR", registers(1, 2)),
        "FIDR": trace("FIDR", registers(1, 2)),
        "MAER": trace("MAER", registers(1, 3, 2)),
        "MSD": trace("MSD", (reg_operand(1), reg_operand(3), D8)),
        "MYR": trace("MYR", registers(4, 3, 2)),
        "MAYR": trace("MAYR", registers(6, 3, 2)),
        "MAYL": trace("MAYL", (reg_operand(5), reg_operand(3), D8)),
    }

    assert traces == {
        "ADR": [
            "read vr 32+8",
            "read vr 64+8",
            "call hfp add_long",
            *_ladder(NORMALIZED, "write vr 32+8", CC),
        ],
        "AU": [
            "read vr 16+4",
            ADDRESS,
            "read storage +4",
            "call hfp add_unnormalized_short",
            *_ladder(UNNORMALIZED, "write vr 16+4", CC),
        ],
        "AXR": [
            "read vr 0+8",
            "read vr 32+8",
            "read vr 64+8",
            "read vr 96+8",
            "call hfp add_extended",
            *_ladder(NORMALIZED, "write vr 0+8", "write vr 32+8", CC),
        ],
        "CDR": ["read vr 16+8", "read vr 32+8", "call hfp compare_long", CC],
        "CE": [
            "read vr 16+4",
            ADDRESS,
            "read storage +4",
            "call hfp compare_short",
            CC,
        ],
        "MDER": [
            "read vr 16+4",
            "read vr 32+4",
            "call hfp multiply_lengthened_short",
            *_ladder(PRODUCT, "write vr 16+8"),
        ],
        "MXD": [
            "read vr 64+8",
            ADDRESS,
            "read storage +8",
            "call hfp multiply_lengthened_long",
            *_ladder(PRODUCT, "write vr 64+8", "write vr 96+8"),
        ],
        "DDR": [
            "read vr 16+8",
            "read vr 32+8",
            "call hfp divide_long",
            "StoreVar __hlasm_abend S0CF",
            *_ladder(PRODUCT, "write vr 16+8"),
        ],
        "SQER": [
            "read vr 32+4",
            "call hfp square_root_short",
            "StoreVar __hlasm_abend S0DD",
            "write vr 16+4",
        ],
        "HDR": [
            "read vr 32+8",
            "call hfp halve_long",
            *_ladder((UNDERFLOW,), "write vr 16+8"),
        ],
        "FIDR": ["read vr 32+8", "call hfp load_fp_integer_long", "write vr 16+8"],
        "MAER": [
            "read vr 48+4",
            "read vr 32+4",
            "read vr 16+4",
            "call hfp multiply_add_short",
            *_ladder(PRODUCT, "write vr 16+4"),
        ],
        "MSD": [
            "read vr 48+8",
            ADDRESS,
            "read storage +8",
            "read vr 16+8",
            "call hfp multiply_subtract_long",
            *_ladder(PRODUCT, "write vr 16+8"),
        ],
        "MYR": [
            "read vr 48+8",
            "read vr 32+8",
            "call hfp multiply_unnormalized_long",
            "write vr 64+8",
            "write vr 96+8",
        ],
        "MAYR": [
            "read vr 48+8",
            "read vr 32+8",
            "read vr 96+8",
            "call hfp multiply_add_unnormalized_long",
            "write vr 64+8",
            "write vr 96+8",
        ],
        "MAYL": [
            "read vr 48+8",
            ADDRESS,
            "read storage +8",
            "read vr 80+8",
            "call hfp multiply_add_unnormalized_long",
            "write vr 80+8",
        ],
    }


@covers(NotLanguageFeature.INFRASTRUCTURE)
def test_sign_forms_are_ir_on_the_image():
    traces = {
        "LTDR": trace("LTDR", registers(1, 2)),
        "LCER": trace("LCER", registers(1, 2)),
        "LNXR": trace("LNXR", registers(0, 4)),
        "LPDR": trace("LPDR", registers(3, 3)),
    }

    assert traces == {
        "LTDR": ["read vr 32+8", "write vr 16+8", CC],
        "LCER": ["read vr 32+4", "write vr 16+4", CC],
        "LNXR": [
            "read vr 64+8",
            "read vr 96+8",
            "write vr 0+8",
            "write vr 32+8",
            CC,
        ],
        "LPDR": ["read vr 48+8", "write vr 48+8", CC],
    }


@covers(NotLanguageFeature.INFRASTRUCTURE)
def test_invalid_pairs_abend_before_any_access():
    traces = [
        trace("AXR", registers(2, 4)),
        trace("SXR", registers(0, 6)),
        trace("CXR", registers(6, 4)),
        trace("MXR", registers(4, 2)),
        trace("MXDR", registers(2, 4)),
        trace("MXD", (reg_operand(6), D8)),
        trace("DXR", registers(0, 3)),
        trace("SQXR", registers(14, 0)),
        trace("FIXR", registers(0, 7)),
        trace("MYR", registers(2, 3, 4)),
        trace("MY", (reg_operand(7), reg_operand(3), D8)),
        trace("LTXR", registers(7, 0)),
        trace("LCXR", registers(0, 2)),
        trace("LNXR", registers(10, 1)),
        trace("LPXR", registers(6, 4)),
    ]

    assert traces == [[SPECIFICATION]] * 15


RR = registers(0, 4)
RX = (reg_operand(0), D8)
FAMILIES: Mapping[str, tuple[Operand, ...]] = {
    "AER ADR AXR SER SDR SXR AUR AWR SUR SWR CER CDR CXR": RR,
    "MEER MDR MXR MDER MER MXDR DER DDR DXR HER HDR": RR,
    "SQER SQDR SQXR FIER FIDR FIXR": RR,
    "LTER LTDR LTXR LCER LCDR LCXR LNER LNDR LNXR LPER LPDR LPXR": RR,
    "AE AD SE SD AU AW SU SW CE CD MEE MD MDE ME MXD DE DD SQE SQD": RX,
    "MAER MADR MSER MSDR MYR MYHR MYLR MAYR MAYHR MAYLR": registers(0, 3, 2),
    "MAE MAD MSE MSD MY MYH MYL MAY MAYH MAYL": (reg_operand(0), reg_operand(3), D8),
}


@covers(NotLanguageFeature.INFRASTRUCTURE)
def test_every_mnemonic_lowers_without_symbolic():
    lowered = {
        m: lowered_ir(m, operands)
        for names, operands in FAMILIES.items()
        for m in names.split()
    }

    assert len(lowered) == 81
    assert [
        m for m, ir in lowered.items() if any(isinstance(i, Symbolic) for i in ir)
    ] == []
