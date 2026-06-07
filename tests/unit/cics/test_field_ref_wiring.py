"""Unit tests for CICS field-ref copy-in / copy-back helpers (Task F0)."""

from __future__ import annotations

from interpreter.cics.strategy import (
    emit_copy_in,
    emit_copy_back_str,
    emit_resp_writeback,
)
from interpreter.cobol.cobol_types import CobolDataCategory, CobolTypeDescriptor
from interpreter.cobol.data_layout import FieldLayout
from interpreter.cobol.field_resolution import ResolvedFieldRef
from interpreter.instructions import LoadRegion
from interpreter.register import Register
from tests.covers import covers, NotLanguageFeature


class FakeCtx:
    """Faithful fake EmitContext that records emitted instructions and emit_encode_and_write calls.

    Backed by a dict of {name: (offset, byte_length)} describing known data items.
    Signatures mirror the real EmitContext methods used by the helpers.
    """

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
        region_reg = Region_for(name)
        return ResolvedFieldRef(fl=fl, offset_reg=offset_reg), region_reg

    def emit_encode_and_write(
        self, region_reg, fl, value_str_reg, offset_reg=None
    ):  # type: ignore[no-untyped-def]
        self.encode_writes.append((region_reg, fl, value_str_reg, offset_reg))

    def emit_to_string(self, value_reg) -> Register:  # type: ignore[no-untyped-def]
        out = self.fresh_reg()
        self.emit_inst(("to_string", out, value_reg))
        return out


def Region_for(name: str) -> Register:
    return Register("%region")


def _ctx() -> FakeCtx:
    # WS-FIELD lives at byte offset 8, 4 bytes long.
    return FakeCtx({"WS-FIELD": (8, 4)})


MATERIALISED = object()  # opaque to the fake; helpers only pass it through


@covers(NotLanguageFeature.INFRASTRUCTURE)
def test_copy_in_emits_loadregion_for_field() -> None:
    ctx = _ctx()
    out = emit_copy_in(ctx, "WS-FIELD", MATERIALISED)
    assert isinstance(out, Register)
    load_regions = [i for i in ctx.emitted if isinstance(i, LoadRegion)]
    assert len(load_regions) == 1
    lr = load_regions[0]
    assert lr.result_reg == out
    assert lr.length == 4


@covers(NotLanguageFeature.INFRASTRUCTURE)
def test_copy_in_returns_none_for_literal() -> None:
    ctx = _ctx()
    out = emit_copy_in(ctx, "'CC01'", MATERIALISED)
    assert out is None
    assert not any(isinstance(i, LoadRegion) for i in ctx.emitted)


@covers(NotLanguageFeature.INFRASTRUCTURE)
def test_copy_in_returns_none_for_none() -> None:
    ctx = _ctx()
    out = emit_copy_in(ctx, None, MATERIALISED)
    assert out is None
    assert not any(isinstance(i, LoadRegion) for i in ctx.emitted)


@covers(NotLanguageFeature.INFRASTRUCTURE)
def test_copy_back_str_writes_for_field() -> None:
    ctx = _ctx()
    value_reg = ctx.fresh_reg()
    emit_copy_back_str(ctx, "WS-FIELD", value_reg, MATERIALISED)
    assert len(ctx.encode_writes) == 1
    region_reg, fl, written_value, offset_reg = ctx.encode_writes[0]
    assert written_value == value_reg
    assert fl.byte_length == 4


@covers(NotLanguageFeature.INFRASTRUCTURE)
def test_copy_back_str_noop_for_literal_or_none() -> None:
    ctx = _ctx()
    value_reg = ctx.fresh_reg()
    emit_copy_back_str(ctx, "'CC01'", value_reg, MATERIALISED)
    emit_copy_back_str(ctx, None, value_reg, MATERIALISED)
    assert ctx.encode_writes == []


def _resp_ctx() -> FakeCtx:
    # EIBRESP (binary) at offset 0 len 4; WS-RC (the RESP target) at offset 16 len 4.
    return FakeCtx({"EIBRESP": (0, 4), "WS-RC": (16, 4)})


@covers(NotLanguageFeature.INFRASTRUCTURE)
def test_resp_writeback_writes_eibresp_and_resp_field() -> None:
    """INQUIRE-style resp write-back targets BOTH EIBRESP and the RESP(name) field."""
    ctx = _resp_ctx()
    r_resp = ctx.fresh_reg()
    emit_resp_writeback(ctx, r_resp, {"RESP": "WS-RC"}, MATERIALISED)

    assert len(ctx.encode_writes) == 2
    written_offsets = sorted(fl.offset for (_, fl, _, _) in ctx.encode_writes)
    assert written_offsets == [0, 16]
    written_names = {fl.name for (_, fl, _, _) in ctx.encode_writes}
    assert written_names == {"EIBRESP", "WS-RC"}
    # Both write-backs encode the SAME stringified resp register.
    value_regs = {written for (_, _, written, _) in ctx.encode_writes}
    assert len(value_regs) == 1


@covers(NotLanguageFeature.INFRASTRUCTURE)
def test_resp_writeback_writes_eibresp_only_when_no_resp_option() -> None:
    """With no RESP(name) option, only EIBRESP is written."""
    ctx = _resp_ctx()
    r_resp = ctx.fresh_reg()
    emit_resp_writeback(ctx, r_resp, {}, MATERIALISED)

    assert len(ctx.encode_writes) == 1
    _, fl, _, _ = ctx.encode_writes[0]
    assert fl.name == "EIBRESP"
