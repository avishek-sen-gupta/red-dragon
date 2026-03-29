"""Unit tests for interface chain walk in type inference.

Tests that _infer_call_method falls back to interface method types
when the concrete class's class_method_types lacks the method.
"""

from __future__ import annotations

from interpreter.func_name import FuncName
from interpreter.instructions import CallMethod
from interpreter.register import Register
from interpreter.types.type_expr import scalar, UNKNOWN
from interpreter.types.type_inference import _InferenceContext, _infer_call_method
from interpreter.types.type_graph import TypeGraph, DEFAULT_TYPE_NODES
from interpreter.types.type_resolver import TypeResolver
from interpreter.types.coercion.default_conversion_rules import (
    DefaultTypeConversionRules,
)


def _resolver():
    return TypeResolver(DefaultTypeConversionRules())


def _make_call_method_inst(result_reg: str, obj_reg: str, method: str, *arg_regs):
    """Build a synthetic CALL_METHOD typed instruction."""
    return CallMethod(
        result_reg=Register(result_reg),
        obj_reg=Register(obj_reg),
        method_name=method,
        args=tuple(Register(r) for r in arg_regs),
    )


class TestInterfaceChainWalk:
    """When class_method_types[class] lacks a method, walk interface_implementations."""

    def test_method_resolved_via_interface(self):
        """Class 'Dog' implements 'Animal'; Dog has no 'speak', but Animal does."""
        ctx = _InferenceContext(
            register_types={Register("%0"): scalar("Dog")},
            class_method_types={
                scalar("Animal"): {FuncName("speak"): scalar("String")},
                scalar("Dog"): {},  # Dog has no methods of its own
            },
            interface_implementations={"Dog": ("Animal",)},
        )
        inst = _make_call_method_inst("%1", "%0", "speak")
        _infer_call_method(inst, ctx, _resolver())
        assert ctx.register_types[Register("%1")] == scalar("String")

    def test_method_on_class_takes_priority(self):
        """Direct class method should be preferred over interface fallback."""
        ctx = _InferenceContext(
            register_types={Register("%0"): scalar("Dog")},
            class_method_types={
                scalar("Animal"): {FuncName("speak"): scalar("String")},
                scalar("Dog"): {FuncName("speak"): scalar("Int")},
            },
            interface_implementations={"Dog": ("Animal",)},
        )
        inst = _make_call_method_inst("%1", "%0", "speak")
        _infer_call_method(inst, ctx, _resolver())
        assert ctx.register_types[Register("%1")] == scalar("Int")

    def test_multiple_interfaces_first_match_wins(self):
        """Walk interfaces in order; first one with the method wins."""
        ctx = _InferenceContext(
            register_types={Register("%0"): scalar("Widget")},
            class_method_types={
                scalar("Drawable"): {FuncName("draw"): scalar("Void")},
                scalar("Clickable"): {FuncName("draw"): scalar("Bool")},
                scalar("Widget"): {},
            },
            interface_implementations={"Widget": ("Drawable", "Clickable")},
        )
        inst = _make_call_method_inst("%1", "%0", "draw")
        _infer_call_method(inst, ctx, _resolver())
        assert ctx.register_types[Register("%1")] == scalar("Void")

    def test_no_interface_no_crash(self):
        """Class not in interface_implementations — no crash, no type."""
        ctx = _InferenceContext(
            register_types={Register("%0"): scalar("Foo")},
            class_method_types={scalar("Foo"): {}},
            interface_implementations={},
        )
        inst = _make_call_method_inst("%1", "%0", "bar")
        _infer_call_method(inst, ctx, _resolver())
        assert "%1" not in ctx.register_types
