"""CICS system service builtins — curried closures over shared state."""

from __future__ import annotations

import logging
import struct
from typing import TYPE_CHECKING

from interpreter.vm.vm_types import BuiltinResult, VMState
from interpreter.types.typed_value import TypedValue
from interpreter.var_name import VarName
from interpreter.address import Address
from interpreter.cics.types import DispatchKind, DispatchResult

if TYPE_CHECKING:
    from interpreter.cics.types import CicsContext

logger = logging.getLogger(__name__)


def _ascii_to_ebcdic_bytes(s: str, length: int) -> list[int]:
    from interpreter.cobol.ebcdic_table import EbcdicTable

    padded = s.ljust(length)[:length]
    return [
        EbcdicTable.ASCII_TO_EBCDIC[ord(c)] if ord(c) < 256 else 0x40 for c in padded
    ]


def _get_ws_region_addr(vm: VMState) -> Address | None:
    ws_var = VarName("__ws_region")
    for frame in reversed(vm.call_stack):
        if ws_var in frame.local_vars:
            tv = frame.local_vars[ws_var]
            return Address(str(tv.value))
    return None


def make_init_eib_builtin(context_holder: list[CicsContext]) -> object:
    """Return a builtin that writes EIB fields to WS at procedure entry."""

    def __cics_init_eib(args: list[TypedValue], vm: VMState) -> BuiltinResult:
        ctx = context_holder[0]
        addr = _get_ws_region_addr(vm)
        if addr is None:
            logger.warning(
                "__cics_init_eib: no __ws_region in VM — EIB not initialised"
            )
            return BuiltinResult(value=None)

        region = vm.region_get(addr)
        if region is None:
            logger.warning(
                "__cics_init_eib: WS region not allocated — EIB not initialised"
            )
            return BuiltinResult(value=None)

        layout = vm.data_layout

        def _write_field(name: str, data: list[int]) -> None:
            if name not in layout:
                return
            f = layout[name]
            off, length = f["offset"], f["length"]
            region[off : off + length] = data[:length]

        _write_field("EIBTRNID", _ascii_to_ebcdic_bytes(ctx.transid, 4))
        _write_field("EIBCALEN", list(struct.pack(">h", len(ctx.commarea))))
        aid_byte = ord(ctx.eibaid) if ctx.eibaid else 0x7D
        _write_field("EIBAID", [aid_byte])
        _write_field("EIBRESP", list(struct.pack(">i", 0)))
        _write_field("EIBRESP2", list(struct.pack(">i", 0)))
        vm.region_set(addr, region)
        return BuiltinResult(value=None)

    return __cics_init_eib


def make_assign_builtin(applid: str = "CARDDEMO", sysid: str = "SYS1") -> object:
    def __cics_assign(args: list[TypedValue], vm: VMState) -> BuiltinResult:
        return BuiltinResult(value=None)

    return __cics_assign


def make_asktime_builtin() -> object:
    def __cics_asktime(args: list[TypedValue], vm: VMState) -> BuiltinResult:
        from datetime import datetime, timezone

        epoch_1900 = datetime(1900, 1, 1, tzinfo=timezone.utc)
        now = datetime.now(timezone.utc)
        abstime = int((now - epoch_1900).total_seconds() * 1_000_000)
        return BuiltinResult(value=abstime)

    return __cics_asktime


def make_formattime_builtin() -> object:
    def __cics_formattime(args: list[TypedValue], vm: VMState) -> BuiltinResult:
        from datetime import datetime, timezone

        return BuiltinResult(value=datetime.now(timezone.utc).strftime("%Y%m%d"))

    return __cics_formattime


def make_writeq_td_builtin(queue: list[str]) -> object:
    def __cics_writeq_td(args: list[TypedValue], vm: VMState) -> BuiltinResult:
        data = str(args[0].value) if args else ""
        name = str(args[1].value) if len(args) > 1 else "CSMT"
        queue.append(f"[{name}] {data}")
        return BuiltinResult(value=None)

    return __cics_writeq_td


def make_handle_abend_builtin() -> object:
    def __cics_handle_abend(args: list[TypedValue], vm: VMState) -> BuiltinResult:
        logger.info("HANDLE ABEND — no-op in emulation")
        return BuiltinResult(value=None)

    return __cics_handle_abend


def make_handle_noop_builtin(verb: str) -> object:
    """Explicit no-op for HANDLE CONDITION / HANDLE AID.

    Deferred to the HANDLE runtime-dispatch machinery follow-up
    (docs/superpowers/plans/2026-06-07-cics-handle-condition-machinery.md). The
    registration args (condition/AID -> label pairs) are intentionally ignored;
    we log so the deferral is visible rather than silently dropped.
    """

    def __cics_handle_noop(args: list[TypedValue], vm: VMState) -> BuiltinResult:
        logger.info("%s ignored (no-op; HANDLE machinery deferred)", verb)
        return BuiltinResult(value=None)

    return __cics_handle_noop


def make_abend_builtin(result_holder: list) -> object:  # type: ignore[type-arg]
    def __cics_abend(args: list[TypedValue], vm: VMState) -> BuiltinResult:
        abcode = str(args[0].value) if args else "UNKN"
        result_holder[0] = DispatchResult(kind=DispatchKind.ABEND, abcode=abcode)
        return BuiltinResult(value=None)

    return __cics_abend


def make_inquire_builtin(program_cache: dict) -> object:  # type: ignore[type-arg]
    def __cics_inquire(args: list[TypedValue], vm: VMState) -> BuiltinResult:
        name = str(args[0].value).strip() if args else ""
        resp = 0 if name in program_cache else 27  # 27 = PGMIDERR
        return BuiltinResult(value=resp)

    return __cics_inquire
