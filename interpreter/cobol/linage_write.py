"""One WRITE on a LINAGE file: the counter it advances, and the END-OF-PAGE phrase it
then runs (IBM Enterprise COBOL LR, WRITE statement, END-OF-PAGE phrases)."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from functools import partial

from cobol_asg.cobol_statements import CobolStatementType, WriteStatement
from cobol_asg.write_advancing import WriteAdvancing
from interpreter.cobol.file_verb_ir import FileVerbIr, VerbOutcome
from interpreter.cobol.linage_page import LinagePage, linage_pages
from interpreter.cobol.lowering_scope import LoweringScope
from interpreter.cobol.no_linage_write import NoLinageWrite
from interpreter.var_name import VarName


@dataclass(frozen=True)
class LinageWrite:
    """One WRITE on a LINAGE file: whether it reached the end of the page."""

    page: LinagePage
    eop: VarName

    def advanced(self, outcome: VerbOutcome, advancing: WriteAdvancing) -> None:
        """A successful WRITE advances the counter."""
        v = self.page.v
        v.when(v.successful(outcome), partial(self.page.advance, advancing, self.eop))

    def respond(self, outcome: VerbOutcome, stmt: WriteStatement) -> None:
        """AT END-OF-PAGE after a WRITE that reached the end of the page; NOT AT
        END-OF-PAGE after any other successful one."""
        v = self.page.v
        v.either(
            v.e.load(self.eop),
            partial(self._lower, stmt.at_end_of_page),
            lambda: v.when(
                v.successful(outcome), partial(self._lower, stmt.not_at_end_of_page)
            ),
        )

    def _lower(self, statements: Sequence[CobolStatementType]) -> None:
        scope = self.page.scope
        _ = [scope.ctx.lower_statement(s, scope.materialised) for s in statements]


def linage_write(
    scope: LoweringScope, v: FileVerbIr, file_name: str
) -> LinageWrite | NoLinageWrite:
    """The WRITE's LINAGE handling, for a LINAGE file; none for any other."""
    pages = linage_pages(scope, v, file_name)
    if not pages:
        return NoLinageWrite()
    return LinageWrite(pages[0], v.e.var("linage_eop", v.e.bool_(False)))
