# pyright: standard
"""The part of a general register an instruction reads and writes: its low word, its high word or all 64 bits."""

from collections.abc import Callable
from dataclasses import dataclass

from interpreter.hlasm.hlasm_constants import BITS_PER_BYTE
from interpreter.hlasm.hlasm_emitter import HlasmEmitter
from interpreter.operator_kind import BinopKind
from interpreter.register import Register


@dataclass(frozen=True)
class RegisterPart:
    load: Callable[[HlasmEmitter, int], Register]
    store: Callable[[HlasmEmitter, int, Register], None]
    bits: int

    def bytes(self) -> int:
        return self.bits // BITS_PER_BYTE

    def merge(
        self, emitter: HlasmEmitter, r: int, inserted: Register, field_mask: int
    ) -> None:
        kept = emitter.binop(
            BinopKind.BIT_AND,
            self.load(emitter, r),
            emitter.int_(((1 << self.bits) - 1) & ~field_mask),
        )
        self.store(emitter, r, emitter.binop(BinopKind.BIT_OR, kept, inserted))
