"""CALL, ALTER, ENTRY, CANCEL statement lowering."""

from __future__ import annotations

import logging
from collections.abc import Sequence

from cobol_asg.cobol_statements import (
    AlterStatement,
    CallStatement,
    CallUsingParam,
    CancelStatement,
    EntryStatement,
)
from cobol_asg.cobol_types import CobolTypeDescriptor
from cobol_asg.pic_parser import parse_pic
from cobol_asg.ref_mod import RefModOperand
from cobol_asg.source_span import SourceSpan
from cobol_memory.field_extent import FieldExtent, Precision
from cobol_memory.region_id import RegionId
from interpreter.cobol.cobol_constants import BuiltinName
from interpreter.cobol.data_layout import FieldLayout
from interpreter.cobol.emit_context import EmitContext, strip_cobol_literal
from interpreter.cobol.field_resolution import ResolvedFieldRef
from interpreter.cobol.figurative_constants import COBOL_FIGURATIVE_CONSTANTS
from interpreter.cobol.lower_arithmetic import eval_ref_mod_expr
from interpreter.cobol.lower_program_exit import (
    emit_return_code_load,
    emit_return_code_store,
)
from interpreter.cobol.sectioned_layout import MaterialisedSectionedLayout
from interpreter.field_name import FieldName
from interpreter.func_name import FuncName
from interpreter.instructions import (
    AllocRegion,
    Binop,
    CallFunction,
    CallWithMemory,
    Label_,
    NewArray,
    NewObject,
    StoreField,
    StoreIndex,
    StoreVar,
)
from interpreter.ir import CodeLabel
from interpreter.operator_kind import resolve_binop
from interpreter.register import NO_REGISTER, Register
from interpreter.var_name import VarName

logger = logging.getLogger(__name__)

LITERAL_ARGUMENT = "%LITERAL"
_ZEROS = frozenset({"ZERO", "ZEROS", "ZEROES"})
_FULLWORD = parse_pic("S9(9)", usage="COMP-5")
_COMP2 = parse_pic("", usage="COMP-2")


def _emit_callee_name(
    ctx: EmitContext,
    operand: RefModOperand,
    materialised: MaterialisedSectionedLayout,
    *,
    span: SourceSpan | None,
) -> Register:
    """Emit IR that produces the callee's name from a data item, at run time.

    ``CALL identifier`` names the program by the *contents* of a data item, so
    the name only exists once the field has been read. The operand is the same
    ``RefModOperand`` MOVE and STRING consume, so its subscripts, ``OF``/``IN``
    qualifiers and reference-modification bounds are honoured by the machinery
    that already handles them — ``CALL WS-PROG(1:8)`` is the common idiom, since
    a program name is 8 characters and the holding field is usually wider.
    """
    if not ctx.has_field(operand.name, materialised):
        raise ValueError(
            f"CALL {operand.name}: the callee is a data name that resolves to no "
            "field, so the program to call cannot be determined"
        )

    field_ref, region_reg = ctx.resolve_field_ref(
        operand.name,
        materialised,
        qualifiers=operand.qualifiers,
        subscripts=operand.subscripts,
        span=span,
    )
    decoded_reg = ctx.emit_decode_field(
        region_reg,
        field_ref.fl,
        field_ref.offset_reg,
        extent=field_ref.extent,
        span=span,
    )
    name_reg = ctx.emit_to_string(decoded_reg, span=span)

    if operand.ref_mod_start is None:
        return name_reg

    raw_start_reg = eval_ref_mod_expr(
        ctx, operand.ref_mod_start, materialised, span=span
    )
    one_reg = ctx.const_to_reg(1, span=span)
    start_0indexed_reg = ctx.fresh_reg()
    ctx.emit_inst(
        Binop(
            result_reg=start_0indexed_reg,
            operator=resolve_binop("-"),
            left=raw_start_reg,
            right=one_reg,
        ),
        span=span,
    )
    if operand.ref_mod_length is not None:
        length_reg = eval_ref_mod_expr(
            ctx, operand.ref_mod_length, materialised, span=span
        )
    else:
        length_reg = ctx.const_to_reg(9999, span=span)
    sliced_reg = ctx.fresh_reg()
    ctx.emit_inst(
        CallFunction(
            result_reg=sliced_reg,
            func_name=FuncName(BuiltinName.STRING_SLICE),
            args=(name_reg, start_0indexed_reg, length_reg),
        ),
        span=span,
    )
    return sliced_reg


