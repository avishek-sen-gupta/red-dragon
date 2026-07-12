"""STRING, UNSTRING, INSPECT statement lowering."""

from __future__ import annotations

import logging

from interpreter.cobol.cobol_constants import BuiltinName, DelimiterMode, InspectType
from interpreter.cobol.cobol_statements import (
    BeforeAfterBoundary,
    InspectStatement,
    StringStatement,
    UnstringStatement,
)
from interpreter.cobol.data_layout import FieldLayout
from interpreter.cobol.emit_context import EmitContext, strip_cobol_literal
from interpreter.cobol.figurative_constants import translate_cobol_figurative
from interpreter.cobol.ir_encoders import (
    build_inspect_replace_ir,
    build_inspect_tally_ir,
)
from interpreter.cobol.lower_arithmetic import eval_ref_mod_expr
from interpreter.cobol.ref_mod import RefModOperand
from interpreter.cobol.sectioned_layout import MaterialisedSectionedLayout
from interpreter.func_name import FuncName
from interpreter.instructions import Binop, CallFunction
from interpreter.operator_kind import resolve_binop
from interpreter.register import NO_REGISTER, Register

logger = logging.getLogger(__name__)


def _write_ref_mod_target(
    ctx: EmitContext,
    target: RefModOperand,
    value_reg: Register,
    materialised: MaterialisedSectionedLayout,
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
        target.name, materialised, target.qualifiers, subscripts=target.subscripts
    )
    target_value_reg = value_reg
    if target.ref_mod_start is not None:
        target_decoded = ctx.emit_decode_field(
            target_rr, target_ref.fl, target_ref.offset_reg
        )
        target_str_reg = ctx.emit_to_string(target_decoded)
        tgt_start_reg = eval_ref_mod_expr(ctx, target.ref_mod_start, materialised)
        one_reg = ctx.const_to_reg(1)
        tgt_start_0indexed_reg = ctx.fresh_reg()
        ctx.emit_inst(
            Binop(
                result_reg=tgt_start_0indexed_reg,
                operator=resolve_binop("-"),
                left=tgt_start_reg,
                right=one_reg,
            )
        )
        if target.ref_mod_length is not None:
            tgt_length_reg = eval_ref_mod_expr(ctx, target.ref_mod_length, materialised)
        else:
            tgt_length_reg = ctx.const_to_reg(999999)
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
            )
        )
        target_value_reg = spliced_reg
    ctx.emit_encode_and_write(
        target_rr, target_ref.fl, target_value_reg, target_ref.offset_reg
    )


