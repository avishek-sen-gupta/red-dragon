"""STRING, UNSTRING, INSPECT statement lowering."""

from __future__ import annotations

import logging
from collections.abc import Sequence

from cobol_asg.cobol_statements import (
    CobolStatementType,
    InspectStatement,
    StringSending,
    StringStatement,
    UnstringStatement,
)
from cobol_asg.ref_mod import RefModOperand
from cobol_asg.source_span import SourceSpan
from cobol_asg.unstring_receiver import UnstringReceiver
from interpreter.cobol.cobol_constants import BuiltinName, InspectType
from interpreter.cobol.emit_context import EmitContext, strip_cobol_literal
from interpreter.cobol.inspect_ir import (
    emit_inspect_convert,
    emit_inspect_replace,
    emit_inspect_tally,
)
from interpreter.cobol.inspect_mode import InspectMode
from interpreter.cobol.inspect_phrase_registers import InspectPhraseRegisters
from interpreter.cobol.ir_emitter import IrEmitter
from interpreter.cobol.lower_arithmetic import eval_ref_mod_expr
from interpreter.cobol.sectioned_layout import MaterialisedSectionedLayout
from interpreter.func_name import FuncName
from interpreter.instructions import Binop, Branch, BranchIf, CallFunction, Label_
from interpreter.ir import CodeLabel
from interpreter.operator_kind import resolve_binop
from interpreter.register import NO_REGISTER, Register

logger = logging.getLogger(__name__)

_NO_OPERAND = RefModOperand(name="")


def _write_ref_mod_target(
    ctx: EmitContext,
    target: RefModOperand,
    value_reg: Register,
    materialised: MaterialisedSectionedLayout,
    *,
    span: SourceSpan | None = None,
) -> None:
    """Write value_reg into target's field.

    Splices into target's own reference modification (INTO dest(start:length))
    instead of overwriting the whole field when present — shared by STRING
    and UNSTRING destination writes (red-dragon-2fxq), mirroring the same
    decode-then-STRING_SPLICE write path MOVE's own target ref-mod already
    uses (lower_arithmetic.py's _store_move_value). Caller is responsible for
    confirming ctx.has_field(target.name, materialised) first.
    """
    target_ref, target_rr = ctx.resolve_field_ref(
        target.name,
        materialised,
        target.qualifiers,
        subscripts=target.subscripts,
        span=span,
    )
    target_value_reg = value_reg
    if target.ref_mod_start is not None:
        target_str_reg = ctx.emit_decode_field_characters(
            target_rr,
            target_ref.fl,
            target_ref.offset_reg,
            extent=target_ref.extent,
            span=span,
        )
        tgt_start_reg = eval_ref_mod_expr(
            ctx, target.ref_mod_start, materialised, span=span
        )
        one_reg = ctx.const_to_reg(1, span=span)
        tgt_start_0indexed_reg = ctx.fresh_reg()
        ctx.emit_inst(
            Binop(
                result_reg=tgt_start_0indexed_reg,
                operator=resolve_binop("-"),
                left=tgt_start_reg,
                right=one_reg,
            ),
            span=span,
        )
        if target.ref_mod_length is not None:
            tgt_length_reg = eval_ref_mod_expr(
                ctx, target.ref_mod_length, materialised, span=span
            )
        else:
            tgt_length_reg = ctx.const_to_reg(999999, span=span)
        spliced_reg = ctx.fresh_reg()
        ctx.emit_inst(
            CallFunction(
                result_reg=spliced_reg,
                func_name=FuncName(BuiltinName.STRING_SPLICE),
                args=(
                    target_str_reg,
                    tgt_start_0indexed_reg,
                    tgt_length_reg,
                    value_reg,
                ),
            ),
            span=span,
        )
        target_value_reg = spliced_reg
    ctx.emit_encode_and_write(
        target_rr,
        target_ref.fl,
        target_value_reg,
        target_ref.offset_reg,
        extent=target_ref.extent,
        span=span,
    )


