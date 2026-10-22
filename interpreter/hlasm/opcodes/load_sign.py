# pyright: standard
"""Load and test, load complement, load positive and load negative opcodes: the loaded value's sign CC, with fixed-point overflow at the maximum negative number."""

from collections.abc import Mapping, Sequence

from hlasm_asg.program.machine_statement import MachineStatement
from interpreter.hlasm.data_movement import (
    Sink,
    Source,
    from_gr32,
    from_gr64,
    to_gr32,
    to_gr64,
)
from interpreter.hlasm.fixed_point_overflow import emit_fixed_point_overflow_check
from interpreter.hlasm.fixed_width_ir import (
    build_absolute_signed_cc_ir,
    build_load_test_cc_ir,
    build_negate_signed_cc_ir,
    build_negative_absolute_cc_ir,
)
from interpreter.hlasm.hlasm_constants import DOUBLEWORD_BITS, PARAM_VALUE, WORD_BITS
from interpreter.hlasm.hlasm_emitter import HlasmEmitter
from interpreter.hlasm.opcodes.operand_sources import (
    DOUBLEWORD_STORAGE,
    SIGNED_LOW_WORD,
    SIGNED_WORD_STORAGE,
    WORD_STORAGE,
)
from interpreter.hlasm.opcodes.result_and_cc import apply_result_and_cc, result_and_cc
from interpreter.hlasm.statement_lowering import StatementLowering
from interpreter.instructions import InstructionBase

type Operation = Sequence[InstructionBase]

LOAD_TEST_32 = build_load_test_cc_ir("hlasm.lt32", WORD_BITS)
LOAD_TEST_64 = build_load_test_cc_ir("hlasm.lt64", DOUBLEWORD_BITS)
COMPLEMENT_32 = build_negate_signed_cc_ir("hlasm.lc32", WORD_BITS)
COMPLEMENT_64 = build_negate_signed_cc_ir("hlasm.lc64", DOUBLEWORD_BITS)
POSITIVE_32 = build_absolute_signed_cc_ir("hlasm.lp32", WORD_BITS)
POSITIVE_64 = build_absolute_signed_cc_ir("hlasm.lp64", DOUBLEWORD_BITS)
NEGATIVE_32 = build_negative_absolute_cc_ir("hlasm.ln32", WORD_BITS)
NEGATIVE_64 = build_negative_absolute_cc_ir("hlasm.ln64", DOUBLEWORD_BITS)


def _unary(operation: Operation, source: Source, sink: Sink) -> StatementLowering:
    return result_and_cc(operation, [(PARAM_VALUE, source)], sink)


def _checked(operation: Operation, source: Source, sink: Sink) -> StatementLowering:
    def lower(emitter: HlasmEmitter, statement: MachineStatement) -> None:
        cc = apply_result_and_cc(
            emitter,
            operation,
            {PARAM_VALUE: source(emitter, statement)},
            lambda value: sink(emitter, statement, value),
        )
        emit_fixed_point_overflow_check(emitter, cc)

    return lower


LOAD_TESTS: Mapping[str, StatementLowering] = {
    "LT": _unary(LOAD_TEST_32, WORD_STORAGE, to_gr32),
    "LTR": _unary(LOAD_TEST_32, from_gr32(1), to_gr32),
    "LTG": _unary(LOAD_TEST_64, DOUBLEWORD_STORAGE, to_gr64),
    "LTGR": _unary(LOAD_TEST_64, from_gr64(1), to_gr64),
    "LTGF": _unary(LOAD_TEST_64, SIGNED_WORD_STORAGE, to_gr64),
    "LTGFR": _unary(LOAD_TEST_64, SIGNED_LOW_WORD, to_gr64),
}

SIGN_CHANGES: Mapping[str, StatementLowering] = {
    "LCR": _checked(COMPLEMENT_32, from_gr32(1), to_gr32),
    "LCGR": _checked(COMPLEMENT_64, from_gr64(1), to_gr64),
    "LCGFR": _unary(COMPLEMENT_64, SIGNED_LOW_WORD, to_gr64),
    "LPR": _checked(POSITIVE_32, from_gr32(1), to_gr32),
    "LPGR": _checked(POSITIVE_64, from_gr64(1), to_gr64),
    "LPGFR": _unary(POSITIVE_64, SIGNED_LOW_WORD, to_gr64),
    "LNR": _unary(NEGATIVE_32, from_gr32(1), to_gr32),
    "LNGR": _unary(NEGATIVE_64, from_gr64(1), to_gr64),
    "LNGFR": _unary(NEGATIVE_64, SIGNED_LOW_WORD, to_gr64),
}

LOAD_SIGN_LOWERINGS: Mapping[str, StatementLowering] = {**LOAD_TESTS, **SIGN_CHANGES}
