# pyright: standard
"""The unsigned value of a one- or two-byte unit, from its image or read at a register offset; its constants are set when the converter is made, before any loop that uses it."""

from collections.abc import Callable

from interpreter.hlasm.hlasm_constants import BINARY_BYTES_TO_INT, ONE_BYTE
from interpreter.hlasm.hlasm_emitter import HlasmEmitter
from interpreter.instructions import LoadIndex
from interpreter.register import Register

type UnitValue = Callable[[Register], Register]
type UnitReader = Callable[[Register, Register], Register]


def _byte_value(emitter: HlasmEmitter) -> UnitValue:
    first = emitter.int_(0)

    def value(image: Register) -> Register:
        result = emitter.fresh_reg()
        emitter.emit_inst(LoadIndex(result_reg=result, arr_reg=image, index_reg=first))
        return result

    return value


def _wide_value(emitter: HlasmEmitter) -> UnitValue:
    unsigned = emitter.unsigned_flag()
    return lambda image: emitter.call(BINARY_BYTES_TO_INT, (image, unsigned))


def unit_value(emitter: HlasmEmitter, width: int) -> UnitValue:
    if width == ONE_BYTE:
        return _byte_value(emitter)
    return _wide_value(emitter)


def unit_reader(emitter: HlasmEmitter, width: int) -> UnitReader:
    value = unit_value(emitter, width)
    return lambda region, at: value(emitter.load_bytes(region, at, width))
