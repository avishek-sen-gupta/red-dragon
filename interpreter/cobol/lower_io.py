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
from interpreter.instructions import Binop, Branch, BranchIf, CallFunction, Label_
from interpreter.operator_kind import resolve_binop
from interpreter.register import Register, NO_REGISTER

logger = logging.getLogger(__name__)


def _select_to_record(ctx: EmitContext) -> dict[str, str]:
    """Return SELECT-file-name → first-FD-record-name (both uppercased)."""
    result: dict[str, str] = {}
    for rec, sel in ctx._asg.file_record_to_select.items():
        if sel not in result:
            result[sel] = rec
    return result


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
    """OPEN [mode file1 ...] ... — emit __cobol_open_file per file with org/key metadata."""
    for mode, files in stmt.mode_groups:
        for filename in files:
            fn_reg = ctx.const_to_reg(filename)
            mode_reg = ctx.const_to_reg(mode.value)

            # Look up FileControlEntry for organization and key metadata
            fce = next(
                (e for e in ctx._asg.file_control if e.file_name == filename), None
            )
            org = fce.organization.value if fce else "SEQUENTIAL"

            # Resolve record length: look up the first FD record for this SELECT
            # file, then read its byte_length from the file section layout.
            record_length = 0
            s2r = _select_to_record(ctx)
            rec_name = s2r.get(filename.upper())
            if rec_name:
                try:
                    fl, _ = materialised.resolve(rec_name)
                    record_length = fl.byte_length
                except KeyError:
                    pass

            # Resolve key offset/length from FileControlEntry.record_key
            key_offset, key_length = 0, 0
            if fce and fce.record_key:
                try:
                    key_fl, _ = materialised.resolve(fce.record_key)
                    key_offset = key_fl.offset
                    key_length = key_fl.byte_length
                except KeyError:
                    pass

            rl_reg = ctx.const_to_reg(record_length)
            org_reg = ctx.const_to_reg(org)
            koff_reg = ctx.const_to_reg(key_offset)
            klen_reg = ctx.const_to_reg(key_length)

            raw_reg = ctx.fresh_reg()
            ctx.emit_inst(
                CallFunction(
                    result_reg=raw_reg,
                    func_name=FuncName("__cobol_open_file"),
                    args=(
                        Register(str(fn_reg)),
                        Register(str(mode_reg)),
                        Register(str(rl_reg)),
                        Register(str(org_reg)),
                        Register(str(koff_reg)),
                        Register(str(klen_reg)),
                    ),
                ),
            )
            status_reg = ctx.fresh_reg()
            ctx.emit_inst(
                CallFunction(
                    result_reg=status_reg,
                    func_name=FuncName("__cobol_io_status"),
                    args=(Register(str(raw_reg)),),
                )
            )
            ctx.emit_file_status_update(filename, status_reg, materialised)
            logger.info("OPEN %s %s", mode.value, filename)


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


def _status_const_reg(ctx: EmitContext, code: str) -> Register:
    """Emit a COBOL file-status literal as a STRING constant.

    __cobol_io_status returns the 2-char status as a Python string (e.g. "10").
    A bare const like "10" is parsed by the VM as the integer 10 (see
    interpreter.vm.vm._parse_const), so ``status == "10"`` would compare String
    vs Int and never match. Quoting forces the literal to stay a string, exactly
    as COBOL alphanumeric literals are emitted. (red-dragon-m0oa.7)
    """
    return ctx.const_to_reg(f'"{code}"')


