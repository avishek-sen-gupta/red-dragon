"""BMS screen builtins: SEND MAP, RECEIVE MAP, SEND TEXT."""

from __future__ import annotations

import logging
import queue
import struct
from typing import Any

from interpreter.cics.bms.loader import BmsLoader
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


def _region_bytes(args: list[TypedValue], idx: int = 2) -> bytes:
    v = args[idx].value if len(args) > idx else b""
    if isinstance(v, (bytes, bytearray)):
        return bytes(v)
    if isinstance(v, list):
        return bytes(v)
    return str(v).encode("cp037", errors="replace")


def make_send_map_builtin(
    loader: BmsLoader, screen_queue: "queue.Queue[Any]"
) -> object:
    def __cics_send_map(args: list[TypedValue], vm: VMState) -> BuiltinResult:
        map_name = _map_name(args, 0)
        region = _region_bytes(args, 2)
        bms_map = loader.get(map_name)
        if bms_map is None:
            logger.warning("SEND MAP: unknown map %s", map_name)
            screen_queue.put({"map": map_name, "fields": {}, "raw": region})
            return BuiltinResult(value=None)

        # Preferred path: read each <base>O symbolic output subfield from the
        # WS region via vm.data_layout (mirrors EIB-init). Used when a WS region
        # is locatable and at least one output subfield is in the layout.
        _addr, ws = _ws_region(vm)
        symbolic: dict[str, str] = {}
        if ws is not None:
            for base in bms_map.fields:
                _inp, out_name, _length = bms_map.symbolic_names(base)
                raw = _read_ws_field(vm, ws, out_name)
                if raw is not None:
                    symbolic[base] = raw.decode("cp037", errors="replace").rstrip()
        if symbolic:
            screen_queue.put({"map": map_name, "fields": symbolic, "raw": region})
            return BuiltinResult(value=None)

        # Fallback: flat region byte-slice model.
        fields = bms_map.extract_fields(region)
        screen_queue.put(
            {
                "map": map_name,
                "fields": {
                    k: v.decode("cp037", errors="replace").rstrip()
                    for k, v in fields.items()
                },
                "raw": region,
            }
        )
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
    loader: BmsLoader, input_queue: "queue.Queue[Any]", timeout: float = 30.0
) -> object:
    def __cics_receive_map(args: list[TypedValue], vm: VMState) -> BuiltinResult:
        map_name = _map_name(args, 0)
        region = bytearray(_region_bytes(args, 2))
        bms_map = loader.get(map_name)
        if bms_map is None:
            logger.warning(
                "RECEIVE MAP: unknown map %s — blocking on input_queue", map_name
            )
        try:
            item: Any = input_queue.get(timeout=timeout)
        except queue.Empty:
            logger.warning("RECEIVE MAP: timeout waiting for input")
            return BuiltinResult(value=bytes(region))
        # Duck-type the queue item: an InputEvent carries .fields and .eibaid;
        # a plain dict (legacy producers) is the field map with a default aid.
        field_values: dict[str, bytes | str] = getattr(item, "fields", item)
        aid: str = getattr(item, "eibaid", _DFHENTER)
        _write_eibaid(vm, aid)

        # Preferred path: write each <base>I symbolic input subfield into the WS
        # region via vm.data_layout (mirrors EIB-init). Also set <base>L to the
        # input length when present. Used when a WS region is locatable and the
        # input subfield is in the layout.
        addr, ws = _ws_region(vm)
        if bms_map is not None and ws is not None:
            cp037_space = " ".encode("cp037")  # 0x40
            wrote_symbolic = False
            for base, v in field_values.items():
                if base not in bms_map.fields:
                    continue
                inp_name, _out, length_name = bms_map.symbolic_names(base)
                raw = v if isinstance(v, bytes) else v.encode("cp037", errors="replace")
                if _write_ws_field(vm, ws, inp_name, raw, pad=cp037_space):
                    wrote_symbolic = True
                    _write_ws_field(vm, ws, length_name, struct.pack(">h", len(raw)))
            if wrote_symbolic:
                assert addr is not None  # ws non-None implies addr non-None
                vm.region_set(addr, ws)
                return BuiltinResult(value=bytes(region))

        # Fallback: flat region byte-slice model.
        if bms_map is not None:
            cp037_space = " ".encode("cp037")  # 0x40
            encoded: dict[str, bytes] = {}
            for k, v in field_values.items():
                raw = v if isinstance(v, bytes) else v.encode("cp037", errors="replace")
                fdef = bms_map.fields.get(k)
                if fdef is not None:
                    raw = raw[: fdef.length].ljust(fdef.length, cp037_space)
                encoded[k] = raw
            bms_map.write_fields(region, encoded)
        return BuiltinResult(value=bytes(region))

    return __cics_receive_map


def make_send_text_builtin(screen_queue: "queue.Queue[Any]") -> object:
    def __cics_send_text(args: list[TypedValue], vm: VMState) -> BuiltinResult:
        text = str(args[0].value) if args else ""
        screen_queue.put({"type": "text", "text": text})
        return BuiltinResult(value=None)

    return __cics_send_text
