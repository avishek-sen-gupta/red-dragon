# pyright: standard
"""Boolean opcodes: AND, OR, exclusive OR and their complemented forms over registers, storage, immediates and storage fields."""

from collections.abc import Callable, Mapping

from hlasm_asg.program.machine_statement import MachineStatement
from interpreter.hlasm.boolean_connective import (
    AND,
    AND_WITH_COMPLEMENT,
    NAND,
    NOR,
    NOT_XOR,
    OR,
    OR_WITH_COMPLEMENT,
    XOR,
    BooleanConnective,
)
from interpreter.hlasm.byte_loop import emit_byte_loop
from interpreter.hlasm.byte_one_layouts import IMMEDIATE_BYTE, LENGTH_BYTE
from interpreter.hlasm.data_field import DataField
from interpreter.hlasm.data_movement import (
    FIRST_OPERAND,
    SECOND_OPERAND,
    Sink,
    Source,
    field_of,
    from_gr32,
    from_gr64,
    immediate,
    into_field,
    to_gr32,
    to_gr64,
)
from interpreter.hlasm.effective_address import (
    effective_address,
    length_operand_address,
)
from interpreter.hlasm.field_lowering import FieldLowering, written_lowerings
from interpreter.hlasm.fixed_width_ir import build_boolean_cc_ir, build_nonzero_ir
from interpreter.hlasm.hlasm_constants import (
    BITS_PER_BYTE,
    BYTES_COMBINED_VAR,
    DOUBLEWORD_BITS,
    HALFWORD_BITS,
    ONE_BYTE,
    PARAM_LEFT,
    PARAM_RIGHT,
    PARAM_VALUE,
    WORD_BITS,
)
from interpreter.hlasm.hlasm_emitter import HlasmEmitter
from interpreter.hlasm.inline_ir import inline_ir
from interpreter.hlasm.opcodes.operand_sources import DOUBLEWORD_STORAGE, WORD_STORAGE
from interpreter.hlasm.opcodes.result_and_cc import (
    Operation,
    result_and_cc,
    storage_immediate_result_and_cc,
)
from interpreter.hlasm.operands import storage_length_operand, storage_operand
from interpreter.hlasm.statement_lowering import StatementLowering
from interpreter.instructions import StoreVar
from interpreter.operator_kind import BinopKind
from interpreter.register import Register

type Combine = Callable[[Source, Source], StatementLowering]

HIGH_WORD_SHIFT = 32
HIGH_HALFWORD_SHIFT = 48
LOW_HIGH_HALFWORD_SHIFT = 16
NO_SHIFT = 0

NONZERO_BYTE = build_nonzero_ir("hlasm.nonzero8", BITS_PER_BYTE)


def _operation(connective: BooleanConnective, bits: int) -> Operation:
    return build_boolean_cc_ir(f"hlasm.boolean{bits}", bits, connective)


def _combine(connective: BooleanConnective, bits: int, sink: Sink) -> Combine:
    operation = _operation(connective, bits)
    return lambda left, right: result_and_cc(
        operation, ((PARAM_LEFT, left), (PARAM_RIGHT, right)), sink
    )


def _field(connective: BooleanConnective, bits: int, shift: int) -> StatementLowering:
    return _combine(connective, bits, into_field(bits, shift))(
        field_of(bits, shift), immediate(bits)
    )


def _storage_byte(connective: BooleanConnective) -> FieldLowering:
    return FieldLowering(
        IMMEDIATE_BYTE,
        storage_immediate_result_and_cc(
            _operation(connective, BITS_PER_BYTE), ONE_BYTE
        ),
    )


def _combine_byte(
    emitter: HlasmEmitter,
    operator: BinopKind,
    addresses: tuple[Register, Register],
    at: Register,
) -> None:
    first, second = (emitter.binop(BinopKind.ADD, a, at) for a in addresses)
    result = emitter.binop(
        operator,
        emitter.load_storage(first, 0, ONE_BYTE),
        emitter.load_storage(second, 0, ONE_BYTE),
    )
    emitter.store_storage(first, 0, ONE_BYTE, result)
    combined = emitter.binop(
        BinopKind.BIT_OR, emitter.load_var(BYTES_COMBINED_VAR), result
    )
    emitter.emit_inst(StoreVar(name=BYTES_COMBINED_VAR, value_reg=combined))


def _storage_to_storage(operator: BinopKind) -> FieldLowering:
    def lower(
        emitter: HlasmEmitter, statement: MachineStatement, field: DataField
    ) -> None:
        first = storage_length_operand(statement, FIRST_OPERAND)
        addresses = (
            length_operand_address(emitter, first),
            effective_address(emitter, storage_operand(statement, SECOND_OPERAND)),
        )
        emitter.emit_inst(StoreVar(name=BYTES_COMBINED_VAR, value_reg=emitter.int_(0)))
        emit_byte_loop(
            emitter,
            field.length(emitter).value(emitter),
            lambda at: _combine_byte(emitter, operator, addresses, at),
        )
        combined = emitter.load_var(BYTES_COMBINED_VAR)
        emitter.set_cc(inline_ir(emitter, NONZERO_BYTE, {PARAM_VALUE: combined}))

    return FieldLowering(LENGTH_BYTE, lower)


def _word(connective: BooleanConnective) -> Combine:
    return _combine(connective, WORD_BITS, to_gr32)


def _doubleword(connective: BooleanConnective) -> Combine:
    return _combine(connective, DOUBLEWORD_BITS, to_gr64)


