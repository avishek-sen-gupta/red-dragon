# pyright: standard
"""TRANSLATE EXTENDED: translates the R1 operand in place through the R2 table up to a byte equal to the GR0 bits 56-63 test byte, in one execution; R1 advances and R1+1 counts down by the bytes processed."""

from hlasm_asg.program.machine_statement import MachineStatement
from interpreter.hlasm.byte_loop import emit_scan_loop
from interpreter.hlasm.compare_cc import emit_loop_exit_cc
from interpreter.hlasm.effective_address import register_address
from interpreter.hlasm.hlasm_constants import BYTE_MASK, ONE_BYTE
from interpreter.hlasm.hlasm_emitter import HlasmEmitter
from interpreter.hlasm.long_registers import operand_pairs, store_progress
from interpreter.hlasm.opcodes.even_odd import even_odd
from interpreter.hlasm.translation_table import translate_byte
from interpreter.hlasm.unit_value import UnitReader, unit_reader
from interpreter.instructions import BranchIf, Label_
from interpreter.ir import CodeLabel
from interpreter.operator_kind import BinopKind
from interpreter.register import Register

TEST_REGISTER = 0
EXHAUSTED_CC = 0
TEST_BYTE_CC = 1


def _translate_unless_test(
    emitter: HlasmEmitter,
    addresses: tuple[Register, Register],
    test: tuple[UnitReader, Register],
    at: Register,
    found: CodeLabel,
) -> None:
    read, test_byte = test
    argument = read(addresses[0], at)
    more = emitter.fresh_label("hl_tre_more")
    equal = emitter.binop(BinopKind.EQ, argument, test_byte)
    emitter.emit_inst(BranchIf(cond_reg=equal, branch_targets=(found, more)))
    emitter.emit_inst(Label_(label=more))
    translate_byte(emitter, addresses, argument, at)


def _test_byte(emitter: HlasmEmitter) -> Register:
    return emitter.binop(
        BinopKind.BIT_AND, emitter.load_gr32(TEST_REGISTER), emitter.int_(BYTE_MASK)
    )


def _lower(emitter: HlasmEmitter, statement: MachineStatement) -> None:
    first, second = operand_pairs(statement)
    test = (unit_reader(emitter, ONE_BYTE), _test_byte(emitter))
    start = register_address(emitter, first)
    length = emitter.load_gr32(first + 1)
    addresses = (start, register_address(emitter, second))
    found = emitter.fresh_label("hl_tre_found")
    at, _ = emit_scan_loop(
        emitter,
        (emitter.int_(0), length),
        ONE_BYTE,
        lambda at: _translate_unless_test(emitter, addresses, test, at, found),
    )
    emit_loop_exit_cc(emitter, (EXHAUSTED_CC, TEST_BYTE_CC), found)
    store_progress(
        emitter,
        first,
        emitter.binop(BinopKind.ADD, start, at),
        emitter.binop(BinopKind.SUB, length, at),
    )


TRANSLATE_EXTENDED = even_odd(_lower)
