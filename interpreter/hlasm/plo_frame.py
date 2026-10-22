# pyright: standard
"""What one PLO function's operands are resolved against: the R1 and R3 numbers (set by EX at run time), the D2(B2) and D4(B4) addresses, and the parameter-list addresses already checked."""

from collections.abc import Mapping
from dataclasses import dataclass

from interpreter.hlasm.hlasm_emitter import HlasmEmitter
from interpreter.register import Register


@dataclass(frozen=True)
class PloFrame:
    emitter: HlasmEmitter
    registers: Mapping[int, Register]
    second: Register
    fourth: Register
    listed: Mapping[int, Register]
