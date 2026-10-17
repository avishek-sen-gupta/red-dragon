"""The relative paths a CORRESPONDING phrase pairs between two group layouts."""

from __future__ import annotations

from cobol_asg.cobol_types import CobolDataCategory, CobolTypeDescriptor
from interpreter.cobol.corresponding_paths import (
    corresponding_paths,
    pairs_for_arithmetic,
    pairs_for_move,
)
from interpreter.cobol.data_layout import DataLayout, FieldLayout

_NUMBER = CobolTypeDescriptor(category=CobolDataCategory.ZONED_DECIMAL, total_digits=2)
_TEXT = CobolTypeDescriptor(category=CobolDataCategory.ALPHANUMERIC, total_digits=2)


def _leaf(
    name: str, kind: CobolTypeDescriptor = _NUMBER, occurs: int = 0, redefines: str = ""
) -> FieldLayout:
    return FieldLayout(
        name=name,
        type_descriptor=kind,
        offset=0,
        byte_length=2,
        occurs_count=occurs,
        redefines=redefines,
    )


def _group(
    *items: FieldLayout | tuple[str, DataLayout], occurs: int = 0, redefines: str = ""
) -> DataLayout:
    return DataLayout(
        fields={item.name: item for item in items if isinstance(item, FieldLayout)},
        groups=dict(item for item in items if isinstance(item, tuple)),
        occurs_count=occurs,
        redefines=redefines,
    )


_SOURCE = _group(
    _leaf("A"),
    _leaf("X", _TEXT),
    _leaf("T", occurs=2),
    _leaf("R"),
    _leaf("E"),
    _leaf("FILLER_1"),
    ("G", _group(_leaf("A"), ("H", _group(_leaf("B"))))),
    ("K", _group(("SUBK", _group(_leaf("C"))))),
    ("GE", _group(_leaf("E1"))),
    ("GR", _group(_leaf("Z"))),
    ("GT", _group(_leaf("Y"), occurs=3)),
)

_TARGET = _group(
    _leaf("A"),
    _leaf("X"),
    _leaf("T"),
    _leaf("R", redefines="A"),
    ("E", _group(_leaf("E9"))),
    _leaf("FILLER_2"),
    ("G", _group(_leaf("a"), ("h", _group(_leaf("B"))))),
    ("K", _group(_leaf("C"))),
    _leaf("GE", _TEXT),
    ("GR", _group(_leaf("Z"), redefines="A")),
    ("GT", _group(_leaf("Y"))),
)


class TestCorrespondingPaths:
    def test_pairs_like_qualified_items_by_verb(self):
        """ANSI X3.23-1985 VI-6.4.3 / ISO 1989 CORRESPONDING: same names and
        qualifiers below the operands, matched without regard to case; OCCURS,
        REDEFINES and the items under them never pair; MOVE needs one
        elementary item of the two, ADD and SUBTRACT two elementary numerics."""
        assert corresponding_paths(_SOURCE, _TARGET, pairs_for_move) == (
            ("A",),
            ("X",),
            ("E",),
            ("G", "A"),
            ("G", "H", "B"),
            ("GE",),
        )
        assert corresponding_paths(_SOURCE, _TARGET, pairs_for_arithmetic) == (
            ("A",),
            ("G", "A"),
            ("G", "H", "B"),
        )
