"""Unit tests for VSAM point-operation builtins + lowering (Task D3a)."""

from __future__ import annotations

import tempfile
from pathlib import Path

from tests.covers import covers, NotLanguageFeature
from interpreter.cics.vsam.engine import (
    VsamEngine,
    RESP_NORMAL,
    RESP_NOTFND,
    RESP_ENDFILE,
)
from interpreter.cics.vsam.fct import FctConfig, DatasetConfig
from interpreter.cics.builtins.vsam import (
    make_vsam_read_builtin,
    make_vsam_write_builtin,
    make_vsam_rewrite_builtin,
    make_vsam_delete_builtin,
    make_vsam_startbr_builtin,
    make_vsam_readnext_builtin,
    make_vsam_readprev_builtin,
    make_vsam_endbr_builtin,
)
from interpreter.vm.vm_types import VMState, StackFrame, BuiltinResult
from interpreter.func_name import FuncName
from interpreter.cics.cics_parser import CicsOperand
from interpreter.var_name import VarName
from interpreter.address import Address
from interpreter.types.typed_value import typed
from interpreter.types.type_expr import UNKNOWN

REC_LEN = 10
KEY_LEN = 4


def _rec(key: str, rest: str = "") -> bytes:
    body = rest.ljust(REC_LEN - KEY_LEN)[: REC_LEN - KEY_LEN]
    return (key.ljust(KEY_LEN)[:KEY_LEN] + body).encode()


def _engine_with_records(records: list[bytes]) -> VsamEngine:
    td = tempfile.mkdtemp()
    p = Path(td) / "data.txt"
    with p.open("wb") as f:
        for r in records:
            f.write(r)
    config = FctConfig(
        datasets={"TESTDS": DatasetConfig(path=p, record_length=REC_LEN)}
    )
    engine = VsamEngine(config)
    engine.load_all()
    return engine


def _make_vm_with_ws_region(region_bytes: bytearray) -> tuple[VMState, Address]:
    vm = VMState()
    addr = Address("ws_region_0")
    vm.region_set(addr, region_bytes)
    frame = StackFrame(
        function_name=FuncName("main"),
        local_vars={VarName("__ws_region"): typed(str(addr), UNKNOWN)},
    )
    vm.call_stack.append(frame)
    return vm, addr


def _args(*vals):
    return [typed(v, UNKNOWN) for v in vals]


@covers(NotLanguageFeature.INFRASTRUCTURE)
def test_write_then_read_round_trip_fills_buffer():
    """WRITE stores a record; READ writes it into the INTO buffer at the offset."""
    engine = _engine_with_records([])
    write = make_vsam_write_builtin(engine)
    read = make_vsam_read_builtin(engine)
    record = _rec("AA01", "HELLO")

    wresult = write(_args("TESTDS", b"AA01", KEY_LEN, record), VMState())
    assert isinstance(wresult, BuiltinResult)
    assert wresult.value == RESP_NORMAL

    # INTO field lives at offset 4, length REC_LEN within a 32-byte WS region.
    into_off, into_len = 4, REC_LEN
    vm, addr = _make_vm_with_ws_region(bytearray(32))
    rresult = read(_args("TESTDS", b"AA01", KEY_LEN, into_off, into_len), vm)
    assert isinstance(rresult, BuiltinResult)
    assert rresult.value == RESP_NORMAL
    region = vm.region_get(addr)
    assert region is not None
    assert bytes(region[into_off : into_off + into_len]) == record


@covers(NotLanguageFeature.INFRASTRUCTURE)
def test_read_not_found_returns_notfnd_and_does_not_write_buffer():
    engine = _engine_with_records([_rec("AA01", "DATA")])
    read = make_vsam_read_builtin(engine)
    vm, addr = _make_vm_with_ws_region(bytearray(32))
    rresult = read(_args("TESTDS", b"ZZ99", KEY_LEN, 4, REC_LEN), vm)
    assert rresult.value == RESP_NOTFND
    region = vm.region_get(addr)
    assert region is not None
    # Buffer untouched (all zero bytes still).
    assert bytes(region[4 : 4 + REC_LEN]) == b"\x00" * REC_LEN


@covers(NotLanguageFeature.INFRASTRUCTURE)
def test_delete_removes_record():
    engine = _engine_with_records([_rec("AA01", "DATA")])
    delete = make_vsam_delete_builtin(engine)
    read = make_vsam_read_builtin(engine)
    dresult = delete(_args("TESTDS", b"AA01", KEY_LEN), VMState())
    assert dresult.value == RESP_NORMAL
    vm, _ = _make_vm_with_ws_region(bytearray(32))
    rresult = read(_args("TESTDS", b"AA01", KEY_LEN, 4, REC_LEN), vm)
    assert rresult.value == RESP_NOTFND


