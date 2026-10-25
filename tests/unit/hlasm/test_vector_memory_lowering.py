# pyright: standard
"""Vector load and store lowerings: whole registers move 16 bytes per register with VLM and VSTM wrapping, element forms touch one element's bytes, run-time-length forms zero V1 then copy byte by byte, VRV forms read V2's element before V1 is written, invalid fields abend S0C6 before any access; no SYMBOLIC in any of the 38."""

from hlasm_asg.program.abs_address import AbsAddress
from hlasm_asg.program.storage_operand import StorageOperand
from interpreter.hlasm.opcodes.vector_memory import VECTOR_MEMORY_LOWERINGS
from interpreter.instructions import Symbolic
from tests.covers import NotLanguageFeature, covers
from tests.unit.hlasm.fp_trace import ADDRESS, D8, SPECIFICATION, lowered_ir, trace
from tests.unit.hlasm.lowering_helpers import imm_operand, mask_operand, reg_operand
from tests.unit.hlasm.lowering_helpers import vec_reg_operand as vr

VRV = StorageOperand(
    kind="STORAGE",
    displacement=8,
    index=3,
    base=12,
    written=AbsAddress(kind="ABS", value=8),
)
IMMEDIATES = ("VLEIB", "VLEIH", "VLEIF", "VLEIG")
GATHER_SCATTER = ("VGEF", "VGEG", "VSCEF", "VSCEG")
LOOP = [
    "StoreVar __hlasm_ss_at 0",
    "read storage +1",
    "write storage +1",
    "StoreVar __hlasm_ss_at reg",
]


@covers(NotLanguageFeature.INFRASTRUCTURE)
def test_whole_register_forms_move_sixteen_bytes_per_register_and_wrap_from_31():
    assert {
        "VL": trace("VL", (vr(1), D8, mask_operand(3))),
        "VST": trace("VST", (vr(1), D8)),
        "VLR": trace("VLR", (vr(1), vr(2))),
        "VLM": trace("VLM", (vr(30), vr(1), D8)),
        "VSTM": trace("VSTM", (vr(2), vr(3), D8)),
        "VLBR": trace("VLBR", (vr(1), D8, mask_operand(4))),
        "VSTER": trace("VSTER", (vr(1), D8, mask_operand(2))),
    } == {
        "VL": [ADDRESS, "read storage +16", "write vr 16+16"],
        "VST": ["read vr 16+16", ADDRESS, "write storage +16"],
        "VLR": ["read vr 32+16", "write vr 16+16"],
        "VLM": [
            ADDRESS,
            "read storage +32",
            "write vr 480+32",
            "read storage +32",
            "write vr 0+32",
        ],
        "VSTM": [ADDRESS, "read vr 32+32", "write storage +32"],
        "VLBR": [ADDRESS, "read storage +16", "write vr 16+16"],
        "VSTER": ["read vr 16+16", ADDRESS, "write storage +16"],
    }


@covers(NotLanguageFeature.INFRASTRUCTURE)
def test_element_forms_touch_only_one_elements_bytes_and_vrv_reads_v2_first():
    assert {
        "VLEF": trace("VLEF", (vr(1), D8, mask_operand(3))),
        "VSTEH": trace("VSTEH", (vr(1), D8, mask_operand(7))),
        "VLEIG": trace("VLEIG", (vr(1), imm_operand(-1), mask_operand(1))),
        "VLEBRG": trace("VLEBRG", (vr(1), D8, mask_operand(1))),
        "VSTEBRF": trace("VSTEBRF", (vr(1), D8, mask_operand(0))),
        "VLREP": trace("VLREP", (vr(1), D8, mask_operand(2))),
        "VLBRREP": trace("VLBRREP", (vr(1), D8, mask_operand(1))),
        "VLLEZ": trace("VLLEZ", (vr(1), D8, mask_operand(6))),
        "VLLEBRZ": trace("VLLEBRZ", (vr(1), D8, mask_operand(3))),
        "VGEF": trace("VGEF", (vr(1), VRV, mask_operand(3))),
        "VSCEG": trace("VSCEG", (vr(1), VRV, mask_operand(1))),
    } == {
        "VLEF": [ADDRESS, "read storage +4", "write vr 28+4"],
        "VSTEH": ["read vr 30+2", ADDRESS, "write storage +2"],
        "VLEIG": ["write vr 24+8"],
        "VLEBRG": [ADDRESS, "read storage +8", "write vr 24+8"],
        "VSTEBRF": ["read vr 16+4", ADDRESS, "write storage +4"],
        "VLREP": [ADDRESS, "read storage +4", "write vr 16+16"],
        "VLBRREP": [ADDRESS, "read storage +2", "write vr 16+16"],
        "VLLEZ": [ADDRESS, "read storage +4", "write vr 16+16"],
        "VLLEBRZ": [ADDRESS, "read storage +8", "write vr 16+16"],
        "VGEF": ["read vr 60+4", ADDRESS, "read storage +4", "write vr 28+4"],
        "VSCEG": ["read vr 56+8", ADDRESS, "read vr 24+8", "write storage +8"],
    }


