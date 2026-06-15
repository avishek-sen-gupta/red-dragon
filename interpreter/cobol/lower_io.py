"""I/O statement lowering — ACCEPT, OPEN, CLOSE, READ, WRITE, REWRITE, START, DELETE."""

from __future__ import annotations

import logging

from interpreter.cobol.cobol_statements import (
    AcceptStatement,
    CloseStatement,
    DeleteStatement,
    OpenStatement,
    ReadStatement,
    RewriteStatement,
    StartStatement,
    WriteStatement,
)
from interpreter.cobol.emit_context import EmitContext
from interpreter.cobol.sectioned_layout import MaterialisedSectionedLayout
from interpreter.func_name import FuncName
from interpreter.instructions import CallFunction
from interpreter.register import Register

logger = logging.getLogger(__name__)


def lower_accept(
    ctx: EmitContext,
    stmt: AcceptStatement,
    materialised: MaterialisedSectionedLayout,
) -> None:
    """ACCEPT target [FROM device] — read input via __cobol_accept."""
    device_reg = ctx.const_to_reg(stmt.from_device)
    result_reg = ctx.fresh_reg()
    ctx.emit_inst(
        CallFunction(
            result_reg=result_reg,
            func_name=FuncName("__cobol_accept"),
            args=(Register(str(device_reg)),),
        ),
    )
    if stmt.target and ctx.has_field(stmt.target, materialised):
        target_ref, target_rr = ctx.resolve_field_ref(stmt.target, materialised)
        str_reg = ctx.emit_to_string(result_reg)
        ctx.emit_encode_and_write(
            target_rr, target_ref.fl, str_reg, target_ref.offset_reg
        )
    logger.info("ACCEPT %s FROM %s", stmt.target, stmt.from_device)


def lower_open(
    ctx: EmitContext,
    stmt: OpenStatement,
    materialised: MaterialisedSectionedLayout,
) -> None:
    """OPEN mode file1 file2 ... — open files via __cobol_open_file."""
    for filename in stmt.files:
        fn_reg = ctx.const_to_reg(filename)
        mode_reg = ctx.const_to_reg(stmt.mode)
        # record_length, organization, key_offset, key_length — defaults until
        # file-control metadata is plumbed through from the ENVIRONMENT DIVISION.
        rec_len_reg = ctx.const_to_reg(0)
        org_reg = ctx.const_to_reg("SEQUENTIAL")
        key_off_reg = ctx.const_to_reg(0)
        key_len_reg = ctx.const_to_reg(0)
        result_reg = ctx.fresh_reg()
        ctx.emit_inst(
            CallFunction(
                result_reg=result_reg,
                func_name=FuncName("__cobol_open_file"),
                args=(
                    Register(str(fn_reg)),
                    Register(str(mode_reg)),
                    Register(str(rec_len_reg)),
                    Register(str(org_reg)),
                    Register(str(key_off_reg)),
                    Register(str(key_len_reg)),
                ),
            ),
        )
        logger.info("OPEN %s %s", stmt.mode, filename)


def lower_close(
    ctx: EmitContext,
    stmt: CloseStatement,
    materialised: MaterialisedSectionedLayout,
) -> None:
    """CLOSE file1 file2 ... — close files via __cobol_close_file."""
    for filename in stmt.files:
        fn_reg = ctx.const_to_reg(filename)
        result_reg = ctx.fresh_reg()
        ctx.emit_inst(
            CallFunction(
                result_reg=result_reg,
                func_name=FuncName("__cobol_close_file"),
                args=(Register(str(fn_reg)),),
            ),
        )
        logger.info("CLOSE %s", filename)


def lower_read(
    ctx: EmitContext,
    stmt: ReadStatement,
    materialised: MaterialisedSectionedLayout,
) -> None:
    """READ file-name [INTO target] — read record via __cobol_read_record."""
    fn_reg = ctx.const_to_reg(stmt.file_name)
    # key — empty string for sequential reads; keyed access will populate this
    # once READ ... KEY IS ... parsing is supported.
    key_reg = ctx.const_to_reg("")
    io_result_reg = ctx.fresh_reg()
    ctx.emit_inst(
        CallFunction(
            result_reg=io_result_reg,
            func_name=FuncName("__cobol_read_record"),
            args=(Register(str(fn_reg)), Register(str(key_reg))),
        ),
    )
    if stmt.into and ctx.has_field(stmt.into, materialised):
        # Extract the string payload from IOResult via __cobol_io_data.
        data_reg = ctx.fresh_reg()
        ctx.emit_inst(
            CallFunction(
                result_reg=data_reg,
                func_name=FuncName("__cobol_io_data"),
                args=(Register(str(io_result_reg)),),
            ),
        )
        target_ref, target_rr = ctx.resolve_field_ref(stmt.into, materialised)
        str_reg = ctx.emit_to_string(data_reg)
        ctx.emit_encode_and_write(
            target_rr, target_ref.fl, str_reg, target_ref.offset_reg
        )
    logger.info("READ %s INTO %s", stmt.file_name, stmt.into or "(none)")


