# pyright: standard
"""TRANSLATE ONE TO ONE, ONE TO TWO, TWO TO ONE and TWO TO TWO: the R2 characters translate through the GR1 table into R1, up to a function equal to the GR0 test character unless M3 bit 3 is on, in one execution."""

from collections.abc import Callable

from hlasm_asg.program.machine_statement import MachineStatement
from interpreter.hlasm.byte_loop import emit_scan_loop
from interpreter.hlasm.compare_cc import emit_loop_exit_cc
from interpreter.hlasm.effective_address import register_address
from interpreter.hlasm.hlasm_constants import (
    BITS_PER_BYTE,
    HALFWORD_BYTES,
    ONE_BYTE,
)
from interpreter.hlasm.hlasm_emitter import HlasmEmitter
from interpreter.hlasm.long_registers import (
    advance_address,
    operand_pairs,
    store_progress,
    unit_length,
)
from interpreter.hlasm.opcodes.even_odd import even_odd
from interpreter.hlasm.operands import optional_mask_operand
from interpreter.hlasm.statement_lowering import StatementLowering
from interpreter.hlasm.translation_table import Rescale, rescale, table_address
from interpreter.hlasm.unit_value import UnitReader, unit_reader, unit_value
from interpreter.instructions import BranchIf, Label_
from interpreter.ir import CodeLabel
from interpreter.operator_kind import BinopKind
from interpreter.register import Register

type FunctionCheck = Callable[[Register], None]
type Widths = tuple[int, int]

TEST_REGISTER = 0
CONTROL_OPERAND = 2
NO_CONTROLS = 0
TEST_CHARACTER_CONTROL = 0b0001
EXHAUSTED_CC = 0
TEST_CHARACTER_CC = 1


def _test_check(emitter: HlasmEmitter, width: int, found: CodeLabel) -> FunctionCheck:
    value = unit_value(emitter, width)
    character = emitter.binop(
        BinopKind.BIT_AND,
        emitter.load_gr32(TEST_REGISTER),
        emitter.int_((1 << (BITS_PER_BYTE * width)) - 1),
    )

    def check(function: Register) -> None:
        more = emitter.fresh_label("hl_tr_more")
        equal = emitter.binop(BinopKind.EQ, value(function), character)
        emitter.emit_inst(BranchIf(cond_reg=equal, branch_targets=(found, more)))
        emitter.emit_inst(Label_(label=more))

    return check


def _no_check(function: Register) -> None:
    return


def _translate_character(
    emitter: HlasmEmitter,
    addresses: tuple[Register, Register, Register],
    units: tuple[UnitReader, Rescale, Rescale, int],
    check: FunctionCheck,
    at: Register,
) -> None:
    target, source, table = addresses
    read, to_function, to_target, function_width = units
    function = emitter.load_bytes(table, to_function(read(source, at)), function_width)
    check(function)
    emitter.write_bytes(target, to_target(at), function_width, function)


def _test(
    emitter: HlasmEmitter, controls: int, width: int
) -> tuple[FunctionCheck, Callable[[], None]]:
    if controls & TEST_CHARACTER_CONTROL:
        return _no_check, lambda: emitter.set_cc(emitter.int_(EXHAUSTED_CC))
    found = emitter.fresh_label("hl_tr_found")
    return _test_check(emitter, width, found), lambda: emit_loop_exit_cc(
        emitter, (EXHAUSTED_CC, TEST_CHARACTER_CC), found
    )


def _units(
    emitter: HlasmEmitter, widths: Widths
) -> tuple[UnitReader, Rescale, Rescale, int]:
    argument_width, function_width = widths
    return (
        unit_reader(emitter, argument_width),
        rescale(emitter, (ONE_BYTE, function_width)),
        rescale(emitter, widths),
        function_width,
    )


def _complete(
    emitter: HlasmEmitter,
    pairs: tuple[int, int],
    addresses: tuple[Register, Register],
    progress: tuple[Register, Register, Register],
) -> None:
    first, second = pairs
    target, source = addresses
    length, at, stored = progress
    advance_address(emitter, second, source, at)
    store_progress(
        emitter,
        first,
        emitter.binop(BinopKind.ADD, target, stored),
        emitter.binop(BinopKind.SUB, length, at),
    )


def _translate(widths: Widths) -> StatementLowering:
    def lower(emitter: HlasmEmitter, statement: MachineStatement) -> None:
        pairs = operand_pairs(statement)
        length = unit_length(emitter, pairs[0], widths[0])
        check, finish = _test(
            emitter,
            optional_mask_operand(statement, CONTROL_OPERAND, NO_CONTROLS),
            widths[1],
        )
        addresses = (
            register_address(emitter, pairs[0]),
            register_address(emitter, pairs[1]),
        )
        table = (*addresses, table_address(emitter))
        units = _units(emitter, widths)
        at, _ = emit_scan_loop(
            emitter,
            (emitter.int_(0), length),
            widths[0],
            lambda at: _translate_character(emitter, table, units, check, at),
        )
        finish()
        _complete(emitter, pairs, addresses, (length, at, units[2](at)))

    return even_odd(lower)


TRANSLATE_ONE_TO_ONE = _translate((ONE_BYTE, ONE_BYTE))
TRANSLATE_ONE_TO_TWO = _translate((ONE_BYTE, HALFWORD_BYTES))
TRANSLATE_TWO_TO_ONE = _translate((HALFWORD_BYTES, ONE_BYTE))
TRANSLATE_TWO_TO_TWO = _translate((HALFWORD_BYTES, HALFWORD_BYTES))
