# pyright: standard
"""One PLO function code as the tests read Figure 7-380: its width, compares and stores as (area, offset) places, and how its operands are written."""

from dataclasses import dataclass

type Location = tuple[str, int]


@dataclass(frozen=True)
class PloFunction:
    width: int
    compares: tuple[tuple[Location, Location], ...]
    stores: tuple[tuple[Location, Location], ...]
    in_registers: bool
    fourth_is_operand: bool
    recorded: bool
