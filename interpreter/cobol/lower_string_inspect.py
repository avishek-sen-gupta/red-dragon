# pyright: standard
"""STRING, UNSTRING, INSPECT statement lowering."""

from __future__ import annotations

import logging

from interpreter.cobol.cobol_constants import BuiltinName, DelimiterMode, InspectType
from interpreter.cobol.cobol_statements import (
    InspectStatement,
    StringStatement,
    UnstringStatement,
)
from interpreter.cobol.data_layout import DataLayout, FieldLayout
from interpreter.cobol.emit_context import EmitContext
from interpreter.cobol.figurative_constants import translate_cobol_figurative
from interpreter.cobol.ir_encoders import (
    build_inspect_replace_ir,
    build_inspect_tally_ir,
    build_string_split_ir,
)
from interpreter.operator_kind import resolve_binop
from interpreter.func_name import FuncName
from interpreter.instructions import Binop, CallFunction
from interpreter.register import Register

logger = logging.getLogger(__name__)


def lower_string(
    ctx: EmitContext,
    stmt: StringStatement,
    layout: DataLayout,
    region_reg: str,
) -> None:
    """STRING ... DELIMITED BY ... INTO target."""
    part_regs: list[str] = []
    for sending in stmt.sendings:
        if ctx.has_field(sending.value, layout):
            source_ref = ctx.resolve_field_ref(sending.value, layout, region_reg)
            decoded_reg = ctx.emit_decode_field(
                region_reg, source_ref.fl, source_ref.offset_reg
            )
            src_str_reg = ctx.emit_to_string(decoded_reg)
        else:
            src_str_reg = ctx.const_to_reg(str(sending.value))

        if sending.delimited_by == DelimiterMode.SIZE:
            part_regs.append(src_str_reg)
        else:
            delim_reg = ctx.const_to_reg(
                translate_cobol_figurative(str(sending.delimited_by))
            )
            find_pos = ctx.fresh_reg()
            ctx.emit_inst(
                CallFunction(
                    result_reg=find_pos,
                    func_name=FuncName(BuiltinName.STRING_FIND),
                    args=(Register(str(src_str_reg)), Register(str(delim_reg))),
                ),
            )
            parts = ctx.fresh_reg()
            ctx.emit_inst(
                CallFunction(
                    result_reg=parts,
                    func_name=FuncName(BuiltinName.STRING_SPLIT),
                    args=(Register(str(src_str_reg)), Register(str(delim_reg))),
                ),
            )
            first_part = ctx.fresh_reg()
            ctx.emit_inst(
                CallFunction(
                    result_reg=first_part,
                    func_name=FuncName(BuiltinName.LIST_GET),
                    args=(Register(str(parts)), 0),  # type: ignore[arg-type]  # see red-dragon-5kgb
                ),
            )
            part_regs.append(first_part)  # type: ignore[arg-type]  # see red-dragon-5kgb

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
                    args=(Register(str(concat_reg)), Register(str(next_reg))),
                ),
            )
            concat_reg = new_concat

    if stmt.into and ctx.has_field(stmt.into, layout):
        target_ref = ctx.resolve_field_ref(stmt.into, layout, region_reg)
        ctx.emit_encode_and_write(
            region_reg, target_ref.fl, concat_reg, target_ref.offset_reg  # type: ignore[arg-type]  # see red-dragon-5kgb
        )
    else:
        logger.warning("STRING INTO target %s not found in layout", stmt.into)


