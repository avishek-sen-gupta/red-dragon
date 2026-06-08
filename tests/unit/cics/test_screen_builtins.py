"""Unit tests for BMS screen builtins."""

import queue

from tests.covers import covers, NotLanguageFeature
from interpreter.cics.builtins.screen import (
    make_send_map_builtin,
    make_receive_map_builtin,
    make_send_text_builtin,
)
from interpreter.cics.dispatcher import InputEvent
from interpreter.types.typed_value import typed
from interpreter.types.type_expr import UNKNOWN
from interpreter.vm.vm_types import VMState, BuiltinResult


class _FakeVM:
    def __init__(self, region, layout, addr=1):
        self._region = region
        self.data_layout = layout
        self._addr = addr

    def region_get(self, addr):
        return self._region if addr == self._addr else None


def _tv(v):
    return typed(v, UNKNOWN)


@covers(NotLanguageFeature.INFRASTRUCTURE)
def test_send_map_reads_named_output_fields_from_ws(monkeypatch):
    layout = {
        "USERIDO": {"offset": 0, "length": 8},
        "ERRMSGO": {"offset": 8, "length": 78},
    }
    region = bytearray(b"\x40" * 86)
    region[0:8] = "USER0001".encode("cp037")
    vm = _FakeVM(region, layout)
    monkeypatch.setattr(
        "interpreter.cics.builtins.system._get_ws_region_addr", lambda _vm: 1
    )
    sq: queue.Queue = queue.Queue()
    builtin = make_send_map_builtin(sq)
    builtin([_tv("COSGN0A"), _tv(["USERID", "ERRMSG"])], vm)
    item = sq.get_nowait()
    assert item["map"] == "COSGN0A"
    assert item["fields"]["USERID"] == "USER0001"
    assert item["fields"]["ERRMSG"] == ""


@covers(NotLanguageFeature.INFRASTRUCTURE)
def test_receive_map_writes_eibaid_from_input_event(monkeypatch):
    layout = {
        "USERIDI": {"offset": 0, "length": 8},
        "EIBAID": {"offset": 200, "length": 1},
    }
    region = bytearray(b"\x40" * 210)
    vm = _FakeVM(region, layout)
    monkeypatch.setattr(
        "interpreter.cics.builtins.system._get_ws_region_addr", lambda _vm: 1
    )
    vm.region_set = lambda addr, data: region.__setitem__(slice(0, len(data)), data)
    iq: queue.Queue = queue.Queue()
    iq.put(InputEvent(eibaid="\x33", fields={"USERID": "ALICE"}))
    builtin = make_receive_map_builtin(iq, timeout=1.0)
    builtin([_tv("COSGN0A"), _tv(["USERID"])], vm)
    # The attention key from the InputEvent lands in EIBAID in the WS region.
    assert region[200] == ord("\x33")


@covers(NotLanguageFeature.INFRASTRUCTURE)
def test_receive_map_backcompat_dict_leaves_eibaid_default(monkeypatch):
    layout = {
        "USERIDI": {"offset": 0, "length": 8},
        "EIBAID": {"offset": 200, "length": 1},
    }
    region = bytearray(b"\x40" * 210)
    # Pre-seed EIBAID with a sentinel so the default write is observable.
    region[200] = 0x00
    vm = _FakeVM(region, layout)
    monkeypatch.setattr(
        "interpreter.cics.builtins.system._get_ws_region_addr", lambda _vm: 1
    )
    vm.region_set = lambda addr, data: region.__setitem__(slice(0, len(data)), data)
    iq: queue.Queue = queue.Queue()
    # Plain dict on the queue (legacy producers) — duck-typed as field values
    # with no .eibaid, so the default DFHENTER aid is written.
    iq.put({"USERID": "BOB"})
    builtin = make_receive_map_builtin(iq, timeout=1.0)
    builtin([_tv("COSGN0A"), _tv(["USERID"])], vm)
    # A named input field still writes into the WS region.
    assert region[0:8].decode("cp037").rstrip() == "BOB"
    # Default EIBAID (DFHENTER) is written when the item has no .eibaid.
    assert region[200] == 0x7D


class _InputEvent:
    def __init__(self, fields, eibaid="\x7d"):
        self.fields = fields
        self.eibaid = eibaid


@covers(NotLanguageFeature.INFRASTRUCTURE)
def test_receive_map_writes_named_input_fields_to_ws(monkeypatch):
    import struct

    layout = {
        "USERIDI": {"offset": 0, "length": 8},
        "USERIDL": {"offset": 100, "length": 2},
        "EIBAID": {"offset": 200, "length": 1},
    }
    region = bytearray(b"\x40" * 210)
    vm = _FakeVM(region, layout)
    monkeypatch.setattr(
        "interpreter.cics.builtins.system._get_ws_region_addr", lambda _vm: 1
    )
    vm.region_set = lambda addr, data: region.__setitem__(slice(0, len(data)), data)
    iq: queue.Queue = queue.Queue()
    iq.put(_InputEvent({"USERID": "USER0001"}))
    builtin = make_receive_map_builtin(iq, timeout=1.0)
    builtin([_tv("COSGN0A"), _tv(["USERID"])], vm)
    assert bytes(region[0:8]) == "USER0001".encode("cp037")
    assert struct.unpack(">h", bytes(region[100:102]))[0] == 8


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