def lower_read(
    ctx: EmitContext,
    stmt: ReadStatement,
    materialised: MaterialisedSectionedLayout,
) -> None:
    """READ file [INTO target] [KEY k] [AT END ...] [INVALID KEY ...] — with IOResult branching."""
    fn_reg = ctx.const_to_reg(stmt.file_name)

    # Key for random access
    if stmt.key and materialised.has_field(stmt.key):
        key_ref, key_rr = ctx.resolve_field_ref(stmt.key, materialised)
        key_val_reg = ctx.emit_decode_field(key_rr, key_ref.fl, key_ref.offset_reg)
        key_str_reg = ctx.emit_to_string(key_val_reg)
    else:
        key_str_reg = ctx.const_to_reg("")

    raw_reg = ctx.fresh_reg()
    ctx.emit_inst(
        CallFunction(
            result_reg=raw_reg,
            func_name=FuncName("__cobol_read_record"),
            args=(Register(str(fn_reg)), Register(str(key_str_reg))),
        ),
    )

    status_reg = ctx.fresh_reg()
    ctx.emit_inst(
        CallFunction(
            result_reg=status_reg,
            func_name=FuncName("__cobol_io_status"),
            args=(Register(str(raw_reg)),),
        )
    )
    ctx.emit_file_status_update(stmt.file_name, status_reg, materialised)

    data_reg = ctx.fresh_reg()
    ctx.emit_inst(
        CallFunction(
            result_reg=data_reg,
            func_name=FuncName("__cobol_io_data"),
            args=(Register(str(raw_reg)),),
        )
    )

    # Write data into file section region via the FD record name for this file
    s2r = _select_to_record(ctx)
    rec_name = s2r.get(stmt.file_name.upper())
    if rec_name:
        try:
            file_fl, file_rr = materialised.resolve(rec_name)
            ctx.emit_encode_and_write(file_rr, file_fl, data_reg, NO_REGISTER)
        except KeyError:
            pass

    # INTO copy
    if stmt.into and materialised.has_field(stmt.into):
        target_ref, target_rr = ctx.resolve_field_ref(stmt.into, materialised)
        str_reg = ctx.emit_to_string(data_reg)
        ctx.emit_encode_and_write(
            target_rr, target_ref.fl, str_reg, target_ref.offset_reg
        )

    after_label = ctx.fresh_label("read_after")
    has_at_end = bool(stmt.at_end or stmt.not_at_end)
    has_inv_key = bool(stmt.invalid_key or stmt.not_invalid_key)

    if has_at_end:
        at_end_lbl = ctx.fresh_label("read_at_end")
        ok_lbl = ctx.fresh_label("read_ok")
        cond_reg = ctx.fresh_reg()
        ten_reg = _status_const_reg(ctx, "10")
        ctx.emit_inst(
            Binop(
                result_reg=cond_reg,
                operator=resolve_binop("=="),
                left=status_reg,
                right=Register(str(ten_reg)),
            )
        )
        ctx.emit_inst(BranchIf(cond_reg=cond_reg, branch_targets=(at_end_lbl, ok_lbl)))
        ctx.emit_inst(Label_(label=at_end_lbl))
        for s in stmt.at_end:
            ctx.lower_statement(s, materialised)
        ctx.emit_inst(Branch(label=after_label))
        ctx.emit_inst(Label_(label=ok_lbl))
        for s in stmt.not_at_end:
            ctx.lower_statement(s, materialised)
        ctx.emit_inst(Branch(label=after_label))

    if has_inv_key:
        inv_lbl = ctx.fresh_label("read_inv_key")
        not_inv_lbl = ctx.fresh_label("read_not_inv")
        cond_reg = ctx.fresh_reg()
        twenty_three_reg = _status_const_reg(ctx, "23")
        ctx.emit_inst(
            Binop(
                result_reg=cond_reg,
                operator=resolve_binop("=="),
                left=status_reg,
                right=Register(str(twenty_three_reg)),
            )
        )
        ctx.emit_inst(
            BranchIf(cond_reg=cond_reg, branch_targets=(inv_lbl, not_inv_lbl))
        )
        ctx.emit_inst(Label_(label=inv_lbl))
        for s in stmt.invalid_key:
            ctx.lower_statement(s, materialised)
        ctx.emit_inst(Branch(label=after_label))
        ctx.emit_inst(Label_(label=not_inv_lbl))
        for s in stmt.not_invalid_key:
            ctx.lower_statement(s, materialised)
        ctx.emit_inst(Branch(label=after_label))

    ctx.emit_inst(Label_(label=after_label))
    logger.info("READ %s INTO %s", stmt.file_name, stmt.into or "(none)")