def _distinct_word(connective: BooleanConnective) -> StatementLowering:
    return _word(connective)(from_gr32(1), from_gr32(2))


def _distinct_doubleword(connective: BooleanConnective) -> StatementLowering:
    return _doubleword(connective)(from_gr64(1), from_gr64(2))


AND_WORD = _word(AND)
AND_DOUBLEWORD = _doubleword(AND)
OR_WORD = _word(OR)
OR_DOUBLEWORD = _doubleword(OR)
XOR_WORD = _word(XOR)
XOR_DOUBLEWORD = _doubleword(XOR)

ANDS: Mapping[str, StatementLowering] = {
    "N": AND_WORD(from_gr32(0), WORD_STORAGE),
    "NY": AND_WORD(from_gr32(0), WORD_STORAGE),
    "NR": AND_WORD(from_gr32(0), from_gr32(1)),
    "NRK": AND_WORD(from_gr32(1), from_gr32(2)),
    "NG": AND_DOUBLEWORD(from_gr64(0), DOUBLEWORD_STORAGE),
    "NGR": AND_DOUBLEWORD(from_gr64(0), from_gr64(1)),
    "NGRK": AND_DOUBLEWORD(from_gr64(1), from_gr64(2)),
    "NIHF": _field(AND, WORD_BITS, HIGH_WORD_SHIFT),
    "NIHH": _field(AND, HALFWORD_BITS, HIGH_HALFWORD_SHIFT),
    "NIHL": _field(AND, HALFWORD_BITS, HIGH_WORD_SHIFT),
    "NILF": _field(AND, WORD_BITS, NO_SHIFT),
    "NILH": _field(AND, HALFWORD_BITS, LOW_HIGH_HALFWORD_SHIFT),
    "NILL": _field(AND, HALFWORD_BITS, NO_SHIFT),
}

ORS: Mapping[str, StatementLowering] = {
    "O": OR_WORD(from_gr32(0), WORD_STORAGE),
    "OY": OR_WORD(from_gr32(0), WORD_STORAGE),
    "OR": OR_WORD(from_gr32(0), from_gr32(1)),
    "ORK": OR_WORD(from_gr32(1), from_gr32(2)),
    "OG": OR_DOUBLEWORD(from_gr64(0), DOUBLEWORD_STORAGE),
    "OGR": OR_DOUBLEWORD(from_gr64(0), from_gr64(1)),
    "OGRK": OR_DOUBLEWORD(from_gr64(1), from_gr64(2)),
    "OIHF": _field(OR, WORD_BITS, HIGH_WORD_SHIFT),
    "OIHH": _field(OR, HALFWORD_BITS, HIGH_HALFWORD_SHIFT),
    "OIHL": _field(OR, HALFWORD_BITS, HIGH_WORD_SHIFT),
    "OILF": _field(OR, WORD_BITS, NO_SHIFT),
    "OILH": _field(OR, HALFWORD_BITS, LOW_HIGH_HALFWORD_SHIFT),
    "OILL": _field(OR, HALFWORD_BITS, NO_SHIFT),
}

EXCLUSIVE_ORS: Mapping[str, StatementLowering] = {
    "X": XOR_WORD(from_gr32(0), WORD_STORAGE),
    "XY": XOR_WORD(from_gr32(0), WORD_STORAGE),
    "XR": XOR_WORD(from_gr32(0), from_gr32(1)),
    "XRK": XOR_WORD(from_gr32(1), from_gr32(2)),
    "XG": XOR_DOUBLEWORD(from_gr64(0), DOUBLEWORD_STORAGE),
    "XGR": XOR_DOUBLEWORD(from_gr64(0), from_gr64(1)),
    "XGRK": XOR_DOUBLEWORD(from_gr64(1), from_gr64(2)),
    "XIHF": _field(XOR, WORD_BITS, HIGH_WORD_SHIFT),
    "XILF": _field(XOR, WORD_BITS, NO_SHIFT),
}

COMPLEMENTED: Mapping[str, StatementLowering] = {
    "NCRK": _distinct_word(AND_WITH_COMPLEMENT),
    "NCGRK": _distinct_doubleword(AND_WITH_COMPLEMENT),
    "OCRK": _distinct_word(OR_WITH_COMPLEMENT),
    "OCGRK": _distinct_doubleword(OR_WITH_COMPLEMENT),
    "NNRK": _distinct_word(NAND),
    "NNGRK": _distinct_doubleword(NAND),
    "NORK": _distinct_word(NOR),
    "NOGRK": _distinct_doubleword(NOR),
    "NXRK": _distinct_word(NOT_XOR),
    "NXGRK": _distinct_doubleword(NOT_XOR),
}

BOOLEAN_FIELD_LOWERINGS: Mapping[str, FieldLowering] = {
    "NI": _storage_byte(AND),
    "NIY": _storage_byte(AND),
    "NC": _storage_to_storage(BinopKind.BIT_AND),
    "OI": _storage_byte(OR),
    "OIY": _storage_byte(OR),
    "OC": _storage_to_storage(BinopKind.BIT_OR),
    "XI": _storage_byte(XOR),
    "XIY": _storage_byte(XOR),
    "XC": _storage_to_storage(BinopKind.BIT_XOR),
}

BOOLEAN_LOWERINGS: Mapping[str, StatementLowering] = {
    **ANDS,
    **ORS,
    **EXCLUSIVE_ORS,
    **COMPLEMENTED,
    **written_lowerings(BOOLEAN_FIELD_LOWERINGS),
}
