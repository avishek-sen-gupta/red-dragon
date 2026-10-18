"""The stores of one arithmetic statement under its SIZE ERROR phrases."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

from cobol_asg.cobol_statements import (
    ArithmeticCorrespondingStatement,
    ArithmeticStatement,
    ComputeStatement,
)
from interpreter.cobol.receiver_result import ReceiverResult
from interpreter.ir import CodeLabel

type SizeErrorPhrases = (
    ArithmeticStatement | ArithmeticCorrespondingStatement | ComputeStatement
)
type SizeErrorGuard = Callable[[CodeLabel], None]


@dataclass(frozen=True)
class SizeErrorStore[R]:
    """The statement with its SIZE ERROR phrases; the guard emitted before any
    store (a zero divisor); the receivers; the step that resolves a receiver and
    computes its result; and what follows the stores when no size error arises
    (REMAINDER)."""

    stmt: SizeErrorPhrases
    guard: SizeErrorGuard
    receivers: tuple[R, ...]
    step: Callable[[R], ReceiverResult]
    follow_up: Callable[[], None]
