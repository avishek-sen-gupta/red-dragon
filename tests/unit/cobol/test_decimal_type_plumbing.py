"""Shared-code plumbing for exact COBOL values (red-dragon-4q25.1)."""

from __future__ import annotations

from types import SimpleNamespace

from cobol_numeric.number import from_literal
from interpreter.constants import FoundationTypeName
from interpreter.instructions import Const, _const
from interpreter.ir import NO_SOURCE_LOCATION
from interpreter.register import Register
from interpreter.types.type_expr import scalar
from interpreter.types.type_graph import DEFAULT_TYPE_NODES
from interpreter.types.typed_value import runtime_type_name, typed
from interpreter.vm.vm_types import _serialize_value
from tests.covers import NotLanguageFeature, covers


@covers(NotLanguageFeature.INFRASTRUCTURE)
def test_decimal_is_a_number_in_the_type_graph():
    nodes = {node.name: node for node in DEFAULT_TYPE_NODES}
    assert str(FoundationTypeName.DECIMAL) == "Decimal"
    assert nodes[FoundationTypeName.DECIMAL].parents == (FoundationTypeName.NUMBER,)


@covers(NotLanguageFeature.INFRASTRUCTURE)
def test_const_decimal_factory_is_typed_decimal():
    inst = Const.decimal_(Register("%0"), from_literal("0.80"))
    assert inst.type_expr == scalar(FoundationTypeName.DECIMAL)
    assert inst.value == from_literal("0.80")


@covers(NotLanguageFeature.INFRASTRUCTURE)
def test_flat_const_with_decimal_literal_type():
    flat = SimpleNamespace(
        result_reg=Register("%0"),
        operands=["1.50"],
        source_location=NO_SOURCE_LOCATION,
        literal_type="Decimal",
    )
    inst = _const(flat)
    assert inst.type_expr == scalar(FoundationTypeName.DECIMAL)
    assert inst.value == from_literal("1.50")


@covers(NotLanguageFeature.INFRASTRUCTURE)
def test_cobol_number_is_never_coerced_by_runtime_type_name():
    assert runtime_type_name(from_literal("1.5")) == ""


@covers(NotLanguageFeature.INFRASTRUCTURE)
def test_cobol_number_serializes_as_plain_text():
    value = typed(from_literal("0.80"), scalar(FoundationTypeName.DECIMAL))
    assert _serialize_value(value) == "0.80"
