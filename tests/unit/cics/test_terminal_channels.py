"""Conformance tests for the terminal-channel protocols.

Proves the CICS region's screen/input seams are swappable: a MINIMAL custom
channel object (NOT a queue.Queue) that implements the ScreenChannel /
InputChannel protocols can drive SEND MAP and RECEIVE MAP. This is the payoff
of extracting the protocols — an external/out-of-process producer (socket,
websocket, multiprocessing) can plug in by implementing put/get without
touching program/VM/strategy logic.
"""

import struct

from tests.covers import covers, NotLanguageFeature
from interpreter.cics.builtins.screen import (
    make_send_map_builtin,
    make_receive_map_builtin,
    make_send_text_builtin,
)
from interpreter.cics.dispatcher import InputEvent
from interpreter.cics.terminal import ScreenChannel, InputChannel
from interpreter.types.typed_value import typed
from interpreter.types.type_expr import UNKNOWN
from interpreter.vm.vm_types import VMState


class _ListScreenChannel:
    """A non-queue ScreenChannel backed by a plain list (e.g. a stand-in for
    an external transport that would serialise+send each rendered screen)."""

    def __init__(self):
        self.items = []

    def put(self, item):
        self.items.append(item)


class _ListInputChannel:
    """A non-queue InputChannel backed by a list. Mirrors queue.Queue.get's
    signature (block=True, timeout=None) so the region's .get()/.get(timeout=)
    calls work over an arbitrary transport."""

    def __init__(self):
        self.items = []

    def put(self, item):
        self.items.append(item)

    def get(self, block=True, timeout=None):
        return self.items.pop(0)


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
def test_custom_screen_channel_satisfies_protocol():
    """A bare put()-only object structurally conforms to ScreenChannel."""
    ch = _ListScreenChannel()
    assert isinstance(ch, ScreenChannel)


@covers(NotLanguageFeature.INFRASTRUCTURE)
def test_custom_input_channel_satisfies_protocol():
    """A put()/get(block, timeout) object structurally conforms to InputChannel."""
    ch = _ListInputChannel()
    assert isinstance(ch, InputChannel)


@covers(NotLanguageFeature.INFRASTRUCTURE)
def test_send_map_drives_a_custom_non_queue_channel(monkeypatch):
    """SEND MAP puts a rendered screen dict on a non-queue ScreenChannel."""
    layout = {"USERIDO": {"offset": 0, "length": 8}}
    region = bytearray(b"\x40" * 8)
    region[0:8] = "USER0001".encode("cp037")
    vm = _FakeVM(region, layout)
    monkeypatch.setattr(
        "interpreter.cics.builtins.system._get_ws_region_addr", lambda _vm: 1
    )
    ch = _ListScreenChannel()
    builtin = make_send_map_builtin(ch)
    builtin([_tv("COSGN0A"), _tv(["USERID"])], vm)
    assert len(ch.items) == 1
    assert ch.items[0]["map"] == "COSGN0A"
    assert ch.items[0]["fields"]["USERID"] == "USER0001"


@covers(NotLanguageFeature.INFRASTRUCTURE)
def test_send_text_drives_a_custom_non_queue_channel():
    """SEND TEXT puts a text dict on a non-queue ScreenChannel."""
    ch = _ListScreenChannel()
    builtin = make_send_text_builtin(ch)
    builtin([_tv("Hello")], VMState())
    assert len(ch.items) == 1
    assert ch.items[0] == {"type": "text", "text": "Hello"}


@covers(NotLanguageFeature.INFRASTRUCTURE)
def test_receive_map_consumes_from_a_custom_non_queue_channel(monkeypatch):
    """RECEIVE MAP gets an InputEvent through a non-queue InputChannel and
    writes its fields + eibaid into the WS region."""
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
    ch = _ListInputChannel()
    ch.put(InputEvent(eibaid="\x33", fields={"USERID": "USER0001"}))
    builtin = make_receive_map_builtin(ch, timeout=1.0)
    builtin([_tv("COSGN0A"), _tv(["USERID"])], vm)
    assert bytes(region[0:8]) == "USER0001".encode("cp037")
    assert struct.unpack(">h", bytes(region[100:102]))[0] == 8
    assert region[200] == ord("\x33")