def lower_unstring(
    ctx: EmitContext,
    stmt: UnstringStatement,
    layout: DataLayout,
    region_reg: str,
) -> None:
    """UNSTRING source DELIMITED BY ... INTO targets."""
    if ctx.has_field(stmt.source, layout):
        source_ref = ctx.resolve_field_ref(stmt.source, layout, region_reg)
        decoded_reg = ctx.emit_decode_field(
            region_reg, source_ref.fl, source_ref.offset_reg
        )
        src_str_reg = ctx.emit_to_string(decoded_reg)
    else:
        src_str_reg = ctx.const_to_reg(str(stmt.source))

    delimiter = translate_cobol_figurative(str(stmt.delimited_by))
    delim_reg = ctx.const_to_reg(delimiter)
    ir = build_string_split_ir(f"unstring_split_{stmt.source}")
    parts_reg = ctx.inline_ir(ir, {"%p_source": src_str_reg, "%p_delimiter": delim_reg})  # type: ignore[arg-type]  # see red-dragon-5kgb

    for i, target_name in enumerate(stmt.into):
        if not ctx.has_field(target_name, layout):
            logger.warning("UNSTRING INTO target %s not found in layout", target_name)
            continue
        target_ref = ctx.resolve_field_ref(target_name, layout, region_reg)
        idx_reg = ctx.const_to_reg(i)
        part_reg = ctx.fresh_reg()
        ctx.emit_inst(
            CallFunction(
                result_reg=part_reg,
                func_name=FuncName(BuiltinName.LIST_GET),
                args=(Register(str(parts_reg)), Register(str(idx_reg))),
            ),
        )
        ctx.emit_encode_and_write(
            region_reg, target_ref.fl, part_reg, target_ref.offset_reg  # type: ignore[arg-type]  # see red-dragon-5kgb
        )


def lower_inspect(
    ctx: EmitContext,
    stmt: InspectStatement,
    layout: DataLayout,
    region_reg: str,
) -> None:
    """INSPECT source TALLYING|REPLACING ..."""
    if not ctx.has_field(stmt.source, layout):
        logger.warning("INSPECT source %s not found in layout", stmt.source)
        return
    source_ref = ctx.resolve_field_ref(stmt.source, layout, region_reg)
    source_fl = source_ref.fl
    decoded_reg = ctx.emit_decode_field(region_reg, source_fl, source_ref.offset_reg)
    src_str_reg = ctx.emit_to_string(decoded_reg)

    if stmt.inspect_type == InspectType.TALLYING:
        lower_inspect_tallying(ctx, stmt, src_str_reg, layout, region_reg)
    elif stmt.inspect_type == InspectType.REPLACING:
        lower_inspect_replacing(ctx, stmt, src_str_reg, source_fl, layout, region_reg)


def lower_inspect_tallying(
    ctx: EmitContext,
    stmt: InspectStatement,
    src_str_reg: str,
    layout: DataLayout,
    region_reg: str,
) -> None:
    """INSPECT TALLYING — count pattern occurrences and write to tally target."""
    total_count_reg = ctx.const_to_reg(0)

    for tally_for in stmt.tallying_for:
        pattern_reg = ctx.const_to_reg(str(tally_for.pattern))
        mode_reg = ctx.const_to_reg(tally_for.mode.lower())
        ir = build_inspect_tally_ir(f"inspect_tally_{stmt.source}")
        count_reg = ctx.inline_ir(
            ir,  # type: ignore[arg-type]  # see red-dragon-5kgb
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
                left=Register(str(total_count_reg)),
                right=Register(str(count_reg)),
            ),
        )
        total_count_reg = new_total

    if stmt.tallying_target and ctx.has_field(stmt.tallying_target, layout):
        tally_ref = ctx.resolve_field_ref(stmt.tallying_target, layout, region_reg)
        count_str_reg = ctx.emit_to_string(total_count_reg)  # type: ignore[arg-type]  # see red-dragon-5kgb
        ctx.emit_encode_and_write(
            region_reg, tally_ref.fl, count_str_reg, tally_ref.offset_reg
        )


def lower_inspect_replacing(
    ctx: EmitContext,
    stmt: InspectStatement,
    src_str_reg: str,
    source_fl: FieldLayout,
    layout: DataLayout,
    region_reg: str,
) -> None:
    """INSPECT REPLACING — apply replacements and write back."""
    current_str_reg = src_str_reg

    for replacing in stmt.replacings:
        from_reg = ctx.const_to_reg(str(replacing.from_pattern))
        to_reg = ctx.const_to_reg(str(replacing.to_pattern))
        mode_reg = ctx.const_to_reg(replacing.mode.lower())
        ir = build_inspect_replace_ir(f"inspect_replace_{stmt.source}")
        new_str_reg = ctx.inline_ir(
            ir,  # type: ignore[arg-type]  # see red-dragon-5kgb
            {
                "%p_source": current_str_reg,
                "%p_from": from_reg,
                "%p_to": to_reg,
                "%p_mode": mode_reg,
            },
        )
        current_str_reg = new_str_reg

    ctx.emit_encode_and_write(region_reg, source_fl, current_str_reg)