def lower_string(
    ctx: EmitContext,
    stmt: StringStatement,
    materialised: MaterialisedSectionedLayout,
) -> None:
    """STRING ... DELIMITED BY ... INTO target."""
    part_regs: list[Register] = []
    for sending in stmt.sendings:
        # An intrinsic FUNCTION sending (e.g. FUNCTION TRIM(WS-VAR)) is evaluated
        # by the shared function-operand lowering so its computed string — not the
        # literal function name — is concatenated (red-dragon-zuhj).
        if sending.function is not None:
            from interpreter.cobol.lower_arithmetic import lower_function_operand

            func_reg = lower_function_operand(ctx, sending.function, materialised)
            part_regs.append(ctx.emit_to_string(func_reg))
            continue

        operand_name = sending.value.name
        if ctx.has_field(operand_name, materialised):
            source_ref, source_rr = ctx.resolve_field_ref(operand_name, materialised)
            decoded_reg = ctx.emit_decode_field(
                source_rr, source_ref.fl, source_ref.offset_reg
            )
            src_str_reg = ctx.emit_to_string(decoded_reg)
        else:
            src_str_reg = ctx.const_to_reg(strip_cobol_literal(str(sending.value.name)))

        if sending.value.ref_mod_start is not None:
            raw_start_reg = eval_ref_mod_expr(
                ctx, sending.value.ref_mod_start, materialised
            )
            one_reg = ctx.const_to_reg(1)
            start_0indexed_reg = ctx.fresh_reg()
            ctx.emit_inst(
                Binop(
                    result_reg=start_0indexed_reg,
                    operator=resolve_binop("-"),
                    left=raw_start_reg,
                    right=one_reg,
                )
            )
            if sending.value.ref_mod_length is not None:
                length_reg = eval_ref_mod_expr(
                    ctx, sending.value.ref_mod_length, materialised
                )
            else:
                length_reg = ctx.const_to_reg(9999)
            sliced_reg = ctx.fresh_reg()
            ctx.emit_inst(
                CallFunction(
                    result_reg=sliced_reg,
                    func_name=FuncName(BuiltinName.STRING_SLICE),
                    args=(src_str_reg, start_0indexed_reg, length_reg),
                )
            )
            src_str_reg = sliced_reg

        if sending.delimited_by == DelimiterMode.SIZE:
            part_regs.append(src_str_reg)
        else:
            delim_reg = ctx.const_to_reg(
                strip_cobol_literal(
                    translate_cobol_figurative(str(sending.delimited_by))
                )
            )
            find_pos = ctx.fresh_reg()
            ctx.emit_inst(
                CallFunction(
                    result_reg=find_pos,
                    func_name=FuncName(BuiltinName.STRING_FIND),
                    args=(src_str_reg, delim_reg),
                ),
            )
            parts = ctx.fresh_reg()
            ctx.emit_inst(
                CallFunction(
                    result_reg=parts,
                    func_name=FuncName(BuiltinName.STRING_SPLIT),
                    args=(src_str_reg, delim_reg),
                ),
            )
            first_part = ctx.fresh_reg()
            zero_reg = ctx.const_to_reg(0)
            ctx.emit_inst(
                CallFunction(
                    result_reg=first_part,
                    func_name=FuncName(BuiltinName.LIST_GET),
                    args=(parts, zero_reg),
                ),
            )
            part_regs.append(first_part)

    if not part_regs:
        concat_reg = ctx.const_to_reg("")
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
            _write_ref_mod_target(ctx, stmt.into, concat_reg, materialised)
            return
        target_ref, target_rr = ctx.resolve_field_ref(stmt.into.name, materialised)
        if stmt.pointer and ctx.has_field(stmt.pointer, materialised):
            # WITH POINTER: read the cursor (1-based), write starting there
            # instead of at offset 0, then advance the cursor by the length of
            # what was just written (red-dragon-4q25.15).
            ptr_ref, ptr_rr = ctx.resolve_field_ref(stmt.pointer, materialised)
            ptr_decoded_reg = ctx.emit_decode_field(
                ptr_rr, ptr_ref.fl, ptr_ref.offset_reg
            )
            one_reg = ctx.const_to_reg(1)
            start_0indexed_reg = ctx.fresh_reg()
            ctx.emit_inst(
                Binop(
                    result_reg=start_0indexed_reg,
                    operator=resolve_binop("-"),
                    left=ptr_decoded_reg,
                    right=one_reg,
                )
            )
            write_offset_reg = ctx.fresh_reg()
            ctx.emit_inst(
                Binop(
                    result_reg=write_offset_reg,
                    operator=resolve_binop("+"),
                    left=ctx.const_to_reg(target_ref.fl.offset),
                    right=start_0indexed_reg,
                )
            )
            ctx.emit_encode_and_write(
                target_rr, target_ref.fl, concat_reg, write_offset_reg
            )
            written_len_reg = ctx.fresh_reg()
            ctx.emit_inst(
                CallFunction(
                    result_reg=written_len_reg,
                    func_name=FuncName(BuiltinName.LENGTH),
                    args=(concat_reg,),
                ),
            )
            new_ptr_reg = ctx.fresh_reg()
            ctx.emit_inst(
                Binop(
                    result_reg=new_ptr_reg,
                    operator=resolve_binop("+"),
                    left=ptr_decoded_reg,
                    right=written_len_reg,
                )
            )
            new_ptr_str_reg = ctx.emit_to_string(new_ptr_reg)
            ctx.emit_encode_and_write(
                ptr_rr, ptr_ref.fl, new_ptr_str_reg, ptr_ref.offset_reg
            )
        else:
            ctx.emit_encode_and_write(
                target_rr, target_ref.fl, concat_reg, target_ref.offset_reg
            )
    else:
        logger.warning("STRING INTO target %s not found in layout", stmt.into.name)


