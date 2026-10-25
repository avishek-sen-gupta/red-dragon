# pyright: standard
"""Vector integer add, subtract, average, multiply, Galois-field multiply, checksum, sum and divide lowerings: each form reads its source registers whole and writes V1 whole, VGFM and VGFMA call one carry-less multiply function per element size, defined once per program, the divides call one element function per operation, size and IDC and reach the S0DB exit only without IDC, an invalid M field abends S0C6 before any access; no SYMBOLIC in any of the 35."""

from collections.abc import Sequence

from hlasm_asg.program.operand import Operand
from interpreter.hlasm.hlasm_emitter import HlasmEmitter
from interpreter.hlasm.ir_function import define_called
from interpreter.hlasm.opcodes import OPCODE_LOWERINGS
from interpreter.hlasm.opcodes.vector_integer_arithmetic import (
    VECTOR_INTEGER_ARITHMETIC_LOWERINGS,
)
from interpreter.instructions import CallFunction, Label_, Symbolic
from tests.covers import NotLanguageFeature, covers
from tests.unit.hlasm.fp_trace import (
    READ_FPC,
    SPECIFICATION,
    WRITE_FPC,
    lowered_ir,
    trace,
)
from tests.unit.hlasm.lowering_helpers import machine_statement, mask_operand
from tests.unit.hlasm.lowering_helpers import vec_reg_operand as vr

READ_V2 = "read vr 32+16"
READ_V3 = "read vr 48+16"
READ_V4 = "read vr 64+16"
WRITE_V1 = "write vr 16+16"
VECTOR_PROCESSING = "StoreVar __hlasm_abend S0DB"
TWO_SOURCES = {
    "VA": 4,
    "VACC": 4,
    "VS": 4,
    "VSCBI": 4,
    "VAVG": 4,
    "VAVGL": 4,
    "VML": 4,
    "VMH": 4,
    "VMLH": 4,
    "VME": 3,
    "VMLE": 3,
    "VMO": 3,
    "VMLO": 3,
    "VGFM": 3,
    "VSUM": 1,
    "VSUMG": 2,
    "VSUMQ": 3,
}
THREE_SOURCES = {
    "VAC": 4,
    "VACCC": 4,
    "VSBI": 4,
    "VSBCBI": 4,
    "VMAL": 4,
    "VMAH": 4,
    "VMALH": 4,
    "VMAE": 3,
    "VMALE": 3,
    "VMAO": 3,
    "VMALO": 3,
    "VGFMA": 3,
}
DIVIDES = {
    "VD": "divide",
    "VDL": "divide_logical",
    "VR": "remainder",
    "VRL": "remainder_logical",
}
DIVIDE_SIZES = {2: "word", 3: "doubleword", 4: "quadword"}
INVALID = {
    **{
        m: 5
        for m in ("VA", "VACC", "VS", "VSCBI", "VAVG", "VAVGL", "VML", "VMH", "VMLH")
    },
    **{m: 4 for m in ("VME", "VMLE", "VMO", "VMLO", "VGFM")},
    "VSUM": 2,
    "VSUMG": 3,
    "VSUMQ": 1,
}
INVALID_THREE = {
    "VAC": 3,
    "VACCC": 0,
    "VSBI": 5,
    "VSBCBI": 3,
    **{m: 5 for m in ("VMAL", "VMAH", "VMALH")},
    **{m: 4 for m in ("VMAE", "VMALE", "VMAO", "VMALO", "VGFMA")},
}


def _two(code: int) -> tuple[Operand, ...]:
    return (vr(1), vr(2), vr(3), mask_operand(code))


def _three(code: int) -> tuple[Operand, ...]:
    return (vr(1), vr(2), vr(3), vr(4), mask_operand(code))


def _divide(code: int, control: int) -> tuple[Operand, ...]:
    return (vr(1), vr(2), vr(3), mask_operand(code), mask_operand(control))


def _multiply_sum(code: int) -> tuple[Operand, ...]:
    return (*_three(code), mask_operand(12))


def _calls(mnemonic: str, operands: Sequence[Operand]) -> list[str]:
    return [
        str(i.func_name)
        for i in lowered_ir(mnemonic, operands)
        if isinstance(i, CallFunction) and str(i.func_name).startswith("__hlasm_vector")
    ]


def _forms() -> dict[str, tuple[Operand, ...]]:
    return {
        **{m: _two(code) for m, code in TWO_SOURCES.items()},
        **{m: _three(code) for m, code in THREE_SOURCES.items()},
        "VMSL": _multiply_sum(3),
        "VCKSM": (vr(1), vr(2), vr(3)),
        **{m: _divide(2, 0) for m in DIVIDES},
    }


