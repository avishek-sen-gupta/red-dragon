# pyright: standard
"""Unit tests for the _const builder in the flat→typed conversion path.

Verifies that _const dispatches on literal_type to produce a correctly typed
Const instruction, without requiring a live LLM.
"""

from tests.covers import NotLanguageFeature, covers
from interpreter.instructions import _const
from interpreter.types.type_expr import scalar, NULL
from interpreter.constants import FoundationTypeName


class _Raw:
    """Minimal stub that mirrors the fields _const reads off a flat instruction."""

    def __init__(
        self,
        result_reg: str,
        operands: list[object],
        literal_type: str,
        source_location: object = None,
    ) -> None:
        self.result_reg = result_reg
        self.operands = operands
        self.literal_type = literal_type
        self.source_location = source_location


class TestConstBuilder:
    @covers(NotLanguageFeature.INFRASTRUCTURE)
    def test_builder_string(self) -> None:
        c = _const(_Raw("%1", ["10"], "String"))
        assert c.value == "10" and c.type_expr == scalar(FoundationTypeName.STRING)

    @covers(NotLanguageFeature.INFRASTRUCTURE)
    def test_builder_int(self) -> None:
        c = _const(_Raw("%1", ["10"], "Int"))
        assert c.value == 10 and c.type_expr == scalar(FoundationTypeName.INT)

    @covers(NotLanguageFeature.INFRASTRUCTURE)
    def test_builder_null(self) -> None:
        assert _const(_Raw("%1", [], "Null")).type_expr == NULL

    @covers(NotLanguageFeature.INFRASTRUCTURE)
    def test_builder_float(self) -> None:
        c = _const(_Raw("%1", ["3.14"], "Float"))
        assert c.value == 3.14 and c.type_expr == scalar(FoundationTypeName.FLOAT)

    @covers(NotLanguageFeature.INFRASTRUCTURE)
    def test_builder_bool_true(self) -> None:
        c = _const(_Raw("%1", ["True"], "Bool"))
        assert c.value is True and c.type_expr == scalar(FoundationTypeName.BOOL)

    @covers(NotLanguageFeature.INFRASTRUCTURE)
    def test_builder_bool_false(self) -> None:
        c = _const(_Raw("%1", ["False"], "Bool"))
        assert c.value is False and c.type_expr == scalar(FoundationTypeName.BOOL)

    @covers(NotLanguageFeature.INFRASTRUCTURE)
    def test_builder_func_ref(self) -> None:
        c = _const(_Raw("%1", ["<function:fib@func_fib_0>"], "FuncRef"))
        assert c.value == "<function:fib@func_fib_0>"

    @covers(NotLanguageFeature.INFRASTRUCTURE)
    def test_builder_class_ref(self) -> None:
        c = _const(_Raw("%1", ["<class:Foo@class_Foo_0>"], "ClassRef"))
        assert c.value == "<class:Foo@class_Foo_0>"

    @covers(NotLanguageFeature.INFRASTRUCTURE)
    def test_builder_missing_literal_type_raises(self) -> None:
        import pytest

        class _NoType:
            result_reg = "%1"
            operands = ["42"]
            source_location = None
            # no literal_type attribute

        with pytest.raises(ValueError, match="literal_type"):
            _const(_NoType())

    @covers(NotLanguageFeature.INFRASTRUCTURE)
    def test_builder_unknown_literal_type_raises(self) -> None:
        import pytest

        with pytest.raises(ValueError, match="literal_type"):
            _const(_Raw("%1", ["42"], "WeirdType"))
