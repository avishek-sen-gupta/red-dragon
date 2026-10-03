"""PROCEDURE DIVISION USING survives the trip through the ASG's dict form."""

from cobol_asg.asg_types import CobolASG
from cobol_asg.cobol_statements import CallUsingParam
from interpreter.cobol.features import CobolFeature
from tests.covers import covers


@covers(CobolFeature.PROCEDURE_DIVISION_USING)
def test_the_using_list_reads_and_writes_back_in_order() -> None:
    data = {
        "program_id": "SUB",
        "procedure_using": [
            {"name": "LK-A", "type": "REFERENCE"},
            {"name": "LK-B", "type": "VALUE"},
        ],
    }

    asg = CobolASG.from_dict(data)

    assert asg.procedure_using == [
        CallUsingParam(name="LK-A", param_type="REFERENCE"),
        CallUsingParam(name="LK-B", param_type="VALUE"),
    ]
    assert asg.to_dict() == data
    assert CobolASG.from_dict({"program_id": "MAIN"}).procedure_using == []
    assert CobolASG.from_dict({}).to_dict() == {}
