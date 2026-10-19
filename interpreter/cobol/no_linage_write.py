"""A WRITE on a file without a LINAGE clause: no page to advance, no END-OF-PAGE."""

from __future__ import annotations

from dataclasses import dataclass

from cobol_asg.cobol_statements import WriteStatement
from cobol_asg.write_advancing import WriteAdvancing
from interpreter.cobol.file_verb_ir import VerbOutcome


@dataclass(frozen=True)
class NoLinageWrite:
    def advanced(self, outcome: VerbOutcome, advancing: WriteAdvancing) -> None:
        return

    def respond(self, outcome: VerbOutcome, stmt: WriteStatement) -> None:
        return
