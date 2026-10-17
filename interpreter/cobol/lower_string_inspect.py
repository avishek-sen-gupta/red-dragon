"""STRING, UNSTRING, INSPECT statement lowering."""

from __future__ import annotations

import logging

from cobol_asg.cobol_statements import (
    InspectStatement,
    StringStatement,
    UnstringStatement,
)
from cobol_asg.ref_mod import RefModOperand
from cobol_asg.source_span import SourceSpan
from interpreter.cobol.cobol_constants import BuiltinName, DelimiterMode, InspectType
from interpreter.cobol.emit_context import EmitContext, strip_cobol_literal
from interpreter.cobol.field_resolution import ResolvedFieldRef
from interpreter.cobol.lower_arithmetic import eval_ref_mod_expr
from interpreter.cobol.sectioned_layout import MaterialisedSectionedLayout
from interpreter.func_name import FuncName
from interpreter.instructions import Binop, CallFunction
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
    """STRING ... DELIMITED BY ... INTO target."""
    span = stmt.span
    part_regs: list[Register] = []
    for sending in stmt.sendings:
        # An intrinsic FUNCTION sending (e.g. FUNCTION TRIM(WS-VAR)) is evaluated
        # by the shared function-operand lowering so its computed string — not the
        # literal function name — is concatenated (red-dragon-zuhj).
        if sending.function is not None:
            from interpreter.cobol.lower_arithmetic import lower_function_operand

            func_reg = lower_function_operand(
                ctx, sending.function, materialised, span=span
            )
            part_regs.append(ctx.emit_to_string(func_reg, span=span))
            continue

        operand_name = sending.value.name
        if ctx.has_field(operand_name, materialised):
            # A sending operand's OF/IN qualifiers and subscripts must both be
            # passed on, exactly as _write_ref_mod_target does for the INTO
            # target. Dropping the qualifiers sends a name the program already
            # qualified to the layout bare, which raises
            # CobolAmbiguousReferenceError for any duplicated leaf name -- a legal
            # program rejected. Dropping the subscripts is quieter and worse: the
            # table's first element is read whatever index the program wrote, with
            # no error at all. The bridge serializes a sending through
            # serializeMoveOperand -> serializeRef, so both are in the JSON and
            # already parsed onto RefModOperand.
            source_ref, source_rr = ctx.resolve_field_ref(
                operand_name,
                materialised,
                sending.value.qualifiers,
                subscripts=sending.value.subscripts,
                span=span,
            )
            src_str_reg = ctx.emit_stored_characters(
                source_rr,
                source_ref.fl,
                source_ref.offset_reg,
                extent=source_ref.extent,
                span=span,
            )
        else:
            src_str_reg = ctx.const_to_reg(
                strip_cobol_literal(str(sending.value.name)), span=span
            )

        if sending.value.ref_mod_start is not None:
            raw_start_reg = eval_ref_mod_expr(
                ctx, sending.value.ref_mod_start, materialised, span=span
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
            if sending.value.ref_mod_length is not None:
                length_reg = eval_ref_mod_expr(
                    ctx, sending.value.ref_mod_length, materialised, span=span
                )
            else:
                length_reg = ctx.const_to_reg(9999, span=span)
            sliced_reg = ctx.fresh_reg()
            ctx.emit_inst(
                CallFunction(
                    result_reg=sliced_reg,
                    func_name=FuncName(BuiltinName.STRING_SLICE),
                    args=(src_str_reg, start_0indexed_reg, length_reg),
                ),
                span=span,
            )
            src_str_reg = sliced_reg

        if sending.delimited_by == DelimiterMode.SIZE:
            part_regs.append(src_str_reg)
        else:
            delim_reg = ctx.const_to_reg(
                strip_cobol_literal(
                    ctx.figuratives.translate(str(sending.delimited_by))
                ),
                span=span,
            )
            find_pos = ctx.fresh_reg()
            ctx.emit_inst(
                CallFunction(
                    result_reg=find_pos,
                    func_name=FuncName(BuiltinName.STRING_FIND),
                    args=(src_str_reg, delim_reg),
                ),
                span=span,
            )
            parts = ctx.fresh_reg()
            ctx.emit_inst(
                CallFunction(
                    result_reg=parts,
                    func_name=FuncName(BuiltinName.STRING_SPLIT),
                    args=(src_str_reg, delim_reg),
                ),
                span=span,
            )
            first_part = ctx.fresh_reg()
            zero_reg = ctx.const_to_reg(0, span=span)
            ctx.emit_inst(
                CallFunction(
                    result_reg=first_part,
                    func_name=FuncName(BuiltinName.LIST_GET),
                    args=(parts, zero_reg),
                ),
                span=span,
            )
            part_regs.append(first_part)

    if not part_regs:
        concat_reg = ctx.const_to_reg("", span=span)
    elif len(part_regs) == 1:
        concat_reg = part_regs[0]
    else:
        concat_reg = part_regs[0]
        for next_reg in part_regs[1:]:
            new_concat = ctx.fresh_reg()
            ctx.emit_inst(
                CallFunction(
                    result_reg=new_concat,
                    func_name=FuncName(BuiltinName.STRING_CONCAT_PAIR),
                    args=(concat_reg, next_reg),
                ),
                span=span,
            )
            concat_reg = new_concat

    if stmt.into.name and ctx.has_field(stmt.into.name, materialised):
        if stmt.into.ref_mod_start is not None:
            # INTO dest(start:length): splice into the sliced region only,
            # leaving the rest of the field untouched (red-dragon-2fxq).
            # WITH POINTER's own cursor-offset write is a distinct mechanism
            # for the same "where to write" question; combining both on one
            # statement is rare in practice and not modelled — ref-mod wins,
            # and the pointer clause (if also present) is not applied.
            if stmt.pointer:
                logger.warning(
                    "STRING INTO target %s has both reference modification "
                    "and WITH POINTER; using reference modification, "
                    "ignoring the pointer",
                    stmt.into.name,
                )
            _write_ref_mod_target(ctx, stmt.into, concat_reg, materialised, span=span)
            return
        target_ref, target_rr = ctx.resolve_field_ref(
            stmt.into.name,
            materialised,
            stmt.into.qualifiers,
            subscripts=stmt.into.subscripts,
            span=span,
        )
        if stmt.pointer and ctx.has_field(stmt.pointer, materialised):
            # WITH POINTER: read the cursor (1-based), write starting there
            # instead of at offset 0, then advance the cursor by the length of
            # what was just written (red-dragon-4q25.15).
            ptr_ref, ptr_rr = ctx.resolve_field_ref(
                stmt.pointer, materialised, span=span
            )
            ptr_decoded_reg = ctx.emit_decode_field(
                ptr_rr,
                ptr_ref.fl,
                ptr_ref.offset_reg,
                extent=ptr_ref.extent,
                span=span,
            )
            one_reg = ctx.const_to_reg(1, span=span)
            start_0indexed_reg = ctx.fresh_reg()
            ctx.emit_inst(
                Binop(
                    result_reg=start_0indexed_reg,
                    operator=resolve_binop("-"),
                    left=ptr_decoded_reg,
                    right=one_reg,
                ),
                span=span,
            )
            _splice_into_receiver(
                ctx, target_ref, target_rr, start_0indexed_reg, concat_reg, span=span
            )
            written_len_reg = ctx.fresh_reg()
            ctx.emit_inst(
                CallFunction(
                    result_reg=written_len_reg,
                    func_name=FuncName(BuiltinName.LENGTH),
                    args=(concat_reg,),
                ),
                span=span,
            )
            new_ptr_reg = ctx.fresh_reg()
            ctx.emit_inst(
                Binop(
                    result_reg=new_ptr_reg,
                    operator=resolve_binop("+"),
                    left=ptr_decoded_reg,
                    right=written_len_reg,
                ),
                span=span,
            )
            new_ptr_str_reg = ctx.emit_to_string(new_ptr_reg, span=span)
            ctx.emit_encode_and_write(
                ptr_rr,
                ptr_ref.fl,
                new_ptr_str_reg,
                ptr_ref.offset_reg,
                extent=ptr_ref.extent,
                span=span,
            )
        else:
            _splice_into_receiver(
                ctx,
                target_ref,
                target_rr,
                ctx.const_to_reg(0, span=span),
                concat_reg,
                span=span,
            )
    else:
        logger.warning("STRING INTO target %s not found in layout", stmt.into.name)


def _splice_into_receiver(
    ctx: EmitContext,
    target_ref: ResolvedFieldRef,
    target_rr: Register,
    start_reg: Register,
    value_reg: Register,
    *,
    span: SourceSpan | None,
) -> None:
    """Write value_reg into the receiver from 0-based start_reg, keeping every
    character it does not reach: STRING changes only what it transfers."""
    current_reg = ctx.emit_decode_field_characters(
        target_rr,
        target_ref.fl,
        target_ref.offset_reg,
        extent=target_ref.extent,
        span=span,
    )
    length_reg = ctx.fresh_reg()
    ctx.emit_inst(
        CallFunction(
            result_reg=length_reg,
            func_name=FuncName(BuiltinName.LENGTH),
            args=(value_reg,),
        ),
        span=span,
    )
    spliced_reg = ctx.fresh_reg()
    ctx.emit_inst(
        CallFunction(
            result_reg=spliced_reg,
            func_name=FuncName(BuiltinName.STRING_SPLICE),
            args=(current_reg, start_reg, length_reg, value_reg),
        ),
        span=span,
    )
    ctx.emit_encode_and_write(
        target_rr,
        target_ref.fl,
        spliced_reg,
        target_ref.offset_reg,
        extent=target_ref.extent,
        span=span,
    )


def _receiver_sizes(
    ctx: EmitContext,
    stmt: UnstringStatement,
    materialised: MaterialisedSectionedLayout,
) -> tuple[Register, ...]:
    """Each INTO receiver's size: without DELIMITED BY, what it takes from the source."""
    return tuple(
        ctx.const_to_reg(
            materialised.resolve(target.name, target.qualifiers)[0].byte_length,
            span=stmt.span,
        )
        for target in stmt.into
        if ctx.has_field(target.name, materialised)
    )


def lower_unstring(
    ctx: EmitContext,
    stmt: UnstringStatement,
    materialised: MaterialisedSectionedLayout,
) -> None:
    """UNSTRING source DELIMITED BY ... INTO targets."""
    span = stmt.span
    source_name = stmt.source.name
    if ctx.has_field(source_name, materialised):
        source_ref, source_rr = ctx.resolve_field_ref(
            source_name, materialised, span=span
        )
        src_str_reg = ctx.emit_decode_field_characters(
            source_rr,
            source_ref.fl,
            source_ref.offset_reg,
            extent=source_ref.extent,
            span=span,
        )
    else:
        src_str_reg = ctx.const_to_reg(
            strip_cobol_literal(str(stmt.source.name)), span=span
        )

    if stmt.source.ref_mod_start is not None:
        raw_start_reg = eval_ref_mod_expr(
            ctx, stmt.source.ref_mod_start, materialised, span=span
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
        if stmt.source.ref_mod_length is not None:
            length_reg = eval_ref_mod_expr(
                ctx, stmt.source.ref_mod_length, materialised, span=span
            )
        else:
            length_reg = ctx.const_to_reg(9999, span=span)
        sliced_reg = ctx.fresh_reg()
        ctx.emit_inst(
            CallFunction(
                result_reg=sliced_reg,
                func_name=FuncName(BuiltinName.STRING_SLICE),
                args=(src_str_reg, start_0indexed_reg, length_reg),
            ),
            span=span,
        )
        src_str_reg = sliced_reg

    if stmt.pointer and ctx.has_field(stmt.pointer, materialised):
        # WITH POINTER: the scan begins at the pointer's current 1-based
        # position, not offset 0 — narrows src_str_reg the same way ref-mod
        # slicing does above, so the split (and later the consumed-length
        # calc, which operates on this same sliced string) both scan from
        # the cursor onward, not from the start of the field
        # (red-dragon-4q25.15). The pointer-advance block further down
        # re-resolves/re-decodes this same field independently rather than
        # threading state out of this block — cheap since nothing writes to
        # it in between, and keeps each block independently readable (the
        # same tradeoff already made for WITH POINTER's own part-length
        # recomputation above).
        ptr_ref, ptr_rr = ctx.resolve_field_ref(stmt.pointer, materialised, span=span)
        ptr_decoded_reg = ctx.emit_decode_field(
            ptr_rr, ptr_ref.fl, ptr_ref.offset_reg, extent=ptr_ref.extent, span=span
        )
        one_reg = ctx.const_to_reg(1, span=span)
        ptr_start_0indexed_reg = ctx.fresh_reg()
        ctx.emit_inst(
            Binop(
                result_reg=ptr_start_0indexed_reg,
                operator=resolve_binop("-"),
                left=ptr_decoded_reg,
                right=one_reg,
            ),
            span=span,
        )
        rest_len_reg = ctx.const_to_reg(9999, span=span)
        ptr_sliced_reg = ctx.fresh_reg()
        ctx.emit_inst(
            CallFunction(
                result_reg=ptr_sliced_reg,
                func_name=FuncName(BuiltinName.STRING_SLICE),
                args=(src_str_reg, ptr_start_0indexed_reg, rest_len_reg),
            ),
            span=span,
        )
        src_str_reg = ptr_sliced_reg

    # One or more candidate delimiters (DELIMITED BY x OR y OR z): each is
    # known statically at lowering time (literal COBOL text), so each becomes
    # its own constant register; MULTI_DELIMITER_SPLIT does the correct
    # repeated-nearest-match scan across all of them at runtime — a single
    # delimiter is just the N=1 case of the same builtin (red-dragon-4q25.12).
    delim_regs = tuple(
        ctx.const_to_reg(
            strip_cobol_literal(ctx.figuratives.translate(str(d))), span=span
        )
        for d in stmt.delimiters
    )
    parts_reg = ctx.fresh_reg()
    ctx.emit_inst(
        (
            CallFunction(
                result_reg=parts_reg,
                func_name=FuncName(BuiltinName.MULTI_DELIMITER_SPLIT),
                args=(src_str_reg, *delim_regs),
            )
            if delim_regs
            else CallFunction(
                result_reg=parts_reg,
                func_name=FuncName(BuiltinName.UNSTRING_BY_SIZE),
                args=(src_str_reg, *_receiver_sizes(ctx, stmt, materialised)),
            )
        ),
        span=span,
    )

    for i, target_operand in enumerate(stmt.into):
        if not ctx.has_field(target_operand.name, materialised):
            logger.warning(
                "UNSTRING INTO target %s not found in layout", target_operand.name
            )
            continue
        idx_reg = ctx.const_to_reg(i, span=span)
        part_reg = ctx.fresh_reg()
        ctx.emit_inst(
            CallFunction(
                result_reg=part_reg,
                func_name=FuncName(BuiltinName.LIST_GET),
                args=(parts_reg, idx_reg),
            ),
            span=span,
        )
        # INTO dest(start:length) splices into the sliced region only,
        # leaving the rest of the field untouched (red-dragon-2fxq); a bare
        # target writes the whole field, as before.
        _write_ref_mod_target(ctx, target_operand, part_reg, materialised, span=span)

    if stmt.pointer and ctx.has_field(stmt.pointer, materialised):
        # WITH POINTER: advance the cursor past however much of the source
        # was actually consumed by the split (delimiter included), via the
        # same repeated-nearest-match scan MULTI_DELIMITER_SPLIT already
        # performs — not an assumed fixed delimiter width (red-dragon-4q25.15).
        # delim_regs is already in scope from the MULTI_DELIMITER_SPLIT call
        # earlier in this same function (Task 2).
        ptr_ref, ptr_rr = ctx.resolve_field_ref(stmt.pointer, materialised, span=span)
        ptr_decoded_reg = ctx.emit_decode_field(
            ptr_rr, ptr_ref.fl, ptr_ref.offset_reg, extent=ptr_ref.extent, span=span
        )
        target_count_reg = ctx.const_to_reg(len(stmt.into), span=span)
        consumed_len_reg = ctx.fresh_reg()
        ctx.emit_inst(
            CallFunction(
                result_reg=consumed_len_reg,
                func_name=FuncName(BuiltinName.MULTI_DELIMITER_CONSUMED_LENGTH),
                args=(src_str_reg, target_count_reg, *delim_regs),
            ),
            span=span,
        )
        new_ptr_reg = ctx.fresh_reg()
        ctx.emit_inst(
            Binop(
                result_reg=new_ptr_reg,
                operator=resolve_binop("+"),
                left=ptr_decoded_reg,
                right=consumed_len_reg,
            ),
            span=span,
        )
        new_ptr_str_reg = ctx.emit_to_string(new_ptr_reg, span=span)
        ctx.emit_encode_and_write(
            ptr_rr,
            ptr_ref.fl,
            new_ptr_str_reg,
            ptr_ref.offset_reg,
            extent=ptr_ref.extent,
            span=span,
        )

    if stmt.tallying_target and ctx.has_field(stmt.tallying_target, materialised):
        tally_ref, tally_rr = ctx.resolve_field_ref(
            stmt.tallying_target, materialised, span=span
        )
        # Real UNSTRING TALLYING IN semantics (IBM Enterprise COBOL Language
        # Reference): the counter ACCUMULATES — final value = initial value +
        # number of receiving areas actually populated, capped at len(into)
        # when there are more delimited substrings than INTO targets.
        len_reg = ctx.fresh_reg()
        ctx.emit_inst(
            CallFunction(
                result_reg=len_reg,
                func_name=FuncName(BuiltinName.LIST_LEN),
                args=(parts_reg,),
            ),
            span=span,
        )
        into_count_reg = ctx.const_to_reg(len(stmt.into), span=span)
        populated_count_reg = ctx.fresh_reg()
        ctx.emit_inst(
            CallFunction(
                result_reg=populated_count_reg,
                func_name=FuncName(BuiltinName.MIN),
                args=(len_reg, into_count_reg),
            ),
            span=span,
        )
        existing_decoded_reg = ctx.emit_decode_field(
            tally_rr,
            tally_ref.fl,
            tally_ref.offset_reg,
            extent=tally_ref.extent,
            span=span,
        )
        new_total_reg = ctx.fresh_reg()
        ctx.emit_inst(
            Binop(
                result_reg=new_total_reg,
                operator=resolve_binop("+"),
                left=existing_decoded_reg,
                right=populated_count_reg,
            ),
            span=span,
        )
        count_str_reg = ctx.emit_to_string(new_total_reg, span=span)
        ctx.emit_encode_and_write(
            tally_rr,
            tally_ref.fl,
            count_str_reg,
            tally_ref.offset_reg,
            extent=tally_ref.extent,
            span=span,
        )


def lower_inspect(
    ctx: EmitContext,
    stmt: InspectStatement,
    materialised: MaterialisedSectionedLayout,
) -> None:
    """INSPECT source TALLYING | REPLACING | TALLYING ... REPLACING | CONVERTING.

    The source, its subscripts and reference modification, and every operand
    are evaluated once; one builtin then runs the standard's single
    left-to-right scan (interpreter.cobol.inspect_scan). TALLYING ...
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
    span = stmt.span
    if stmt.inspect_type == InspectType.CONVERTING:
        return _call(
            ctx,
            BuiltinName.COBOL_INSPECT_CONVERT,
            (
                inspected_reg,
                *(
                    _resolve_inspect_operand(ctx, operand, materialised, span=span)
                    for operand in (
                        stmt.converting_from,
                        stmt.converting_to,
                        stmt.converting_after,
                        stmt.converting_before,
                    )
                ),
            ),
            span=span,
        )
    if not stmt.replacings:
        return NO_REGISTER
    phrase_args = tuple(
        arg
        for replacing in stmt.replacings
        for arg in _phrase_args(
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
            span=span,
        )
    )
    return _call(
        ctx, BuiltinName.COBOL_INSPECT_REPLACE, (inspected_reg, *phrase_args), span=span
    )


def _phrase_args(
    ctx: EmitContext,
    mode: str,
    operands: tuple[RefModOperand, RefModOperand, RefModOperand, RefModOperand],
    counter: int,
    materialised: MaterialisedSectionedLayout,
    *,
    span: SourceSpan | None,
) -> tuple[Register, ...]:
    """One phrase as the builtins take it: mode, pattern, BY value, AFTER
    operand, BEFORE operand (empty when absent) and counter number."""
    return (
        ctx.const_to_reg(mode, span=span),
        *(
            _resolve_inspect_operand(ctx, operand, materialised, span=span)
            for operand in operands
        ),
        ctx.const_to_reg(counter, span=span),
    )


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
    phrase_args = tuple(
        arg
        for counter, group in enumerate(stmt.tallying_groups)
        for tally_for in group.patterns
        for arg in _phrase_args(
            ctx,
            tally_for.mode,
            (tally_for.pattern, _NO_OPERAND, tally_for.after, tally_for.before),
            counter,
            materialised,
            span=span,
        )
    )
    counts_reg = _call(
        ctx,
        BuiltinName.COBOL_INSPECT_TALLY,
        (
            inspected_reg,
            ctx.const_to_reg(len(stmt.tallying_groups), span=span),
            *phrase_args,
        ),
        span=span,
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
