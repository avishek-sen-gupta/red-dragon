"""Tests for Address domain type."""

import pytest
from interpreter.address import Address, NoAddress, NO_ADDRESS


class TestAddress:
    def test_str(self):
        assert str(Address("obj_0")) == "obj_0"

    def test_value(self):
        assert Address("obj_0").value == "obj_0"

    def test_is_present(self):
        assert Address("obj_0").is_present()

    def test_equality(self):
        assert Address("obj_0") == Address("obj_0")
        assert Address("obj_0") != Address("arr_1")

    def test_not_equal_to_string(self):
        assert Address("obj_0") != "obj_0"

    def test_hash(self):
        assert hash(Address("obj_0")) == hash(Address("obj_0"))

    def test_dict_lookup(self):
        d = {Address("obj_0"): 42}
        assert d[Address("obj_0")] == 42

    def test_lt(self):
        assert Address("arr_0") < Address("obj_0")

    def test_startswith(self):
        assert Address("obj_0").startswith("obj_")
        assert not Address("arr_0").startswith("obj_")

    def test_post_init_rejects_double_wrap(self):
        with pytest.raises(TypeError, match="must be str"):
            Address(Address("obj_0"))


class TestNoAddress:
    def test_str(self):
        assert str(NO_ADDRESS) == ""

    def test_not_present(self):
        assert not NO_ADDRESS.is_present()

    def test_is_instance(self):
        assert isinstance(NO_ADDRESS, Address)
