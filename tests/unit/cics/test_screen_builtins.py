"""Unit tests for BMS screen builtins."""

import queue

import pytest

from tests.covers import covers, NotLanguageFeature
from interpreter.cics.bms.loader import BmsLoader, BmsMap, BmsField
from interpreter.cics.builtins.screen import (
    make_send_map_builtin,
    make_receive_map_builtin,
    make_send_text_builtin,
)
from interpreter.cics.dispatcher import InputEvent
from interpreter.func_name import FuncName
from interpreter.var_name import VarName
from interpreter.address import Address
from interpreter.types.typed_value import typed
from interpreter.types.type_expr import UNKNOWN
from interpreter.vm.vm_types import VMState, StackFrame, BuiltinResult


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


@pytest.mark.skip(reason="re-enabled after Task 7 migration (red-dragon-zvta)")
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


@pytest.mark.skip(reason="re-enabled after Task 7 migration (red-dragon-zvta)")
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


@pytest.mark.skip(reason="re-enabled after Task 7 migration (red-dragon-zvta)")
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


def _make_vm_with_ws_region(region_bytes: bytearray) -> tuple[VMState, Address]:
    vm = VMState()
    addr = Address("ws_region_0")
    vm.region_set(addr, region_bytes)
    frame = StackFrame(
        function_name=FuncName("main"),
        local_vars={VarName("__ws_region"): typed(str(addr), UNKNOWN)},
    )
    vm.call_stack.append(frame)
    vm.data_layout = {
        "EIBAID": {"offset": 0, "length": 1, "category": "ALPHANUMERIC"},
    }
    return vm, addr


@pytest.mark.skip(reason="re-enabled after Task 7 migration (red-dragon-zvta)")
@covers(NotLanguageFeature.INFRASTRUCTURE)
def test_receive_map_writes_eibaid_from_input_event():
    input_q: queue.Queue = queue.Queue()
    loader = _make_loader()
    input_q.put(
        InputEvent(
            eibaid="\x33", fields={"USERID": b"ALICE   ", "PASSWORD": b"SECRET  "}
        )
    )
    builtin = make_receive_map_builtin(loader, input_q)
    vm, addr = _make_vm_with_ws_region(bytearray(8))
    args = [
        typed("COSGN0A", UNKNOWN),
        typed("COSGN0", UNKNOWN),
        typed(b" " * 16, UNKNOWN),
    ]
    result = builtin(args, vm)
    # Field values still land in the INTO region.
    region = bytes(result.value)
    assert region[0:8] == b"ALICE   "
    assert region[8:16] == b"SECRET  "
    # The attention key is written into EIBAID in the WS region.
    ws = vm.region_get(addr)
    assert ws is not None
    assert ws[0] == ord("\x33")


@pytest.mark.skip(reason="re-enabled after Task 7 migration (red-dragon-zvta)")
@covers(NotLanguageFeature.INFRASTRUCTURE)
def test_receive_map_backcompat_dict_leaves_eibaid_default():
    input_q: queue.Queue = queue.Queue()
    loader = _make_loader()
    # Plain dict on the queue (legacy producers) — treated as field values.
    input_q.put({"USERID": b"BOB     ", "PASSWORD": b"PW      "})
    builtin = make_receive_map_builtin(loader, input_q)
    vm, addr = _make_vm_with_ws_region(bytearray(8))
    # Pre-seed EIBAID with a sentinel so a default write is observable.
    ws = vm.region_get(addr)
    assert ws is not None
    ws[0] = 0x00
    vm.region_set(addr, ws)
    args = [
        typed("COSGN0A", UNKNOWN),
        typed("COSGN0", UNKNOWN),
        typed(b" " * 16, UNKNOWN),
    ]
    result = builtin(args, vm)
    region = bytes(result.value)
    assert region[0:8] == b"BOB     "
    ws = vm.region_get(addr)
    assert ws is not None
    assert ws[0] == 0x7D  # default DFHENTER


def _make_vm_with_symbolic_layout(
    region_bytes: bytearray, layout: dict
) -> tuple[VMState, Address]:
    vm = VMState()
    addr = Address("ws_region_0")
    vm.region_set(addr, region_bytes)
    frame = StackFrame(
        function_name=FuncName("main"),
        local_vars={VarName("__ws_region"): typed(str(addr), UNKNOWN)},
    )
    vm.call_stack.append(frame)
    vm.data_layout = layout
    return vm, addr


@pytest.mark.skip(reason="re-enabled after Task 7 migration (red-dragon-zvta)")
@covers(NotLanguageFeature.INFRASTRUCTURE)
def test_receive_map_writes_input_subfields_into_ws():
    input_q: queue.Queue = queue.Queue()
    loader = _make_loader()
    input_q.put(InputEvent(eibaid="\x7d", fields={"USERID": "ALICE"}))
    builtin = make_receive_map_builtin(loader, input_q)
    region = bytearray(" ".encode("cp037") * 16)
    vm, addr = _make_vm_with_symbolic_layout(
        region,
        {
            "USERIDI": {"offset": 0, "length": 8, "category": "ALPHANUMERIC"},
            "USERIDL": {"offset": 8, "length": 2, "category": "BINARY"},
        },
    )
    args = [
        typed("COSGN0A", UNKNOWN),
        typed("COSGN0", UNKNOWN),
        typed(b" " * 16, UNKNOWN),
    ]
    builtin(args, vm)
    ws = vm.region_get(addr)
    assert ws is not None
    assert ws[0:8].decode("cp037").rstrip() == "ALICE"
    # USERIDL set to the input length.
    import struct

    assert struct.unpack(">h", bytes(ws[8:10]))[0] == 5


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
