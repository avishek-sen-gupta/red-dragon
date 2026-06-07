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
            field_values: dict[str, bytes | str] = input_queue.get(timeout=timeout)
        except queue.Empty:
            logger.warning("RECEIVE MAP: timeout waiting for input")
            return BuiltinResult(value=bytes(region))
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
