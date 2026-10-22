# pyright: standard
"""One PLO function code as data: its operand width, compares, stores in order, boundary checks, even registers and what an unequal compare does."""

from collections.abc import Callable
from dataclasses import dataclass

from interpreter.hlasm.place import Place
from interpreter.hlasm.plo_frame import PloFrame
from interpreter.register import Register

type Spot = Callable[[PloFrame], Place]
type Address = Callable[[PloFrame], Register]
type OnUnequal = Callable[[PloFrame, int], None]


@dataclass(frozen=True)
class LockedOperation:
    width: int
    compares: tuple[tuple[Spot, Spot], ...]
    stores: tuple[tuple[Spot, Spot], ...]
    checks: tuple[tuple[Address, int], ...]
    even_registers: tuple[int, ...]
    unequal: OnUnequal
