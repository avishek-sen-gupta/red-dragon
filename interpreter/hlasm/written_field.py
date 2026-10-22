# pyright: standard
"""A data field written at assembly: its arithmetic is done at compile time, a span of its length is one block region access, and a dispatch on it picks one case."""

from collections.abc import Mapping
from dataclasses import dataclass

from interpreter.hlasm.data_field import DataField, FieldCase, FieldFallback
from interpreter.hlasm.hlasm_emitter import HlasmEmitter
from interpreter.register import Register


@dataclass(frozen=True)
class WrittenField(DataField):
    written: int

    def value(self, emitter: HlasmEmitter) -> Register:
        return emitter.int_(self.written)

    def part(self, emitter: HlasmEmitter, shift: int, width: int) -> DataField:
        return WrittenField((self.written >> shift) & ((1 << width) - 1))

    def length(self, emitter: HlasmEmitter) -> DataField:
        return WrittenField(self.written + 1)

    def loaded(self, emitter: HlasmEmitter, address: Register) -> Register:
        return emitter.load_storage(address, 0, self.written)

    def copied(
        self, emitter: HlasmEmitter, addresses: tuple[Register, Register]
    ) -> None:
        target, source = addresses
        start = emitter.int_(0)
        image = emitter.load_bytes(source, start, self.written)
        emitter.write_bytes(target, start, self.written, image)

    def select(
        self,
        emitter: HlasmEmitter,
        cases: Mapping[int, FieldCase],
        otherwise: FieldFallback,
    ) -> None:
        if self.written in cases:
            cases[self.written](emitter)
            return
        otherwise(emitter, str(self.written))
