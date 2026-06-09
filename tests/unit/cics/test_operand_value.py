"""Unit tests for emit_operand_value — RETURN TRANSID / XCTL PROGRAM operand resolution.

A data-name operand decodes the field to a register holding its runtime value;
a literal operand emits a Const (with COBOL quotes stripped).
"""

from __future__ import annotations

from interpreter.cics.strategy import emit_operand_value
from interpreter.cics.cics_parser import CicsOperand
from interpreter.cobol.cobol_types import CobolDataCategory, CobolTypeDescriptor
from interpreter.cobol.data_layout import FieldLayout
from interpreter.cobol.field_resolution import ResolvedFieldRef
from interpreter.instructions import Const
from interpreter.register import Register
from tests.covers import covers, NotLanguageFeature


class FakeCtx:
    """Fake EmitContext recording decode_field calls and emitted instructions."""

    def __init__(self, fields: dict[str, tuple[int, int]]) -> None:
        self._fields = fields
        self.emitted: list = []
        self.decoded: list = []
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

    def resolve_field_ref(self, name, materialised, qualifiers=(), subscripts=()):  # type: ignore[no-untyped-def]
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
        return ResolvedFieldRef(fl=fl, offset_reg=offset_reg), Register("%region")

    def emit_decode_field(self, region_reg, fl, offset_reg=None):  # type: ignore[no-untyped-def]
        out = self.fresh_reg()
        self.decoded.append((region_reg, fl, out))
        return out


MATERIALISED = object()


@covers(NotLanguageFeature.INFRASTRUCTURE)
def test_field_operand_emits_decode_not_literal_const() -> None:
    ctx = FakeCtx({"WS-MAPNM": (0, 4)})
    out = emit_operand_value(ctx, CicsOperand("WS-MAPNM", False), MATERIALISED)
    assert isinstance(out, Register)
    # A decode happened ...
    assert len(ctx.decoded) == 1
    assert ctx.decoded[0][2] == out
    # ... and no Const whose value is the field NAME was emitted.
    assert not any(isinstance(i, Const) and i.value == "WS-MAPNM" for i in ctx.emitted)


@covers(NotLanguageFeature.INFRASTRUCTURE)
def test_literal_operand_emits_const_with_quotes_stripped() -> None:
    ctx = FakeCtx({})
    out = emit_operand_value(ctx, CicsOperand("CC01", True), MATERIALISED)
    assert isinstance(out, Register)
    assert ctx.decoded == []
    consts = [i for i in ctx.emitted if isinstance(i, Const)]
    assert len(consts) == 1
    assert consts[0].value == "CC01"
    assert consts[0].result_reg == out


@covers(NotLanguageFeature.INFRASTRUCTURE)
def test_literal_never_consults_has_field_on_name_collision() -> None:
    """The SGNMAP collision: a quoted literal must NOT decode a same-named field.

    The BMS symbolic-map group is conventionally named after the map, so a literal
    MAP('SGNMAP') collides with a real WS field SGNMAP. A literal operand must emit
    Const('SGNMAP') and NEVER consult has_field.
    """
    ctx = FakeCtx({"SGNMAP": (0, 8)})
    out = emit_operand_value(ctx, CicsOperand("SGNMAP", True), MATERIALISED)
    assert isinstance(out, Register)
    assert ctx.decoded == [], "a literal must not decode the colliding field"
    consts = [i for i in ctx.emitted if isinstance(i, Const)]
    assert len(consts) == 1
    assert consts[0].value == "SGNMAP"
    assert consts[0].result_reg == out


@covers(NotLanguageFeature.INFRASTRUCTURE)
def test_none_operand_emits_empty_const() -> None:
    ctx = FakeCtx({})
    out = emit_operand_value(ctx, None, MATERIALISED)
    assert isinstance(out, Register)
    assert ctx.decoded == []
    consts = [i for i in ctx.emitted if isinstance(i, Const)]
    assert len(consts) == 1
    assert consts[0].value == ""
