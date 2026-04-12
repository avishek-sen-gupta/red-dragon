"""Tests for PathName wrapper type."""

import pytest

from interpreter.path_name import PathName, NoPathName, NO_PATH_NAME


class TestPathName:
    def test_construction(self):
        p = PathName("./utils")
        assert p.value == "./utils"

    def test_str(self):
        assert str(PathName("os.path")) == "os.path"

    def test_hash_equality(self):
        a = PathName("./utils")
        b = PathName("./utils")
        assert a == b
        assert hash(a) == hash(b)

    def test_inequality(self):
        assert PathName("./a") != PathName("./b")

    def test_ordering(self):
        assert PathName("a") < PathName("b")

    def test_is_present(self):
        assert PathName("x").is_present() is True

    def test_rejects_non_string(self):
        with pytest.raises(TypeError):
            PathName(123)  # type: ignore[arg-type]

    def test_not_equal_to_string(self):
        assert PathName("x") != "x"


class TestNoPathName:
    def test_is_not_present(self):
        assert NO_PATH_NAME.is_present() is False

    def test_str(self):
        assert str(NO_PATH_NAME) == ""

    def test_not_equal_to_pathname(self):
        assert NO_PATH_NAME != PathName("x")

    def test_is_instance(self):
        assert isinstance(NO_PATH_NAME, PathName)
