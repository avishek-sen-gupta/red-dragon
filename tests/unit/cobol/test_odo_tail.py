"""Tests for finding the OCCURS DEPENDING ON table a data item ends with."""

from cobol_asg.cobol_types import CobolDataCategory, CobolTypeDescriptor
from interpreter.cobol.data_layout import DataLayout, FieldLayout
from interpreter.cobol.features import CobolFeature
from interpreter.cobol.odo_tail import NO_ODO_TAIL, OdoTail
from tests.covers import covers


def _leaf(
    name: str, length: int, occurs: int = 0, depending_on: str = ""
) -> FieldLayout:
    return FieldLayout(
        name=name,
        type_descriptor=CobolTypeDescriptor(
            category=CobolDataCategory.ALPHANUMERIC, total_digits=length
        ),
        offset=0,
        byte_length=length * max(occurs, 1),
        occurs_count=occurs,
        element_size=length,
        occurs_depending_on=depending_on,
    )


@covers(CobolFeature.OCCURS_DEPENDING_ON)
def test_odo_tail_is_found_in_leaves_nested_groups_and_the_table_itself():
    leaf_table = DataLayout(
        fields={"CNT": _leaf("CNT", 1), "ELT": _leaf("ELT", 2, 4, "CNT")},
        total_bytes=9,
    )
    group_table = DataLayout(
        fields={"A": _leaf("A", 3)},
        total_bytes=15,
        occurs_count=5,
        element_size=3,
        occurs_depending_on="N",
    )
    unsized_group_table = DataLayout(
        fields={"A": _leaf("A", 3)},
        total_bytes=12,
        occurs_count=4,
        occurs_depending_on="M",
    )
    nested = DataLayout(
        fields={"H": _leaf("H", 2)},
        groups={"INNER": DataLayout(groups={"ROWS": group_table}, total_bytes=15)},
        total_bytes=17,
    )
    fixed = DataLayout(fields={"F": _leaf("F", 4, 3)}, total_bytes=12)
    assert [
        leaf_table.odo_tail(),
        group_table.odo_tail(),
        unsized_group_table.odo_tail(),
        nested.odo_tail(),
        fixed.odo_tail(),
    ] == [
        OdoTail("CNT", 2, 4),
        OdoTail("N", 3, 5),
        OdoTail("M", 3, 4),
        OdoTail("N", 3, 5),
        NO_ODO_TAIL,
    ]
