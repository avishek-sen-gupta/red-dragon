"""A receiver of an arithmetic statement with the result to be stored in it."""

from __future__ import annotations

from dataclasses import dataclass

from interpreter.cobol.arithmetic_receiver import ArithmeticReceiver
from interpreter.register import Register


@dataclass(frozen=True)
class ReceiverResult:
    receiver: ArithmeticReceiver
    value: Register
