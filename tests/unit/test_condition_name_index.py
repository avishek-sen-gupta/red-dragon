"""Tests for ConditionNameIndex and build_condition_index."""

import pytest

from cobol_asg.cobol_types import CobolDataCategory, CobolTypeDescriptor
from cobol_asg.condition_name import ConditionName, ConditionValue
from cobol_asg.ref_mod import RefModOperand
from interpreter.cobol.condition_name_index import (
    ConditionEntry,
    ConditionNameIndex,
    build_condition_index,
)
from interpreter.cobol.data_layout import (
    CobolAmbiguousReferenceError,
    DataLayout,
    FieldLayout,
)
from interpreter.cobol.features import CobolFeature
from tests.covers import covers


def _make_field_layout(
    name: str,
    conditions: list[ConditionName],
) -> FieldLayout:
    """Helper to create a FieldLayout with conditions."""
    return FieldLayout(
        name=name,
        type_descriptor=CobolTypeDescriptor(
            category=CobolDataCategory.ALPHANUMERIC,
            total_digits=1,
        ),
        offset=0,
        byte_length=1,
        conditions=conditions,
    )


class TestConditionNameIndex:
    @covers(CobolFeature.LEVEL_88_CONDITION)
    def test_lookup_existing(self):
        entries = {
            "STATUS-ACTIVE": (
                ConditionEntry(
                    parent=RefModOperand(name="WS-STATUS"),
                    values=[ConditionValue(from_val="A")],
                ),
            ),
        }
        index = ConditionNameIndex(entries)
        entry = index.lookup("STATUS-ACTIVE")
        assert entry.parent == RefModOperand(name="WS-STATUS")
        assert len(entry.values) == 1

    @covers(CobolFeature.LEVEL_88_CONDITION)
    def test_lookup_missing(self):
        index = ConditionNameIndex({})
        entry = index.lookup("NONEXISTENT")
        assert entry.parent == RefModOperand(name="")
        assert entry.values == []

    @covers(CobolFeature.LEVEL_88_CONDITION)
    def test_has_condition(self):
        entries = {
            "IS-ACTIVE": (
                ConditionEntry(
                    parent=RefModOperand(name="WS-FLAG"),
                    values=[ConditionValue(from_val="1")],
                ),
            ),
        }
        index = ConditionNameIndex(entries)
        assert index.has_condition("IS-ACTIVE")
        assert not index.has_condition("IS-INACTIVE")

    @covers(CobolFeature.LEVEL_88_CONDITION)
    def test_empty_index(self):
        index = ConditionNameIndex({})
        assert not index.has_condition("ANYTHING")
        assert index.entries == {}


