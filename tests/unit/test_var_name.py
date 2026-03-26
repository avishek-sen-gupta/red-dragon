"""Tests for VarName domain type."""

import pytest

from interpreter.var_name import VarName, NoVarName, NO_VAR_NAME


class TestVarName:
    def test_str(self):
        assert str(VarName("x")) == "x"

    def test_value(self):
        assert VarName("x").value == "x"

    def test_is_present(self):
        assert VarName("x").is_present()

    def test_is_self_python(self):
        assert VarName("self").is_self

    def test_is_self_java(self):
        assert VarName("this").is_self

    def test_is_self_php(self):
        assert VarName("$this").is_self

    def test_is_self_false(self):
        assert not VarName("x").is_self

    def test_equality(self):
        assert VarName("x") == VarName("x")
        assert VarName("x") != VarName("y")

    def test_equality_with_string_bridge(self):
        assert VarName("x") == "x"
        assert VarName("x") != "y"

    def test_hash_consistent_with_str(self):
        assert hash(VarName("x")) == hash("x")

    def test_dict_lookup_with_str_key(self):
        d = {VarName("x"): 42}
        assert d["x"] == 42

    def test_contains(self):
        assert "__" in VarName("__cobol_x")
        assert "z" not in VarName("abc")

    def test_startswith(self):
        assert VarName("__cobol_x").startswith("__cobol_")
        assert not VarName("x").startswith("__cobol_")

    def test_post_init_rejects_double_wrap(self):
        with pytest.raises(TypeError, match="must be str"):
            VarName(VarName("x"))


class TestNoVarName:
    def test_str(self):
        assert str(NO_VAR_NAME) == ""

    def test_not_present(self):
        assert not NO_VAR_NAME.is_present()

    def test_is_instance(self):
        assert isinstance(NO_VAR_NAME, VarName)
