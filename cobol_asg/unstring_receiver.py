"""One UNSTRING INTO receiver with its DELIMITER IN and COUNT IN items; an item
that was not written has an empty name."""

from dataclasses import dataclass, field

from cobol_asg.ref_mod import RefModOperand


@dataclass(frozen=True)
class UnstringReceiver:
    target: RefModOperand
    delimiter_in: RefModOperand = field(default_factory=lambda: RefModOperand(name=""))
    count_in: RefModOperand = field(default_factory=lambda: RefModOperand(name=""))