class TestBuildConditionIndex:
    @covers(CobolFeature.LEVEL_88_CONDITION)
    def test_builds_from_fields_with_conditions(self):
        fields = {
            "WS-STATUS": _make_field_layout(
                "WS-STATUS",
                conditions=[
                    ConditionName(
                        name="STATUS-ACTIVE",
                        values=[ConditionValue(from_val="A")],
                    ),
                    ConditionName(
                        name="STATUS-INACTIVE",
                        values=[ConditionValue(from_val="I")],
                    ),
                ],
            ),
        }
        layout = DataLayout(fields=fields, groups={})
        index = build_condition_index(layout)
        assert index.has_condition("STATUS-ACTIVE")
        assert index.has_condition("STATUS-INACTIVE")
        assert index.lookup("STATUS-ACTIVE").parent == RefModOperand(name="WS-STATUS")

    @covers(CobolFeature.LEVEL_88_CONDITION)
    def test_builds_from_multiple_parent_fields(self):
        fields = {
            "WS-STATUS": _make_field_layout(
                "WS-STATUS",
                conditions=[
                    ConditionName(
                        name="IS-ACTIVE",
                        values=[ConditionValue(from_val="A")],
                    ),
                ],
            ),
            "WS-TYPE": _make_field_layout(
                "WS-TYPE",
                conditions=[
                    ConditionName(
                        name="IS-CREDIT",
                        values=[ConditionValue(from_val="C")],
                    ),
                ],
            ),
        }
        layout = DataLayout(fields=fields, groups={})
        index = build_condition_index(layout)
        assert index.lookup("IS-ACTIVE").parent == RefModOperand(name="WS-STATUS")
        assert index.lookup("IS-CREDIT").parent == RefModOperand(name="WS-TYPE")

    @covers(CobolFeature.LEVEL_88_CONDITION)
    def test_builds_empty_from_fields_without_conditions(self):
        fields = {
            "WS-AMOUNT": _make_field_layout("WS-AMOUNT", conditions=[]),
        }
        layout = DataLayout(fields=fields, groups={})
        index = build_condition_index(layout)
        assert index.entries == {}

    @covers(CobolFeature.LEVEL_88_CONDITION)
    def test_group_level_conditions_are_indexed(self):
        """Group nodes (no PIC, has children) can carry 88-level conditions.

        Example: 10 WS-PHONE-FLGS. / 88 WS-PHONE-IS-VALID VALUE LOW-VALUES.
        The group has no PIC so it is a DataLayout node, not a FieldLayout leaf.
        build_condition_index must still find and index these conditions.
        """
        child_fl = FieldLayout(
            name="WS-PHONE-AREA",
            type_descriptor=CobolTypeDescriptor(
                category=CobolDataCategory.ALPHANUMERIC, total_digits=3
            ),
            offset=0,
            byte_length=3,
        )
        group_layout = DataLayout(
            fields={"WS-PHONE-AREA": child_fl},
            groups={},
            offset=0,
            total_bytes=3,
            conditions=[
                ConditionName(
                    "WS-PHONE-IS-VALID", values=[ConditionValue("LOW-VALUES")]
                ),
                ConditionName("WS-PHONE-IS-INVALID", values=[ConditionValue("000")]),
            ],
        )
        layout = DataLayout(fields={}, groups={"WS-PHONE-FLGS": group_layout})
        index = build_condition_index(layout)
        assert index.has_condition("WS-PHONE-IS-VALID")
        assert index.has_condition("WS-PHONE-IS-INVALID")
        assert index.lookup("WS-PHONE-IS-VALID").parent == RefModOperand(
            name="WS-PHONE-FLGS"
        )
        assert index.lookup("WS-PHONE-IS-INVALID").parent == RefModOperand(
            name="WS-PHONE-FLGS"
        )

    @covers(CobolFeature.LEVEL_88_CONDITION)
    def test_preserves_multi_values(self):
        fields = {
            "WS-CODE": _make_field_layout(
                "WS-CODE",
                conditions=[
                    ConditionName(
                        name="VALID-CODE",
                        values=[
                            ConditionValue(from_val="A"),
                            ConditionValue(from_val="B"),
                            ConditionValue(from_val="X", to_val="Z"),
                        ],
                    ),
                ],
            ),
        }
        layout = DataLayout(fields=fields, groups={})
        index = build_condition_index(layout)
        entry = index.lookup("VALID-CODE")
        assert len(entry.values) == 3
        assert entry.values[2].is_range


class TestQualifiedConditionNames:
    @covers(CobolFeature.LEVEL_88_CONDITION)
    def test_parents_are_fully_qualified_and_qualifiers_select_the_declaration(self):
        def leaf(name: str, *conditions: str) -> FieldLayout:
            return _make_field_layout(
                name, [ConditionName(c, values=[ConditionValue(c)]) for c in conditions]
            )

        layout = DataLayout(
            groups={
                "R": DataLayout(
                    groups={
                        "G1": DataLayout(fields={"F": leaf("F", "OK1")}),
                        "G2": DataLayout(fields={"F": leaf("F")}),
                        "D32": DataLayout(
                            fields={"X": leaf("X")},
                            conditions=[
                                ConditionName("B", values=[ConditionValue("1")])
                            ],
                        ),
                    },
                    fields={"D33": leaf("D33", "B")},
                )
            }
        )
        index = build_condition_index(layout)
        assert index.lookup("ok1") == ConditionEntry(
            parent=RefModOperand(name="F", qualifiers=("G1", "R")),
            values=[ConditionValue("OK1")],
        )
        assert index.lookup("B", ("D32",)).parent == RefModOperand(
            name="D32", qualifiers=("R",)
        )
        assert index.lookup("B", ("D33", "R")).parent == RefModOperand(
            name="D33", qualifiers=("R",)
        )
        assert index.lookup("B", ("G1",)).parent == RefModOperand(name="")
        with pytest.raises(CobolAmbiguousReferenceError, match="'B'"):
            index.lookup("B", ("R",))
