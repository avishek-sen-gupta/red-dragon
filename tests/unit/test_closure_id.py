"""Unit tests for ClosureId domain type."""

from __future__ import annotations

import pytest

from interpreter.closure_id import ClosureId, NoClosureId, NO_CLOSURE_ID


class TestClosureId:
    def test_construction(self):
        cid = ClosureId("closure_42")
        assert cid.value == "closure_42"

    def test_str(self):
        cid = ClosureId("closure_42")
        assert str(cid) == "closure_42"

    def test_is_present(self):
        cid = ClosureId("closure_42")
        assert cid.is_present() is True

    def test_hash_and_dict_key(self):
        cid = ClosureId("closure_42")
        d = {cid: "env"}
        assert d[ClosureId("closure_42")] == "env"

    def test_equality(self):
        assert ClosureId("closure_42") == ClosureId("closure_42")
        assert ClosureId("closure_42") != ClosureId("closure_99")

    def test_no_str_equality(self):
        """ClosureId does not compare equal to bare strings."""
        assert ClosureId("closure_42") != "closure_42"
        assert ClosureId("closure_42").__eq__("closure_42") is NotImplemented

    def test_frozen(self):
        cid = ClosureId("closure_42")
        with pytest.raises(AttributeError):
            cid.value = "other"

    def test_bool_truthy(self):
        assert bool(ClosureId("closure_42")) is True

    def test_rejects_non_str(self):
        with pytest.raises(TypeError):
            ClosureId(42)

    def test_contains(self):
        cid = ClosureId("closure_42")
        assert "42" in cid


class TestNoClosureId:
    def test_is_present_false(self):
        assert NO_CLOSURE_ID.is_present() is False

    def test_value_is_empty(self):
        assert NO_CLOSURE_ID.value == ""

    def test_bool_falsy(self):
        assert bool(NO_CLOSURE_ID) is False

    def test_str_is_empty(self):
        assert str(NO_CLOSURE_ID) == ""

    def test_is_instance(self):
        assert isinstance(NO_CLOSURE_ID, ClosureId)
        assert isinstance(NO_CLOSURE_ID, NoClosureId)
