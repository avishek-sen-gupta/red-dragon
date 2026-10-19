"""The IR one LINAGE file's verbs add around its file primitives: the logical page OPEN
begins, the LINAGE-COUNTER each WRITE advances, and the end-of-page condition WRITE's
END-OF-PAGE phrases respond to (IBM Enterprise COBOL LR, LINAGE clause, LINAGE-COUNTER,
WRITE statement)."""

from __future__ import annotations

from dataclasses import dataclass
from functools import partial

from cobol_asg.advancing_lines import AdvancingLines
from cobol_asg.advancing_page import AdvancingPage
from cobol_asg.cobol_expression import FieldRefNode
from cobol_asg.linage_clause import LinageClause
from cobol_asg.no_footing import NoFooting
from cobol_asg.write_advancing import WriteAdvancing
from interpreter.cobol.condition_lowering import lower_expr_node
from interpreter.cobol.file_verb_ir import FileVerbIr, VerbOutcome
from interpreter.cobol.linage_counters import LINAGE_COUNTER_NAME, linage_files
from interpreter.cobol.lowering_scope import LoweringScope
from interpreter.register import Register
from interpreter.var_name import VarName

_FIRST_LINE = 1


@dataclass(frozen=True)
class LinagePage:
    """One LINAGE file's logical page, emitted over its verb's file state."""

    scope: LoweringScope
    v: FileVerbIr
    file_name: str
    clause: LinageClause

    def begin(self) -> None:
        """A new logical page: its page body and footing from the clause's values
        now, and the counter on its first line."""
        e = self.v.e
        e.store(self.v.state.page_body, lower_expr_node(self.scope, self.clause.lines))
        if not isinstance(self.clause.footing, NoFooting):
            e.store(
                self.v.state.page_footing,
                lower_expr_node(self.scope, self.clause.footing),
            )
        self._set_counter(e.int_(_FIRST_LINE))

    def advance(self, advancing: WriteAdvancing, eop: VarName) -> None:
        """The counter after a WRITE, and whether it reached the end of the page."""
        if isinstance(advancing, AdvancingPage):
            self.begin()
            self.v.e.store(eop, self._in_footing(self.v.e.int_(_FIRST_LINE)))
            return
        if not isinstance(advancing, AdvancingLines):
            raise NotImplementedError(
                f"WRITE ADVANCING mnemonic-name on LINAGE file {self.file_name}"
            )
        e = self.v.e
        target = e.binop(
            "+", self._counter(), lower_expr_node(self.scope, advancing.lines)
        )
        self.v.either(
            e.binop(">", target, e.load(self.v.state.page_body)),
            partial(self._overflowed, eop),
            partial(self._within, target, eop),
        )

    def _overflowed(self, eop: VarName) -> None:
        self.begin()
        self.v.e.store(eop, self.v.e.bool_(True))

    def _within(self, target: Register, eop: VarName) -> None:
        self._set_counter(target)
        self.v.e.store(eop, self._in_footing(target))

    def _in_footing(self, line: Register) -> Register:
        if isinstance(self.clause.footing, NoFooting):
            return self.v.e.bool_(False)
        return self.v.e.binop(">=", line, self.v.e.load(self.v.state.page_footing))

    def _reference(self) -> FieldRefNode:
        return FieldRefNode(LINAGE_COUNTER_NAME, qualifiers=(self.file_name,))

    def _counter(self) -> Register:
        return lower_expr_node(self.scope, self._reference())

    def _set_counter(self, value: Register) -> None:
        ctx, span = self.scope.ctx, self.scope.span
        reference = self._reference()
        ref, region = ctx.resolve_field_ref(
            reference.name,
            self.scope.materialised,
            qualifiers=reference.qualifiers,
            span=span,
        )
        ctx.emit_encode_and_write(
            region,
            ref.fl,
            ctx.emit_to_string(value, span=span),
            ref.offset_reg,
            extent=ref.extent,
            span=span,
        )


def linage_pages(
    scope: LoweringScope, v: FileVerbIr, file_name: str
) -> tuple[LinagePage, ...]:
    """The file's logical page: one for a LINAGE file, none for any other."""
    return tuple(
        LinagePage(scope, v, name, clause)
        for name, clause in linage_files(scope.ctx._asg)
        if name.upper() == file_name.upper()
    )


def emit_linage_open(
    scope: LoweringScope, v: FileVerbIr, outcome: VerbOutcome, file_name: str
) -> None:
    """A successful OPEN begins the file's first logical page."""
    _ = [
        v.when(v.successful(outcome), page.begin)
        for page in linage_pages(scope, v, file_name)
    ]
