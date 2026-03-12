"""Unit tests for TypeCompatibility — runtime arg vs declared type scoring."""

from interpreter.constants import TypeName
from interpreter.type_compatibility import DefaultTypeCompatibility
from interpreter.type_expr import scalar, UNKNOWN


class TestDefaultTypeCompatibility:
    def setup_method(self):
        self.compat = DefaultTypeCompatibility()

    # -- Exact matches (score 2) --

    def test_int_matches_int(self):
        assert self.compat.score(42, scalar(TypeName.INT)) == 2

    def test_float_matches_float(self):
        assert self.compat.score(3.14, scalar(TypeName.FLOAT)) == 2

    def test_string_matches_string(self):
        assert self.compat.score("hello", scalar(TypeName.STRING)) == 2

    def test_bool_matches_bool(self):
        assert self.compat.score(True, scalar(TypeName.BOOL)) == 2

    # -- Compatible pairs (score 1) --

    def test_int_compatible_with_float(self):
        assert self.compat.score(42, scalar(TypeName.FLOAT)) == 1

    def test_float_compatible_with_int(self):
        assert self.compat.score(3.14, scalar(TypeName.INT)) == 1

    def test_bool_compatible_with_int(self):
        assert self.compat.score(True, scalar(TypeName.INT)) == 1

    # -- Neutral (score 0) --

    def test_heap_address_is_neutral(self):
        assert self.compat.score("obj_Dog_0", scalar(TypeName.STRING)) == 0

    def test_none_is_neutral(self):
        assert self.compat.score(None, scalar(TypeName.INT)) == 0

    def test_unknown_declared_type_is_neutral(self):
        assert self.compat.score(42, UNKNOWN) == 0

    def test_list_runtime_type_is_neutral(self):
        assert self.compat.score([1, 2], scalar(TypeName.ARRAY)) == 0

    # -- Mismatches (score -1) --

    def test_string_mismatches_int(self):
        assert self.compat.score("hello", scalar(TypeName.INT)) == -1

    def test_int_mismatches_string(self):
        assert self.compat.score(42, scalar(TypeName.STRING)) == -1

    def test_float_mismatches_string(self):
        assert self.compat.score(3.14, scalar(TypeName.STRING)) == -1
