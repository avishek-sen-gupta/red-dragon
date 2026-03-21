"""Unit tests for SymbolTable data model."""

from __future__ import annotations

import pytest

from interpreter.frontends.symbol_table import (
    ClassInfo,
    FieldInfo,
    FunctionInfo,
    SymbolTable,
)


class TestSymbolTableEmpty:
    def test_empty_returns_empty_classes(self):
        st = SymbolTable.empty()
        assert st.classes == {}

    def test_empty_returns_empty_functions(self):
        st = SymbolTable.empty()
        assert st.functions == {}

    def test_empty_returns_empty_constants(self):
        st = SymbolTable.empty()
        assert st.constants == {}


class TestFieldInfo:
    def test_flat_field_has_empty_children(self):
        fi = FieldInfo(name="x", type_hint="int", has_initializer=False)
        assert fi.children == ()

    def test_flat_field_stores_attributes(self):
        fi = FieldInfo(name="name", type_hint="str", has_initializer=True)
        assert fi.name == "name"
        assert fi.type_hint == "str"
        assert fi.has_initializer is True

    def test_hierarchical_field_carries_children(self):
        child = FieldInfo(name="x", type_hint="float", has_initializer=False)
        parent = FieldInfo(
            name="point",
            type_hint="Point",
            has_initializer=False,
            children=(child,),
        )
        assert len(parent.children) == 1
        assert parent.children[0].name == "x"

    def test_field_info_is_frozen(self):
        fi = FieldInfo(name="x", type_hint="int", has_initializer=False)
        with pytest.raises(Exception):
            fi.name = "y"  # type: ignore[misc]


class TestFunctionInfo:
    def test_stores_name_params_return_type(self):
        fn = FunctionInfo(name="add", params=("a", "b"), return_type="int")
        assert fn.name == "add"
        assert fn.params == ("a", "b")
        assert fn.return_type == "int"

    def test_function_info_is_frozen(self):
        fn = FunctionInfo(name="f", params=(), return_type="void")
        with pytest.raises(Exception):
            fn.name = "g"  # type: ignore[misc]


class TestClassInfo:
    def test_stores_fields_methods_constants_parents(self):
        field = FieldInfo(name="value", type_hint="int", has_initializer=False)
        method = FunctionInfo(name="get_value", params=("self",), return_type="int")
        ci = ClassInfo(
            name="Counter",
            fields={"value": field},
            methods={"get_value": method},
            constants={"MAX": "100"},
            parents=("Base",),
        )
        assert ci.name == "Counter"
        assert "value" in ci.fields
        assert "get_value" in ci.methods
        assert ci.constants["MAX"] == "100"
        assert ci.parents == ("Base",)

    def test_match_args_defaults_to_empty_tuple(self):
        ci = ClassInfo(
            name="Point",
            fields={},
            methods={},
            constants={},
            parents=(),
        )
        assert ci.match_args == ()

    def test_match_args_can_be_set(self):
        ci = ClassInfo(
            name="Point",
            fields={},
            methods={},
            constants={},
            parents=(),
            match_args=("x", "y"),
        )
        assert ci.match_args == ("x", "y")

    def test_class_info_is_frozen(self):
        ci = ClassInfo(
            name="A",
            fields={},
            methods={},
            constants={},
            parents=(),
        )
        with pytest.raises(Exception):
            ci.name = "B"  # type: ignore[misc]


class TestResolveField:
    def test_finds_own_field(self):
        st = SymbolTable(
            classes={
                "Circle": ClassInfo(
                    name="Circle",
                    fields={
                        "radius": FieldInfo(
                            name="radius", type_hint="int", has_initializer=False
                        )
                    },
                    methods={},
                    constants={},
                    parents=(),
                ),
            }
        )
        result = st.resolve_field("Circle", "radius")
        assert result is not None and result.name == "radius"

    def test_finds_parent_field(self):
        st = SymbolTable(
            classes={
                "Animal": ClassInfo(
                    name="Animal",
                    fields={
                        "name": FieldInfo(
                            name="name", type_hint="String", has_initializer=False
                        )
                    },
                    methods={},
                    constants={},
                    parents=(),
                ),
                "Dog": ClassInfo(
                    name="Dog",
                    fields={},
                    methods={},
                    constants={},
                    parents=("Animal",),
                ),
            }
        )
        result = st.resolve_field("Dog", "name")
        assert result is not None and result.name == "name"

    def test_finds_grandparent_field(self):
        st = SymbolTable(
            classes={
                "A": ClassInfo(
                    name="A",
                    fields={
                        "x": FieldInfo(name="x", type_hint="int", has_initializer=False)
                    },
                    methods={},
                    constants={},
                    parents=(),
                ),
                "B": ClassInfo(
                    name="B",
                    fields={},
                    methods={},
                    constants={},
                    parents=("A",),
                ),
                "C": ClassInfo(
                    name="C",
                    fields={},
                    methods={},
                    constants={},
                    parents=("B",),
                ),
            }
        )
        result = st.resolve_field("C", "x")
        assert result is not None and result.name == "x"

    def test_returns_null_field_for_unknown_field(self):
        st = SymbolTable(
            classes={
                "Foo": ClassInfo(
                    name="Foo", fields={}, methods={}, constants={}, parents=()
                ),
            }
        )
        result = st.resolve_field("Foo", "nonexistent")
        assert not result.name

    def test_returns_null_field_for_unknown_class(self):
        st = SymbolTable.empty()
        result = st.resolve_field("Unknown", "x")
        assert not result.name


class TestSymbolTableLookup:
    def test_lookup_class(self):
        ci = ClassInfo(
            name="Dog",
            fields={},
            methods={},
            constants={},
            parents=(),
        )
        st = SymbolTable(classes={"Dog": ci})
        assert st.classes["Dog"] is ci

    def test_lookup_function(self):
        fn = FunctionInfo(name="greet", params=("name",), return_type="str")
        st = SymbolTable(functions={"greet": fn})
        assert st.functions["greet"] is fn

    def test_lookup_constant(self):
        st = SymbolTable(constants={"PI": "3.14159"})
        assert st.constants["PI"] == "3.14159"

    def test_missing_class_raises_key_error(self):
        st = SymbolTable.empty()
        with pytest.raises(KeyError):
            _ = st.classes["NonExistent"]
