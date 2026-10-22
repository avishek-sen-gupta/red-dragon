# pyright: standard
"""TRANSLATE AND TEST EXTENDED and its reverse: the R1 arguments select GR1 table function codes, left to right or from the rightmost right to left, up to a nonzero one, in one execution; M3 sets the argument and function widths and the 255 limit."""

from collections.abc import Callable

from hlasm_asg.program.machine_statement import MachineStatement
from interpreter.hlasm.byte_loop import emit_scan_loop
from interpreter.hlasm.effective_address import register_address
from interpreter.hlasm.hlasm_constants import (
    BYTE_MASK,
    HALFWORD_BYTES,
    ONE_BYTE,
)
from interpreter.hlasm.hlasm_emitter import HlasmEmitter
from interpreter.hlasm.long_registers import (
    operand_pairs,
    store_progress,
    unit_length,
)
from interpreter.hlasm.opcodes.even_odd import even_odd
from interpreter.hlasm.operands import optional_mask_operand
from interpreter.hlasm.statement_lowering import StatementLowering
from interpreter.hlasm.translation_table import Rescale, rescale, table_address
from interpreter.hlasm.unit_value import UnitReader, unit_reader
from interpreter.instructions import Branch, BranchIf, Label_
from interpreter.ir import CodeLabel
from interpreter.operator_kind import BinopKind
from interpreter.register import Register

type ArgumentLimit = Callable[[Register, CodeLabel], None]

CONTROL_OPERAND = 2
NO_CONTROLS = 0
ARGUMENT_CHARACTER_CONTROL = 0b1000
FUNCTION_CODE_CONTROL = 0b0100
ARGUMENT_LIMIT_CONTROL = 0b0010
EXHAUSTED_CC = 0
NONZERO_FUNCTION_CC = 1


def _width(controls: int, control: int) -> int:
    return HALFWORD_BYTES if controls & control else ONE_BYTE


def _over_limit(emitter: HlasmEmitter) -> ArgumentLimit:
    limit = emitter.int_(BYTE_MASK)

    def skip(argument: Register, more: CodeLabel) -> None:
        lookup = emitter.fresh_label("hl_trte_lookup")
        over = emitter.binop(BinopKind.GT, argument, limit)
        emitter.emit_inst(BranchIf(cond_reg=over, branch_targets=(more, lookup)))
        emitter.emit_inst(Label_(label=lookup))

    return skip


def _unlimited(argument: Register, more: CodeLabel) -> None:
    return


def _argument_limit(emitter: HlasmEmitter, controls: int) -> ArgumentLimit:
    if controls & ARGUMENT_CHARACTER_CONTROL and controls & ARGUMENT_LIMIT_CONTROL:
        return _over_limit(emitter)
    return _unlimited


def _function_code(
    emitter: HlasmEmitter,
    addresses: tuple[Register, Register],
    units: tuple[UnitReader, ArgumentLimit, Rescale, UnitReader],
    scan: tuple[BinopKind, Register, CodeLabel],
    at: Register,
) -> Register:
    start, table = addresses
    read_argument, limit, to_function, read_function = units
    direction, no_offset, found = scan
    more = emitter.fresh_label("hl_trte_more")
    argument = read_argument(emitter.binop(direction, start, at), no_offset)
    limit(argument, more)
    function = read_function(table, to_function(argument))
    emitter.emit_inst(BranchIf(cond_reg=function, branch_targets=(found, more)))
    emitter.emit_inst(Label_(label=more))
    return function


def _units(
    emitter: HlasmEmitter, controls: int
) -> tuple[UnitReader, ArgumentLimit, Rescale, UnitReader]:
    function_width = _width(controls, FUNCTION_CODE_CONTROL)
    return (
        unit_reader(emitter, _width(controls, ARGUMENT_CHARACTER_CONTROL)),
        _argument_limit(emitter, controls),
        rescale(emitter, (ONE_BYTE, function_width)),
        unit_reader(emitter, function_width),
    )


def _exit_registers(
    emitter: HlasmEmitter, function_register: int, function: Register, found: CodeLabel
) -> None:
    join = emitter.fresh_label("hl_trte_join")
    emitter.store_gr32(function_register, emitter.int_(0))
    emitter.set_cc(emitter.int_(EXHAUSTED_CC))
    emitter.emit_inst(Branch(label=join))
    emitter.emit_inst(Label_(label=found))
    emitter.store_gr32(function_register, function)
    emitter.set_cc(emitter.int_(NONZERO_FUNCTION_CC))
    emitter.emit_inst(Label_(label=join))


def _translate_and_test(direction: BinopKind) -> StatementLowering:
    def lower(emitter: HlasmEmitter, statement: MachineStatement) -> None:
        first, function_register = operand_pairs(statement)
        controls = optional_mask_operand(statement, CONTROL_OPERAND, NO_CONTROLS)
        length = unit_length(
            emitter, first, _width(controls, ARGUMENT_CHARACTER_CONTROL)
        )
        addresses = (register_address(emitter, first), table_address(emitter))
        units = _units(emitter, controls)
        scan = (direction, emitter.int_(0), emitter.fresh_label("hl_trte_found"))
        at, function = emit_scan_loop(
            emitter,
            (scan[1], length),
            _width(controls, ARGUMENT_CHARACTER_CONTROL),
            lambda at: _function_code(emitter, addresses, units, scan, at),
        )
        _exit_registers(emitter, function_register, function, scan[2])
        store_progress(
            emitter,
            first,
            emitter.binop(direction, addresses[0], at),
            emitter.binop(BinopKind.SUB, length, at),
        )

    return even_odd(lower)


TRANSLATE_AND_TEST_EXTENDED = _translate_and_test(BinopKind.ADD)
TRANSLATE_AND_TEST_REVERSE_EXTENDED = _translate_and_test(BinopKind.SUB)
