"""One SIZE ERROR arm of an arithmetic statement as emitted."""

from __future__ import annotations

from collections.abc import Callable, Sequence
from dataclasses import dataclass

from cobol_asg.cobol_statements import CobolStatementType
from interpreter.ir import CodeLabel


@dataclass(frozen=True)
class SizeErrorArm:
    """The arm's label, its statements, what runs before them (REMAINDER for
    NOT ON SIZE ERROR), and the label every arm ends at."""

    label: CodeLabel
    statements: Sequence[CobolStatementType]
    follow_up: Callable[[], None]
    end: CodeLabel
