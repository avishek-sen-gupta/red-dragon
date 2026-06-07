"""BMS screen builtins: SEND MAP, RECEIVE MAP, SEND TEXT."""

from __future__ import annotations

import logging
import queue
from typing import Any

from interpreter.cics.bms.loader import BmsLoader
from interpreter.types.typed_value import TypedValue
from interpreter.vm.vm_types import BuiltinResult, VMState

logger = logging.getLogger(__name__)


def _map_name(args: list[TypedValue], idx: int = 0) -> str:
    return str(args[idx].value).strip("'\" ") if len(args) > idx else ""


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
    from interpreter.cics.builtins.system import _get_ws_region_addr

    if vm is None:
        logger.warning("RECEIVE MAP: no VM state — EIBAID not updated")
        return
    addr = _get_ws_region_addr(vm)
    if addr is None:
        logger.warning("RECEIVE MAP: no __ws_region in VM — EIBAID not updated")
        return
    region = vm.region_get(addr)
    if region is None:
        logger.warning("RECEIVE MAP: WS region not allocated — EIBAID not updated")
        return
    f = vm.data_layout.get("EIBAID")
    if f is None:
        logger.warning("RECEIVE MAP: EIBAID not in data layout — EIBAID not updated")
        return
    off = f["offset"]
    aid_byte = ord(aid) if aid else 0x7D
    region[off : off + 1] = bytes([aid_byte])
    vm.region_set(addr, region)


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
