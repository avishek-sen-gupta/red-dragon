"""Tests for common property accessor registration and emit helpers."""

from __future__ import annotations

from interpreter.ir import Opcode
from interpreter.frontends.context import TreeSitterEmitContext
from interpreter.frontends.common.property_accessors import (
    register_property_accessor,
    has_property_accessor,
    emit_field_load_or_getter,
    emit_field_store_or_setter,
)


class TestPropertyAccessorRegistration:
    def test_register_getter(self):
        ctx = _make_ctx()
        register_property_accessor(ctx, "Foo", "x", "get")
        assert has_property_accessor(ctx, "Foo", "x", "get")

    def test_register_setter(self):
        ctx = _make_ctx()
        register_property_accessor(ctx, "Foo", "x", "set")
        assert has_property_accessor(ctx, "Foo", "x", "set")

    def test_unregistered_returns_false(self):
        ctx = _make_ctx()
        assert not has_property_accessor(ctx, "Foo", "x", "get")

    def test_register_both(self):
        ctx = _make_ctx()
        register_property_accessor(ctx, "Foo", "x", "get")
        register_property_accessor(ctx, "Foo", "x", "set")
        assert has_property_accessor(ctx, "Foo", "x", "get")
        assert has_property_accessor(ctx, "Foo", "x", "set")


class TestEmitFieldLoadOrGetter:
    def test_without_getter_emits_load_field(self):
        ctx = _make_ctx()
        obj_reg = ctx.fresh_reg()
        emit_field_load_or_getter(ctx, obj_reg, "Foo", "x", None)
        load_fields = [i for i in ctx.instructions if i.opcode == Opcode.LOAD_FIELD]
        assert len(load_fields) == 1
        assert "x" in load_fields[0].operands

    def test_with_getter_emits_call_method(self):
        ctx = _make_ctx()
        register_property_accessor(ctx, "Foo", "x", "get")
        obj_reg = ctx.fresh_reg()
        emit_field_load_or_getter(ctx, obj_reg, "Foo", "x", None)
        call_methods = [i for i in ctx.instructions if i.opcode == Opcode.CALL_METHOD]
        assert len(call_methods) == 1
        assert "__get_x__" in call_methods[0].operands


class TestEmitFieldStoreOrSetter:
    def test_without_setter_emits_store_field(self):
        ctx = _make_ctx()
        obj_reg = ctx.fresh_reg()
        val_reg = ctx.fresh_reg()
        emit_field_store_or_setter(ctx, obj_reg, "Foo", "x", val_reg, None)
        store_fields = [i for i in ctx.instructions if i.opcode == Opcode.STORE_FIELD]
        assert len(store_fields) == 1
        assert "x" in store_fields[0].operands

    def test_with_setter_emits_call_method(self):
        ctx = _make_ctx()
        register_property_accessor(ctx, "Foo", "x", "set")
        obj_reg = ctx.fresh_reg()
        val_reg = ctx.fresh_reg()
        emit_field_store_or_setter(ctx, obj_reg, "Foo", "x", val_reg, None)
        call_methods = [i for i in ctx.instructions if i.opcode == Opcode.CALL_METHOD]
        assert len(call_methods) == 1
        assert "__set_x__" in call_methods[0].operands


def _make_ctx() -> TreeSitterEmitContext:
    from interpreter.frontends.context import GrammarConstants
    from interpreter.frontend_observer import NullFrontendObserver
    from interpreter.constants import Language

    return TreeSitterEmitContext(
        source=b"",
        language=Language.KOTLIN,
        observer=NullFrontendObserver(),
        constants=GrammarConstants(),
    )