@covers(NotLanguageFeature.INFRASTRUCTURE)
def test_rewrite_updates_record():
    engine = _engine_with_records([_rec("AA01", "OLD")])
    rewrite = make_vsam_rewrite_builtin(engine)
    read = make_vsam_read_builtin(engine)
    rwresult = rewrite(
        _args("TESTDS", b"AA01", KEY_LEN, _rec("AA01", "NEW")), VMState()
    )
    assert rwresult.value == RESP_NORMAL
    vm, addr = _make_vm_with_ws_region(bytearray(32))
    read(_args("TESTDS", b"AA01", KEY_LEN, 0, REC_LEN), vm)
    region = vm.region_get(addr)
    assert region is not None
    assert b"NEW" in bytes(region[0:REC_LEN])


@covers(NotLanguageFeature.INFRASTRUCTURE)
def test_read_no_ws_region_still_returns_resp():
    """No __ws_region in VM: buffer write is skipped but resp still returned."""
    engine = _engine_with_records([_rec("AA01", "DATA")])
    read = make_vsam_read_builtin(engine)
    rresult = read(_args("TESTDS", b"AA01", KEY_LEN, 4, REC_LEN), VMState())
    assert rresult.value == RESP_NORMAL


# ── Browse builtin tests ──────────────────────────────────────────────────────


@covers(NotLanguageFeature.INFRASTRUCTURE)
def test_browse_forward_fills_buffer_in_key_order():
    """STARTBR then READNEXT twice fills the INTO buffer with successive records."""
    rec_a = _rec("AA01", "ALPHA")
    rec_b = _rec("BB02", "BRAVO")
    engine = _engine_with_records([rec_b, rec_a])  # written out of order
    startbr = make_vsam_startbr_builtin(engine)
    readnext = make_vsam_readnext_builtin(engine)

    sresult = startbr(_args("TESTDS", b"\x00" * KEY_LEN, KEY_LEN), VMState())
    assert isinstance(sresult, BuiltinResult)
    assert sresult.value == RESP_NORMAL

    into_off, into_len = 4, REC_LEN
    vm, addr = _make_vm_with_ws_region(bytearray(32))
    r1 = readnext(_args("TESTDS", into_off, into_len), vm)
    assert r1.value == RESP_NORMAL
    region = vm.region_get(addr)
    assert region is not None
    assert bytes(region[into_off : into_off + into_len]) == rec_a  # sorted first

    r2 = readnext(_args("TESTDS", into_off, into_len), vm)
    assert r2.value == RESP_NORMAL
    region = vm.region_get(addr)
    assert region is not None
    assert bytes(region[into_off : into_off + into_len]) == rec_b


@covers(NotLanguageFeature.INFRASTRUCTURE)
def test_readnext_past_end_returns_endfile():
    engine = _engine_with_records([_rec("AA01", "ONE")])
    startbr = make_vsam_startbr_builtin(engine)
    readnext = make_vsam_readnext_builtin(engine)
    startbr(_args("TESTDS", b"\x00" * KEY_LEN, KEY_LEN), VMState())
    vm, _ = _make_vm_with_ws_region(bytearray(32))
    first = readnext(_args("TESTDS", 4, REC_LEN), vm)
    assert first.value == RESP_NORMAL
    second = readnext(_args("TESTDS", 4, REC_LEN), vm)
    assert second.value == RESP_ENDFILE


@covers(NotLanguageFeature.INFRASTRUCTURE)
def test_readprev_after_stepping_forward_returns_prior_record():
    rec_a = _rec("AA01", "ALPHA")
    rec_b = _rec("BB02", "BRAVO")
    engine = _engine_with_records([rec_a, rec_b])
    startbr = make_vsam_startbr_builtin(engine)
    readnext = make_vsam_readnext_builtin(engine)
    readprev = make_vsam_readprev_builtin(engine)
    startbr(_args("TESTDS", b"\x00" * KEY_LEN, KEY_LEN), VMState())
    vm, addr = _make_vm_with_ws_region(bytearray(32))
    readnext(_args("TESTDS", 4, REC_LEN), vm)  # rec_a
    readnext(_args("TESTDS", 4, REC_LEN), vm)  # rec_b
    pres = readprev(_args("TESTDS", 4, REC_LEN), vm)
    assert pres.value == RESP_NORMAL
    region = vm.region_get(addr)
    assert region is not None
    assert bytes(region[4 : 4 + REC_LEN]) == rec_a


