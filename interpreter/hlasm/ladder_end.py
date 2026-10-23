# pyright: standard
"""How an IEEE trap ladder ends: what a trapped overflow or underflow does after its scaled delivery, and what follows a completion without an interruption."""

from collections.abc import Callable
from dataclasses import dataclass

from interpreter.hlasm.hlasm_emitter import HlasmEmitter
from interpreter.register import Register

type ScaledTrap = Callable[[HlasmEmitter, Register, Register], None]
type Completed = Callable[[HlasmEmitter, Register], None]


@dataclass(frozen=True)
class LadderEnd:
    scaled_trap: ScaledTrap
    completed: Completed
