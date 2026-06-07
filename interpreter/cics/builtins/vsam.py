"""CICS VSAM point-operation builtins — curried closures over a VsamEngine.

These are value-in/value-out builtins with one documented exception: ``__cics_read``
fills the program's INTO buffer itself (locked design "Option A"). On a successful
read it writes the record into the WORKING-STORAGE region at the INTO field's
compile-time offset and RETURNS only the response code; the lowering then writes
that resp into EIBRESP/RESP via ``emit_resp_writeback``.

NOTE: the INTO field is assumed to live in WORKING-STORAGE — true for the target
programs. ``_get_ws_region_addr`` locates that region by walking the call stack.

Browse operations (STARTBR/READNEXT/READPREV/ENDBR) are a separate task (D3b).
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from interpreter.cics.builtins.system import _get_ws_region_addr
from interpreter.vm.vm_types import BuiltinResult, VMState

if TYPE_CHECKING:
    from interpreter.cics.vsam.engine import VsamEngine
    from interpreter.types.typed_value import TypedValue

logger = logging.getLogger(__name__)


def _file(args: list[TypedValue], i: int = 0) -> str:
    return str(args[i].value).strip("'\" ") if len(args) > i else ""


def _bytes(args: list[TypedValue], i: int) -> bytes:
    v = args[i].value if len(args) > i else b""
    return (
        bytes(v)
        if isinstance(v, (bytes, bytearray, list))
        else str(v).encode("cp037", "replace")
    )


def _int(args: list[TypedValue], i: int) -> int:
    return int(args[i].value) if len(args) > i else 0


def make_vsam_read_builtin(engine: VsamEngine) -> object:
    """READ: returns the resp code; on success writes the record into INTO buffer.

    args: (file_str, key_bytes, key_len_int, into_offset_int, into_length_int)
    """

    def __cics_read(args: list[TypedValue], vm: VMState) -> BuiltinResult:
        file_name = _file(args, 0)
        key = _bytes(args, 1)
        key_len = _int(args, 2)
        into_off = _int(args, 3)
        into_len = _int(args, 4)

        record, resp = engine.read(file_name, key, key_len)
        if record is not None:
            addr = _get_ws_region_addr(vm)
            if addr is None:
                logger.warning("__cics_read: no __ws_region in VM — INTO not filled")
            else:
                region = vm.region_get(addr)
                if region is None:
                    logger.warning(
                        "__cics_read: WS region not allocated — INTO not filled"
                    )
                else:
                    # Pad/truncate the record to the INTO field length.
                    payload = record[:into_len].ljust(into_len, b"\x00")
                    region[into_off : into_off + into_len] = payload
                    vm.region_set(addr, region)
        return BuiltinResult(value=resp)

    return __cics_read


def make_vsam_write_builtin(engine: VsamEngine) -> object:
    """WRITE: args (file, key_bytes, key_len, record_bytes); returns resp."""

    def __cics_write(args: list[TypedValue], vm: VMState) -> BuiltinResult:
        return BuiltinResult(
            value=engine.write(
                _file(args, 0), _bytes(args, 1), _int(args, 2), _bytes(args, 3)
            )
        )

    return __cics_write


def make_vsam_rewrite_builtin(engine: VsamEngine) -> object:
    """REWRITE: args (file, key_bytes, key_len, record_bytes); returns resp."""

    def __cics_rewrite(args: list[TypedValue], vm: VMState) -> BuiltinResult:
        return BuiltinResult(
            value=engine.rewrite(
                _file(args, 0), _bytes(args, 1), _int(args, 2), _bytes(args, 3)
            )
        )

    return __cics_rewrite


def make_vsam_delete_builtin(engine: VsamEngine) -> object:
    """DELETE: args (file, key_bytes, key_len); returns resp."""

    def __cics_delete(args: list[TypedValue], vm: VMState) -> BuiltinResult:
        return BuiltinResult(
            value=engine.delete(_file(args, 0), _bytes(args, 1), _int(args, 2))
        )

    return __cics_delete
