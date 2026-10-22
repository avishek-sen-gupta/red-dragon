# pyright: standard
"""A data field EX sets at run time: its arithmetic is IR, a span of its length is one block per set bit of the length, 256 bytes down to 1, at increasing offsets, and a dispatch on it is a chain of equality tests."""

from collections.abc import Callable, Mapping
from dataclasses import dataclass

from interpreter.hlasm.data_field import (
    DataField,
    FieldCase,
    FieldFallback,
    FieldPart,
)
from interpreter.hlasm.hlasm_constants import (
    BINARY_BYTES_TO_INT,
    BITS_PER_BYTE,
    ONE_BYTE,
    SPAN_VALUE_VAR,
)
from interpreter.hlasm.hlasm_emitter import HlasmEmitter
from interpreter.instructions import Branch, BranchIf, Label_, StoreVar
from interpreter.ir import CodeLabel
from interpreter.operator_kind import BinopKind
from interpreter.register import Register

LONGEST_SPAN_BITS = 8
SPAN_OFFSET_BITS = (2 << LONGEST_SPAN_BITS) - 1
SPAN_BLOCKS = tuple(1 << k for k in range(LONGEST_SPAN_BITS, -1, -1))


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

    def _block(
        self, emitter: HlasmEmitter, size: int, move: Callable[[Register, int], None]
    ) -> None:
        present, absent = emitter.fresh_label("hl_span_block"), emitter.fresh_label(
            "hl_span_next"
        )
        bit = emitter.binop(BinopKind.BIT_AND, self.register, emitter.int_(size))
        emitter.emit_inst(BranchIf(cond_reg=bit, branch_targets=(present, absent)))
        emitter.emit_inst(Label_(label=present))
        before = emitter.int_(SPAN_OFFSET_BITS & ~(2 * size - 1))
        move(emitter.binop(BinopKind.BIT_AND, self.register, before), size)
        emitter.emit_inst(Label_(label=absent))

    def _append(
        self,
        emitter: HlasmEmitter,
        read: tuple[Register, Register],
        offset: Register,
        size: int,
    ) -> None:
        address, unsigned = read
        image = emitter.load_bytes(address, offset, size)
        block = emitter.call(BINARY_BYTES_TO_INT, (image, unsigned))
        moved = emitter.binop(
            BinopKind.LSHIFT,
            emitter.load_var(SPAN_VALUE_VAR),
            emitter.int_(BITS_PER_BYTE * size),
        )
        combined = emitter.binop(BinopKind.BIT_OR, moved, block)
        emitter.emit_inst(StoreVar(name=SPAN_VALUE_VAR, value_reg=combined))

    def loaded(self, emitter: HlasmEmitter, address: Register) -> Register:
        emitter.emit_inst(StoreVar(name=SPAN_VALUE_VAR, value_reg=emitter.int_(0)))
        read = (address, emitter.unsigned_flag())
        _ = [
            self._block(
                emitter,
                size,
                lambda offset, width: self._append(emitter, read, offset, width),
            )
            for size in SPAN_BLOCKS
        ]
        return emitter.load_var(SPAN_VALUE_VAR)

    def copied(
        self, emitter: HlasmEmitter, addresses: tuple[Register, Register]
    ) -> None:
        target, source = addresses
        _ = [
            self._block(
                emitter,
                size,
                lambda offset, width: emitter.write_bytes(
                    target, offset, width, emitter.load_bytes(source, offset, width)
                ),
            )
            for size in SPAN_BLOCKS
        ]

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
