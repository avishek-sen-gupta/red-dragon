# pyright: standard
"""Reads the unsigned value of a one- or two-byte unit at a register offset; its constants are set when the reader is made, before any loop that uses it."""

from collections.abc import Callable

from interpreter.hlasm.hlasm_constants import BINARY_BYTES_TO_INT, ONE_BYTE
from interpreter.hlasm.hlasm_emitter import HlasmEmitter
from interpreter.instructions import LoadIndex
from interpreter.register import Register

type UnitReader = Callable[[Register, Register], Register]


def _byte_reader(emitter: HlasmEmitter) -> UnitReader:
    first = emitter.int_(0)

    def read(region: Register, at: Register) -> Register:
        value = emitter.fresh_reg()
        image = emitter.load_bytes(region, at, ONE_BYTE)
        emitter.emit_inst(LoadIndex(result_reg=value, arr_reg=image, index_reg=first))
        return value

    return read


def _wide_reader(emitter: HlasmEmitter, width: int) -> UnitReader:
    unsigned = emitter.unsigned_flag()
    return lambda region, at: emitter.call(
        BINARY_BYTES_TO_INT, (emitter.load_bytes(region, at, width), unsigned)
    )


def unit_reader(emitter: HlasmEmitter, width: int) -> UnitReader:
    if width == ONE_BYTE:
        return _byte_reader(emitter)
    return _wide_reader(emitter, width)
