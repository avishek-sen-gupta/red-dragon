"""Tests for ContinuationName domain type."""

import pytest
from interpreter.continuation_name import (
    ContinuationName,
    NoContinuationName,
    NO_CONTINUATION_NAME,
)


class TestContinuationName:
    def test_str(self):
        assert str(ContinuationName("para_X_end")) == "para_X_end"

    def test_hash(self):
        a = ContinuationName("para_X_end")
        b = ContinuationName("para_X_end")
        assert hash(a) == hash(b)
        assert a == b

    def test_eq_different_values(self):
        assert ContinuationName("a") != ContinuationName("b")

    def test_eq_rejects_str(self):
        assert ContinuationName("x").__eq__("x") is NotImplemented

    def test_bool_truthy(self):
        assert bool(ContinuationName("para_X_end")) is True

    def test_bool_falsy_empty(self):
        assert bool(ContinuationName("")) is False

    def test_post_init_rejects_non_str(self):
        with pytest.raises(TypeError):
            ContinuationName(42)  # type: ignore[arg-type]

    def test_post_init_rejects_double_wrap(self):
        with pytest.raises(TypeError):
            ContinuationName(ContinuationName("x"))  # type: ignore[arg-type]

    def test_is_present(self):
        assert ContinuationName("x").is_present() is True

    def test_dict_key(self):
        d = {ContinuationName("a"): 1, ContinuationName("b"): 2}
        assert d[ContinuationName("a")] == 1


class TestNoContinuationName:
    def test_is_present_false(self):
        assert NO_CONTINUATION_NAME.is_present() is False

    def test_bool_false(self):
        assert bool(NO_CONTINUATION_NAME) is False

    def test_str_empty(self):
        assert str(NO_CONTINUATION_NAME) == ""

    def test_singleton_value(self):
        assert isinstance(NO_CONTINUATION_NAME, NoContinuationName)
        assert isinstance(NO_CONTINUATION_NAME, ContinuationName)
