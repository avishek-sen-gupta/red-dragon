"""Unit tests for FuncRef and BoundFuncRef dataclasses."""

from __future__ import annotations

from interpreter.refs.func_ref import FuncRef, BoundFuncRef
from interpreter.func_name import FuncName
from interpreter.ir import CodeLabel


class TestFuncRef:
    def test_construction(self):
        ref = FuncRef(name=FuncName("add"), label=CodeLabel("func_add_0"))
        assert ref.name == FuncName("add")
        assert ref.label == "func_add_0"

    def test_frozen(self):
        ref = FuncRef(name=FuncName("add"), label=CodeLabel("func_add_0"))
        import pytest

        with pytest.raises(AttributeError):
            ref.name = FuncName("other")

    def test_equality(self):
        a = FuncRef(name=FuncName("add"), label=CodeLabel("func_add_0"))
        b = FuncRef(name=FuncName("add"), label=CodeLabel("func_add_0"))
        assert a == b

    def test_different_labels_not_equal(self):
        a = FuncRef(name=FuncName("add"), label=CodeLabel("func_add_0"))
        b = FuncRef(name=FuncName("add"), label=CodeLabel("func_add_1"))
        assert a != b

    def test_dotted_name(self):
        """Dotted names like Counter.new are valid — the whole point of this refactor."""
        ref = FuncRef(name=FuncName("Counter.new"), label=CodeLabel("func_new_0"))
        assert ref.name == FuncName("Counter.new")


class TestBoundFuncRef:
    def test_construction_with_closure(self):
        fr = FuncRef(name=FuncName("inner"), label=CodeLabel("func_inner_0"))
        bound = BoundFuncRef(func_ref=fr, closure_id="closure_42")
        assert bound.func_ref.name == FuncName("inner")
        assert bound.func_ref.label == "func_inner_0"
        assert bound.closure_id == "closure_42"

    def test_construction_without_closure(self):
        fr = FuncRef(name=FuncName("add"), label=CodeLabel("func_add_0"))
        bound = BoundFuncRef(func_ref=fr, closure_id="")
        assert bound.closure_id == ""

    def test_frozen(self):
        fr = FuncRef(name=FuncName("add"), label=CodeLabel("func_add_0"))
        bound = BoundFuncRef(func_ref=fr, closure_id="")
        import pytest

        with pytest.raises(AttributeError):
            bound.closure_id = "other"

    def test_composition_not_inheritance(self):
        """BoundFuncRef is NOT a FuncRef subclass."""
        assert not issubclass(BoundFuncRef, FuncRef)
