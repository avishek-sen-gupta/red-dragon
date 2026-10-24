# pyright: standard
"""Translates: TR, TRANSLATE AND TEST and its reverse, TRANSLATE EXTENDED, the one- and two-byte translates and TRANSLATE AND TEST EXTENDED and its reverse."""

from collections.abc import Callable, Mapping

from hlasm_asg.program.machine_statement import MachineStatement
from interpreter.hlasm.byte_loop import emit_byte_loop, emit_scan_loop
from interpreter.hlasm.byte_one_layouts import LENGTH_BYTE
from interpreter.hlasm.compare_cc import emit_cc_constant
from interpreter.hlasm.data_field import DataField, LowerWithField
from interpreter.hlasm.data_movement import FIRST_OPERAND, SECOND_OPERAND
from interpreter.hlasm.effective_address import (
    effective_address,
    length_operand_address,
)
from interpreter.hlasm.field_lowering import (
    FieldLowering,
    written_lowerings,
)
from interpreter.hlasm.hlasm_constants import (
    AMODE_31_LINK_BIT,
    BYTE_MASK,
    LOW_WORD_MASK,
    ONE_BYTE,
)
from interpreter.hlasm.hlasm_emitter import HlasmEmitter
from interpreter.hlasm.long_registers import store_address
from interpreter.hlasm.operands import storage_length_operand, storage_operand
from interpreter.hlasm.statement_lowering import StatementLowering
from interpreter.hlasm.translate_and_test_extended import (
    TRANSLATE_AND_TEST_EXTENDED,
    TRANSLATE_AND_TEST_REVERSE_EXTENDED,
)
from interpreter.hlasm.translate_characters import (
    TRANSLATE_ONE_TO_ONE,
    TRANSLATE_ONE_TO_TWO,
    TRANSLATE_TWO_TO_ONE,
    TRANSLATE_TWO_TO_TWO,
)
from interpreter.hlasm.translate_extended import TRANSLATE_EXTENDED
from interpreter.hlasm.translation_table import translate_byte
from interpreter.hlasm.unit_value import UnitReader, unit_reader
from interpreter.instructions import Branch, BranchIf, Label_
from interpreter.ir import CodeLabel
from interpreter.operator_kind import BinopKind
from interpreter.register import Register

type ArgumentStore = Callable[[HlasmEmitter, int, Register], None]

ARGUMENT_REGISTER = 1
FUNCTION_REGISTER = 2
NONE_CC = 0
FOUND_CC = 1
LAST_CC = 2


def _field(
    emitter: HlasmEmitter, statement: MachineStatement, field: DataField
) -> tuple[tuple[Register, Register], DataField]:
    first = storage_length_operand(statement, FIRST_OPERAND)
    start = length_operand_address(emitter, first)
    table = effective_address(emitter, storage_operand(statement, SECOND_OPERAND))
    return (start, table), field.length(emitter)


def _translate(
    emitter: HlasmEmitter, statement: MachineStatement, field: DataField
) -> None:
    addresses, length = _field(emitter, statement, field)
    read = unit_reader(emitter, ONE_BYTE)
    emit_byte_loop(
        emitter,
        length.value(emitter),
        lambda at: translate_byte(emitter, addresses, read(addresses[0], at), at),
    )


def _function_byte(
    emitter: HlasmEmitter,
    addresses: tuple[Register, Register],
    scan: tuple[UnitReader, BinopKind, Register],
    at: Register,
    found: CodeLabel,
) -> tuple[Register, Register]:
    start, table = addresses
    read, direction, no_offset = scan
    address = emitter.binop(direction, start, at)
    function = read(table, read(address, no_offset))
    more = emitter.fresh_label("hl_trt_more")
    emitter.emit_inst(BranchIf(cond_reg=function, branch_targets=(found, more)))
    emitter.emit_inst(Label_(label=more))
    return address, function


def _keep_bit_32(emitter: HlasmEmitter, r: int, address: Register) -> None:
    kept = emitter.binop(
        BinopKind.BIT_AND, emitter.load_gr32(r), emitter.int_(AMODE_31_LINK_BIT)
    )
    emitter.store_gr32(
        r, emitter.binop(BinopKind.BIT_OR, kept, emitter.masked_address(address))
    )


def _insert_function_byte(emitter: HlasmEmitter, function: Register) -> None:
    kept = emitter.binop(
        BinopKind.BIT_AND,
        emitter.load_gr32(FUNCTION_REGISTER),
        emitter.int_(LOW_WORD_MASK ^ BYTE_MASK),
    )
    emitter.store_gr32(
        FUNCTION_REGISTER, emitter.binop(BinopKind.BIT_OR, kept, function)
    )


def _found_cc(
    emitter: HlasmEmitter, at: Register, last: Register, done: CodeLabel
) -> None:
    remaining, exhausted = emitter.fresh_label("hl_trt_remaining"), emitter.fresh_label(
        "hl_trt_last"
    )
    is_last = emitter.binop(BinopKind.EQ, at, last)
    emitter.emit_inst(BranchIf(cond_reg=is_last, branch_targets=(exhausted, remaining)))
    emit_cc_constant(emitter, FOUND_CC, remaining, done)
    emit_cc_constant(emitter, LAST_CC, exhausted, done)
    emitter.emit_inst(Label_(label=done))


def _none_found(emitter: HlasmEmitter, found: CodeLabel, done: CodeLabel) -> None:
    emitter.set_cc(emitter.int_(NONE_CC))
    emitter.emit_inst(Branch(label=done))
    emitter.emit_inst(Label_(label=found))


def _translate_and_test(
    direction: BinopKind, store_argument: ArgumentStore
) -> LowerWithField:
    def lower(
        emitter: HlasmEmitter, statement: MachineStatement, field: DataField
    ) -> None:
        addresses, length = _field(emitter, statement, field)
        scan = (unit_reader(emitter, ONE_BYTE), direction, emitter.int_(0))
        found, done = emitter.fresh_label("hl_trt_found"), emitter.fresh_label(
            "hl_trt_done"
        )
        at, (address, function) = emit_scan_loop(
            emitter,
            (scan[2], length.value(emitter)),
            ONE_BYTE,
            lambda at: _function_byte(emitter, addresses, scan, at, found),
        )
        _none_found(emitter, found, done)
        store_argument(emitter, ARGUMENT_REGISTER, address)
        _insert_function_byte(emitter, function)
        _found_cc(emitter, at, field.value(emitter), done)

    return lower


TRANSLATE_FIELD_LOWERINGS: Mapping[str, FieldLowering] = {
    "TR": FieldLowering(LENGTH_BYTE, _translate),
    "TRT": FieldLowering(
        LENGTH_BYTE, _translate_and_test(BinopKind.ADD, store_address)
    ),
    "TRTR": FieldLowering(
        LENGTH_BYTE, _translate_and_test(BinopKind.SUB, _keep_bit_32)
    ),
}

TRANSLATE_LOWERINGS: Mapping[str, StatementLowering] = {
    **written_lowerings(TRANSLATE_FIELD_LOWERINGS),
    "TRE": TRANSLATE_EXTENDED,
    "TROO": TRANSLATE_ONE_TO_ONE,
    "TROT": TRANSLATE_ONE_TO_TWO,
    "TRTO": TRANSLATE_TWO_TO_ONE,
    "TRTT": TRANSLATE_TWO_TO_TWO,
    "TRTE": TRANSLATE_AND_TEST_EXTENDED,
    "TRTRE": TRANSLATE_AND_TEST_REVERSE_EXTENDED,
}