def lower_string(
    ctx: EmitContext,
    stmt: StringStatement,
    materialised: MaterialisedSectionedLayout,
) -> None:
    """STRING sendings DELIMITED BY ... INTO receiver [WITH POINTER] [ON / NOT ON
    OVERFLOW]. Every operand is evaluated once; one builtin then runs the
    transfer (interpreter.cobol.string_transfer)."""
    span = stmt.span
    if not ctx.has_field(stmt.into.name, materialised):
        logger.warning("STRING INTO target %s not found in layout", stmt.into.name)
        return
    has_pointer = bool(stmt.pointer.name) and ctx.has_field(
        stmt.pointer.name, materialised
    )
    outcome_reg = _string_outcome(ctx, stmt, has_pointer, materialised)
    _write_ref_mod_target(
        ctx,
        stmt.into,
        _list_item(ctx, outcome_reg, 0, span=span),
        materialised,
        span=span,
    )
    if has_pointer:
        _write_number(
            ctx,
            stmt.pointer,
            _list_item(ctx, outcome_reg, 1, span=span),
            materialised,
            span=span,
        )
    _lower_overflow_phrases(
        ctx,
        _list_item(ctx, outcome_reg, 2, span=span),
        stmt.on_overflow,
        stmt.not_on_overflow,
        materialised,
        span=span,
    )


def _string_outcome(
    ctx: EmitContext,
    stmt: StringStatement,
    has_pointer: bool,
    materialised: MaterialisedSectionedLayout,
) -> Register:
    """[receiver characters, pointer, overflow] after the transfer; the pointer
    starts at 1 without WITH POINTER."""
    span = stmt.span
    parts = tuple(
        _delimited_sending(ctx, sending, materialised, span=span)
        for sending in stmt.sendings
    )
    return _call(
        ctx,
        BuiltinName.COBOL_STRING,
        (
            _receiver_characters(ctx, stmt.into, materialised, span=span),
            (
                _read_pointer(ctx, stmt.pointer, materialised, span=span)
                if has_pointer
                else ctx.const_to_reg(1, span=span)
            ),
            *parts,
        ),
        span=span,
    )


def _delimited_sending(
    ctx: EmitContext,
    sending: StringSending,
    materialised: MaterialisedSectionedLayout,
    *,
    span: SourceSpan | None,
) -> Register:
    """The characters a sending contributes: all of them for DELIMITED BY SIZE,
    else those before the delimiter's first occurrence."""
    characters_reg = _sending_characters(ctx, sending, materialised, span=span)
    if not sending.delimiter.name:
        return characters_reg
    pieces_reg = _call(
        ctx,
        BuiltinName.STRING_SPLIT,
        (
            characters_reg,
            _resolve_inspect_operand(ctx, sending.delimiter, materialised, span=span),
        ),
        span=span,
    )
    return _list_item(ctx, pieces_reg, 0, span=span)


def _sending_characters(
    ctx: EmitContext,
    sending: StringSending,
    materialised: MaterialisedSectionedLayout,
    *,
    span: SourceSpan | None,
) -> Register:
    """An intrinsic FUNCTION's value, a data item's stored characters (with its
    qualifiers, subscripts and reference modification), a figurative constant's
    single character, or a literal's text."""
    if sending.function is not None:
        from interpreter.cobol.lower_arithmetic import lower_function_operand

        return ctx.emit_to_string(
            lower_function_operand(ctx, sending.function, materialised, span=span),
            span=span,
        )
    if not ctx.has_field(sending.value.name, materialised):
        return ctx.const_to_reg(
            strip_cobol_literal(ctx.figuratives.translate(sending.value.name)),
            span=span,
        )
    ref, rr = ctx.resolve_field_ref(
        sending.value.name,
        materialised,
        sending.value.qualifiers,
        subscripts=sending.value.subscripts,
        span=span,
    )
    stored_reg = ctx.emit_stored_characters(
        rr, ref.fl, ref.offset_reg, extent=ref.extent, span=span
    )
    window = _ref_mod_window(ctx, sending.value, materialised, span=span)
    return (
        _call(ctx, BuiltinName.STRING_SLICE, (stored_reg, *window), span=span)
        if window
        else stored_reg
    )


def _receiver_characters(
    ctx: EmitContext,
    receiver: RefModOperand,
    materialised: MaterialisedSectionedLayout,
    *,
    span: SourceSpan | None,
) -> Register:
    """The receiving item's current characters, only its reference-modified
    window when it has one."""
    ref, rr = ctx.resolve_field_ref(
        receiver.name,
        materialised,
        receiver.qualifiers,
        subscripts=receiver.subscripts,
        span=span,
    )
    current_reg = ctx.emit_decode_field_characters(
        rr, ref.fl, ref.offset_reg, extent=ref.extent, span=span
    )
    window = _ref_mod_window(ctx, receiver, materialised, span=span)
    return (
        _call(ctx, BuiltinName.STRING_SLICE, (current_reg, *window), span=span)
        if window
        else current_reg
    )


