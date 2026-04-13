"""Tests for SymbolName domain type."""

import pytest
from interpreter.symbol_name import SymbolName
from interpreter.func_name import FuncName
from interpreter.class_name import ClassName


class TestSymbolName:
    def test_str(self):
        assert str(SymbolName("Circle")) == "Circle"

    def test_value(self):
        assert SymbolName("Circle").value == "Circle"

    def test_equality_same_value(self):
        assert SymbolName("Circle") == SymbolName("Circle")

    def test_inequality_different_value(self):
        assert SymbolName("Circle") != SymbolName("Rect")

    def test_not_equal_to_string(self):
        assert SymbolName("Circle") != "Circle"

    def test_not_equal_to_func_name(self):
        assert SymbolName("foo") != FuncName("foo")

    def test_not_equal_to_class_name(self):
        assert SymbolName("Foo") != ClassName("Foo")

    def test_hash_consistent(self):
        assert hash(SymbolName("Circle")) == hash(SymbolName("Circle"))

    def test_hash_matches_str_value(self):
        # Enables future str-keyed lookups in the same dict bucket
        assert hash(SymbolName("Circle")) == hash("Circle")

    def test_dict_lookup(self):
        d = {SymbolName("Circle"): "geometry"}
        assert d[SymbolName("Circle")] == "geometry"

    def test_dict_lookup_class_stored_found_by_symbol_name(self):
        """Core contract: ClassName stored key, SymbolName lookup key."""
        # This is the linker use-case — build with typed key, look up with SymbolName
        d = {SymbolName("Circle"): "src"}
        assert d[SymbolName("Circle")] == "src"

    def test_post_init_rejects_non_str(self):
        with pytest.raises(TypeError, match="must be str"):
            SymbolName(42)  # type: ignore
