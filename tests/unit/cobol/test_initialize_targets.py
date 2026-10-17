"""INITIALIZE's elementary targets under a group, qualified and subscripted."""

from __future__ import annotations

from cobol_asg.asg_types import CobolField
from cobol_asg.cobol_expression import LiteralNode
from cobol_asg.ref_mod import RefModOperand
from interpreter.cobol.data_layout import build_data_layout
from interpreter.cobol.features import CobolFeature
from interpreter.cobol.initialize_targets import initialize_targets
from tests.covers import covers


def _leaf(
    name: str, offset: int, *, filler: bool = False, redefines: str = ""
) -> CobolField:
    return CobolField(
        name=name,
        level=5,
        pic="X",
        usage="DISPLAY",
        offset=offset,
        filler=filler,
        redefines=redefines,
    )


@covers(CobolFeature.INITIALIZE)
def test_targets_skip_filler_and_redefines_and_name_every_occurrence() -> None:
    record = CobolField(
        name="REC",
        level=1,
        pic="",
        usage="DISPLAY",
        offset=0,
        children=[
            _leaf("FILLER_1", 0, filler=True),
            _leaf("A", 1),
            _leaf("B", 2, redefines="A"),
            CobolField(
                name="ROW",
                level=3,
                pic="",
                usage="DISPLAY",
                offset=2,
                occurs=2,
                element_size=1,
                children=[_leaf("C", 0)],
            ),
        ],
    )
    layout = build_data_layout([record])
    (row,) = layout.qualified_matches("ROW", ())
    (whole,) = layout.qualified_matches("REC", ())
    one_row = RefModOperand(name="ROW", subscripts=(LiteralNode("2"),))

    assert (
        [t.operand for t in initialize_targets(RefModOperand(name="REC"), whole)],
        [t.operand for t in initialize_targets(one_row, row)],
    ) == (
        [
            RefModOperand(name="A", qualifiers=("REC",)),
            RefModOperand(
                name="C", qualifiers=("ROW", "REC"), subscripts=(LiteralNode("1"),)
            ),
            RefModOperand(
                name="C", qualifiers=("ROW", "REC"), subscripts=(LiteralNode("2"),)
            ),
        ],
        [
            RefModOperand(
                name="C", qualifiers=("ROW", "REC"), subscripts=(LiteralNode("2"),)
            )
        ],
    )