def lower_unstring(
    ctx: EmitContext,
    stmt: UnstringStatement,
    materialised: MaterialisedSectionedLayout,
) -> None:
    """UNSTRING source DELIMITED BY ... INTO targets."""
    source_name = stmt.source.name
    if ctx.has_field(source_name, materialised):
        source_ref, source_rr = ctx.resolve_field_ref(source_name, materialised)
        decoded_reg = ctx.emit_decode_field(
            source_rr, source_ref.fl, source_ref.offset_reg
        )
        src_str_reg = ctx.emit_to_string(decoded_reg)
    else:
        src_str_reg = ctx.const_to_reg(strip_cobol_literal(str(stmt.source.name)))

    if stmt.source.ref_mod_start is not None:
        raw_start_reg = eval_ref_mod_expr(ctx, stmt.source.ref_mod_start, materialised)
        one_reg = ctx.const_to_reg(1)
        start_0indexed_reg = ctx.fresh_reg()
        ctx.emit_inst(
            Binop(
                result_reg=start_0indexed_reg,
                operator=resolve_binop("-"),
                left=raw_start_reg,
                right=one_reg,
            )
        )
        if stmt.source.ref_mod_length is not None:
            length_reg = eval_ref_mod_expr(
                ctx, stmt.source.ref_mod_length, materialised
            )
        else:
            length_reg = ctx.const_to_reg(9999)
        sliced_reg = ctx.fresh_reg()
        ctx.emit_inst(
            CallFunction(
                result_reg=sliced_reg,
                func_name=FuncName(BuiltinName.STRING_SLICE),
                args=(src_str_reg, start_0indexed_reg, length_reg),
            )
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
        ptr_ref, ptr_rr = ctx.resolve_field_ref(stmt.pointer, materialised)
        ptr_decoded_reg = ctx.emit_decode_field(ptr_rr, ptr_ref.fl, ptr_ref.offset_reg)
        one_reg = ctx.const_to_reg(1)
        ptr_start_0indexed_reg = ctx.fresh_reg()
        ctx.emit_inst(
            Binop(
                result_reg=ptr_start_0indexed_reg,
                operator=resolve_binop("-"),
                left=ptr_decoded_reg,
                right=one_reg,
            )
        )
        rest_len_reg = ctx.const_to_reg(9999)
        ptr_sliced_reg = ctx.fresh_reg()
        ctx.emit_inst(
            CallFunction(
                result_reg=ptr_sliced_reg,
                func_name=FuncName(BuiltinName.STRING_SLICE),
                args=(src_str_reg, ptr_start_0indexed_reg, rest_len_reg),
            )
        )
        src_str_reg = ptr_sliced_reg

    # One or more candidate delimiters (DELIMITED BY x OR y OR z): each is
    # known statically at lowering time (literal COBOL text), so each becomes
    # its own constant register; MULTI_DELIMITER_SPLIT does the correct
    # repeated-nearest-match scan across all of them at runtime — a single
    # delimiter is just the N=1 case of the same builtin (red-dragon-4q25.12).
    delim_regs = tuple(
        ctx.const_to_reg(strip_cobol_literal(translate_cobol_figurative(str(d))))
        for d in stmt.delimiters
    )
    parts_reg = ctx.fresh_reg()
    ctx.emit_inst(
        CallFunction(
            result_reg=parts_reg,
            func_name=FuncName(BuiltinName.MULTI_DELIMITER_SPLIT),
            args=(src_str_reg,) + delim_regs,
        ),
    )

    for i, target_operand in enumerate(stmt.into):
        if not ctx.has_field(target_operand.name, materialised):
            logger.warning(
                "UNSTRING INTO target %s not found in layout", target_operand.name
            )
            continue
        idx_reg = ctx.const_to_reg(i)
        part_reg = ctx.fresh_reg()
        ctx.emit_inst(
            CallFunction(
                result_reg=part_reg,
                func_name=FuncName(BuiltinName.LIST_GET),
                args=(parts_reg, idx_reg),
            ),
        )
        # INTO dest(start:length) splices into the sliced region only,
        # leaving the rest of the field untouched (red-dragon-2fxq); a bare
        # target writes the whole field, as before.
        _write_ref_mod_target(ctx, target_operand, part_reg, materialised)

    if stmt.pointer and ctx.has_field(stmt.pointer, materialised):
        # WITH POINTER: advance the cursor past however much of the source
        # was actually consumed by the split (delimiter included), via the
        # same repeated-nearest-match scan MULTI_DELIMITER_SPLIT already
        # performs — not an assumed fixed delimiter width (red-dragon-4q25.15).
        # delim_regs is already in scope from the MULTI_DELIMITER_SPLIT call
        # earlier in this same function (Task 2).
        ptr_ref, ptr_rr = ctx.resolve_field_ref(stmt.pointer, materialised)
        ptr_decoded_reg = ctx.emit_decode_field(ptr_rr, ptr_ref.fl, ptr_ref.offset_reg)
        target_count_reg = ctx.const_to_reg(len(stmt.into))
        consumed_len_reg = ctx.fresh_reg()
        ctx.emit_inst(
            CallFunction(
                result_reg=consumed_len_reg,
                func_name=FuncName(BuiltinName.MULTI_DELIMITER_CONSUMED_LENGTH),
                args=(src_str_reg, target_count_reg) + delim_regs,
            ),
        )
        new_ptr_reg = ctx.fresh_reg()
        ctx.emit_inst(
            Binop(
                result_reg=new_ptr_reg,
                operator=resolve_binop("+"),
                left=ptr_decoded_reg,
                right=consumed_len_reg,
            )
        )
        new_ptr_str_reg = ctx.emit_to_string(new_ptr_reg)
        ctx.emit_encode_and_write(
            ptr_rr, ptr_ref.fl, new_ptr_str_reg, ptr_ref.offset_reg
        )

    if stmt.tallying_target and ctx.has_field(stmt.tallying_target, materialised):
        tally_ref, tally_rr = ctx.resolve_field_ref(stmt.tallying_target, materialised)
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
        )
        into_count_reg = ctx.const_to_reg(len(stmt.into))
        populated_count_reg = ctx.fresh_reg()
        ctx.emit_inst(
            CallFunction(
                result_reg=populated_count_reg,
                func_name=FuncName(BuiltinName.MIN),
                args=(len_reg, into_count_reg),
            ),
        )
        existing_decoded_reg = ctx.emit_decode_field(
            tally_rr, tally_ref.fl, tally_ref.offset_reg
        )
        new_total_reg = ctx.fresh_reg()
        ctx.emit_inst(
            Binop(
                result_reg=new_total_reg,
                operator=resolve_binop("+"),
                left=existing_decoded_reg,
                right=populated_count_reg,
            ),
        )
        count_str_reg = ctx.emit_to_string(new_total_reg)
        ctx.emit_encode_and_write(
            tally_rr, tally_ref.fl, count_str_reg, tally_ref.offset_reg
        )