def _ref_mod_window(
    ctx: EmitContext,
    operand: RefModOperand,
    materialised: MaterialisedSectionedLayout,
    *,
    span: SourceSpan | None,
) -> tuple[Register, ...]:
    """(0-based start, length) registers of a reference-modified operand, else ()."""
    if operand.ref_mod_start is None:
        return ()
    start_reg = ctx.fresh_reg()
    ctx.emit_inst(
        Binop(
            result_reg=start_reg,
            operator=resolve_binop("-"),
            left=eval_ref_mod_expr(ctx, operand.ref_mod_start, materialised, span=span),
            right=ctx.const_to_reg(1, span=span),
        ),
        span=span,
    )
    length_reg = (
        eval_ref_mod_expr(ctx, operand.ref_mod_length, materialised, span=span)
        if operand.ref_mod_length is not None
        else ctx.const_to_reg(9999, span=span)
    )
    return start_reg, length_reg


def _read_pointer(
    ctx: EmitContext,
    item: RefModOperand,
    materialised: MaterialisedSectionedLayout,
    *,
    span: SourceSpan | None,
) -> Register:
    ref, rr = ctx.resolve_field_ref(
        item.name, materialised, item.qualifiers, item.subscripts, span=span
    )
    return ctx.emit_decode_field(
        rr, ref.fl, ref.offset_reg, extent=ref.extent, span=span
    )


def _write_number(
    ctx: EmitContext,
    item: RefModOperand,
    value_reg: Register,
    materialised: MaterialisedSectionedLayout,
    *,
    span: SourceSpan | None,
) -> None:
    ref, rr = ctx.resolve_field_ref(
        item.name, materialised, item.qualifiers, item.subscripts, span=span
    )
    ctx.emit_encode_and_write(
        rr,
        ref.fl,
        ctx.emit_to_string(value_reg, span=span),
        ref.offset_reg,
        extent=ref.extent,
        span=span,
    )


def _list_item(
    ctx: EmitContext, list_reg: Register, index: int, *, span: SourceSpan | None
) -> Register:
    return _call(
        ctx,
        BuiltinName.LIST_GET,
        (list_reg, ctx.const_to_reg(index, span=span)),
        span=span,
    )


def _lower_overflow_phrases(
    ctx: EmitContext,
    overflow_reg: Register,
    on_overflow: Sequence[CobolStatementType],
    not_on_overflow: Sequence[CobolStatementType],
    materialised: MaterialisedSectionedLayout,
    *,
    span: SourceSpan | None,
) -> None:
    """ON OVERFLOW runs when the overflow condition arose, NOT ON OVERFLOW when
    it did not; control then passes to the end of the statement."""
    if not (on_overflow or not_on_overflow):
        return
    on_label = ctx.fresh_label("on_overflow")
    not_on_label = ctx.fresh_label("not_on_overflow")
    end_label = ctx.fresh_label("overflow_end")
    ctx.emit_inst(
        BranchIf(cond_reg=overflow_reg, branch_targets=(on_label, not_on_label)),
        span=span,
    )
    _lower_overflow_arm(ctx, on_label, on_overflow, end_label, materialised, span=span)
    _lower_overflow_arm(
        ctx, not_on_label, not_on_overflow, end_label, materialised, span=span
    )
    ctx.emit_inst(Label_(label=end_label), span=span)


def _lower_overflow_arm(
    ctx: EmitContext,
    label: CodeLabel,
    body: Sequence[CobolStatementType],
    end_label: CodeLabel,
    materialised: MaterialisedSectionedLayout,
    *,
    span: SourceSpan | None,
) -> None:
    ctx.emit_inst(Label_(label=label), span=span)
    for child in body:
        ctx.lower_statement(child, materialised)
    ctx.emit_inst(Branch(label=end_label), span=span)


