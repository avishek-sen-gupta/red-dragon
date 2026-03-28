"""Tests for FuncName domain type."""

import pytest
from interpreter.func_name import FuncName, NO_FUNC_NAME


class TestFuncName:
    def test_str(self):
        assert str(FuncName("add")) == "add"

    def test_value(self):
        assert FuncName("add").value == "add"

    def test_is_present(self):
        assert FuncName("add").is_present()

    def test_equality(self):
        assert FuncName("add") == FuncName("add")
        assert FuncName("add") != FuncName("sub")

    def test_not_equal_to_string(self):
        assert FuncName("add") != "add"

    def test_hash(self):
        assert hash(FuncName("add")) == hash(FuncName("add"))

    def test_dict_lookup(self):
        d = {FuncName("add"): 42}
        assert d[FuncName("add")] == 42

    def test_lt(self):
        assert FuncName("a") < FuncName("b")

    def test_startswith(self):
        assert FuncName("__cobol_accept").startswith("__cobol_")
        assert not FuncName("add").startswith("__cobol_")

    def test_contains(self):
        assert "[" in FuncName("Box[Node]")
        assert "[" not in FuncName("add")

    def test_post_init_rejects_double_wrap(self):
        with pytest.raises(TypeError, match="must be str"):
            FuncName(FuncName("add"))


class TestNoFuncName:
    def test_str(self):
        assert str(NO_FUNC_NAME) == ""

    def test_not_present(self):
        assert not NO_FUNC_NAME.is_present()

    def test_is_instance(self):
        assert isinstance(NO_FUNC_NAME, FuncName)