def lower_inspect(
    ctx: EmitContext,
    stmt: InspectStatement,
    materialised: MaterialisedSectionedLayout,
) -> None:
    """INSPECT source TALLYING|REPLACING ..."""
    if not ctx.has_field(stmt.source.name, materialised):
        logger.warning("INSPECT source %s not found in layout", stmt.source.name)
        return
    source_ref, source_rr = ctx.resolve_field_ref(stmt.source.name, materialised)
    source_fl = source_ref.fl
    decoded_reg = ctx.emit_decode_field(source_rr, source_fl, source_ref.offset_reg)
    src_str_reg = ctx.emit_to_string(decoded_reg)

    if stmt.source.ref_mod_start is not None:
        raw_start_reg = eval_ref_mod_expr(ctx, stmt.source.ref_mod_start, materialised)
        one_reg = ctx.const_to_reg(1)
        start_0indexed_reg = ctx.fresh_reg()
        ctx.emit_inst(
            Binop(
                result_reg=start_0indexed_reg,
                operator=resolve_binop("-"),
                left=raw_start_reg,
                right=one_reg,
            )
        )
        if stmt.source.ref_mod_length is not None:
            length_reg = eval_ref_mod_expr(
                ctx, stmt.source.ref_mod_length, materialised
            )
        else:
            length_reg = ctx.const_to_reg(9999)
        sliced_reg = ctx.fresh_reg()
        ctx.emit_inst(
            CallFunction(
                result_reg=sliced_reg,
                func_name=FuncName(BuiltinName.STRING_SLICE),
                args=(src_str_reg, start_0indexed_reg, length_reg),
            )
        )
        src_str_reg = sliced_reg

    if stmt.inspect_type == InspectType.TALLYING:
        lower_inspect_tallying(ctx, stmt, src_str_reg, materialised)
    elif stmt.inspect_type == InspectType.REPLACING:
        lower_inspect_replacing(ctx, stmt, src_str_reg, source_fl, materialised)
    elif stmt.inspect_type == InspectType.CONVERTING:
        lower_inspect_converting(ctx, stmt, src_str_reg, source_fl, materialised)