def _emit_invalid_key_branch(
    ctx: EmitContext,
    status_reg: Register,
    file_name: str,
    invalid_key: list,
    not_invalid_key: list,
    materialised: MaterialisedSectionedLayout,
    after_label: object,
) -> None:
    if not (invalid_key or not_invalid_key):
        return
    inv_lbl = ctx.fresh_label("inv_key")
    not_inv_lbl = ctx.fresh_label("not_inv_key")
    cond_reg = ctx.fresh_reg()
    twenty_three_reg = _status_const_reg(ctx, "23")
    ctx.emit_inst(
        Binop(
            result_reg=cond_reg,
            operator=resolve_binop("=="),
            left=status_reg,
            right=Register(str(twenty_three_reg)),
        )
    )
    ctx.emit_inst(BranchIf(cond_reg=cond_reg, branch_targets=(inv_lbl, not_inv_lbl)))
    ctx.emit_inst(Label_(label=inv_lbl))
    for s in invalid_key:
        ctx.lower_statement(s, materialised)
    ctx.emit_inst(Branch(label=after_label))  # type: ignore[arg-type]
    ctx.emit_inst(Label_(label=not_inv_lbl))
    for s in not_invalid_key:
        ctx.lower_statement(s, materialised)
    ctx.emit_inst(Branch(label=after_label))  # type: ignore[arg-type]


def _write_source_reg(
    ctx: EmitContext,
    from_field: str | None,
    record_name: str,
    materialised: MaterialisedSectionedLayout,
) -> Register:
    """Resolve the data register for WRITE/REWRITE.

    `WRITE rec FROM fld` writes the contents of `fld`; a plain `WRITE rec`
    writes the current contents of the record area `rec`. Both decode the
    source field's bytes to its logical value. Only when neither names a known
    field do we fall back to the bare name as a string constant.
    """
    source = from_field or record_name
    if ctx.has_field(source, materialised):
        ref, rr = ctx.resolve_field_ref(source, materialised)
        decoded_reg = ctx.emit_decode_field(rr, ref.fl, ref.offset_reg)
        return ctx.emit_to_string(decoded_reg)
    return ctx.const_to_reg(source)


def lower_write(
    ctx: EmitContext,
    stmt: WriteStatement,
    materialised: MaterialisedSectionedLayout,
) -> None:
    """WRITE record-name [FROM field] [INVALID KEY ...] — write record via __cobol_write_record."""
    data_reg = _write_source_reg(ctx, stmt.from_field, stmt.record_name, materialised)

    # Map FD record name → SELECT file name for the provider dispatch
    r2s = ctx._asg.file_record_to_select
    file_name = r2s.get(stmt.record_name.upper(), stmt.record_name)
    fn_reg = ctx.const_to_reg(file_name)
    raw_reg = ctx.fresh_reg()
    ctx.emit_inst(
        CallFunction(
            result_reg=raw_reg,
            func_name=FuncName("__cobol_write_record"),
            args=(Register(str(fn_reg)), Register(str(data_reg))),
        ),
    )
    status_reg = ctx.fresh_reg()
    ctx.emit_inst(
        CallFunction(
            result_reg=status_reg,
            func_name=FuncName("__cobol_io_status"),
            args=(Register(str(raw_reg)),),
        )
    )
    ctx.emit_file_status_update(file_name, status_reg, materialised)
    after_label = ctx.fresh_label("write_after")
    _emit_invalid_key_branch(
        ctx,
        status_reg,
        stmt.record_name,
        stmt.invalid_key,
        stmt.not_invalid_key,
        materialised,
        after_label,
    )
    ctx.emit_inst(Label_(label=after_label))
    logger.info("WRITE %s FROM %s", stmt.record_name, stmt.from_field or "(none)")


