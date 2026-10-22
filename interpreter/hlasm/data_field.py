# pyright: standard
"""A byte-1 data field as a lowering sees it: an SS length code, an SI immediate or an SVC number, written at assembly or set by EX at run time."""

from collections.abc import Callable, Mapping
from typing import Protocol

from hlasm_asg.program.machine_statement import MachineStatement
from interpreter.hlasm.hlasm_emitter import HlasmEmitter
from interpreter.register import Register

type FieldCase = Callable[[HlasmEmitter], None]
type FieldFallback = Callable[[HlasmEmitter, str], None]
type LowerWithField = Callable[[HlasmEmitter, MachineStatement, "DataField"], None]


class DataField(Protocol):
    def value(self, emitter: HlasmEmitter) -> Register: ...

    def part(self, emitter: HlasmEmitter, shift: int, width: int) -> "DataField": ...

    def length(self, emitter: HlasmEmitter) -> "DataField": ...

    def loaded(self, emitter: HlasmEmitter, address: Register) -> Register: ...

    def copied(
        self, emitter: HlasmEmitter, addresses: tuple[Register, Register]
    ) -> None: ...

    def select(
        self,
        emitter: HlasmEmitter,
        cases: Mapping[int, FieldCase],
        otherwise: FieldFallback,
    ) -> None: ...
