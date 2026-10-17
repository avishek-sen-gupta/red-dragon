"""Tests for splitting an undelimited UNSTRING source by its receivers' sizes."""

from interpreter.cobol.byte_builtins import _builtin_unstring_by_size
from interpreter.cobol.features import CobolFeature
from interpreter.types.typed_value import typed_from_runtime
from tests.covers import covers


@covers(CobolFeature.UNSTRING_VERB)
def test_each_receiver_takes_its_size_until_the_source_is_exhausted():
    cases = [("ABCDEF", (3, 5)), ("ABCDEFGH", (2, 2)), ("AB", (3, 5)), ("ABCD", (4, 1))]
    assert [
        _builtin_unstring_by_size(
            [typed_from_runtime(source), *(typed_from_runtime(n) for n in sizes)],
            None,
        ).value
        for source, sizes in cases
    ] == [["ABC", "DEF"], ["AB", "CD"], ["AB"], ["ABCD"]]