@covers(NotLanguageFeature.INFRASTRUCTURE)
def test_arithmetic_forms_read_their_sources_whole_and_write_v1_whole():
    forms = {m: o for m, o in _forms().items() if m not in DIVIDES}

    assert {m: trace(m, operands) for m, operands in forms.items()} == {
        **{m: [READ_V2, READ_V3, WRITE_V1] for m in TWO_SOURCES},
        **{m: [READ_V2, READ_V3, READ_V4, WRITE_V1] for m in THREE_SOURCES},
        "VMSL": [READ_V2, READ_V3, READ_V4, WRITE_V1],
        "VCKSM": [READ_V2, READ_V3, WRITE_V1],
    }


@covers(NotLanguageFeature.INFRASTRUCTURE)
def test_divides_call_one_function_per_operation_size_and_idc_and_trap_only_without_idc():
    assert (
        {
            (m, code, control): _calls(m, _divide(code, control))
            for m in DIVIDES
            for code in DIVIDE_SIZES
            for control in (0, 8)
        },
        trace("VD", _divide(2, 0)),
        trace("VRL", _divide(4, 0b0111)),
        trace("VDL", _divide(3, 0b1000)),
        trace("VR", _divide(2, 0b1111)),
    ) == (
        {
            (m, code, control): [
                f"__hlasm_vector_{kind}_{name}{'_masked' if control else ''}"
            ]
            for m, kind in DIVIDES.items()
            for code, name in DIVIDE_SIZES.items()
            for control in (0, 8)
        },
        [READ_V2, READ_V3, READ_FPC, WRITE_FPC, VECTOR_PROCESSING, WRITE_V1],
        [READ_V2, READ_V3, READ_FPC, WRITE_FPC, VECTOR_PROCESSING, WRITE_V1],
        [READ_V2, READ_V3, WRITE_V1],
        [READ_V2, READ_V3, WRITE_V1],
    )


@covers(NotLanguageFeature.INFRASTRUCTURE)
def test_an_invalid_m_field_abends_s0c6_before_any_access():
    invalid = {
        **{(m, code): _two(code) for m, code in INVALID.items()},
        **{(m, code): _three(code) for m, code in INVALID_THREE.items()},
        **{("VMSL", code): _multiply_sum(code) for code in (2, 4)},
        **{(m, 1): _divide(1, 8) for m in DIVIDES},
        **{(m, 5): _divide(5, 0) for m in DIVIDES},
    }

    assert {form: trace(form[0], operands) for form, operands in invalid.items()} == {
        form: [SPECIFICATION] for form in invalid
    }


@covers(NotLanguageFeature.INFRASTRUCTURE)
def test_every_vector_integer_arithmetic_instruction_lowers_without_symbolic():
    forms = _forms()
    lowered = {m: lowered_ir(m, operands) for m, operands in forms.items()}

    assert (
        sorted(lowered),
        len(VECTOR_INTEGER_ARITHMETIC_LOWERINGS),
        [m for m, ir in lowered.items() if any(isinstance(i, Symbolic) for i in ir)],
        [m for m, ir in lowered.items() if trace(m, forms[m]) == [SPECIFICATION]],
    ) == (sorted(VECTOR_INTEGER_ARITHMETIC_LOWERINGS), 35, [], [])


@covers(NotLanguageFeature.INFRASTRUCTURE)
def test_galois_forms_call_one_carryless_function_per_size_defined_once():
    emitter = HlasmEmitter()
    uses = [("VGFM", _two(0)), ("VGFMA", _three(0)), ("VGFM", _two(3))]
    _ = [
        OPCODE_LOWERINGS[m](emitter, machine_statement(m, operands))
        for m, operands in uses
    ]
    define_called(emitter)
    ir = emitter.instructions()
    calls = [
        str(i.func_name)
        for i in ir
        if isinstance(i, CallFunction) and str(i.func_name).startswith("__hlasm")
    ]
    defined = [
        str(i.label)
        for i in ir
        if isinstance(i, Label_) and str(i.label).startswith("func___hlasm")
    ]

    assert (calls, defined) == (
        ["__hlasm_vector_carryless_byte"] * 32
        + ["__hlasm_vector_carryless_doubleword"] * 2,
        [
            "func___hlasm_vector_carryless_byte_0",
            "func___hlasm_vector_carryless_doubleword_0",
        ],
    )