@covers(NotLanguageFeature.INFRASTRUCTURE)
def test_endbr_returns_normal():
    engine = _engine_with_records([_rec("AA01", "ONE")])
    startbr = make_vsam_startbr_builtin(engine)
    endbr = make_vsam_endbr_builtin(engine)
    startbr(_args("TESTDS", b"\x00" * KEY_LEN, KEY_LEN), VMState())
    eresult = endbr(_args("TESTDS"), VMState())
    assert isinstance(eresult, BuiltinResult)
    assert eresult.value == RESP_NORMAL


# ── Lowering tests (fake-ctx, mirror test_field_ref_wiring.py) ────────────────


from interpreter.cobol.cobol_types import CobolDataCategory, CobolTypeDescriptor
from interpreter.cobol.data_layout import FieldLayout
from interpreter.cobol.field_resolution import ResolvedFieldRef
from interpreter.instructions import CallFunction
from interpreter.register import Register


class FakeCtx:
    def __init__(self, fields: dict[str, tuple[int, int]]) -> None:
        self._fields = fields
        self.emitted: list = []
        self.encode_writes: list = []
        self._counter = 0

    def fresh_reg(self) -> Register:
        reg = Register(f"%{self._counter}")
        self._counter += 1
        return reg

    def emit_inst(self, inst):  # type: ignore[no-untyped-def]
        self.emitted.append(inst)
        return inst

    def has_field(self, name, materialised) -> bool:  # type: ignore[no-untyped-def]
        return name in self._fields

    def resolve_field_ref(self, name, materialised):  # type: ignore[no-untyped-def]
        offset, byte_length = self._fields[name]
        fl = FieldLayout(
            name=name,
            type_descriptor=CobolTypeDescriptor(
                category=CobolDataCategory.ALPHANUMERIC,
                total_digits=byte_length,
            ),
            offset=offset,
            byte_length=byte_length,
        )
        offset_reg = self.fresh_reg()
        self.emit_inst(("const_offset", offset_reg, offset))
        return ResolvedFieldRef(fl=fl, offset_reg=offset_reg), Register("%region")

    def emit_encode_and_write(
        self, region_reg, fl, value_str_reg, offset_reg=None
    ):  # type: ignore[no-untyped-def]
        self.encode_writes.append((region_reg, fl, value_str_reg, offset_reg))

    def emit_to_string(self, value_reg) -> Register:  # type: ignore[no-untyped-def]
        out = self.fresh_reg()
        self.emit_inst(("to_string", out, value_reg))
        return out


class FakeStmt:
    def __init__(self, verb: str, options: dict[str, "CicsOperand | None"]) -> None:
        self.verb = verb
        self.options = options


MATERIALISED = object()


def _make_strategy():
    from interpreter.cics.strategy import CicsLoweringStrategy
    from interpreter.cics.types import CicsContext

    engine = _engine_with_records([])
    holder = [CicsContext(transid="CC00", commarea=b"", eibaid="\x7d")]
    return CicsLoweringStrategy(context_holder=holder, vsam_engine=engine)


def _calls_to(ctx, name):
    return [
        i
        for i in ctx.emitted
        if isinstance(i, CallFunction) and str(i.func_name) == name
    ]


@covers(NotLanguageFeature.INFRASTRUCTURE)
def test_lower_read_emits_call_and_resp_writeback():
    """READ FILE INTO RIDFLD emits __cics_read then EIBRESP write-back."""
    ctx = FakeCtx({"WS-REC": (4, 10), "WS-KEY": (0, 4), "EIBRESP": (20, 4)})
    strategy = _make_strategy()
    strategy.lower(
        ctx,
        FakeStmt(
            "READ",
            {
                "FILE": CicsOperand("TESTDS", True),
                "INTO": CicsOperand("WS-REC", False),
                "RIDFLD": CicsOperand("WS-KEY", False),
            },
        ),
        MATERIALISED,
    )
    calls = _calls_to(ctx, "__cics_read")
    assert len(calls) == 1
    # 5 args: file, key, key_len, into_off, into_len
    assert len(calls[0].args) == 5
    # EIBRESP write-back happened.
    assert any(fl.name == "EIBRESP" for (_, fl, _, _) in ctx.encode_writes)