def lower_rewrite(
    ctx: EmitContext,
    stmt: RewriteStatement,
    materialised: MaterialisedSectionedLayout,
) -> None:
    """REWRITE record-name [FROM field] [INVALID KEY ...] — rewrite via __cobol_rewrite_record."""
    data_reg = _write_source_reg(ctx, stmt.from_field, stmt.record_name, materialised)

    r2s = ctx._asg.file_record_to_select
    file_name = r2s.get(stmt.record_name.upper(), stmt.record_name)
    fn_reg = ctx.const_to_reg(file_name)
    raw_reg = ctx.fresh_reg()
    ctx.emit_inst(
        CallFunction(
            result_reg=raw_reg,
            func_name=FuncName("__cobol_rewrite_record"),
            args=(Register(str(fn_reg)), Register(str(data_reg))),
        ),
    )
    status_reg = ctx.fresh_reg()
    ctx.emit_inst(
        CallFunction(
            result_reg=status_reg,
            func_name=FuncName("__cobol_io_status"),
            args=(Register(str(raw_reg)),),
        )
    )
    ctx.emit_file_status_update(file_name, status_reg, materialised)
    after_label = ctx.fresh_label("rewrite_after")
    _emit_invalid_key_branch(
        ctx,
        status_reg,
        file_name,
        stmt.invalid_key,
        stmt.not_invalid_key,
        materialised,
        after_label,
    )
    ctx.emit_inst(Label_(label=after_label))
    logger.info("REWRITE %s FROM %s", stmt.record_name, stmt.from_field or "(none)")


def lower_start(
    ctx: EmitContext,
    stmt: StartStatement,
    materialised: MaterialisedSectionedLayout,
) -> None:
    """START file-name [KEY relop key] [INVALID KEY ...] — position via __cobol_start_file."""
    fn_reg = ctx.const_to_reg(stmt.file_name)
    key_reg = ctx.const_to_reg(stmt.key or "")
    relop_reg = ctx.const_to_reg(stmt.relop or "=")
    raw_reg = ctx.fresh_reg()
    ctx.emit_inst(
        CallFunction(
            result_reg=raw_reg,
            func_name=FuncName("__cobol_start_file"),
            args=(
                Register(str(fn_reg)),
                Register(str(key_reg)),
                Register(str(relop_reg)),
            ),
        ),
    )
    status_reg = ctx.fresh_reg()
    ctx.emit_inst(
        CallFunction(
            result_reg=status_reg,
            func_name=FuncName("__cobol_io_status"),
            args=(Register(str(raw_reg)),),
        )
    )
    ctx.emit_file_status_update(stmt.file_name, status_reg, materialised)
    after_label = ctx.fresh_label("start_after")
    _emit_invalid_key_branch(
        ctx,
        status_reg,
        stmt.file_name,
        stmt.invalid_key,
        stmt.not_invalid_key,
        materialised,
        after_label,
    )
    ctx.emit_inst(Label_(label=after_label))
    logger.info("START %s KEY %s %s", stmt.file_name, stmt.relop, stmt.key or "(none)")


def lower_delete(
    ctx: EmitContext,
    stmt: DeleteStatement,
    materialised: MaterialisedSectionedLayout,
) -> None:
    """DELETE file-name [INVALID KEY ...] — delete record via __cobol_delete_record."""
    fn_reg = ctx.const_to_reg(stmt.file_name)
    raw_reg = ctx.fresh_reg()
    ctx.emit_inst(
        CallFunction(
            result_reg=raw_reg,
            func_name=FuncName("__cobol_delete_record"),
            args=(Register(str(fn_reg)),),
        ),
    )
    status_reg = ctx.fresh_reg()
    ctx.emit_inst(
        CallFunction(
            result_reg=status_reg,
            func_name=FuncName("__cobol_io_status"),
            args=(Register(str(raw_reg)),),
        )
    )
    ctx.emit_file_status_update(stmt.file_name, status_reg, materialised)
    after_label = ctx.fresh_label("delete_after")
    _emit_invalid_key_branch(
        ctx,
        status_reg,
        stmt.file_name,
        stmt.invalid_key,
        stmt.not_invalid_key,
        materialised,
        after_label,
    )
    ctx.emit_inst(Label_(label=after_label))
    logger.info("DELETE %s", stmt.file_name)
