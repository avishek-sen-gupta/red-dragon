"""The routine CANCEL calls in the program it cancels: it closes each of the program's
open files that has an internal file connector, as IBM's CANCEL statement requires.
An EXTERNAL file's connector is the run unit's and stays as it is."""

from __future__ import annotations

from interpreter import constants
from interpreter.cobol.emit_context import EmitContext
from interpreter.cobol.lower_io import emit_implicit_close
from interpreter.cobol.program_object import ARGUMENTS_PARAM, cancel_label
from interpreter.instructions import Label_, Return_, Symbolic


def lower_cancel_routine(ctx: EmitContext, program_id: str) -> None:
    ctx.emit_inst(Label_(label=cancel_label(program_id)), span=None)
    ctx.emit_inst(
        Symbolic(
            result_reg=ctx.fresh_reg(),
            hint=f"{constants.PARAM_PREFIX}{ARGUMENTS_PARAM}",
        ),
        span=None,
    )
    external = ctx._asg.external_file_names()
    _ = [
        emit_implicit_close(ctx, entry)
        for entry in ctx._asg.file_control
        if entry.file_name.upper() not in external
    ]
    ctx.emit_inst(Return_(value_reg=None), span=None)