@covers(NotLanguageFeature.INFRASTRUCTURE)
def test_lower_write_emits_call_with_record_arg():
    ctx = FakeCtx({"WS-REC": (4, 10), "WS-KEY": (0, 4), "EIBRESP": (20, 4)})
    strategy = _make_strategy()
    strategy.lower(
        ctx,
        FakeStmt(
            "WRITE",
            {
                "FILE": CicsOperand("TESTDS", True),
                "FROM": CicsOperand("WS-REC", False),
                "RIDFLD": CicsOperand("WS-KEY", False),
            },
        ),
        MATERIALISED,
    )
    calls = _calls_to(ctx, "__cics_write")
    assert len(calls) == 1
    assert len(calls[0].args) == 4  # file, key, key_len, record
    assert any(fl.name == "EIBRESP" for (_, fl, _, _) in ctx.encode_writes)


@covers(NotLanguageFeature.INFRASTRUCTURE)
def test_lower_rewrite_emits_call():
    ctx = FakeCtx({"WS-REC": (4, 10), "WS-KEY": (0, 4), "EIBRESP": (20, 4)})
    strategy = _make_strategy()
    strategy.lower(
        ctx,
        FakeStmt(
            "REWRITE",
            {
                "FILE": CicsOperand("TESTDS", True),
                "FROM": CicsOperand("WS-REC", False),
                "RIDFLD": CicsOperand("WS-KEY", False),
            },
        ),
        MATERIALISED,
    )
    assert len(_calls_to(ctx, "__cics_rewrite")) == 1


@covers(NotLanguageFeature.INFRASTRUCTURE)
def test_lower_delete_emits_call_with_three_args():
    ctx = FakeCtx({"WS-KEY": (0, 4), "EIBRESP": (20, 4)})
    strategy = _make_strategy()
    strategy.lower(
        ctx,
        FakeStmt(
            "DELETE",
            {
                "FILE": CicsOperand("TESTDS", True),
                "RIDFLD": CicsOperand("WS-KEY", False),
            },
        ),
        MATERIALISED,
    )
    calls = _calls_to(ctx, "__cics_delete")
    assert len(calls) == 1
    assert len(calls[0].args) == 3  # file, key, key_len


@covers(NotLanguageFeature.INFRASTRUCTURE)
def test_lower_startbr_emits_call_and_resp_writeback():
    """STARTBR FILE RIDFLD emits __cics_startbr then EIBRESP write-back."""
    ctx = FakeCtx({"WS-KEY": (0, 4), "EIBRESP": (20, 4)})
    strategy = _make_strategy()
    strategy.lower(
        ctx,
        FakeStmt(
            "STARTBR",
            {
                "FILE": CicsOperand("TESTDS", True),
                "RIDFLD": CicsOperand("WS-KEY", False),
            },
        ),
        MATERIALISED,
    )
    calls = _calls_to(ctx, "__cics_startbr")
    assert len(calls) == 1
    assert len(calls[0].args) == 3  # file, key, key_len
    assert any(fl.name == "EIBRESP" for (_, fl, _, _) in ctx.encode_writes)


@covers(NotLanguageFeature.INFRASTRUCTURE)
def test_lower_readnext_emits_call_and_resp_writeback():
    """READNEXT FILE INTO emits __cics_readnext then EIBRESP write-back."""
    ctx = FakeCtx({"WS-REC": (4, 10), "EIBRESP": (20, 4)})
    strategy = _make_strategy()
    strategy.lower(
        ctx,
        FakeStmt(
            "READNEXT",
            {"FILE": CicsOperand("TESTDS", True), "INTO": CicsOperand("WS-REC", False)},
        ),
        MATERIALISED,
    )
    calls = _calls_to(ctx, "__cics_readnext")
    assert len(calls) == 1
    assert len(calls[0].args) == 3  # file, into_off, into_len
    assert any(fl.name == "EIBRESP" for (_, fl, _, _) in ctx.encode_writes)


@covers(NotLanguageFeature.INFRASTRUCTURE)
def test_lower_readprev_emits_call():
    ctx = FakeCtx({"WS-REC": (4, 10), "EIBRESP": (20, 4)})
    strategy = _make_strategy()
    strategy.lower(
        ctx,
        FakeStmt(
            "READPREV",
            {"FILE": CicsOperand("TESTDS", True), "INTO": CicsOperand("WS-REC", False)},
        ),
        MATERIALISED,
    )
    assert len(_calls_to(ctx, "__cics_readprev")) == 1


@covers(NotLanguageFeature.INFRASTRUCTURE)
def test_lower_endbr_emits_call_with_one_arg():
    ctx = FakeCtx({"EIBRESP": (20, 4)})
    strategy = _make_strategy()
    strategy.lower(
        ctx,
        FakeStmt("ENDBR", {"FILE": CicsOperand("TESTDS", True)}),
        MATERIALISED,
    )
    calls = _calls_to(ctx, "__cics_endbr")
    assert len(calls) == 1
    assert len(calls[0].args) == 1  # file only
