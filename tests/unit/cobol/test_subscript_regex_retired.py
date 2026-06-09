# pyright: standard
"""The legacy subscript-string parser is retired (red-dragon-6ddr).

Subscripts are now fully structural: every production caller passes a bare
base name plus a structured ``subscripts`` array to ``resolve_field_ref``.
The regex-based ``parse_subscript_notation`` / ``_SUBSCRIPT_RE`` fallback is
therefore dead and must not exist.
"""

import interpreter.cobol.field_resolution as fr
from tests.covers import covers
from interpreter.cobol.features import CobolFeature


class TestSubscriptRegexRetired:
    @covers(CobolFeature.OCCURS_FIXED)
    def test_subscript_string_parser_is_gone(self) -> None:
        assert not hasattr(fr, "parse_subscript_notation")
        assert not hasattr(fr, "_SUBSCRIPT_RE")
