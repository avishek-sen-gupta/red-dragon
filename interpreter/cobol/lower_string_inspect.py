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
from cobol_asg.nonnumeric_literal import literal_characters
from cobol_asg.ref_mod import RefModOperand
from cobol_asg.unstring_receiver import UnstringReceiver
from interpreter.cobol.cobol_constants import BuiltinName, InspectType
from interpreter.cobol.emit_context import EmitContext
from interpreter.cobol.inspect_ir import (
    emit_inspect_convert,
    emit_inspect_replace,
    emit_inspect_tally,
)
from interpreter.cobol.inspect_mode import InspectMode
from interpreter.cobol.inspect_phrase_registers import InspectPhraseRegisters
from interpreter.cobol.lower_arithmetic import eval_ref_mod_expr
from interpreter.cobol.lowering_scope import LoweringScope
from interpreter.cobol.sectioned_layout import MaterialisedSectionedLayout
from interpreter.cobol.string_ir import emit_string
from interpreter.cobol.string_ir_outcome import StringIrOutcome
from interpreter.cobol.unstring_ir import emit_unstring
from interpreter.cobol.unstring_ir_outcome import UnstringIrOutcome
from interpreter.cobol.unstring_ir_piece import UnstringIrPiece
from interpreter.cobol.zoned_sign_ir import (
    emit_inspected_characters,
    emit_write_inspected_characters,
)
from interpreter.func_name import FuncName
from interpreter.instructions import Binop, Branch, BranchIf, CallFunction, Label_
from interpreter.ir import CodeLabel
from interpreter.operator_kind import resolve_binop
from interpreter.register import NO_REGISTER, Register

logger = logging.getLogger(__name__)

_NO_OPERAND = RefModOperand(name="")


def _write_ref_mod_target(
    scope: LoweringScope, target: RefModOperand, value_reg: Register
) -> None:
    """Write value_reg into target's field.

    Splices into target's own reference modification (INTO dest(start:length))
    instead of overwriting the whole field when present — shared by STRING
    and UNSTRING destination writes (red-dragon-2fxq), mirroring the same
    decode-then-STRING_SPLICE write path MOVE's own target ref-mod already
    uses (lower_arithmetic.py's _store_move_value). Caller is responsible for
    confirming ctx.has_field(target.name, materialised) first.
    """
    ctx, materialised, span = scope.ctx, scope.materialised, scope.span
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
    OVERFLOW]. Every operand is evaluated once; IR then runs the transfer
    (interpreter.cobol.string_ir)."""
    scope = LoweringScope(ctx, materialised, stmt.span)
    if not ctx.has_field(stmt.into.name, materialised):
        logger.warning("STRING INTO target %s not found in layout", stmt.into.name)
        return
    has_pointer = bool(stmt.pointer.name) and ctx.has_field(
        stmt.pointer.name, materialised
    )
    outcome = _string_outcome(scope, stmt, has_pointer)
    _write_ref_mod_target(scope, stmt.into, outcome.image)
    if has_pointer:
        _write_number(scope, stmt.pointer, outcome.pointer)
    _lower_overflow_phrases(
        scope, outcome.overflow, stmt.on_overflow, stmt.not_on_overflow
    )


def _string_outcome(
    scope: LoweringScope, stmt: StringStatement, has_pointer: bool
) -> StringIrOutcome:
    """The receiver characters, pointer and overflow after the transfer; the
    pointer starts at 1 without WITH POINTER."""
    parts = tuple(_delimited_sending(scope, sending) for sending in stmt.sendings)
    return emit_string(
        scope.emitter,
        _receiver_characters(scope, stmt.into),
        (
            _read_pointer(scope, stmt.pointer)
            if has_pointer
            else scope.ctx.const_to_reg(1, span=scope.span)
        ),
        parts,
    )


def _delimited_sending(scope: LoweringScope, sending: StringSending) -> Register:
    """The characters a sending contributes: all of them for DELIMITED BY SIZE,
    else those before the delimiter's first occurrence."""
    characters_reg = _sending_characters(scope, sending)
    if not sending.delimiter.name:
        return characters_reg
    pieces_reg = _call(
        scope,
        BuiltinName.STRING_SPLIT,
        (characters_reg, _resolve_inspect_operand(scope, sending.delimiter)),
    )
    return _call(
        scope,
        BuiltinName.LIST_GET,
        (pieces_reg, scope.ctx.const_to_reg(0, span=scope.span)),
    )