def lower_unstring(
    ctx: EmitContext,
    stmt: UnstringStatement,
    materialised: MaterialisedSectionedLayout,
) -> None:
    """UNSTRING source [DELIMITED BY [ALL] d1 OR ...] INTO receivers [WITH
    POINTER] [TALLYING IN] [ON / NOT ON OVERFLOW]. The source, pointer and
    delimiters are evaluated once; one builtin then examines the source
    (interpreter.cobol.unstring_scan) and each receiver it acted on is written."""
    span = stmt.span
    if not ctx.has_field(stmt.source.name, materialised):
        logger.warning("UNSTRING source %s not found in layout", stmt.source.name)
        return
    has_pointer = bool(stmt.pointer.name) and ctx.has_field(
        stmt.pointer.name, materialised
    )
    outcome_reg = _unstring_outcome(ctx, stmt, has_pointer, materialised)
    acted_reg = _list_item(ctx, outcome_reg, 2, span=span)
    for index, receiver in enumerate(stmt.into):
        _write_unstring_receiver(
            ctx, receiver, outcome_reg, acted_reg, index, materialised, span=span
        )
    if has_pointer:
        _write_number(
            ctx,
            stmt.pointer,
            _list_item(ctx, outcome_reg, 0, span=span),
            materialised,
            span=span,
        )
    if stmt.tallying_target.name and ctx.has_field(
        stmt.tallying_target.name, materialised
    ):
        _add_to_number(ctx, stmt.tallying_target, acted_reg, materialised, span=span)
    _lower_overflow_phrases(
        ctx,
        _list_item(ctx, outcome_reg, 1, span=span),
        stmt.on_overflow,
        stmt.not_on_overflow,
        materialised,
        span=span,
    )


def _unstring_outcome(
    ctx: EmitContext,
    stmt: UnstringStatement,
    has_pointer: bool,
    materialised: MaterialisedSectionedLayout,
) -> Register:
    """The builtin's result for this statement; the pointer starts at 1
    without WITH POINTER."""
    span = stmt.span
    delimiter_args = tuple(
        arg
        for delimiter in stmt.delimiters
        for arg in (
            _resolve_inspect_operand(ctx, delimiter.operand, materialised, span=span),
            ctx.const_to_reg(delimiter.all, span=span),
        )
    )
    return _call(
        ctx,
        BuiltinName.COBOL_UNSTRING,
        (
            _receiver_characters(ctx, stmt.source, materialised, span=span),
            (
                _read_pointer(ctx, stmt.pointer, materialised, span=span)
                if has_pointer
                else ctx.const_to_reg(1, span=span)
            ),
            ctx.const_to_reg(len(stmt.delimiters), span=span),
            *delimiter_args,
            *(
                ctx.const_to_reg(
                    materialised.resolve(
                        receiver.target.name, receiver.target.qualifiers
                    )[0].byte_length,
                    span=span,
                )
                for receiver in stmt.into
            ),
        ),
        span=span,
    )


def _write_unstring_receiver(
    ctx: EmitContext,
    receiver: UnstringReceiver,
    outcome_reg: Register,
    acted_reg: Register,
    index: int,
    materialised: MaterialisedSectionedLayout,
    *,
    span: SourceSpan | None,
) -> None:
    """Receiver ``index`` and its DELIMITER IN and COUNT IN items get their
    piece when the examination reached that receiver, and are untouched when
    it did not."""
    write_label = ctx.fresh_label("unstring_receive")
    skip_label = ctx.fresh_label("unstring_skip")
    reached_reg = ctx.fresh_reg()
    ctx.emit_inst(
        Binop(
            result_reg=reached_reg,
            operator=resolve_binop(">"),
            left=acted_reg,
            right=ctx.const_to_reg(index, span=span),
        ),
        span=span,
    )
    ctx.emit_inst(
        BranchIf(cond_reg=reached_reg, branch_targets=(write_label, skip_label)),
        span=span,
    )
    ctx.emit_inst(Label_(label=write_label), span=span)
    first = 3 + 3 * index
    _write_ref_mod_target(
        ctx,
        receiver.target,
        _list_item(ctx, outcome_reg, first, span=span),
        materialised,
        span=span,
    )
    if receiver.delimiter_in.name:
        _write_ref_mod_target(
            ctx,
            receiver.delimiter_in,
            _list_item(ctx, outcome_reg, first + 1, span=span),
            materialised,
            span=span,
        )
    if receiver.count_in.name:
        _write_ref_mod_target(
            ctx,
            receiver.count_in,
            ctx.emit_to_string(
                _list_item(ctx, outcome_reg, first + 2, span=span), span=span
            ),
            materialised,
            span=span,
        )
    ctx.emit_inst(Branch(label=skip_label), span=span)
    ctx.emit_inst(Label_(label=skip_label), span=span)


def _add_to_number(
    ctx: EmitContext,
    item: RefModOperand,
    addend_reg: Register,
    materialised: MaterialisedSectionedLayout,
    *,
    span: SourceSpan | None,
) -> None:
    total_reg = ctx.fresh_reg()
    ctx.emit_inst(
        Binop(
            result_reg=total_reg,
            operator=resolve_binop("+"),
            left=_read_pointer(ctx, item, materialised, span=span),
            right=addend_reg,
        ),
        span=span,
    )
    _write_number(ctx, item, total_reg, materialised, span=span)


