"""ACCEPT's fill is emitted as IR over one-record __cobol_accept calls."""

from __future__ import annotations

from interpreter.cobol.accept_fill import AcceptFill
from interpreter.cobol.emit_context import EmitContext
from interpreter.cobol.features import CobolFeature
from interpreter.cobol.ir_emitter import IrEmitter
from interpreter.cobol.statement_dispatch import dispatch_statement
from interpreter.instructions import CallFunction
from interpreter.register import Register
from tests.covers import covers


def _ignored(received: Register) -> None:
    return


@covers(CobolFeature.ACCEPT)
def test_accept_fill_calls_the_provider_for_one_record_at_a_time() -> None:
    ctx = EmitContext(dispatch_fn=dispatch_statement)
    e = IrEmitter(ctx=ctx, span=None)
    AcceptFill(e, "SYSIN", 10).emit(e.text("PGM"), _ignored)
    assert [
        (str(i.func_name), len(i.args))
        for i in ctx.instructions
        if isinstance(i, CallFunction)
    ] == [
        ("__cobol_accept", 1),
        ("__cobol_io_outcome", 2),
        ("__cobol_io_data", 2),
        ("__string_concat_pair", 2),
        ("__length", 1),
        ("__string_slice", 3),
    ]