def _sending_characters(scope: LoweringScope, sending: StringSending) -> Register:
    """An intrinsic FUNCTION's value, a data item's stored characters (with its
    qualifiers, subscripts and reference modification), a figurative constant's
    single character, or a literal's text."""
    ctx, materialised, span = scope.ctx, scope.materialised, scope.span
    if sending.function is not None:
        from interpreter.cobol.lower_arithmetic import lower_function_operand

        return ctx.emit_to_string(
            lower_function_operand(ctx, sending.function, materialised, span=span),
            span=span,
        )
    if not sending.value.names_data:
        return ctx.const_to_reg(
            literal_characters(ctx.figuratives.translate(sending.value.name)),
            span=span,
        )
    ref, rr = ctx.resolve_field_ref(
        sending.value.name,
        materialised,
        sending.value.qualifiers,
        subscripts=sending.value.subscripts,
        span=span,
    )
    stored_reg = ctx.emit_stored_characters(rr, ref, span=span)
    window = _ref_mod_window(scope, sending.value)
    return (
        _call(scope, BuiltinName.STRING_SLICE, (stored_reg, *window))
        if window
        else stored_reg
    )


def _receiver_characters(scope: LoweringScope, receiver: RefModOperand) -> Register:
    """The receiving item's current characters, only its reference-modified
    window when it has one."""
    ctx, span = scope.ctx, scope.span
    ref, rr = ctx.resolve_field_ref(
        receiver.name,
        scope.materialised,
        receiver.qualifiers,
        subscripts=receiver.subscripts,
        span=span,
    )
    current_reg = ctx.emit_decode_field_characters(
        rr, ref.fl, ref.offset_reg, extent=ref.extent, span=span
    )
    window = _ref_mod_window(scope, receiver)
    return (
        _call(scope, BuiltinName.STRING_SLICE, (current_reg, *window))
        if window
        else current_reg
    )


def _ref_mod_window(
    scope: LoweringScope, operand: RefModOperand
) -> tuple[Register, ...]:
    """(0-based start, length) registers of a reference-modified operand, else ()."""
    if operand.ref_mod_start is None:
        return ()
    ctx, materialised, span = scope.ctx, scope.materialised, scope.span
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


def _read_pointer(scope: LoweringScope, item: RefModOperand) -> Register:
    ctx, span = scope.ctx, scope.span
    ref, rr = ctx.resolve_field_ref(
        item.name, scope.materialised, item.qualifiers, item.subscripts, span=span
    )
    return ctx.emit_decode_field(
        rr, ref.fl, ref.offset_reg, extent=ref.extent, span=span
    )


def _write_number(
    scope: LoweringScope, item: RefModOperand, value_reg: Register
) -> None:
    ctx, span = scope.ctx, scope.span
    ref, rr = ctx.resolve_field_ref(
        item.name, scope.materialised, item.qualifiers, item.subscripts, span=span
    )
    ctx.emit_encode_and_write(
        rr,
        ref.fl,
        ctx.emit_to_string(value_reg, span=span),
        ref.offset_reg,
        extent=ref.extent,
        span=span,
    )


def _lower_overflow_phrases(
    scope: LoweringScope,
    overflow_reg: Register,
    on_overflow: Sequence[CobolStatementType],
    not_on_overflow: Sequence[CobolStatementType],
) -> None:
    """ON OVERFLOW runs when the overflow condition arose, NOT ON OVERFLOW when
    it did not; control then passes to the end of the statement."""
    if not (on_overflow or not_on_overflow):
        return
    ctx, span = scope.ctx, scope.span
    on_label = ctx.fresh_label("on_overflow")
    not_on_label = ctx.fresh_label("not_on_overflow")
    end_label = ctx.fresh_label("overflow_end")
    ctx.emit_inst(
        BranchIf(cond_reg=overflow_reg, branch_targets=(on_label, not_on_label)),
        span=span,
    )
    _lower_overflow_arm(scope, on_label, on_overflow, end_label)
    _lower_overflow_arm(scope, not_on_label, not_on_overflow, end_label)
    ctx.emit_inst(Label_(label=end_label), span=span)


def _lower_overflow_arm(
    scope: LoweringScope,
    label: CodeLabel,
    body: Sequence[CobolStatementType],
    end_label: CodeLabel,
) -> None:
    ctx, span = scope.ctx, scope.span
    ctx.emit_inst(Label_(label=label), span=span)
    for child in body:
        ctx.lower_statement(child, scope.materialised)
    ctx.emit_inst(Branch(label=end_label), span=span)


