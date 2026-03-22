"""Unit tests for FuncRef and BoundFuncRef dataclasses."""

from __future__ import annotations

from interpreter.refs.func_ref import FuncRef, BoundFuncRef


class TestFuncRef:
    def test_construction(self):
        ref = FuncRef(name="add", label="func_add_0")
        assert ref.name == "add"
        assert ref.label == "func_add_0"

    def test_frozen(self):
        ref = FuncRef(name="add", label="func_add_0")
        import pytest

        with pytest.raises(AttributeError):
            ref.name = "other"

    def test_equality(self):
        a = FuncRef(name="add", label="func_add_0")
        b = FuncRef(name="add", label="func_add_0")
        assert a == b

    def test_different_labels_not_equal(self):
        a = FuncRef(name="add", label="func_add_0")
        b = FuncRef(name="add", label="func_add_1")
        assert a != b

    def test_dotted_name(self):
        """Dotted names like Counter.new are valid — the whole point of this refactor."""
        ref = FuncRef(name="Counter.new", label="func_new_0")
        assert ref.name == "Counter.new"


class TestBoundFuncRef:
    def test_construction_with_closure(self):
        fr = FuncRef(name="inner", label="func_inner_0")
        bound = BoundFuncRef(func_ref=fr, closure_id="closure_42")
        assert bound.func_ref.name == "inner"
        assert bound.func_ref.label == "func_inner_0"
        assert bound.closure_id == "closure_42"

    def test_construction_without_closure(self):
        fr = FuncRef(name="add", label="func_add_0")
        bound = BoundFuncRef(func_ref=fr, closure_id="")
        assert bound.closure_id == ""

    def test_frozen(self):
        fr = FuncRef(name="add", label="func_add_0")
        bound = BoundFuncRef(func_ref=fr, closure_id="")
        import pytest

        with pytest.raises(AttributeError):
            bound.closure_id = "other"

    def test_composition_not_inheritance(self):
        """BoundFuncRef is NOT a FuncRef subclass."""
        assert not issubclass(BoundFuncRef, FuncRef)
