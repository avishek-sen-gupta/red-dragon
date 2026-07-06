"""STRING, UNSTRING, INSPECT statement lowering."""

from __future__ import annotations

import logging

from interpreter.cobol.cobol_constants import BuiltinName, DelimiterMode, InspectType
from interpreter.cobol.cobol_statements import (
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
from interpreter.cobol.sectioned_layout import MaterialisedSectionedLayout
from interpreter.operator_kind import resolve_binop
from interpreter.func_name import FuncName
from interpreter.instructions import Binop, CallFunction
from interpreter.register import Register

logger = logging.getLogger(__name__)


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

    if stmt.into and ctx.has_field(stmt.into, materialised):
        target_ref, target_rr = ctx.resolve_field_ref(stmt.into, materialised)
        ctx.emit_encode_and_write(
            target_rr, target_ref.fl, concat_reg, target_ref.offset_reg
        )
    else:
        logger.warning("STRING INTO target %s not found in layout", stmt.into)


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

    for i, target_name in enumerate(stmt.into):
        if not ctx.has_field(target_name, materialised):
            logger.warning("UNSTRING INTO target %s not found in layout", target_name)
            continue
        target_ref, target_rr = ctx.resolve_field_ref(target_name, materialised)
        idx_reg = ctx.const_to_reg(i)
        part_reg = ctx.fresh_reg()
        ctx.emit_inst(
            CallFunction(
                result_reg=part_reg,
                func_name=FuncName(BuiltinName.LIST_GET),
                args=(parts_reg, idx_reg),
            ),
        )
        ctx.emit_encode_and_write(
            target_rr, target_ref.fl, part_reg, target_ref.offset_reg
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
    """INSPECT TALLYING — count pattern occurrences and write to tally target."""
    total_count_reg = ctx.const_to_reg(0)

    for tally_for in stmt.tallying_for:
        pattern_reg = ctx.const_to_reg(strip_cobol_literal(str(tally_for.pattern)))
        mode_reg = ctx.const_to_reg(tally_for.mode.lower())
        ir = build_inspect_tally_ir(f"inspect_tally_{stmt.source}")
        count_reg = ctx.inline_ir(
            ir,
            {
                "%p_source": src_str_reg,
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

    if stmt.tallying_target and ctx.has_field(stmt.tallying_target, materialised):
        tally_ref, tally_rr = ctx.resolve_field_ref(stmt.tallying_target, materialised)
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
        from_reg = ctx.const_to_reg(strip_cobol_literal(str(replacing.from_pattern)))
        to_reg = ctx.const_to_reg(strip_cobol_literal(str(replacing.to_pattern)))
        mode_reg = ctx.const_to_reg(replacing.mode.lower())
        ir = build_inspect_replace_ir(f"inspect_replace_{stmt.source}")
        new_str_reg = ctx.inline_ir(
            ir,
            {
                "%p_source": current_str_reg,
                "%p_from": from_reg,
                "%p_to": to_reg,
                "%p_mode": mode_reg,
            },
        )
        current_str_reg = new_str_reg

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
