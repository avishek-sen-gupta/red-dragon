# pyright: standard
"""A lowering whose byte 1 is a data field: the instruction's layout and its lowering given that field; written statements pass the assembled byte."""

from collections.abc import Callable, Mapping
from dataclasses import dataclass

from hlasm_asg.program.machine_statement import MachineStatement
from interpreter.hlasm.byte_one_layout import ByteOneLayout
from interpreter.hlasm.data_field import DataField, LowerWithField
from interpreter.hlasm.data_movement import Source
from interpreter.hlasm.hlasm_emitter import HlasmEmitter
from interpreter.hlasm.statement_lowering import StatementLowering
from interpreter.hlasm.written_field import WrittenField


@dataclass(frozen=True)
class FieldLowering:
    layout: ByteOneLayout
    lower: LowerWithField

    def written(self) -> StatementLowering:
        return lambda emitter, statement: self.lower(
            emitter, statement, WrittenField(self.layout.byte_of(statement))
        )


def written_lowerings(
    lowerings: Mapping[str, FieldLowering],
) -> Mapping[str, StatementLowering]:
    return {mnemonic: lowering.written() for mnemonic, lowering in lowerings.items()}


def with_field_source(build: Callable[[Source], StatementLowering]) -> LowerWithField:
    def lower(
        emitter: HlasmEmitter, statement: MachineStatement, field: DataField
    ) -> None:
        build(lambda into, _: field.value(into))(emitter, statement)

    return lower
