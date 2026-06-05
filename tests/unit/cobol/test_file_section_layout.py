"""COBOL FILE SECTION fields flow into the ASG and SectionedLayout (layout only,
no runtime wiring) — red-dragon-4q25.32."""

from __future__ import annotations

from interpreter.cobol.asg_types import CobolASG, CobolField
from tests.covers import covers, NotLanguageFeature


def _file_record_fields() -> list[CobolField]:
    # 01 CUSTOMER-RECORD / 05 CUST-ID PIC 9(5) / 05 CUST-NAME PIC X(20)
    return [
        CobolField(
            name="CUSTOMER-RECORD",
            level=1,
            pic="",
            usage="DISPLAY",
            offset=0,
            children=[
                CobolField(
                    name="CUST-ID", level=5, pic="9(5)", usage="DISPLAY", offset=0
                ),
                CobolField(
                    name="CUST-NAME", level=5, pic="X(20)", usage="DISPLAY", offset=5
                ),
            ],
        )
    ]


@covers(NotLanguageFeature.INFRASTRUCTURE)
def test_cobol_asg_round_trips_file_fields():
    asg = CobolASG(program_id="T", file_fields=_file_record_fields())
    assert len(asg.file_fields) == 1
    assert asg.file_fields[0].name == "CUSTOMER-RECORD"
    # to_dict/from_dict round-trip preserves file_fields
    restored = CobolASG.from_dict(asg.to_dict())
    assert [f.name for f in restored.file_fields] == ["CUSTOMER-RECORD"]