def lower_inspect(
    ctx: EmitContext,
    stmt: InspectStatement,
    materialised: MaterialisedSectionedLayout,
) -> None:
    """INSPECT source TALLYING | REPLACING | TALLYING ... REPLACING | CONVERTING.

    The source, its subscripts and reference modification, and every operand
    are evaluated once; IR then runs the standard's single left-to-right
    scan (interpreter.cobol.inspect_ir). TALLYING ...
    REPLACING tallies first and then replaces, as two statements would.
    """
    span = stmt.span
    if not ctx.has_field(stmt.source.name, materialised):
        logger.warning("INSPECT source %s not found in layout", stmt.source.name)
        return
    source_ref, source_rr = ctx.resolve_field_ref(
        stmt.source.name,
        materialised,
        stmt.source.qualifiers,
        subscripts=stmt.source.subscripts,
        span=span,
    )
    image_reg = ctx.emit_inspected_characters(
        source_rr,
        source_ref.fl,
        source_ref.offset_reg,
        extent=source_ref.extent,
        span=span,
    )
    window = _inspected_window(ctx, stmt, materialised)
    inspected_reg = (
        _call(ctx, BuiltinName.STRING_SLICE, (image_reg, *window), span=span)
        if window
        else image_reg
    )
    if stmt.tallying_groups:
        _lower_inspect_tallying(ctx, stmt, inspected_reg, materialised)
    rewritten_reg = _rewritten(ctx, stmt, inspected_reg, materialised)
    if not rewritten_reg.is_present():
        return
    ctx.emit_write_inspected_characters(
        source_rr,
        source_ref.fl,
        (
            _call(
                ctx,
                BuiltinName.STRING_SPLICE,
                (image_reg, *window, rewritten_reg),
                span=span,
            )
            if window
            else rewritten_reg
        ),
        source_ref.offset_reg,
        extent=source_ref.extent,
        span=span,
    )


def _inspected_window(
    ctx: EmitContext,
    stmt: InspectStatement,
    materialised: MaterialisedSectionedLayout,
) -> tuple[Register, ...]:
    """(start, length) registers of a reference-modified source, else ()."""
    if stmt.source.ref_mod_start is None:
        return ()
    span = stmt.span
    start_reg = ctx.fresh_reg()
    ctx.emit_inst(
        Binop(
            result_reg=start_reg,
            operator=resolve_binop("-"),
            left=eval_ref_mod_expr(
                ctx, stmt.source.ref_mod_start, materialised, span=span
            ),
            right=ctx.const_to_reg(1, span=span),
        ),
        span=span,
    )
    length_reg = (
        eval_ref_mod_expr(ctx, stmt.source.ref_mod_length, materialised, span=span)
        if stmt.source.ref_mod_length is not None
        else ctx.const_to_reg(9999, span=span)
    )
    return start_reg, length_reg


def _rewritten(
    ctx: EmitContext,
    stmt: InspectStatement,
    inspected_reg: Register,
    materialised: MaterialisedSectionedLayout,
) -> Register:
    """The new characters REPLACING or CONVERTING give, or NO_REGISTER."""
    emitter = IrEmitter(ctx=ctx, span=stmt.span)
    if stmt.inspect_type == InspectType.CONVERTING:
        return emit_inspect_convert(
            emitter,
            inspected_reg,
            (
                _written_operand(
                    ctx, stmt.converting_from, materialised, span=stmt.span
                ),
                _written_operand(ctx, stmt.converting_to, materialised, span=stmt.span),
            ),
            (
                _written_operand(
                    ctx, stmt.converting_after, materialised, span=stmt.span
                ),
                _written_operand(
                    ctx, stmt.converting_before, materialised, span=stmt.span
                ),
            ),
        )
    if not stmt.replacings:
        return NO_REGISTER
    return emit_inspect_replace(
        emitter,
        inspected_reg,
        tuple(
            _phrase_registers(
                ctx,
                replacing.mode,
                (
                    replacing.from_pattern,
                    replacing.to_pattern,
                    replacing.after,
                    replacing.before,
                ),
                0,
                materialised,
                span=stmt.span,
            )
            for replacing in stmt.replacings
        ),
    )


