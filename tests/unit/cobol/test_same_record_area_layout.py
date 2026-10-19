"""The records of the files a SAME RECORD AREA clause names lie over one area of the
FILE SECTION layout; every other file keeps an area of its own, after those before it.
"""

from __future__ import annotations

from cobol_asg.asg_types import CobolASG, CobolField
from interpreter.cobol.features import CobolFeature
from interpreter.cobol.sectioned_layout import build_sectioned_layout
from tests.covers import covers


def _record(name: str, pic: str) -> CobolField:
    return CobolField(name=name, level=1, pic=pic, usage="DISPLAY", offset=0)


@covers(CobolFeature.READ)
def test_files_in_one_same_record_area_share_its_offset() -> None:
    asg = CobolASG(
        program_id="T",
        file_fields=[
            _record("R1", "X(4)"),
            _record("P-REC", "X(3)"),
            _record("R2", "X(6)"),
        ],
        file_record_to_select={"R1": "F1", "P-REC": "P", "R2": "F2"},
        same_record_areas=[("F1", "F2")],
    )
    file = build_sectioned_layout(asg).file
    assert {
        name: file.lookup_or_raise(name).offset for name in ("R1", "R2", "P-REC")
    } == {"R1": 0, "R2": 0, "P-REC": 6}
