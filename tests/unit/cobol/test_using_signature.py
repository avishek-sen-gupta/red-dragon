# pyright: standard
"""A program's USING signature: one mode and byte length per bound LINKAGE parameter, in order."""

from cobol_asg.asg_types import CobolASG, CobolField
from cobol_asg.cobol_statements import CallUsingParam
from interpreter.cobol.features import CobolFeature
from interpreter.cobol.sectioned_layout import using_signature
from interpreter.project.argument_mode import ArgumentMode
from interpreter.project.using_parameter import UsingParameter
from tests.covers import covers


def _field(name: str, pic: str, usage: str = "DISPLAY") -> CobolField:
    return CobolField(name=name, level=1, pic=pic, usage=usage, offset=0)


@covers(CobolFeature.PROCEDURE_DIVISION_USING)
def test_each_using_position_has_its_mode_and_length() -> None:
    linkage = [
        _field("LK-A", "X(10)"),
        _field("LK-N", "S9(9)", "COMP-5"),
        _field("LK-H", "S9(4)", "COMP"),
        _field("LK-SPARE", "X(3)"),
    ]
    using = [
        CallUsingParam(name="LK-A", param_type="REFERENCE"),
        CallUsingParam(name="LK-N", param_type="VALUE"),
        CallUsingParam(name="LK-H", param_type="VALUE"),
    ]

    assert (
        using_signature(CobolASG(linkage_fields=linkage, procedure_using=using)),
        using_signature(CobolASG(linkage_fields=linkage[:1])),
        using_signature(CobolASG()),
    ) == (
        (
            UsingParameter(ArgumentMode.REFERENCE, 10),
            UsingParameter(ArgumentMode.VALUE, 4),
            UsingParameter(ArgumentMode.VALUE, 2),
        ),
        (UsingParameter(ArgumentMode.REFERENCE, 10),),
        (),
    )
