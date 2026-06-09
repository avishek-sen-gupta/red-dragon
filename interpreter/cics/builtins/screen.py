"""BMS screen builtins: SEND MAP, RECEIVE MAP, SEND TEXT."""

from __future__ import annotations

import logging
import queue
import struct
from typing import Any

from interpreter.cics.terminal import InputChannel, ScreenChannel
from interpreter.types.typed_value import TypedValue
from interpreter.vm.vm_types import BuiltinResult, VMState

logger = logging.getLogger(__name__)


def _map_name(args: list[TypedValue], idx: int = 0) -> str:
    return str(args[idx].value).strip("'\" ") if len(args) > idx else ""


def _ws_region(vm: VMState):
    """Locate the (addr, region bytearray) for the WS region, or (None, None).

    Mirrors ``make_init_eib_builtin``: the WS region address lives in the
    ``__ws_region`` local var and its bytes in ``vm.region_get``.
    """
    from interpreter.cics.builtins.system import _get_ws_region_addr

    if vm is None:
        return None, None
    addr = _get_ws_region_addr(vm)
    if addr is None:
        return None, None
    region = vm.region_get(addr)
    if region is None:
        return None, None
    return addr, region


def _read_ws_field(vm: VMState, region, name: str) -> bytes | None:
    """Read a named field's bytes from the WS region via vm.data_layout."""
    f = vm.data_layout.get(name)
    if f is None:
        return None
    off, length = f["offset"], f["length"]
    return bytes(region[off : off + length])


def _write_ws_field(
    vm: VMState, region, name: str, data: bytes, pad: bytes = b"\x00"
) -> bool:
    """Write data into a named field in the WS region via vm.data_layout.

    Truncates/pads to the field length (pad byte defaults to NUL; pass the
    cp037 space for alphanumeric fields). Returns True if the field was present
    in the layout and written.
    """
    f = vm.data_layout.get(name)
    if f is None:
        return False
    off, length = f["offset"], f["length"]
    region[off : off + length] = data[:length].ljust(length, pad)[:length]
    return True


def make_send_map_builtin(screen_queue: ScreenChannel) -> object:
    def __cics_send_map(args: list[TypedValue], vm: VMState) -> BuiltinResult:
        map_name = _map_name(args, 0)
        base_names = (
            list(args[1].value)
            if len(args) > 1 and isinstance(args[1].value, list)
            else []
        )
        _addr, ws = _ws_region(vm)
        symbolic: dict[str, str] = {}
        if ws is not None:
            for base in base_names:
                raw = _read_ws_field(vm, ws, base + "O")
                if raw is not None:
                    symbolic[base] = raw.decode("cp037", errors="replace").rstrip()
        screen_queue.put({"map": map_name, "fields": symbolic})
        return BuiltinResult(value=None)

    return __cics_send_map


_DFHENTER = "\x7d"


def _write_eibaid(vm: VMState, aid: str) -> None:
    """Write the attention id into the EIB's EIBAID field in the WS region.

    Mirrors ``make_init_eib_builtin``'s single-byte EIBAID write. Missing WS
    region or no EIBAID in the data layout → log + skip (non-fatal).
    """
    addr, region = _ws_region(vm)
    if region is None:
        logger.warning("RECEIVE MAP: no WS region — EIBAID not updated")
        return
    assert addr is not None  # region non-None implies addr non-None (_ws_region)
    aid_byte = ord(aid) if aid else 0x7D
    if _write_ws_field(vm, region, "EIBAID", bytes([aid_byte])):
        vm.region_set(addr, region)
    else:
        logger.warning("RECEIVE MAP: EIBAID not in data layout — EIBAID not updated")


def make_receive_map_builtin(
    input_queue: InputChannel, timeout: float = 30.0
) -> object:
    def __cics_receive_map(args: list[TypedValue], vm: VMState) -> BuiltinResult:
        base_names = (
            set(args[1].value)
            if len(args) > 1 and isinstance(args[1].value, list)
            else set()
        )
        try:
            item: Any = input_queue.get(timeout=timeout)
        except queue.Empty:
            logger.warning("RECEIVE MAP: timeout waiting for input")
            return BuiltinResult(value=None)
        # Duck-type the queue item: an InputEvent carries .fields and .eibaid;
        # a plain dict (legacy producers) is the field map with a default aid.
        field_values: dict[str, bytes | str] = getattr(item, "fields", item)
        aid: str = getattr(item, "eibaid", _DFHENTER)
        _write_eibaid(vm, aid)

        addr, ws = _ws_region(vm)
        if ws is not None:
            cp037_space = " ".encode("cp037")  # 0x40
            for base, v in field_values.items():
                if base not in base_names:
                    continue
                raw = v if isinstance(v, bytes) else v.encode("cp037", errors="replace")
                if _write_ws_field(vm, ws, base + "I", raw, pad=cp037_space):
                    _write_ws_field(vm, ws, base + "L", struct.pack(">h", len(raw)))
            assert addr is not None  # ws non-None implies addr non-None
            vm.region_set(addr, ws)
        return BuiltinResult(value=None)

    return __cics_receive_map


def make_send_text_builtin(screen_queue: ScreenChannel) -> object:
    def __cics_send_text(args: list[TypedValue], vm: VMState) -> BuiltinResult:
        text = str(args[0].value) if args else ""
        screen_queue.put({"type": "text", "text": text})
        return BuiltinResult(value=None)

    return __cics_send_text
