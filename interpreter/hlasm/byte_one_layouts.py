# pyright: standard
"""Byte 1 of each instruction format, by format and operand shape (Principles of Operation, chapter 5); an unlisted shape has an opcode byte."""

from collections.abc import Mapping

from hlasm_asg.program.machine_statement import MachineStatement
from hlasm_asg.program.operand import Operand
from hlasm_asg.program.storage_length_operand import StorageLengthOperand
from hlasm_asg.program.storage_operand import StorageOperand
from interpreter.hlasm.byte_one_field import ByteOneField
from interpreter.hlasm.byte_one_layout import ByteOneLayout
from interpreter.hlasm.length_code_part import LengthCode
from interpreter.hlasm.operand_slot import OperandSlot
from interpreter.hlasm.operand_value_part import OperandValue
from interpreter.hlasm.storage_index_part import StorageIndex

V = OperandSlot.VALUE
S = OperandSlot.STORAGE

NIBBLE = 4
BYTE = 8
HIGH = 4
LOW = 0
LOW_NIBBLE_BITS = 0x0F
BYTE_BITS = 0xFF
NO_BITS = 0

type Shape = tuple[str, tuple[OperandSlot, ...]]

_VALUE = OperandValue()
_INDEX = StorageIndex()
_LENGTH = LengthCode()


def _high(operand: int) -> ByteOneField:
    return ByteOneField(HIGH, NIBBLE, operand, _VALUE)


def _low(operand: int) -> ByteOneField:
    return ByteOneField(LOW, NIBBLE, operand, _VALUE)


def _byte(operand: int) -> ByteOneField:
    return ByteOneField(LOW, BYTE, operand, _VALUE)


def _layout(*fields: ByteOneField) -> ByteOneLayout:
    return ByteOneLayout(fields, NO_BITS)


def _low_ignored(field: ByteOneField) -> ByteOneLayout:
    return ByteOneLayout((field,), LOW_NIBBLE_BITS)


OPCODE_BYTE = _layout()
R1_R2 = _layout(_high(0), _low(1))
R1_X2 = _layout(_high(0), ByteOneField(LOW, NIBBLE, 1, _INDEX))
R1_OPCODE = _layout(_high(0))
R1_R3 = _layout(_high(0), _low(2))
R1_IGNORED = _low_ignored(_high(0))
LENGTH_BYTE = _layout(ByteOneField(LOW, BYTE, 0, _LENGTH))
LENGTH_NIBBLES = _layout(
    ByteOneField(HIGH, NIBBLE, 0, _LENGTH), ByteOneField(LOW, NIBBLE, 1, _LENGTH)
)
SECOND_LENGTH_BYTE = _layout(ByteOneField(LOW, BYTE, 1, _LENGTH))
LENGTH_HIGH_NIBBLE = _low_ignored(ByteOneField(HIGH, NIBBLE, 0, _LENGTH))
LENGTH_AND_IMMEDIATE = _layout(ByteOneField(HIGH, NIBBLE, 0, _LENGTH), _low(2))
IMMEDIATE_BYTE = _layout(_byte(1))
NUMBER_BYTE = _layout(_byte(0))

BYTE_ONE_LAYOUTS: Mapping[Shape, ByteOneLayout] = {
    ("I", (V,)): NUMBER_BYTE,
    ("SI", (S, V)): IMMEDIATE_BYTE,
    ("SI", (S,)): ByteOneLayout((), BYTE_BITS),
    ("SIY", (S, V)): IMMEDIATE_BYTE,
    ("SS-a", (S, S)): LENGTH_BYTE,
    ("SS-b", (S, S)): LENGTH_NIBBLES,
    ("SS-c", (S, S, V)): LENGTH_AND_IMMEDIATE,
    ("SS-e", (V, V, S, S)): R1_R2,
    ("SS-e", (V, S, V, S)): R1_R3,
    ("SS-f", (S, S)): SECOND_LENGTH_BYTE,
    ("RSL-a", (S,)): LENGTH_HIGH_NIBBLE,
    ("RSL-b", (V, S, V)): SECOND_LENGTH_BYTE,
    ("RR", (V, V)): R1_R2,
    ("RR", (V,)): R1_IGNORED,
    ("RX-a", (V, S)): R1_X2,
    ("RX-b", (V, S)): R1_X2,
    ("RXE", (V, S)): R1_X2,
    ("RXE", (V, S, V)): R1_X2,
    ("RXY-a", (V, S)): R1_X2,
    ("RXY-b", (V, S)): R1_X2,
    ("RXY-c", (V, S)): R1_X2,
    ("RXF", (V, V, S)): _layout(_high(1), ByteOneField(LOW, NIBBLE, 2, _INDEX)),
    ("RS-a", (V, V, S)): R1_R2,
    ("RS-a", (V, S)): R1_IGNORED,
    ("RSY-a", (V, V, S)): R1_R2,
    ("RS-b", (V, V, S)): R1_R2,
    ("RSY-b", (V, V, S)): R1_R2,
    ("RSY-b", (V, S, V)): _layout(_high(0), _low(2)),
    ("RSI", (V, V, V)): R1_R2,
    ("RI-a", (V, V)): R1_OPCODE,
    ("RI-b", (V, V)): R1_OPCODE,
    ("RI-c", (V, V)): R1_OPCODE,
    ("RIL-a", (V, V)): R1_OPCODE,
    ("RIL-b", (V, V)): R1_OPCODE,
    ("RIL-c", (V, V)): R1_OPCODE,
    ("RIE-a", (V, V, V)): R1_IGNORED,
    ("RIE-b", (V, V, V, V)): R1_R2,
    ("RIE-c", (V, V, V, V)): _layout(_high(0), _low(2)),
    ("RIE-d", (V, V, V)): R1_R2,
    ("RIE-e", (V, V, V)): R1_R2,
    ("RIE-f", (V, V, V, V)): R1_R2,
    ("RIE-f", (V, V, V, V, V)): R1_R2,
    ("RIE-g", (V, V, V)): _layout(_high(0), _low(2)),
    ("RIS", (V, V, V, S)): _layout(_high(0), _low(2)),
    ("RRS", (V, V, V, S)): R1_R2,
    ("SMI", (V, V, S)): R1_IGNORED,
    ("MII", (V, V, V)): R1_OPCODE,
    ("SSF", (V, S, S)): R1_OPCODE,
    ("SSF", (S, S, V)): _layout(_high(2)),
}


def _slot(operand: Operand) -> OperandSlot:
    match operand:
        case StorageOperand() | StorageLengthOperand():
            return S
        case _:
            return V


def byte_one_layout(statement: MachineStatement) -> ByteOneLayout:
    shape = (statement.format, tuple(_slot(o) for o in statement.operands))
    return BYTE_ONE_LAYOUTS.get(shape, OPCODE_BYTE)