def lower_call(
    ctx: EmitContext,
    stmt: CallStatement,
    materialised: MaterialisedSectionedLayout,
) -> None:
    """CALL (identifier | literal) USING params — one address per argument.

    The callee receives an argument array: per USING argument, by position, a
    region and an offset into it. BY REFERENCE passes the argument's own bytes,
    so the callee's writes land in the caller as they happen and nothing is
    copied back; BY CONTENT, BY VALUE and a literal pass a fresh copy; OMITTED
    passes a marker. The callee binds each LINKAGE 01 to its argument.
    """
    span = stmt.span
    args_reg = _argument_array(ctx, stmt.using, materialised, span=span)

    target = stmt.target
    target_reg = (
        _emit_callee_name(ctx, target.identifier, materialised, span=span)
        if target.identifier is not None
        else NO_REGISTER
    )

    # The callee returns its RETURN-CODE in result_reg, and the copy-up below
    # writes it into the caller's. Seeding that same register with the caller's
    # OWN value first is what makes a callee that returns nothing harmless: a
    # VOID return is deliberately not written back into the caller's register
    # (see run.py), so an unseeded result_reg would still be unwritten and would
    # resolve to the literal string "%n" — which the copy-up would then store
    # into RETURN-CODE as garbage.
    result_reg = emit_return_code_load(ctx, materialised, span=span)
    ctx.emit_inst(
        CallWithMemory(
            result_reg=result_reg,
            func_name=FuncName(target.literal),
            params_reg=args_reg,
            target_reg=target_reg,
        ),
        span=span,
    )

    # Copy-up: a returning COBOL program leaves its RETURN-CODE in register 15
    # and its caller stores R15 into its own. result_reg is that R15.
    emit_return_code_store(ctx, materialised, result_reg, span=span)

    # Restore the caller's __ws_region binding. CallWithMemory dispatches into the
    # callee's func_init_params, whose body re-binds the shared __ws_region var to
    # the CALLEE's WS region. When the callee frame is popped on EXIT PROGRAM the
    # caller's __ws_region binding does not reliably survive, so consumers that
    # read __ws_region directly (e.g. CICS SEND/RECEIVE MAP via
    # _get_ws_region_addr) would otherwise see the callee's region after the CALL.
    # caller_ws_reg holds the caller's WS region (loaded at function entry), so
    # re-binding __ws_region to it is a no-op for field access but repairs the var
    # for direct readers. (Field access reloads via the singleton, so it was never
    # affected; this only matters for the shared __ws_region var.)
    _ws_layout, caller_ws_reg = materialised.working_storage
    ctx.emit_inst(
        StoreVar(name=VarName("__ws_region"), value_reg=caller_ws_reg), span=span
    )

    if stmt.giving and ctx.has_field(stmt.giving, materialised):
        giving_ref, giving_rr = ctx.resolve_field_ref(
            stmt.giving, materialised, span=span
        )
        str_reg = ctx.emit_to_string(result_reg, span=span)
        ctx.emit_encode_and_write(
            giving_rr,
            giving_ref.fl,
            str_reg,
            giving_ref.offset_reg,
            extent=giving_ref.extent,
            span=span,
        )

    logger.info(
        "CALL %s with %d params (CallWithMemory)",
        target.describe(),
        len(stmt.using),
    )


def _argument_array(
    ctx: EmitContext,
    using: Sequence[CallUsingParam],
    materialised: MaterialisedSectionedLayout,
    *,
    span: SourceSpan | None,
) -> Register:
    """One element per USING argument, by position: a region, an offset, and
    whether it was OMITTED."""
    args = ctx.fresh_reg()
    ctx.emit_inst(
        NewArray(result_reg=args, size_reg=ctx.const_to_reg(len(using), span=span)),
        span=span,
    )
    _store_field(ctx, args, "count", ctx.const_to_reg(len(using), span=span), span=span)
    for position, param in enumerate(using):
        ctx.emit_inst(
            StoreIndex(
                arr_reg=args,
                index_reg=ctx.const_to_reg(position, span=span),
                value_reg=_argument(ctx, param, materialised, span=span),
            ),
            span=span,
        )
    return args


def _argument(
    ctx: EmitContext,
    param: CallUsingParam,
    materialised: MaterialisedSectionedLayout,
    *,
    span: SourceSpan | None,
) -> Register:
    element = ctx.fresh_reg()
    ctx.emit_inst(NewObject(result_reg=element), span=span)
    omitted = param.omitted
    _store_field(
        ctx, element, "omitted", ctx.const_to_reg(omitted, span=span), span=span
    )
    if omitted:
        return element
    region, offset = _address(ctx, param, materialised, span=span)
    _store_field(ctx, element, "region", region, span=span)
    _store_field(ctx, element, "offset", offset, span=span)
    return element


def _address(
    ctx: EmitContext,
    param: CallUsingParam,
    materialised: MaterialisedSectionedLayout,
    *,
    span: SourceSpan | None,
) -> tuple[Register, Register]:
    """BY REFERENCE: the argument's own bytes. Anything else: a fresh copy."""
    if param.is_literal:
        return _literal_copy(ctx, param, span=span)
    ref, region_reg = ctx.resolve_field_ref(param.name, materialised, span=span)
    if param.param_type == "REFERENCE":
        return region_reg, ref.offset_reg
    return _content_copy(ctx, ref, region_reg, param.name, span=span)


