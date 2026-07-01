"""Unit tests for the centralised intrinsic-argument disambiguator.

red-dragon-zgwl: ProLeap over-splits an arithmetic function argument F(a - b)
into [a, neg(b)] because its grammar's argument separator is optional and it has
no per-function arity. resolve_intrinsic_args is the SINGLE place that repairs
this, using each function's known arity (mirroring GnuCOBOL's cb_intrinsic_table).
"""

from interpreter.cobol.features import CobolFeature
from interpreter.cobol.intrinsic_arity import resolve_intrinsic_args
from tests.covers import covers


def _ref(n):
    return {"kind": "ref", "name": n}


def _lit(v):
    return {"kind": "lit", "value": v}


def _neg(v):
    return {"kind": "neg", "expr": _lit(v)}


def _fn(name, *a):
    return {"kind": "function", "name": name, "args": list(a)}


class TestResolveIntrinsicArgs:
    @covers(CobolFeature.INTRINSIC_FUNCTION)
    def test_single_arity_folds_split_arithmetic(self):
        # DATE-OF-INTEGER(INTEGER-OF-DATE(x) - 1) over-split to [g(x), neg(1)]
        # must fold back to a single argument g(x) + neg(1)  ( == g(x) - 1 ).
        g = _fn("INTEGER-OF-DATE", _ref("WS-N"))
        out = resolve_intrinsic_args("DATE-OF-INTEGER", [g, _neg("1")])
        # the sign is unwrapped into a real subtraction: g - 1
        assert out == [{"kind": "binop", "op": "-", "left": g, "right": _lit("1")}]

    @covers(CobolFeature.INTRINSIC_FUNCTION)
    def test_single_arity_single_arg_unchanged(self):
        raw = [_lit("154498")]
        assert resolve_intrinsic_args("DATE-OF-INTEGER", raw) == raw

    @covers(CobolFeature.INTRINSIC_FUNCTION)
    def test_single_arity_chained_minus_folds_all(self):
        # A - 1 - 2  ->  [A, neg1, neg2]  ->  one argument ((A + neg1) + neg2)
        out = resolve_intrinsic_args(
            "DATE-OF-INTEGER", [_ref("A"), _neg("1"), _neg("2")]
        )
        assert len(out) == 1
        assert out[0]["kind"] == "binop"

    @covers(CobolFeature.INTRINSIC_FUNCTION)
    def test_two_arity_plain_args_unchanged(self):
        # MOD(A, B) -> [A, B]; count == arity, nothing to fold.
        raw = [_ref("A"), _ref("B")]
        assert resolve_intrinsic_args("MOD", raw) == raw

    @covers(CobolFeature.INTRINSIC_FUNCTION)
    def test_two_arity_arithmetic_in_first_arg(self):
        # MOD(A - 1, B) -> [A, neg1, B] -> [A+neg1, B]
        out = resolve_intrinsic_args("MOD", [_ref("A"), _neg("1"), _ref("B")])
        assert len(out) == 2
        assert out[0] == {
            "kind": "binop",
            "op": "-",
            "left": _ref("A"),
            "right": _lit("1"),
        }
        assert out[1] == _ref("B")

    @covers(CobolFeature.INTRINSIC_FUNCTION)
    def test_two_arity_arithmetic_in_second_arg(self):
        # MOD(A, B - 1) -> [A, B, neg1] -> [A, B+neg1]
        out = resolve_intrinsic_args("MOD", [_ref("A"), _ref("B"), _neg("1")])
        assert len(out) == 2
        assert out[0] == _ref("A")
        assert out[1] == {
            "kind": "binop",
            "op": "-",
            "left": _ref("B"),
            "right": _lit("1"),
        }

    @covers(CobolFeature.INTRINSIC_FUNCTION)
    def test_variadic_never_folds(self):
        # MAX is variadic (arity -1): cannot disambiguate, leave untouched.
        raw = [_ref("A"), _ref("B"), _neg("1")]
        assert resolve_intrinsic_args("MAX", raw) == raw

    @covers(CobolFeature.INTRINSIC_FUNCTION)
    def test_unknown_function_unchanged(self):
        # Not in the arity table -> treated as variadic, no regrouping.
        raw = [_ref("A"), _neg("1")]
        assert resolve_intrinsic_args("SOME-USER-FUNC", raw) == raw

    @covers(CobolFeature.INTRINSIC_FUNCTION)
    def test_case_insensitive_name(self):
        out = resolve_intrinsic_args("date-of-integer", [_ref("A"), _neg("1")])
        assert len(out) == 1
