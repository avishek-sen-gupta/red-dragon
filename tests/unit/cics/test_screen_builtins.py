"""Unit tests for BMS screen builtins."""

import queue

from tests.covers import covers, NotLanguageFeature
from interpreter.cics.bms.loader import BmsLoader, BmsMap, BmsField
from interpreter.cics.builtins.screen import (
    make_send_map_builtin,
    make_receive_map_builtin,
    make_send_text_builtin,
)
from interpreter.types.typed_value import typed
from interpreter.types.type_expr import UNKNOWN
from interpreter.vm.vm_types import VMState, BuiltinResult


def _make_loader() -> BmsLoader:
    loader = BmsLoader(maps_dir=None)
    loader.register_stub(
        "COSGN0A",
        BmsMap(
            name="COSGN0A",
            fields={
                "USERID": BmsField(offset=0, length=8),
                "PASSWORD": BmsField(offset=8, length=8),
            },
        ),
    )
    return loader


@covers(NotLanguageFeature.INFRASTRUCTURE)
def test_send_map_enqueues_screen():
    screen_q: queue.Queue = queue.Queue()
    loader = _make_loader()
    builtin = make_send_map_builtin(loader, screen_q)
    args = [
        typed("COSGN0A", UNKNOWN),
        typed("COSGN0", UNKNOWN),
        typed(b" " * 16, UNKNOWN),
    ]
    result = builtin(args, VMState())
    assert isinstance(result, BuiltinResult)
    assert not screen_q.empty()
    screen = screen_q.get_nowait()
    assert screen["map"] == "COSGN0A"
    assert "fields" in screen


@covers(NotLanguageFeature.INFRASTRUCTURE)
def test_send_map_unknown_map_enqueues_empty_fields():
    screen_q: queue.Queue = queue.Queue()
    loader = _make_loader()
    builtin = make_send_map_builtin(loader, screen_q)
    args = [typed("NOPE", UNKNOWN), typed("SET", UNKNOWN), typed(b" " * 8, UNKNOWN)]
    builtin(args, VMState())
    screen = screen_q.get_nowait()
    assert screen["map"] == "NOPE"
    assert screen["fields"] == {}


@covers(NotLanguageFeature.INFRASTRUCTURE)
def test_receive_map_returns_field_values():
    input_q: queue.Queue = queue.Queue()
    loader = _make_loader()
    input_q.put({"USERID": b"ALICE   ", "PASSWORD": b"SECRET  "})
    builtin = make_receive_map_builtin(loader, input_q)
    args = [
        typed("COSGN0A", UNKNOWN),
        typed("COSGN0", UNKNOWN),
        typed(b" " * 16, UNKNOWN),
    ]
    result = builtin(args, VMState())
    assert result.value is not None
    region = bytes(result.value)
    assert region[0:8] == b"ALICE   "
    assert region[8:16] == b"SECRET  "


@covers(NotLanguageFeature.INFRASTRUCTURE)
def test_receive_map_accepts_str_field_values():
    input_q: queue.Queue = queue.Queue()
    loader = _make_loader()
    input_q.put({"USERID": "BOB"})
    builtin = make_receive_map_builtin(loader, input_q)
    args = [
        typed("COSGN0A", UNKNOWN),
        typed("COSGN0", UNKNOWN),
        typed(b" " * 16, UNKNOWN),
    ]
    result = builtin(args, VMState())
    region = bytes(result.value)
    # "BOB" encoded to cp037 then space-padded to length 8
    assert region[0:8].decode("cp037").rstrip() == "BOB"


@covers(NotLanguageFeature.INFRASTRUCTURE)
def test_receive_map_timeout_returns_unchanged_region():
    input_q: queue.Queue = queue.Queue()
    loader = _make_loader()
    builtin = make_receive_map_builtin(loader, input_q, timeout=0.1)
    args = [
        typed("COSGN0A", UNKNOWN),
        typed("COSGN0", UNKNOWN),
        typed(b"X" * 16, UNKNOWN),
    ]
    result = builtin(args, VMState())
    assert bytes(result.value) == b"X" * 16


@covers(NotLanguageFeature.INFRASTRUCTURE)
def test_send_text_enqueues_text():
    screen_q: queue.Queue = queue.Queue()
    builtin = make_send_text_builtin(screen_q)
    args = [typed("Hello, world!", UNKNOWN)]
    result = builtin(args, VMState())
    assert isinstance(result, BuiltinResult)
    item = screen_q.get_nowait()
    assert item["type"] == "text"
    assert "Hello" in item["text"]
