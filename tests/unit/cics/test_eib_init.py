"""Unit tests for EIB initialization builtin."""

import struct
from tests.covers import covers, NotLanguageFeature
from interpreter.cics.types import CicsContext
from interpreter.cics.builtins.system import make_init_eib_builtin
from interpreter.vm.vm_types import VMState, StackFrame, BuiltinResult
from interpreter.func_name import FuncName
from interpreter.var_name import VarName
from interpreter.address import Address
from interpreter.types.typed_value import typed
from interpreter.types.type_expr import scalar


def _make_vm_with_ws_region(region_bytes: bytearray) -> tuple[VMState, Address]:
    vm = VMState()
    addr = Address("ws_region_0")
    vm.region_set(addr, region_bytes)
    frame = StackFrame(
        function_name=FuncName("main"),
        local_vars={VarName("__ws_region"): typed(str(addr), scalar("str"))},
    )
    vm.call_stack.append(frame)
    vm.data_layout = {
        "EIBTRNID": {"offset": 0, "length": 4, "category": "ALPHANUMERIC"},
        "EIBCALEN": {"offset": 4, "length": 2, "category": "BINARY"},
        "EIBAID": {"offset": 6, "length": 1, "category": "ALPHANUMERIC"},
        "EIBRESP": {"offset": 7, "length": 4, "category": "BINARY"},
        "EIBRESP2": {"offset": 11, "length": 4, "category": "BINARY"},
    }
    return vm, addr


@covers(NotLanguageFeature.INFRASTRUCTURE)
def test_eib_init_writes_transid():
    ctx = CicsContext(transid="CC00", commarea=b"", eibaid="\x7d")
    builtin = make_init_eib_builtin([ctx])
    vm, addr = _make_vm_with_ws_region(bytearray(64))
    result = builtin([], vm)
    assert isinstance(result, BuiltinResult)
    region = vm.region_get(addr)
    assert region is not None
    assert region[0:4] != bytearray(4)  # EIBTRNID written


@covers(NotLanguageFeature.INFRASTRUCTURE)
def test_eib_init_writes_eibcalen():
    ctx = CicsContext(transid="CC00", commarea=b"\x00" * 24, eibaid="\x7d")
    builtin = make_init_eib_builtin([ctx])
    vm, addr = _make_vm_with_ws_region(bytearray(64))
    builtin([], vm)
    region = vm.region_get(addr)
    assert region is not None
    calen = struct.unpack(">h", bytes(region[4:6]))[0]
    assert calen == 24


@covers(NotLanguageFeature.INFRASTRUCTURE)
def test_eib_init_writes_zero_calen_for_empty_commarea():
    ctx = CicsContext(transid="CC00", commarea=b"", eibaid="\x7d")
    builtin = make_init_eib_builtin([ctx])
    vm, addr = _make_vm_with_ws_region(bytearray(64))
    builtin([], vm)
    region = vm.region_get(addr)
    calen = struct.unpack(">h", bytes(region[4:6]))[0]
    assert calen == 0
