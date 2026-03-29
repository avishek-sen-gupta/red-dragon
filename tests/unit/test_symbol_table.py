"""Unit tests for SymbolTable data model."""

from __future__ import annotations

import pytest

from interpreter.class_name import ClassName
from interpreter.field_name import FieldName
from interpreter.func_name import FuncName
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
        fi = FieldInfo(name=FieldName("x"), type_hint="int", has_initializer=False)
        assert fi.children == ()

    def test_flat_field_stores_attributes(self):
        fi = FieldInfo(name=FieldName("name"), type_hint="str", has_initializer=True)
        assert fi.name == FieldName("name")
        assert fi.type_hint == "str"
        assert fi.has_initializer is True

    def test_hierarchical_field_carries_children(self):
        child = FieldInfo(name=FieldName("x"), type_hint="float", has_initializer=False)
        parent = FieldInfo(
            name=FieldName("point"),
            type_hint="Point",
            has_initializer=False,
            children=(child,),
        )
        assert len(parent.children) == 1
        assert parent.children[0].name == FieldName("x")

    def test_field_info_is_frozen(self):
        fi = FieldInfo(name=FieldName("x"), type_hint="int", has_initializer=False)
        with pytest.raises(Exception):
            fi.name = FieldName("y")  # type: ignore[misc]


class TestFunctionInfo:
    def test_stores_name_params_return_type(self):
        fn = FunctionInfo(name=FuncName("add"), params=("a", "b"), return_type="int")
        assert fn.name == FuncName("add")
        assert fn.params == ("a", "b")
        assert fn.return_type == "int"

    def test_function_info_is_frozen(self):
        fn = FunctionInfo(name=FuncName("f"), params=(), return_type="void")
        with pytest.raises(Exception):
            fn.name = FuncName("g")  # type: ignore[misc]


class TestClassInfo:
    def test_stores_fields_methods_constants_parents(self):
        field = FieldInfo(
            name=FieldName("value"), type_hint="int", has_initializer=False
        )
        method = FunctionInfo(
            name=FuncName("get_value"), params=("self",), return_type="int"
        )
        ci = ClassInfo(
            name=ClassName("Counter"),
            fields={FieldName("value"): field},
            methods={FuncName("get_value"): method},
            constants={"MAX": "100"},
            parents=(ClassName("Base"),),
        )
        assert ci.name == ClassName("Counter")
        assert FieldName("value") in ci.fields
        assert FuncName("get_value") in ci.methods
        assert ci.constants["MAX"] == "100"
        assert ci.parents == (ClassName("Base"),)

    def test_match_args_defaults_to_empty_tuple(self):
        ci = ClassInfo(
            name=ClassName("Point"),
            fields={},
            methods={},
            constants={},
            parents=(),
        )
        assert ci.match_args == ()

    def test_match_args_can_be_set(self):
        ci = ClassInfo(
            name=ClassName("Point"),
            fields={},
            methods={},
            constants={},
            parents=(),
            match_args=("x", "y"),
        )
        assert ci.match_args == ("x", "y")

    def test_class_info_is_frozen(self):
        ci = ClassInfo(
            name=ClassName("A"),
            fields={},
            methods={},
            constants={},
            parents=(),
        )
        with pytest.raises(Exception):
            ci.name = ClassName("B")  # type: ignore[misc]


class TestResolveField:
    def test_finds_own_field(self):
        st = SymbolTable(
            classes={
                ClassName("Circle"): ClassInfo(
                    name=ClassName("Circle"),
                    fields={
                        FieldName("radius"): FieldInfo(
                            name=FieldName("radius"),
                            type_hint="int",
                            has_initializer=False,
                        )
                    },
                    methods={},
                    constants={},
                    parents=(),
                ),
            }
        )
        result = st.resolve_field(ClassName("Circle"), FieldName("radius"))
        assert result is not None and result.name == FieldName("radius")

    def test_finds_parent_field(self):
        st = SymbolTable(
            classes={
                ClassName("Animal"): ClassInfo(
                    name=ClassName("Animal"),
                    fields={
                        FieldName("name"): FieldInfo(
                            name=FieldName("name"),
                            type_hint="String",
                            has_initializer=False,
                        )
                    },
                    methods={},
                    constants={},
                    parents=(),
                ),
                ClassName("Dog"): ClassInfo(
                    name=ClassName("Dog"),
                    fields={},
                    methods={},
                    constants={},
                    parents=(ClassName("Animal"),),
                ),
            }
        )
        result = st.resolve_field(ClassName("Dog"), FieldName("name"))
        assert result is not None and result.name == FieldName("name")

    def test_finds_grandparent_field(self):
        st = SymbolTable(
            classes={
                ClassName("A"): ClassInfo(
                    name=ClassName("A"),
                    fields={
                        FieldName("x"): FieldInfo(
                            name=FieldName("x"), type_hint="int", has_initializer=False
                        )
                    },
                    methods={},
                    constants={},
                    parents=(),
                ),
                ClassName("B"): ClassInfo(
                    name=ClassName("B"),
                    fields={},
                    methods={},
                    constants={},
                    parents=(ClassName("A"),),
                ),
                ClassName("C"): ClassInfo(
                    name=ClassName("C"),
                    fields={},
                    methods={},
                    constants={},
                    parents=(ClassName("B"),),
                ),
            }
        )
        result = st.resolve_field(ClassName("C"), FieldName("x"))
        assert result is not None and result.name == FieldName("x")

    def test_returns_null_field_for_unknown_field(self):
        st = SymbolTable(
            classes={
                ClassName("Foo"): ClassInfo(
                    name=ClassName("Foo"),
                    fields={},
                    methods={},
                    constants={},
                    parents=(),
                ),
            }
        )
        result = st.resolve_field(ClassName("Foo"), FieldName("nonexistent"))
        assert not result.name

    def test_returns_null_field_for_unknown_class(self):
        st = SymbolTable.empty()
        result = st.resolve_field(ClassName("Unknown"), FieldName("x"))
        assert not result.name


class TestSymbolTableLookup:
    def test_lookup_class(self):
        ci = ClassInfo(
            name=ClassName("Dog"),
            fields={},
            methods={},
            constants={},
            parents=(),
        )
        st = SymbolTable(classes={ClassName("Dog"): ci})
        assert st.classes[ClassName("Dog")] is ci

    def test_lookup_function(self):
        fn = FunctionInfo(name=FuncName("greet"), params=("name",), return_type="str")
        st = SymbolTable(functions={FuncName("greet"): fn})
        assert st.functions[FuncName("greet")] is fn

    def test_lookup_constant(self):
        st = SymbolTable(constants={"PI": "3.14159"})
        assert st.constants["PI"] == "3.14159"

    def test_missing_class_raises_key_error(self):
        st = SymbolTable.empty()
        with pytest.raises(KeyError):
            _ = st.classes[ClassName("NonExistent")]