def lower_unstring(
    ctx: EmitContext,
    stmt: UnstringStatement,
    materialised: MaterialisedSectionedLayout,
) -> None:
    """UNSTRING source [DELIMITED BY [ALL] d1 OR ...] INTO receivers [WITH
    POINTER] [TALLYING IN] [ON / NOT ON OVERFLOW]. The source, pointer and
    delimiters are evaluated once; IR then examines the source
    (interpreter.cobol.unstring_ir) and each receiver it acted on is written."""
    scope = LoweringScope(ctx, materialised, stmt.span)
    if not ctx.has_field(stmt.source.name, materialised):
        logger.warning("UNSTRING source %s not found in layout", stmt.source.name)
        return
    has_pointer = bool(stmt.pointer.name) and ctx.has_field(
        stmt.pointer.name, materialised
    )
    outcome = _unstring_outcome(scope, stmt, has_pointer)
    for index, (receiver, piece) in enumerate(
        zip(stmt.into, outcome.pieces, strict=True)
    ):
        _write_unstring_receiver(scope, receiver, (piece, outcome.acted), index)
    if has_pointer:
        _write_number(scope, stmt.pointer, outcome.pointer)
    if stmt.tallying_target.name and ctx.has_field(
        stmt.tallying_target.name, materialised
    ):
        _add_to_number(scope, stmt.tallying_target, outcome.acted)
    _lower_overflow_phrases(
        scope, outcome.overflow, stmt.on_overflow, stmt.not_on_overflow
    )


def _unstring_outcome(
    scope: LoweringScope, stmt: UnstringStatement, has_pointer: bool
) -> UnstringIrOutcome:
    """The examination's outcome for this statement; the pointer starts at 1
    without WITH POINTER."""
    materialised = scope.materialised
    delimiters = tuple(
        (_resolve_inspect_operand(scope, delimiter.operand), delimiter.all)
        for delimiter in stmt.delimiters
    )
    return emit_unstring(
        scope.emitter,
        _receiver_characters(scope, stmt.source),
        (
            _read_pointer(scope, stmt.pointer)
            if has_pointer
            else scope.ctx.const_to_reg(1, span=scope.span)
        ),
        (
            delimiters,
            tuple(
                materialised.resolve(receiver.target.name, receiver.target.qualifiers)[
                    0
                ].byte_length
                for receiver in stmt.into
            ),
        ),
    )


def _write_unstring_receiver(
    scope: LoweringScope,
    receiver: UnstringReceiver,
    received: tuple[UnstringIrPiece, Register],
    index: int,
) -> None:
    """Receiver ``index`` and its DELIMITER IN and COUNT IN items get their
    piece when the examination reached that receiver, and are untouched when
    it did not."""
    ctx, span = scope.ctx, scope.span
    piece, acted_reg = received
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
    _write_ref_mod_target(scope, receiver.target, piece.text)
    if receiver.delimiter_in.name:
        _write_ref_mod_target(scope, receiver.delimiter_in, piece.delimiter)
    if receiver.count_in.name:
        _write_ref_mod_target(
            scope, receiver.count_in, ctx.emit_to_string(piece.count, span=span)
        )
    ctx.emit_inst(Branch(label=skip_label), span=span)
    ctx.emit_inst(Label_(label=skip_label), span=span)


def _add_to_number(
    scope: LoweringScope, item: RefModOperand, addend_reg: Register
) -> None:
    ctx = scope.ctx
    total_reg = ctx.fresh_reg()
    ctx.emit_inst(
        Binop(
            result_reg=total_reg,
            operator=resolve_binop("+"),
            left=_read_pointer(scope, item),
            right=addend_reg,
        ),
        span=scope.span,
    )
    _write_number(scope, item, total_reg)


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
    scope = LoweringScope(ctx, materialised, stmt.span)
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
    image_reg = emit_inspected_characters(scope.emitter, source_rr, source_ref)
    window = _ref_mod_window(scope, stmt.source)
    inspected_reg = (
        _call(scope, BuiltinName.STRING_SLICE, (image_reg, *window))
        if window
        else image_reg
    )
    if stmt.tallying_groups:
        _lower_inspect_tallying(scope, stmt, inspected_reg)
    rewritten_reg = _rewritten(scope, stmt, inspected_reg)
    if not rewritten_reg.is_present():
        return
    emit_write_inspected_characters(
        scope.emitter,
        source_rr,
        source_ref,
        (
            _call(
                scope,
                BuiltinName.STRING_SPLICE,
                (image_reg, *window, rewritten_reg),
            )
            if window
            else rewritten_reg
        ),
    )


