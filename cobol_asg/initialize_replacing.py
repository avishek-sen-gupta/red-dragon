"""One INITIALIZE REPLACING phrase: a data category and the value it is given."""

from dataclasses import dataclass

from cobol_asg.initialize_category import InitializeCategory
from cobol_asg.ref_mod import RefModOperand


@dataclass(frozen=True)
class InitializeReplacing:
    """``REPLACING <category> DATA BY <identifier or literal>``."""

    category: InitializeCategory
    by: RefModOperand
