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
    make_abend_builtin,
)
from interpreter.func_name import FuncName
from interpreter.instructions import CallFunction, Const, Return_
from interpreter.register import NO_REGISTER

if TYPE_CHECKING:
    from interpreter.cobol.emit_context import EmitContext
    from interpreter.cobol.cobol_statements import ExecCicsStatement
    from interpreter.cobol.sectioned_layout import MaterialisedSectionedLayout
    from interpreter.cics.types import CicsContext

logger = logging.getLogger(__name__)

_BUILTIN_INIT_EIB = FuncName("__cics_init_eib")

_SYS_VERBS: dict[str, str] = {
    "ASSIGN": "__cics_assign",
    "ASKTIME": "__cics_asktime",
    "FORMATTIME": "__cics_formattime",
    "INQUIRE": "__cics_inquire",
    "WRITEQ TD": "__cics_writeq_td",
    "HANDLE ABEND": "__cics_handle_abend",
    "HANDLE CONDITION": "__cics_handle_abend",
    "HANDLE AID": "__cics_handle_abend",
}


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
                r_transid = ctx.fresh_reg()
                ctx.emit_inst(
                    Const(result_reg=r_transid, value=opts.get("TRANSID", ""))
                )
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
            r_prog = ctx.fresh_reg()
            prog_opt = opts.get("PROGRAM", "")
            ctx.emit_inst(Const(result_reg=r_prog, value=prog_opt))
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
