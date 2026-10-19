"""ALTER targets get ordinals per paragraph, and each alterable GO TO dispatches on its paragraph's ordinal in IR."""

from __future__ import annotations

from interpreter.cobol.alter_table import AlterTable
from interpreter.cobol.alterable_goto import AlterableGoto
from interpreter.cobol.emit_context import EmitContext
from interpreter.cobol.features import CobolFeature
from interpreter.cobol.lower_alter import alter_var, emit_alter_dispatches
from interpreter.cobol.statement_dispatch import dispatch_statement
from interpreter.instructions import Branch, Label_, LoadVar
from interpreter.ir import CodeLabel
from tests.covers import covers

_P = CodeLabel("para_P")
_Q = CodeLabel("para_Q")
_A = CodeLabel("para_A")
_B = CodeLabel("para_B")


@covers(CobolFeature.ALTER)
def test_each_paragraphs_alter_targets_are_numbered_from_one_in_first_seen_order():
    table = (
        AlterTable()
        .with_target(_P, _A)
        .with_target(_P, _B)
        .with_target(_P, _A)
        .with_target(_Q, _B)
    )

    assert [table.ordinal(_P, _A), table.ordinal(_P, _B), table.ordinal(_Q, _B)] == [
        1,
        2,
        1,
    ]
    assert table.targets_of(_P) == (_A, _B)
    assert table.targets_of(_A) == ()


@covers(CobolFeature.ALTER, CobolFeature.GO_TO)
def test_an_alterable_go_to_dispatches_on_its_ordinal_then_takes_its_written_target():
    ctx = EmitContext(dispatch_fn=dispatch_statement)
    ctx.record_alterable_goto(AlterableGoto(paragraph=_P, unaltered=_Q))
    ctx.record_alter(_P, _A)
    ctx.record_alter(_P, _B)

    emit_alter_dispatches(ctx)

    dispatch = ctx.instructions[
        ctx.instructions.index(Label_(label=CodeLabel("para_P_altered_goto"))) :
    ]
    assert (
        [i.name for i in dispatch[1:2] if isinstance(i, LoadVar)],
        [i.label for i in dispatch if isinstance(i, Branch)][:3],
    ) == ([alter_var("MAIN", _P)], [_A, _B, _Q])
