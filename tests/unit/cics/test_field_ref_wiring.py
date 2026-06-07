"""Unit tests for CICS field-ref copy-in / copy-back helpers (Task F0)."""

from __future__ import annotations

from interpreter.cics.strategy import emit_copy_in, emit_copy_back_str
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