def _phrase_registers(
    ctx: EmitContext,
    mode: str,
    operands: tuple[RefModOperand, RefModOperand, RefModOperand, RefModOperand],
    counter: int,
    materialised: MaterialisedSectionedLayout,
    *,
    span: SourceSpan | None,
) -> InspectPhraseRegisters:
    """One phrase's mode, its written operands' characters (pattern, BY value,
    AFTER, BEFORE) and the counter it tallies into."""
    pattern, replacement, after, before = (
        _written_operand(ctx, operand, materialised, span=span) for operand in operands
    )
    return InspectPhraseRegisters(
        mode=InspectMode(mode),
        pattern=pattern,
        replacement=replacement,
        after=after,
        before=before,
        counter=counter,
    )


def _written_operand(
    ctx: EmitContext,
    operand: RefModOperand,
    materialised: MaterialisedSectionedLayout,
    *,
    span: SourceSpan | None,
) -> Register:
    """The operand's characters, or NO_REGISTER when it was not written."""
    if not operand.name:
        return NO_REGISTER
    return _resolve_inspect_operand(ctx, operand, materialised, span=span)


def _call(
    ctx: EmitContext,
    builtin: str,
    args: tuple[Register, ...],
    *,
    span: SourceSpan | None,
) -> Register:
    result_reg = ctx.fresh_reg()
    ctx.emit_inst(
        CallFunction(result_reg=result_reg, func_name=FuncName(builtin), args=args),
        span=span,
    )
    return result_reg


def _resolve_inspect_operand(
    ctx: EmitContext,
    operand: RefModOperand,
    materialised: MaterialisedSectionedLayout,
    *,
    span: SourceSpan | None,
) -> Register:
    """An INSPECT operand's characters: a data item (with its qualifiers and
    subscripts) decoded at run time, a figurative constant's character, or a
    literal's text. An operand that was not written is the empty string."""
    if ctx.has_field(operand.name, materialised):
        ref, rr = ctx.resolve_field_ref(
            operand.name,
            materialised,
            operand.qualifiers,
            subscripts=operand.subscripts,
            span=span,
        )
        return ctx.emit_decode_field_characters(
            rr, ref.fl, ref.offset_reg, extent=ref.extent, span=span
        )
    return ctx.const_to_reg(
        strip_cobol_literal(ctx.figuratives.translate(operand.name)), span=span
    )


def _lower_inspect_tallying(
    ctx: EmitContext,
    stmt: InspectStatement,
    inspected_reg: Register,
    materialised: MaterialisedSectionedLayout,
) -> None:
    """Each TALLYING identifier gains the matches of its own phrases; the count
    ACCUMULATES into its existing value (IBM Enterprise COBOL LR, INSPECT)."""
    span = stmt.span
    counts_reg = emit_inspect_tally(
        IrEmitter(ctx=ctx, span=span),
        inspected_reg,
        tuple(
            _phrase_registers(
                ctx,
                tally_for.mode,
                (tally_for.pattern, _NO_OPERAND, tally_for.after, tally_for.before),
                counter,
                materialised,
                span=span,
            )
            for counter, group in enumerate(stmt.tallying_groups)
            for tally_for in group.patterns
        ),
        len(stmt.tallying_groups),
    )
    for counter, group in enumerate(stmt.tallying_groups):
        if ctx.has_field(group.target.name, materialised):
            _add_to_tally(ctx, stmt, group.target, counts_reg, counter, materialised)


def _add_to_tally(
    ctx: EmitContext,
    stmt: InspectStatement,
    target: RefModOperand,
    counts_reg: Register,
    counter: int,
    materialised: MaterialisedSectionedLayout,
) -> None:
    span = stmt.span
    tally_ref, tally_rr = ctx.resolve_field_ref(
        target.name,
        materialised,
        target.qualifiers,
        subscripts=target.subscripts,
        span=span,
    )
    total_reg = ctx.fresh_reg()
    ctx.emit_inst(
        Binop(
            result_reg=total_reg,
            operator=resolve_binop("+"),
            left=ctx.emit_decode_field(
                tally_rr,
                tally_ref.fl,
                tally_ref.offset_reg,
                extent=tally_ref.extent,
                span=span,
            ),
            right=_call(
                ctx,
                BuiltinName.LIST_GET,
                (counts_reg, ctx.const_to_reg(counter, span=span)),
                span=span,
            ),
        ),
        span=span,
    )
    ctx.emit_encode_and_write(
        tally_rr,
        tally_ref.fl,
        ctx.emit_to_string(total_reg, span=span),
        tally_ref.offset_reg,
        extent=tally_ref.extent,
        span=span,
    )