@covers(NotLanguageFeature.INFRASTRUCTURE)
def test_run_time_length_forms_copy_byte_by_byte_and_loads_zero_v1_first():
    assert {
        "VLL": trace("VLL", (vr(1), reg_operand(3), D8)),
        "VSTL": trace("VSTL", (vr(1), reg_operand(3), D8)),
        "VLBB": trace("VLBB", (vr(1), D8, mask_operand(6))),
    } == {
        "VLL": [ADDRESS, "read gpr 28+4", "write vr 16+16", *LOOP],
        "VSTL": [ADDRESS, "read gpr 28+4", *LOOP],
        "VLBB": [ADDRESS, "write vr 16+16", *LOOP],
    }


@covers(NotLanguageFeature.INFRASTRUCTURE)
def test_an_invalid_field_abends_s0c6_before_any_access():
    invalid = {
        "VLEF": (vr(1), D8, mask_operand(4)),
        "VSTEG": (vr(1), D8, mask_operand(2)),
        "VLEIH": (vr(1), imm_operand(1), mask_operand(8)),
        "VGEG": (vr(1), VRV, mask_operand(2)),
        "VSCEF": (vr(1), VRV, mask_operand(4)),
        "VLEBRH": (vr(1), D8, mask_operand(8)),
        "VLREP": (vr(1), D8, mask_operand(4)),
        "VLBRREP": (vr(1), D8, mask_operand(0)),
        "VLLEZ": (vr(1), D8, mask_operand(5)),
        "VLLEBRZ": (vr(1), D8, mask_operand(0)),
        "VLBR": (vr(1), D8, mask_operand(0)),
        "VLER": (vr(1), D8, mask_operand(4)),
        "VLBB": (vr(1), D8, mask_operand(7)),
        "VLM": (vr(0), vr(16), D8),
        "VSTM": (vr(20), vr(19), D8),
    }

    assert {m: trace(m, operands) for m, operands in invalid.items()} == {
        m: [SPECIFICATION] for m in invalid
    }


@covers(NotLanguageFeature.INFRASTRUCTURE)
def test_every_vector_load_and_store_lowers_without_symbolic():
    forms = {
        **{m: (vr(1), D8, mask_operand(1)) for m in VECTOR_MEMORY_LOWERINGS},
        "VLR": (vr(1), vr(2)),
        "VLM": (vr(1), vr(4), D8),
        "VSTM": (vr(1), vr(4), D8),
        "VLL": (vr(1), reg_operand(3), D8),
        "VSTL": (vr(1), reg_operand(3), D8),
        **{m: (vr(1), imm_operand(-7), mask_operand(1)) for m in IMMEDIATES},
        **{m: (vr(1), VRV, mask_operand(1)) for m in GATHER_SCATTER},
    }
    lowered = {m: lowered_ir(m, operands) for m, operands in forms.items()}

    assert (
        len(lowered),
        [m for m, ir in lowered.items() if any(isinstance(i, Symbolic) for i in ir)],
        [m for m, ir in lowered.items() if trace(m, forms[m]) == [SPECIFICATION]],
    ) == (38, [], [])