def _resolve_convert_operand(
    ctx: EmitContext,
    operand: str,
    materialised: MaterialisedSectionedLayout,
) -> Register:
    """Resolve a CONVERTING from/to operand: a data-item name is decoded at
    runtime; otherwise it is a figurative / quoted-literal constant."""
    if ctx.has_field(operand, materialised):
        ref, rr = ctx.resolve_field_ref(operand, materialised)
        decoded = ctx.emit_decode_field(rr, ref.fl, ref.offset_reg)
        return ctx.emit_to_string(decoded)
    if operand in ("SPACES", "SPACE", "ZEROS", "ZEROES", "ZERO", "LOW-VALUES"):
        return ctx.const_to_reg(translate_cobol_figurative(operand))
    return ctx.const_to_reg(strip_cobol_literal(str(operand)))


def lower_inspect_converting(
    ctx: EmitContext,
    stmt: InspectStatement,
    src_str_reg: Register,
    source_fl: FieldLayout,
    materialised: MaterialisedSectionedLayout,
) -> None:
    """INSPECT source CONVERTING <from> TO <to>: positional character translate.

    Builds the converted string via the STRING_CONVERT builtin and writes it back
    to the source field (red-dragon-zuhj — unblocks CardDemo's alphabetic edits).
    """
    from_reg = _resolve_convert_operand(ctx, str(stmt.converting_from), materialised)
    to_reg = _resolve_convert_operand(ctx, str(stmt.converting_to), materialised)
    converted_reg = ctx.fresh_reg()
    ctx.emit_inst(
        CallFunction(
            result_reg=converted_reg,
            func_name=FuncName(BuiltinName.STRING_CONVERT),
            args=(src_str_reg, from_reg, to_reg),
        )
    )
    if ctx.has_field(stmt.source.name, materialised):
        _, source_rr = ctx.resolve_field_ref(stmt.source.name, materialised)
        ctx.emit_encode_and_write(source_rr, source_fl, converted_reg)
    else:
        logger.warning(
            "INSPECT CONVERTING: source field %s not found in materialised layout;"
            " skipping write-back",
            stmt.source.name,
        )


def lower_inspect_tallying(
    ctx: EmitContext,
    stmt: InspectStatement,
    src_str_reg: Register,
    materialised: MaterialisedSectionedLayout,
) -> None:
    """INSPECT TALLYING — count pattern occurrences per independent target.

    Each TallyingGroup gets its own accumulator and its own write-back, so
    ``INSPECT src TALLYING cnt1 FOR ALL 'A' cnt2 FOR ALL 'B'`` updates both
    counters independently in one statement (red-dragon-4q25.17).
    """
    for group in stmt.tallying_groups:
        has_target = bool(group.target) and ctx.has_field(group.target, materialised)
        if has_target:
            # Real INSPECT TALLYING semantics (IBM Enterprise COBOL Language
            # Reference): the counter ACCUMULATES into its existing value
            # across separate statement executions — it is not reset to zero
            # each time (red-dragon-pvxc).
            tally_ref, tally_rr = ctx.resolve_field_ref(group.target, materialised)
            total_count_reg = ctx.emit_decode_field(
                tally_rr, tally_ref.fl, tally_ref.offset_reg
            )
        else:
            total_count_reg = ctx.const_to_reg(0)
        for tally_for in group.patterns:
            bounded_str_reg = src_str_reg
            if isinstance(tally_for.boundary, BeforeAfterBoundary):
                boundary_text_reg = ctx.const_to_reg(
                    strip_cobol_literal(str(tally_for.boundary.boundary_text))
                )
                kind_reg = ctx.const_to_reg(tally_for.boundary.kind.lower())
                bounded_str_reg = ctx.fresh_reg()
                ctx.emit_inst(
                    CallFunction(
                        result_reg=bounded_str_reg,
                        func_name=FuncName(BuiltinName.STRING_BOUNDARY_SLICE),
                        args=(src_str_reg, boundary_text_reg, kind_reg),
                    ),
                )
            pattern_reg = ctx.const_to_reg(strip_cobol_literal(str(tally_for.pattern)))
            mode_reg = ctx.const_to_reg(tally_for.mode.lower())
            ir = build_inspect_tally_ir(f"inspect_tally_{stmt.source}")
            count_reg = ctx.inline_ir(
                ir,
                {
                    "%p_source": bounded_str_reg,
                    "%p_pattern": pattern_reg,
                    "%p_mode": mode_reg,
                },
            )
            new_total = ctx.fresh_reg()
            ctx.emit_inst(
                Binop(
                    result_reg=new_total,
                    operator=resolve_binop("+"),
                    left=total_count_reg,
                    right=count_reg,
                ),
            )
            total_count_reg = new_total

        if has_target:
            tally_ref, tally_rr = ctx.resolve_field_ref(group.target, materialised)
            count_str_reg = ctx.emit_to_string(total_count_reg)
            ctx.emit_encode_and_write(
                tally_rr, tally_ref.fl, count_str_reg, tally_ref.offset_reg
            )


