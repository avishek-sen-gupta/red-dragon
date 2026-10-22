# pyright: standard
"""A signed-packed-decimal field as read: its magnitude, its negative bit (sign B or D), and a bit each for a bad digit (A-F) and a bad sign (0-9), each an int register."""

from dataclasses import dataclass

from interpreter.hlasm.hlasm_emitter import HlasmEmitter
from interpreter.operator_kind import BinopKind
from interpreter.register import Register


@dataclass(frozen=True)
class PackedValue:
    magnitude: Register
    negative: Register
    bad_digits: Register
    bad_sign: Register

    def invalid(self, emitter: HlasmEmitter) -> Register:
        return emitter.binop(BinopKind.BIT_OR, self.bad_digits, self.bad_sign)
