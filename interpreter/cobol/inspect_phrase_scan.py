"""One INSPECT phrase as the scan loop sees it: its region, length and loop variables."""

from __future__ import annotations

from dataclasses import dataclass

from interpreter.cobol.inspect_phrase_registers import InspectPhraseRegisters
from interpreter.register import Register
from interpreter.var_name import VarName


@dataclass(frozen=True)
class InspectPhraseScan:
    """The phrase, the (start, end) of the part of the source it inspects, the
    characters a match covers, the position a LEADING match must be at, and
    whether a FIRST phrase has matched."""

    phrase: InspectPhraseRegisters
    start: Register
    end: Register
    length: Register
    leading_at: VarName
    first_done: VarName
