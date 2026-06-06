"""CICS system service builtins — curried closures over shared state."""

from __future__ import annotations

import logging
import struct
from typing import TYPE_CHECKING

from interpreter.vm.vm_types import BuiltinResult, VMState
from interpreter.types.typed_value import TypedValue
from interpreter.var_name import VarName
from interpreter.address import Address

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
