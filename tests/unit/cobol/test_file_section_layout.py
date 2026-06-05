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


@covers(NotLanguageFeature.INFRASTRUCTURE)
def test_build_sectioned_layout_includes_file_section():
    from interpreter.cobol.sectioned_layout import build_sectioned_layout

    asg = CobolASG(program_id="T", file_fields=_file_record_fields())
    layout = build_sectioned_layout(asg)
    # FILE SECTION fields are present in the dedicated `file` layout...
    assert layout.file.lookup_as_storage("CUST-ID") is not None
    assert layout.file.lookup_as_storage("CUST-NAME") is not None
    # ...and NOT leaked into working-storage (no wiring/merging).
    assert layout.working_storage.lookup_as_storage("CUST-ID") is None
