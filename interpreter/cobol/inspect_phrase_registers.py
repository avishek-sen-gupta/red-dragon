"""One INSPECT TALLYING or REPLACING phrase: its mode and the registers holding its operands."""

from __future__ import annotations

from dataclasses import dataclass

from interpreter.cobol.inspect_mode import InspectMode
from interpreter.register import NO_REGISTER, Register


@dataclass(frozen=True)
class InspectPhraseRegisters:
    """A phrase's mode, pattern, BY value, AFTER / BEFORE operands and counter.

    An operand that was not written is NO_REGISTER; ``counter`` numbers the
    TALLYING identifier the phrase counts into.
    """

    mode: InspectMode
    pattern: Register = NO_REGISTER
    replacement: Register = NO_REGISTER
    after: Register = NO_REGISTER
    before: Register = NO_REGISTER
    counter: int = 0
