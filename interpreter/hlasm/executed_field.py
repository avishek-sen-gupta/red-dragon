# pyright: standard
"""A data field EX sets at run time: its arithmetic is IR, a span of its length is a byte loop, and a dispatch on it is a chain of equality tests."""

from collections.abc import Mapping
from dataclasses import dataclass

from interpreter.hlasm.byte_loop import copy_byte, emit_counted_loop
from interpreter.hlasm.data_field import (
    DataField,
    FieldCase,
    FieldFallback,
    FieldPart,
)
from interpreter.hlasm.hlasm_constants import BITS_PER_BYTE, ONE_BYTE, SPAN_VALUE_VAR
from interpreter.hlasm.hlasm_emitter import HlasmEmitter
from interpreter.hlasm.unit_value import unit_reader
from interpreter.instructions import Branch, BranchIf, Label_, StoreVar
from interpreter.ir import CodeLabel
from interpreter.operator_kind import BinopKind
from interpreter.register import Register


@dataclass(frozen=True)
class ExecutedField(DataField):
    register: Register

    def value(self, emitter: HlasmEmitter) -> Register:
        return self.register

    def part(self, emitter: HlasmEmitter, shift: int, width: int) -> DataField:
        moved = emitter.binop(BinopKind.RSHIFT, self.register, emitter.int_(shift))
        mask = emitter.int_((1 << width) - 1)
        return ExecutedField(emitter.binop(BinopKind.BIT_AND, moved, mask))

    def length(self, emitter: HlasmEmitter) -> DataField:
        return ExecutedField(
            emitter.binop(BinopKind.ADD, self.register, emitter.int_(ONE_BYTE))
        )

    def shorter(
        self, emitter: HlasmEmitter, parts: tuple[FieldPart, FieldPart]
    ) -> DataField:
        first, second = (
            self.part(emitter, shift, width).value(emitter) for shift, width in parts
        )
        excess = emitter.binop(BinopKind.SUB, first, second)
        negative = emitter.binop(BinopKind.RSHIFT, excess, emitter.int_(BITS_PER_BYTE))
        least = emitter.binop(
            BinopKind.ADD, second, emitter.binop(BinopKind.BIT_AND, excess, negative)
        )
        return ExecutedField(least).length(emitter)

    def _append(self, emitter: HlasmEmitter, shift: Register, byte: Register) -> None:
        moved = emitter.binop(BinopKind.LSHIFT, emitter.load_var(SPAN_VALUE_VAR), shift)
        combined = emitter.binop(BinopKind.BIT_OR, moved, byte)
        emitter.emit_inst(StoreVar(name=SPAN_VALUE_VAR, value_reg=combined))

    def loaded(self, emitter: HlasmEmitter, address: Register) -> Register:
        emitter.emit_inst(StoreVar(name=SPAN_VALUE_VAR, value_reg=emitter.int_(0)))
        read = unit_reader(emitter, ONE_BYTE)
        shift = emitter.int_(BITS_PER_BYTE)
        emit_counted_loop(
            emitter,
            (emitter.int_(0), self.register),
            ONE_BYTE,
            lambda at: self._append(emitter, shift, read(address, at)),
        )
        return emitter.load_var(SPAN_VALUE_VAR)

    def copied(
        self, emitter: HlasmEmitter, addresses: tuple[Register, Register]
    ) -> None:
        emit_counted_loop(
            emitter,
            (emitter.int_(0), self.register),
            ONE_BYTE,
            lambda at: copy_byte(emitter, addresses, at),
        )

    def _case(
        self, emitter: HlasmEmitter, case: tuple[int, FieldCase], done: CodeLabel
    ) -> None:
        value, lower = case
        hit, miss = emitter.fresh_label("hl_field_case"), emitter.fresh_label(
            "hl_field_next"
        )
        equal = emitter.binop(BinopKind.EQ, self.register, emitter.int_(value))
        emitter.emit_inst(BranchIf(cond_reg=equal, branch_targets=(hit, miss)))
        emitter.emit_inst(Label_(label=hit))
        lower(emitter)
        emitter.emit_inst(Branch(label=done))
        emitter.emit_inst(Label_(label=miss))

    def select(
        self,
        emitter: HlasmEmitter,
        cases: Mapping[int, FieldCase],
        otherwise: FieldFallback,
    ) -> None:
        done = emitter.fresh_label("hl_field_done")
        _ = [self._case(emitter, case, done) for case in cases.items()]
        otherwise(emitter, f"other than {', '.join(str(v) for v in cases)}")
        emitter.emit_inst(Label_(label=done))