def lower_inspect_replacing(
    ctx: EmitContext,
    stmt: InspectStatement,
    src_str_reg: Register,
    source_fl: FieldLayout,
    materialised: MaterialisedSectionedLayout,
) -> None:
    """INSPECT REPLACING — apply replacements and write back."""
    current_str_reg: Register = src_str_reg

    for replacing in stmt.replacings:
        remainder_reg: Register = NO_REGISTER
        if isinstance(replacing.boundary, BeforeAfterBoundary):
            boundary_text_reg = ctx.const_to_reg(
                strip_cobol_literal(str(replacing.boundary.boundary_text))
            )
            kind_reg = ctx.const_to_reg(replacing.boundary.kind.lower())
            split_reg = ctx.fresh_reg()
            ctx.emit_inst(
                CallFunction(
                    result_reg=split_reg,
                    func_name=FuncName(BuiltinName.STRING_BOUNDARY_SPLIT),
                    args=(current_str_reg, boundary_text_reg, kind_reg),
                ),
            )
            zero_reg = ctx.const_to_reg(0)
            one_reg = ctx.const_to_reg(1)
            bounded_str_reg = ctx.fresh_reg()
            ctx.emit_inst(
                CallFunction(
                    result_reg=bounded_str_reg,
                    func_name=FuncName(BuiltinName.LIST_GET),
                    args=(split_reg, zero_reg),
                ),
            )
            remainder_reg = ctx.fresh_reg()
            ctx.emit_inst(
                CallFunction(
                    result_reg=remainder_reg,
                    func_name=FuncName(BuiltinName.LIST_GET),
                    args=(split_reg, one_reg),
                ),
            )
        else:
            bounded_str_reg = current_str_reg

        from_reg = ctx.const_to_reg(strip_cobol_literal(str(replacing.from_pattern)))
        to_reg = ctx.const_to_reg(strip_cobol_literal(str(replacing.to_pattern)))
        mode_reg = ctx.const_to_reg(replacing.mode.lower())
        ir = build_inspect_replace_ir(f"inspect_replace_{stmt.source}")
        replaced_bounded_reg = ctx.inline_ir(
            ir,
            {
                "%p_source": bounded_str_reg,
                "%p_from": from_reg,
                "%p_to": to_reg,
                "%p_mode": mode_reg,
            },
        )

        if remainder_reg.is_present():
            spliced_reg = ctx.fresh_reg()
            # BEFORE: replaced prefix + untouched remainder (boundary onward).
            # AFTER: untouched remainder (up to and including boundary) + replaced suffix.
            args = (
                (replaced_bounded_reg, remainder_reg)
                if replacing.boundary.kind == "BEFORE"
                else (remainder_reg, replaced_bounded_reg)
            )
            ctx.emit_inst(
                CallFunction(
                    result_reg=spliced_reg,
                    func_name=FuncName(BuiltinName.STRING_CONCAT_PAIR),
                    args=args,
                ),
            )
            current_str_reg = spliced_reg
        else:
            current_str_reg = replaced_bounded_reg

    # Resolve the source region register for the write-back
    if ctx.has_field(stmt.source.name, materialised):
        _, source_rr = ctx.resolve_field_ref(stmt.source.name, materialised)
        ctx.emit_encode_and_write(source_rr, source_fl, current_str_reg)
    else:
        # Fallback: source_fl carries offset; need a region register — skip write
        logger.warning(
            "INSPECT REPLACING: source field %s not found in materialised layout; skipping write-back",
            stmt.source.name,
        )