def lower_write(
    ctx: EmitContext,
    stmt: WriteStatement,
    materialised: MaterialisedSectionedLayout,
) -> None:
    """WRITE record-name [FROM field] — write record via __cobol_write_record."""
    if stmt.from_field and ctx.has_field(stmt.from_field, materialised):
        from_ref, from_rr = ctx.resolve_field_ref(stmt.from_field, materialised)
        decoded_reg = ctx.emit_decode_field(from_rr, from_ref.fl, from_ref.offset_reg)
        data_reg = ctx.emit_to_string(decoded_reg)
    else:
        data_reg = ctx.const_to_reg(stmt.from_field or stmt.record_name)

    fn_reg = ctx.const_to_reg(stmt.record_name)
    result_reg = ctx.fresh_reg()
    ctx.emit_inst(
        CallFunction(
            result_reg=result_reg,
            func_name=FuncName("__cobol_write_record"),
            args=(Register(str(fn_reg)), Register(str(data_reg))),
        ),
    )
    logger.info("WRITE %s FROM %s", stmt.record_name, stmt.from_field or "(none)")


def lower_rewrite(
    ctx: EmitContext,
    stmt: RewriteStatement,
    materialised: MaterialisedSectionedLayout,
) -> None:
    """REWRITE record-name [FROM field] — rewrite record via __cobol_rewrite_record."""
    if stmt.from_field and ctx.has_field(stmt.from_field, materialised):
        from_ref, from_rr = ctx.resolve_field_ref(stmt.from_field, materialised)
        decoded_reg = ctx.emit_decode_field(from_rr, from_ref.fl, from_ref.offset_reg)
        data_reg = ctx.emit_to_string(decoded_reg)
    else:
        data_reg = ctx.const_to_reg(stmt.from_field or stmt.record_name)

    fn_reg = ctx.const_to_reg(stmt.record_name)
    result_reg = ctx.fresh_reg()
    ctx.emit_inst(
        CallFunction(
            result_reg=result_reg,
            func_name=FuncName("__cobol_rewrite_record"),
            args=(Register(str(fn_reg)), Register(str(data_reg))),
        ),
    )
    logger.info("REWRITE %s FROM %s", stmt.record_name, stmt.from_field or "(none)")


def lower_start(
    ctx: EmitContext,
    stmt: StartStatement,
    materialised: MaterialisedSectionedLayout,
) -> None:
    """START file-name [KEY ...] — position file via __cobol_start_file."""
    fn_reg = ctx.const_to_reg(stmt.file_name)
    key_reg = ctx.const_to_reg(stmt.key or "")
    # relop — empty string default until START ... KEY IS ... relop parsing is supported.
    relop_reg = ctx.const_to_reg("")
    result_reg = ctx.fresh_reg()
    ctx.emit_inst(
        CallFunction(
            result_reg=result_reg,
            func_name=FuncName("__cobol_start_file"),
            args=(
                Register(str(fn_reg)),
                Register(str(key_reg)),
                Register(str(relop_reg)),
            ),
        ),
    )
    logger.info("START %s KEY %s", stmt.file_name, stmt.key or "(none)")


def lower_delete(
    ctx: EmitContext,
    stmt: DeleteStatement,
    materialised: MaterialisedSectionedLayout,
) -> None:
    """DELETE file-name — delete record via __cobol_delete_record."""
    fn_reg = ctx.const_to_reg(stmt.file_name)
    result_reg = ctx.fresh_reg()
    ctx.emit_inst(
        CallFunction(
            result_reg=result_reg,
            func_name=FuncName("__cobol_delete_record"),
            args=(Register(str(fn_reg)),),
        ),
    )
    logger.info("DELETE %s", stmt.file_name)