def _literal_copy(
    ctx: EmitContext, param: CallUsingParam, *, span: SourceSpan | None
) -> tuple[Register, Register]:
    """A literal argument in the representation IBM defines for it, in a fresh copy."""
    layout = _layout(_literal_type(param))
    copy = ctx.fresh_reg()
    ctx.emit_inst(
        AllocRegion(
            result_reg=copy, size_reg=ctx.const_to_reg(layout.byte_length, span=span)
        ),
        span=span,
    )
    zero = ctx.const_to_reg(0, span=span)
    ctx.emit_encode_and_write(
        copy,
        layout,
        ctx.const_to_reg(_literal_value(param), span=span),
        zero,
        extent=_copy_extent(layout.byte_length, LITERAL_ARGUMENT),
        span=span,
    )
    return copy, zero


def _literal_type(param: CallUsingParam) -> CobolTypeDescriptor:
    """BY VALUE: a numeric literal or ZERO as a fullword binary, a floating-point
    literal as COMP-2. Anything else: its characters, a figurative constant one."""
    word = param.name.upper()
    if param.param_type == "VALUE" and _is_numeric(word):
        return _COMP2 if word not in _ZEROS and "E" in word else _FULLWORD
    return parse_pic(f"X({max(len(_literal_value(param)), 1)})")


def _is_numeric(word: str) -> bool:
    return word in _ZEROS or (
        word not in COBOL_FIGURATIVE_CONSTANTS and strip_cobol_literal(word) == word
    )


def _literal_value(param: CallUsingParam) -> str:
    return COBOL_FIGURATIVE_CONSTANTS.get(
        param.name.upper(), strip_cobol_literal(param.name)
    )


def _layout(type_descriptor: CobolTypeDescriptor) -> FieldLayout:
    return FieldLayout(
        name=LITERAL_ARGUMENT,
        type_descriptor=type_descriptor,
        offset=0,
        byte_length=type_descriptor.byte_length,
    )


def _content_copy(
    ctx: EmitContext,
    ref: ResolvedFieldRef,
    region_reg: Register,
    name: str,
    *,
    span: SourceSpan | None,
) -> tuple[Register, Register]:
    length = ref.fl.byte_length
    copy = ctx.fresh_reg()
    ctx.emit_inst(
        AllocRegion(result_reg=copy, size_reg=ctx.const_to_reg(length, span=span)),
        span=span,
    )
    value = ctx.fresh_reg()
    ctx._emit_load_region(
        result_reg=value,
        region_reg=region_reg,
        offset_reg=ref.offset_reg,
        length=length,
        extent=ref.extent,
        span=span,
    )
    zero = ctx.const_to_reg(0, span=span)
    ctx._emit_write_region(
        region_reg=copy,
        offset_reg=zero,
        value_reg=value,
        length=length,
        extent=_copy_extent(length, name),
        span=span,
    )
    return copy, zero


def _copy_extent(length: int, name: str) -> FieldExtent:
    return FieldExtent(RegionId.CALL_ARGUMENT, 0, length, Precision.EXACT, name)


def _store_field(
    ctx: EmitContext,
    obj: Register,
    name: str,
    value: Register,
    *,
    span: SourceSpan | None,
) -> None:
    ctx.emit_inst(
        StoreField(obj_reg=obj, field_name=FieldName(name), value_reg=value),
        span=span,
    )


def lower_alter(
    ctx: EmitContext,
    stmt: AlterStatement,
    _materialised: MaterialisedSectionedLayout,
) -> None:
    """ALTER para-1 TO PROCEED TO para-2."""
    span = stmt.span
    for pt in stmt.proceed_tos:
        target_reg = ctx.const_to_reg(f"para_{pt.target}", span=span)
        ctx.emit_inst(
            StoreVar(
                name=VarName(f"__alter_{pt.source}"),
                value_reg=target_reg,
            ),
            span=span,
        )
        logger.info("ALTER %s TO PROCEED TO %s", pt.source, pt.target)


def lower_entry(
    ctx: EmitContext,
    stmt: EntryStatement,
    _materialised: MaterialisedSectionedLayout,
) -> None:
    """ENTRY 'name' — alternate entry point for a subprogram."""
    if stmt.entry_name:
        ctx.emit_inst(
            Label_(label=CodeLabel(f"entry_{stmt.entry_name}")), span=stmt.span
        )
        logger.info("ENTRY %s", stmt.entry_name)


def lower_cancel(
    _ctx: EmitContext,
    stmt: CancelStatement,
    _materialised: MaterialisedSectionedLayout,
) -> None:
    """CANCEL program — no-op for static analysis."""
    for prog in stmt.programs:
        logger.info("CANCEL %s (no-op for static analysis)", prog)
