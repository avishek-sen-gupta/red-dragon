# pyright: standard
"""Where an operand lives for one lowering: how to read its value and how to replace it."""

from collections.abc import Callable
from dataclasses import dataclass

from interpreter.register import Register


@dataclass(frozen=True)
class Place:
    read: Callable[[], Register]
    write: Callable[[Register], None]
