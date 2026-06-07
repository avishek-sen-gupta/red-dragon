"""ExecCicsStrategy protocol and null-object implementation."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Protocol

from interpreter.cics.builtins.system import (
    make_init_eib_builtin,
    make_assign_builtin,
    make_asktime_builtin,
    make_formattime_builtin,
    make_inquire_builtin,
    make_writeq_td_builtin,
    make_handle_abend_builtin,
    make_handle_noop_builtin,
    make_abend_builtin,
)
from interpreter.func_name import FuncName
from interpreter.instructions import CallFunction, Const, LoadRegion, Return_

if TYPE_CHECKING:
    import queue

    from interpreter.cobol.emit_context import EmitContext
    from interpreter.cobol.cobol_statements import ExecCicsStatement
    from interpreter.cobol.sectioned_layout import MaterialisedSectionedLayout
    from interpreter.cics.types import CicsContext
    from interpreter.cics.bms.loader import BmsLoader
    from interpreter.register import Register

logger = logging.getLogger(__name__)

_BUILTIN_INIT_EIB = FuncName("__cics_init_eib")

_SYS_VERBS: dict[str, str] = {
    "ASSIGN": "__cics_assign",
    "ASKTIME": "__cics_asktime",
    "FORMATTIME": "__cics_formattime",
    "INQUIRE": "__cics_inquire",
    "WRITEQ TD": "__cics_writeq_td",
    "HANDLE ABEND": "__cics_handle_abend",
    # HANDLE CONDITION / HANDLE AID are explicit no-ops for now — the real
    # runtime-dispatch machinery is a deferred follow-up
    # (docs/superpowers/plans/2026-06-07-cics-handle-condition-machinery.md).
    "HANDLE CONDITION": "__cics_handle_condition",
    "HANDLE AID": "__cics_handle_aid",
}

# Verbs whose builtin returns a CICS response code to be written into EIBRESP
# (always) and the RESP(name) option's field (when present). Only INQUIRE among
# the current system verbs produces a resp code; D extends this set with the
# VSAM verbs (READ/WRITE/REWRITE/DELETE/STARTBR/...).
_RESP_PRODUCING_VERBS: set[str] = {"INQUIRE"}

# VSAM point operations.
_VSAM_POINT_VERBS: set[str] = {"READ", "WRITE", "REWRITE", "DELETE"}

# VSAM browse operations (implicit single cursor per file).
_VSAM_BROWSE_VERBS: set[str] = {"STARTBR", "READNEXT", "READPREV", "ENDBR"}

_BMS_VERBS: dict[str, str] = {
    "SEND MAP": "__cics_send_map",
    "RECEIVE MAP": "__cics_receive_map",
    "SEND TEXT": "__cics_send_text",
}


def emit_copy_in(
    ctx: "EmitContext",
    name: str | None,
    materialised: "MaterialisedSectionedLayout",
) -> "Register | None":
    """If ``name`` is a data item, LoadRegion its bytes into a fresh register and return it.

    Returns ``None`` when ``name`` is ``None`` or a literal (caller falls back to Const).
    """
    if name is None or not ctx.has_field(name, materialised):
        return None
    ref, region_reg = ctx.resolve_field_ref(name, materialised)
    out = ctx.fresh_reg()
    ctx.emit_inst(
        LoadRegion(
            result_reg=out,
            region_reg=region_reg,
            offset_reg=ref.offset_reg,
            length=ref.fl.byte_length,
        )
    )
    return out


def emit_operand_value(
    ctx: "EmitContext",
    name: str | None,
    materialised: "MaterialisedSectionedLayout",
) -> "Register":
    """Resolve a CICS operand to a register holding its runtime VALUE.

    If ``name`` is a data item, decode the field to a register; otherwise treat it
    as a literal (strip COBOL quotes) and emit a Const. Returns a Register.
    """
    if name and ctx.has_field(name, materialised):
        ref, region_reg = ctx.resolve_field_ref(name, materialised)
        return ctx.emit_decode_field(region_reg, ref.fl)
    literal = (name or "").strip("'\" ")
    r = ctx.fresh_reg()
    ctx.emit_inst(Const(result_reg=r, value=literal))
    return r


def emit_copy_back_str(
    ctx: "EmitContext",
    name: str | None,
    value_str_reg: "Register",
    materialised: "MaterialisedSectionedLayout",
) -> None:
    """Encode a string-valued result into the named field, if it is a data item.

    No-op for ``None`` or literal names.
    """
    if name is None or not ctx.has_field(name, materialised):
        return
    ref, region_reg = ctx.resolve_field_ref(name, materialised)
    ctx.emit_encode_and_write(region_reg, ref.fl, value_str_reg, ref.offset_reg)


def emit_resp_writeback(
    ctx: "EmitContext",
    r_resp_result: "Register",
    opts: dict[str, str | None],
    materialised: "MaterialisedSectionedLayout",
) -> None:
    """Write a builtin's returned resp code into EIBRESP (always) and RESP(name) if present.

    ``r_resp_result`` is the numeric register returned by the service builtin.
    It is stringified, then encoded per each target field's layout — EIBRESP is
    ``PIC S9(8) COMP`` (binary), so the numeric string is packed correctly by
    ``emit_encode_and_write`` (same path as the GIVING clause in lower_call.py).
    Reusable by D for the VSAM verbs.
    """
    str_reg = ctx.emit_to_string(r_resp_result)
    emit_copy_back_str(ctx, "EIBRESP", str_reg, materialised)
    emit_copy_back_str(ctx, opts.get("RESP"), str_reg, materialised)


def _resolve_keylen(
    ctx: "EmitContext",
    opts: dict[str, str | None],
    materialised: "MaterialisedSectionedLayout",
) -> int:
    """Key length for a VSAM verb.

    Precedence: a digit-literal KEYLENGTH option, else the RIDFLD field's byte
    length, else 0.
    """
    keylength = opts.get("KEYLENGTH")
    if keylength is not None and str(keylength).strip().isdigit():
        return int(str(keylength).strip())
    ridfld = opts.get("RIDFLD")
    if ridfld is not None and ctx.has_field(ridfld, materialised):
        ref, _ = ctx.resolve_field_ref(ridfld, materialised)
        return ref.fl.byte_length
    return 0


def _resolve_into(
    ctx: "EmitContext",
    name: str | None,
    materialised: "MaterialisedSectionedLayout",
) -> tuple[int, int]:
    """(offset, byte_length) of the INTO field, or (0, 0) if it is not a field."""
    if name is not None and ctx.has_field(name, materialised):
        ref, _ = ctx.resolve_field_ref(name, materialised)
        return ref.fl.offset, ref.fl.byte_length
    return 0, 0


def _register(table: dict, name: str, fn: object) -> None:  # type: ignore[type-arg]
    key = FuncName(name)
    if key in table:
        logger.warning("Builtins.TABLE already contains %s — overwriting.", key)
    table[key] = fn


class ExecCicsStrategy(Protocol):
    """Injectable strategy for lowering EXEC CICS statements to IR."""

    def on_procedure_entry(
        self,
        ctx: "EmitContext",
        materialised: "MaterialisedSectionedLayout",
    ) -> None:
        """Called once at the start of the procedure division."""
        ...

    def lower(
        self,
        ctx: "EmitContext",
        stmt: "ExecCicsStatement",
        materialised: "MaterialisedSectionedLayout",
    ) -> None:
        """Lower one EXEC CICS statement to IR."""
        ...


class CicsLoweringStrategy:
    """Full CICS lowering strategy. Inject at CobolFrontend construction for CICS mode."""

    def __init__(
        self,
        context_holder: "list[CicsContext]",
        result_holder: list | None = None,  # type: ignore[type-arg]
        program_cache: dict | None = None,  # type: ignore[type-arg]
        td_queue: list[str] | None = None,
        applid: str = "CARDDEMO",
        sysid: str = "SYS1",
        bms_loader: "BmsLoader | None" = None,
        screen_queue: "queue.Queue | None" = None,  # type: ignore[type-arg]
        input_queue: "queue.Queue | None" = None,  # type: ignore[type-arg]
        vsam_engine: object = None,
    ) -> None:
        self._context_holder = context_holder
        # Deferred imports to avoid violating project-no-vm-internals import contract.
        from interpreter.vm.builtins import Builtins  # noqa: PLC0415
        from interpreter.cics.builtins.flow import (  # noqa: PLC0415
            make_set_return_context_builtin,
            make_set_xctl_context_builtin,
        )

        if _BUILTIN_INIT_EIB in Builtins.TABLE:
            logger.warning(
                "Builtins.TABLE already contains %s — overwriting. "
                "Multiple CicsLoweringStrategy instances in one process is unsupported.",
                _BUILTIN_INIT_EIB,
            )
        init_eib = make_init_eib_builtin(context_holder)
        Builtins.TABLE[_BUILTIN_INIT_EIB] = init_eib

        _holder: list = result_holder if result_holder is not None else [None]
        td = td_queue if td_queue is not None else []
        prog_cache = program_cache or {}

        _register(Builtins.TABLE, "__cics_assign", make_assign_builtin(applid, sysid))
        _register(Builtins.TABLE, "__cics_asktime", make_asktime_builtin())
        _register(Builtins.TABLE, "__cics_formattime", make_formattime_builtin())
        _register(Builtins.TABLE, "__cics_inquire", make_inquire_builtin(prog_cache))
        _register(Builtins.TABLE, "__cics_writeq_td", make_writeq_td_builtin(td))
        _register(Builtins.TABLE, "__cics_handle_abend", make_handle_abend_builtin())
        _register(
            Builtins.TABLE,
            "__cics_handle_condition",
            make_handle_noop_builtin("HANDLE CONDITION"),
        )
        _register(
            Builtins.TABLE,
            "__cics_handle_aid",
            make_handle_noop_builtin("HANDLE AID"),
        )
        _register(Builtins.TABLE, "__cics_abend", make_abend_builtin(_holder))
        _register(
            Builtins.TABLE,
            "__cics_set_return_context",
            make_set_return_context_builtin(_holder),
        )
        _register(
            Builtins.TABLE,
            "__cics_set_xctl_context",
            make_set_xctl_context_builtin(_holder),
        )

        if (
            bms_loader is not None
            and screen_queue is not None
            and input_queue is not None
        ):
            from interpreter.cics.builtins.screen import (  # noqa: PLC0415
                make_send_map_builtin,
                make_receive_map_builtin,
                make_send_text_builtin,
            )

            _register(
                Builtins.TABLE,
                "__cics_send_map",
                make_send_map_builtin(bms_loader, screen_queue),
            )
            _register(
                Builtins.TABLE,
                "__cics_receive_map",
                make_receive_map_builtin(bms_loader, input_queue),
            )
            _register(
                Builtins.TABLE,
                "__cics_send_text",
                make_send_text_builtin(screen_queue),
            )

        if vsam_engine is not None:
            from interpreter.cics.builtins.vsam import (  # noqa: PLC0415
                make_vsam_read_builtin,
                make_vsam_write_builtin,
                make_vsam_rewrite_builtin,
                make_vsam_delete_builtin,
                make_vsam_startbr_builtin,
                make_vsam_readnext_builtin,
                make_vsam_readprev_builtin,
                make_vsam_endbr_builtin,
            )

            _register(
                Builtins.TABLE, "__cics_read", make_vsam_read_builtin(vsam_engine)
            )
            _register(
                Builtins.TABLE, "__cics_write", make_vsam_write_builtin(vsam_engine)
            )
            _register(
                Builtins.TABLE,
                "__cics_rewrite",
                make_vsam_rewrite_builtin(vsam_engine),
            )
            _register(
                Builtins.TABLE, "__cics_delete", make_vsam_delete_builtin(vsam_engine)
            )
            _register(
                Builtins.TABLE,
                "__cics_startbr",
                make_vsam_startbr_builtin(vsam_engine),
            )
            _register(
                Builtins.TABLE,
                "__cics_readnext",
                make_vsam_readnext_builtin(vsam_engine),
            )
            _register(
                Builtins.TABLE,
                "__cics_readprev",
                make_vsam_readprev_builtin(vsam_engine),
            )
            _register(
                Builtins.TABLE,
                "__cics_endbr",
                make_vsam_endbr_builtin(vsam_engine),
            )

    def on_procedure_entry(
        self,
        ctx: "EmitContext",
        materialised: "MaterialisedSectionedLayout",
    ) -> None:
        ctx.emit_inst(
            CallFunction(
                result_reg=ctx.fresh_reg(),
                func_name=_BUILTIN_INIT_EIB,
                args=(),
            )
        )

    def lower(
        self,
        ctx: "EmitContext",
        stmt: "ExecCicsStatement",
        materialised: "MaterialisedSectionedLayout",
    ) -> None:
        verb = stmt.verb
        opts = stmt.options

        # ── Flow control ──────────────────────────────────────────────────
        if verb == "RETURN":
            if "TRANSID" in opts:
                r_transid = emit_operand_value(ctx, opts.get("TRANSID"), materialised)
                r_ca = emit_copy_in(ctx, opts.get("COMMAREA"), materialised)
                if r_ca is None:
                    r_ca = ctx.fresh_reg()
                    ctx.emit_inst(Const(result_reg=r_ca, value=b""))
                r_res = ctx.fresh_reg()
                ctx.emit_inst(
                    CallFunction(
                        result_reg=r_res,
                        func_name=FuncName("__cics_set_return_context"),
                        args=(r_transid, r_ca),
                    )
                )
            else:
                r_res = ctx.fresh_reg()
                ctx.emit_inst(
                    CallFunction(
                        result_reg=r_res,
                        func_name=FuncName("__cics_set_return_context"),
                        args=(),
                    )
                )
            ctx.emit_inst(Return_())
            return

        if verb == "XCTL":
            r_prog = emit_operand_value(ctx, opts.get("PROGRAM"), materialised)
            r_ca = emit_copy_in(ctx, opts.get("COMMAREA"), materialised)
            if r_ca is None:
                r_ca = ctx.fresh_reg()
                ctx.emit_inst(Const(result_reg=r_ca, value=b""))
            r_res = ctx.fresh_reg()
            ctx.emit_inst(
                CallFunction(
                    result_reg=r_res,
                    func_name=FuncName("__cics_set_xctl_context"),
                    args=(r_prog, r_ca),
                )
            )
            ctx.emit_inst(Return_())
            return

        if verb == "ABEND":
            r_code = ctx.fresh_reg()
            ctx.emit_inst(Const(result_reg=r_code, value=opts.get("ABCODE", "UNKN")))
            r_res = ctx.fresh_reg()
            ctx.emit_inst(
                CallFunction(
                    result_reg=r_res,
                    func_name=FuncName("__cics_abend"),
                    args=(r_code,),
                )
            )
            ctx.emit_inst(Return_())
            return

        # ── BMS screen verbs ──────────────────────────────────────────────
        bms_builtin = _BMS_VERBS.get(verb)
        if bms_builtin:
            if verb == "SEND TEXT":
                r_text = ctx.fresh_reg()
                ctx.emit_inst(Const(result_reg=r_text, value=opts.get("TEXT", "")))
                r_res = ctx.fresh_reg()
                ctx.emit_inst(
                    CallFunction(
                        result_reg=r_res,
                        func_name=FuncName(bms_builtin),
                        args=(r_text,),
                    )
                )
                return
            r_map = ctx.fresh_reg()
            ctx.emit_inst(
                Const(result_reg=r_map, value=opts.get("MAP", opts.get("MAPNAME", "")))
            )
            r_set = ctx.fresh_reg()
            ctx.emit_inst(Const(result_reg=r_set, value=opts.get("MAPSET", "")))
            r_region = ctx.fresh_reg()
            ctx.emit_inst(Const(result_reg=r_region, value=b""))
            r_res = ctx.fresh_reg()
            ctx.emit_inst(
                CallFunction(
                    result_reg=r_res,
                    func_name=FuncName(bms_builtin),
                    args=(r_map, r_set, r_region),
                )
            )
            return

        # ── ASSIGN / FORMATTIME: write each output sub-option to its field ──
        if verb == "ASSIGN":
            for subopt in ("APPLID", "SYSID"):
                field_name = opts.get(subopt)
                if field_name is None:
                    continue
                r_key = ctx.fresh_reg()
                ctx.emit_inst(Const(result_reg=r_key, value=subopt))
                r_res = ctx.fresh_reg()
                ctx.emit_inst(
                    CallFunction(
                        result_reg=r_res,
                        func_name=FuncName("__cics_assign"),
                        args=(r_key,),
                    )
                )
                str_reg = ctx.emit_to_string(r_res)
                emit_copy_back_str(ctx, field_name, str_reg, materialised)
            return

        if verb == "FORMATTIME":
            # ABSTIME(src) names the time base; each remaining output sub-option
            # names a field to receive a formatted value.
            for subopt in ("YYYYMMDD", "DATE", "TIME"):
                field_name = opts.get(subopt)
                if field_name is None:
                    continue
                r_key = ctx.fresh_reg()
                ctx.emit_inst(Const(result_reg=r_key, value=subopt))
                r_res = ctx.fresh_reg()
                ctx.emit_inst(
                    CallFunction(
                        result_reg=r_res,
                        func_name=FuncName("__cics_formattime"),
                        args=(r_key,),
                    )
                )
                str_reg = ctx.emit_to_string(r_res)
                emit_copy_back_str(ctx, field_name, str_reg, materialised)
            return

        # ── VSAM point operations ─────────────────────────────────────────
        if verb in _VSAM_POINT_VERBS:
            r_file = ctx.fresh_reg()
            ctx.emit_inst(
                Const(result_reg=r_file, value=(opts.get("FILE") or "").strip("'\" "))
            )
            r_key = emit_copy_in(ctx, opts.get("RIDFLD"), materialised)
            if r_key is None:
                r_key = ctx.fresh_reg()
                ctx.emit_inst(Const(result_reg=r_key, value=b""))
            klen = _resolve_keylen(ctx, opts, materialised)
            r_klen = ctx.fresh_reg()
            ctx.emit_inst(Const(result_reg=r_klen, value=klen))

            if verb == "READ":
                into_off, into_len = _resolve_into(ctx, opts.get("INTO"), materialised)
                r_off = ctx.fresh_reg()
                ctx.emit_inst(Const(result_reg=r_off, value=into_off))
                r_len = ctx.fresh_reg()
                ctx.emit_inst(Const(result_reg=r_len, value=into_len))
                r_res = ctx.fresh_reg()
                ctx.emit_inst(
                    CallFunction(
                        result_reg=r_res,
                        func_name=FuncName("__cics_read"),
                        args=(r_file, r_key, r_klen, r_off, r_len),
                    )
                )
            elif verb in ("WRITE", "REWRITE"):
                r_rec = emit_copy_in(ctx, opts.get("FROM"), materialised)
                if r_rec is None:
                    r_rec = ctx.fresh_reg()
                    ctx.emit_inst(Const(result_reg=r_rec, value=b""))
                name = "__cics_write" if verb == "WRITE" else "__cics_rewrite"
                r_res = ctx.fresh_reg()
                ctx.emit_inst(
                    CallFunction(
                        result_reg=r_res,
                        func_name=FuncName(name),
                        args=(r_file, r_key, r_klen, r_rec),
                    )
                )
            else:  # DELETE
                r_res = ctx.fresh_reg()
                ctx.emit_inst(
                    CallFunction(
                        result_reg=r_res,
                        func_name=FuncName("__cics_delete"),
                        args=(r_file, r_key, r_klen),
                    )
                )
            emit_resp_writeback(ctx, r_res, opts, materialised)
            return

        # ── VSAM browse operations (implicit single cursor per file) ───────
        if verb in _VSAM_BROWSE_VERBS:
            r_file = ctx.fresh_reg()
            ctx.emit_inst(
                Const(result_reg=r_file, value=(opts.get("FILE") or "").strip("'\" "))
            )
            if verb == "STARTBR":
                r_key = emit_copy_in(ctx, opts.get("RIDFLD"), materialised)
                if r_key is None:
                    r_key = ctx.fresh_reg()
                    ctx.emit_inst(Const(result_reg=r_key, value=b""))
                klen = _resolve_keylen(ctx, opts, materialised)
                r_klen = ctx.fresh_reg()
                ctx.emit_inst(Const(result_reg=r_klen, value=klen))
                r_res = ctx.fresh_reg()
                ctx.emit_inst(
                    CallFunction(
                        result_reg=r_res,
                        func_name=FuncName("__cics_startbr"),
                        args=(r_file, r_key, r_klen),
                    )
                )
            elif verb in ("READNEXT", "READPREV"):
                into_off, into_len = _resolve_into(ctx, opts.get("INTO"), materialised)
                r_off = ctx.fresh_reg()
                ctx.emit_inst(Const(result_reg=r_off, value=into_off))
                r_len = ctx.fresh_reg()
                ctx.emit_inst(Const(result_reg=r_len, value=into_len))
                name = "__cics_readnext" if verb == "READNEXT" else "__cics_readprev"
                r_res = ctx.fresh_reg()
                ctx.emit_inst(
                    CallFunction(
                        result_reg=r_res,
                        func_name=FuncName(name),
                        args=(r_file, r_off, r_len),
                    )
                )
            else:  # ENDBR
                r_res = ctx.fresh_reg()
                ctx.emit_inst(
                    CallFunction(
                        result_reg=r_res,
                        func_name=FuncName("__cics_endbr"),
                        args=(r_file,),
                    )
                )
            emit_resp_writeback(ctx, r_res, opts, materialised)
            return

        # ── System verbs ──────────────────────────────────────────────────
        builtin_name = _SYS_VERBS.get(verb)
        if builtin_name:
            r_res = ctx.fresh_reg()
            ctx.emit_inst(
                CallFunction(
                    result_reg=r_res,
                    func_name=FuncName(builtin_name),
                    args=(),
                )
            )
            if verb in _RESP_PRODUCING_VERBS:
                emit_resp_writeback(ctx, r_res, opts, materialised)
            return

        logger.warning(
            "CicsLoweringStrategy: unimplemented verb %r — no IR emitted", verb
        )


class CatchAllLoweringStrategy:
    """Default no-op strategy. Logs a warning for every EXEC CICS statement."""

    def on_procedure_entry(
        self,
        ctx: "EmitContext",
        materialised: "MaterialisedSectionedLayout",
    ) -> None:
        logger.debug("on_procedure_entry: no-op (CatchAllLoweringStrategy)")

    def lower(
        self,
        ctx: "EmitContext",
        stmt: "ExecCicsStatement",
        materialised: "MaterialisedSectionedLayout",
    ) -> None:
        logger.warning("EXEC CICS %s ignored (no CICS strategy injected)", stmt.verb)
