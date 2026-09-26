# pyright: standard
"""The one place a COBOL program's return to its caller is emitted.

``GOBACK``, ``EXIT PROGRAM`` and running off the end of the PROCEDURE DIVISION are
three spellings of the same event, so they share one emitter. ``STOP RUN`` is not
among them: it ends the run unit rather than returning, and lowers to ``Halt_``.

The return carries this program's RETURN-CODE. That is how z/OS does it — a
returning program leaves its RETURN-CODE in register 15, and the caller stores
R15 into its own RETURN-CODE — and modelling it as the function return value is
what makes the propagation work for ``CALL identifier`` too, where the callee's
identity is not known until run time (red-dragon-ltq6).

The value travels as the register's raw bytes, never as a decoded integer: both
ends of the copy are the same 2-byte big-endian field, so decoding on the way out
only to re-encode on the way in would add arithmetic that cannot change the
answer.

Kept in its own module so ``lower_procedure`` can reach it without importing
``lower_arithmetic`` (which imports the procedure lowering back).
"""

from __future__ import annotations

from cobol_asg.source_span import SourceSpan
from cobol_memory.region_id import RegionId
from interpreter.cobol.cobol_constants import BuiltinName
from interpreter.cobol.emit_context import EmitContext
from interpreter.cobol.field_resolution import whole_field_extent
from interpreter.cobol.sectioned_layout import MaterialisedSectionedLayout
from interpreter.cobol.special_registers import RETURN_CODE_NAME
from interpreter.func_name import FuncName
from interpreter.instructions import CallFunction, Return_
from interpreter.register import Register


def lower_program_exit(
    ctx: EmitContext,
    materialised: MaterialisedSectionedLayout,
    *,
    span: SourceSpan | None,
    implicit: bool = False,
) -> None:
    """Emit the return that hands control back to this program's caller.

    ``implicit`` marks the exit the compiler supplies at the end of a PROCEDURE
    DIVISION, as distinct from one a GOBACK or EXIT PROGRAM asked for. Pascal,
    Java and the common frontend already mark theirs; COBOL was the odd one out.
    The flag has one consumer -- type_inference skips implicit returns when
    inferring a return type -- and it also lets a reader of the IR tell an exit
    a statement wrote from one that is merely where the program ran out.
    """
    value_reg = emit_return_code_load(ctx, materialised, span=span)
    emit_publish_run_unit_return_code(ctx, value_reg, span=span)
    ctx.emit_inst(Return_(value_reg=value_reg, implicit=implicit), span=span)


def emit_publish_run_unit_return_code(
    ctx: EmitContext,
    value_reg: Register,
    *,
    span: SourceSpan | None,
) -> None:
    """Record this program's RETURN-CODE as the run unit's, on the way out.

    Every program exit publishes, and so does ``STOP RUN``, so the last program
    to end is the one whose value survives — which is the value the operating
    system receives. Without it the read-back has N per-program registers and no
    way to tell which is the run unit's (red-dragon-cvwu).
    """
    ctx.emit_inst(
        CallFunction(
            result_reg=ctx.fresh_reg(),
            func_name=FuncName(BuiltinName.PUBLISH_RETURN_CODE),
            args=(value_reg,),
        ),
        span=span,
    )


def emit_return_code_load(
    ctx: EmitContext,
    materialised: MaterialisedSectionedLayout,
    *,
    span: SourceSpan | None,
) -> Register:
    """Read RETURN-CODE's raw bytes out of this program's special-register region.

    Shared with the CALL site, which pre-seeds the call's result register with the
    caller's own value so that a callee returning nothing (a CICS task-ending
    RETURN, which is VOID and therefore never written back) leaves the caller's
    RETURN-CODE alone instead of leaving the register unwritten.
    """
    sr_layout, sr_reg = materialised.special_registers
    fl = sr_layout.lookup_or_raise(RETURN_CODE_NAME)
    value_reg = ctx.fresh_reg()
    ctx._emit_load_region(
        result_reg=value_reg,
        region_reg=sr_reg,
        offset_reg=ctx.const_to_reg(fl.offset, span=span),
        length=fl.byte_length,
        extent=whole_field_extent(fl, RegionId.SPECIAL_REGISTERS),
        span=span,
    )
    return value_reg


def emit_return_code_store(
    ctx: EmitContext,
    materialised: MaterialisedSectionedLayout,
    value_reg: Register,
    *,
    span: SourceSpan | None,
) -> None:
    """Write raw bytes into this program's RETURN-CODE — the caller side of a copy-up."""
    sr_layout, sr_reg = materialised.special_registers
    fl = sr_layout.lookup_or_raise(RETURN_CODE_NAME)
    ctx._emit_write_region(
        region_reg=sr_reg,
        offset_reg=ctx.const_to_reg(fl.offset, span=span),
        value_reg=value_reg,
        length=fl.byte_length,
        extent=whole_field_extent(fl, RegionId.SPECIAL_REGISTERS),
        span=span,
    )