def _rewritten(
    scope: LoweringScope, stmt: InspectStatement, inspected_reg: Register
) -> Register:
    """The new characters REPLACING or CONVERTING give, or NO_REGISTER."""
    emitter = scope.emitter
    if stmt.inspect_type == InspectType.CONVERTING:
        return emit_inspect_convert(
            emitter,
            inspected_reg,
            (
                _written_operand(scope, stmt.converting_from),
                _written_operand(scope, stmt.converting_to),
            ),
            (
                _written_operand(scope, stmt.converting_after),
                _written_operand(scope, stmt.converting_before),
            ),
        )
    if not stmt.replacings:
        return NO_REGISTER
    return emit_inspect_replace(
        emitter,
        inspected_reg,
        tuple(
            _phrase_registers(
                scope,
                replacing.mode,
                (
                    replacing.from_pattern,
                    replacing.to_pattern,
                    replacing.after,
                    replacing.before,
                ),
                0,
            )
            for replacing in stmt.replacings
        ),
    )


def _phrase_registers(
    scope: LoweringScope,
    mode: str,
    operands: tuple[RefModOperand, RefModOperand, RefModOperand, RefModOperand],
    counter: int,
) -> InspectPhraseRegisters:
    """One phrase's mode, its written operands' characters (pattern, BY value,
    AFTER, BEFORE) and the counter it tallies into."""
    pattern, replacement, after, before = (
        _written_operand(scope, operand) for operand in operands
    )
    return InspectPhraseRegisters(
        mode=InspectMode(mode),
        pattern=pattern,
        replacement=replacement,
        after=after,
        before=before,
        counter=counter,
    )


def _written_operand(scope: LoweringScope, operand: RefModOperand) -> Register:
    """The operand's characters, or NO_REGISTER when it was not written."""
    if not operand.name:
        return NO_REGISTER
    return _resolve_inspect_operand(scope, operand)


def _call(scope: LoweringScope, builtin: str, args: tuple[Register, ...]) -> Register:
    result_reg = scope.ctx.fresh_reg()
    scope.ctx.emit_inst(
        CallFunction(result_reg=result_reg, func_name=FuncName(builtin), args=args),
        span=scope.span,
    )
    return result_reg


def _resolve_inspect_operand(scope: LoweringScope, operand: RefModOperand) -> Register:
    """An INSPECT operand's characters: a data item (with its qualifiers and
    subscripts) decoded at run time, a figurative constant's character, or a
    literal's text. An operand that was not written is the empty string."""
    ctx, span = scope.ctx, scope.span
    if operand.names_data:
        ref, rr = ctx.resolve_field_ref(
            operand.name,
            scope.materialised,
            operand.qualifiers,
            subscripts=operand.subscripts,
            span=span,
        )
        return ctx.emit_decode_field_characters(
            rr, ref.fl, ref.offset_reg, extent=ref.extent, span=span
        )
    return ctx.const_to_reg(
        literal_characters(ctx.figuratives.translate(operand.name)), span=span
    )


def _lower_inspect_tallying(
    scope: LoweringScope, stmt: InspectStatement, inspected_reg: Register
) -> None:
    """Each TALLYING identifier gains the matches of its own phrases; the count
    ACCUMULATES into its existing value (IBM Enterprise COBOL LR, INSPECT)."""
    counts_reg = emit_inspect_tally(
        scope.emitter,
        inspected_reg,
        tuple(
            _phrase_registers(
                scope,
                tally_for.mode,
                (tally_for.pattern, _NO_OPERAND, tally_for.after, tally_for.before),
                counter,
            )
            for counter, group in enumerate(stmt.tallying_groups)
            for tally_for in group.patterns
        ),
        len(stmt.tallying_groups),
    )
    for counter, group in enumerate(stmt.tallying_groups):
        if scope.ctx.has_field(group.target.name, scope.materialised):
            _add_to_tally(scope, group.target, counts_reg, counter)


def _add_to_tally(
    scope: LoweringScope,
    target: RefModOperand,
    counts_reg: Register,
    counter: int,
) -> None:
    ctx, span = scope.ctx, scope.span
    tally_ref, tally_rr = ctx.resolve_field_ref(
        target.name,
        scope.materialised,
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
                scope,
                BuiltinName.LIST_GET,
                (counts_reg, ctx.const_to_reg(counter, span=span)),
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
