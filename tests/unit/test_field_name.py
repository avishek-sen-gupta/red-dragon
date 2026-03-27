"""Tests for FieldName domain type."""

import pytest
from interpreter.field_name import FieldName, FieldKind, NoFieldName, NO_FIELD_NAME


class TestFieldName:
    def test_str(self):
        assert str(FieldName("x")) == "x"

    def test_value_and_kind(self):
        f = FieldName("x")
        assert f.value == "x"
        assert f.kind == FieldKind.PROPERTY

    def test_explicit_kind(self):
        f = FieldName("0", FieldKind.INDEX)
        assert f.kind == FieldKind.INDEX
        assert str(f) == "0"

    def test_is_present(self):
        assert FieldName("x").is_present()

    def test_equality_same_kind(self):
        assert FieldName("x") == FieldName("x")
        assert FieldName("x") != FieldName("y")

    def test_equality_different_kind(self):
        assert FieldName("0", FieldKind.INDEX) != FieldName("0", FieldKind.PROPERTY)

    def test_not_equal_to_string(self):
        assert FieldName("x") != "x"

    def test_hash_includes_kind(self):
        assert hash(FieldName("0", FieldKind.INDEX)) != hash(
            FieldName("0", FieldKind.PROPERTY)
        )

    def test_hash_consistent(self):
        assert hash(FieldName("x")) == hash(FieldName("x"))

    def test_dict_lookup(self):
        d = {FieldName("x"): 42, FieldName("0", FieldKind.INDEX): 99}
        assert d[FieldName("x")] == 42
        assert d[FieldName("0", FieldKind.INDEX)] == 99

    def test_lt(self):
        assert FieldName("a") < FieldName("b")

    def test_contains(self):
        assert "__" in FieldName("__method_missing__")

    def test_startswith(self):
        assert FieldName("__x").startswith("__")

    def test_post_init_rejects_double_wrap(self):
        with pytest.raises(TypeError, match="must be str"):
            FieldName(FieldName("x"))


class TestNoFieldName:
    def test_str(self):
        assert str(NO_FIELD_NAME) == ""

    def test_not_present(self):
        assert not NO_FIELD_NAME.is_present()

    def test_is_instance(self):
        assert isinstance(NO_FIELD_NAME, FieldName)
