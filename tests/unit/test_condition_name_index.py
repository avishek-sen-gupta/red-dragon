"""Tests for ConditionNameIndex and build_condition_index."""

from interpreter.cobol.condition_name import ConditionName, ConditionValue
from interpreter.cobol.condition_name_index import (
    ConditionEntry,
    ConditionNameIndex,
    build_condition_index,
)
from interpreter.cobol.cobol_types import CobolTypeDescriptor, CobolDataCategory
from interpreter.cobol.data_layout import FieldLayout


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
    def test_lookup_existing(self):
        entries = {
            "STATUS-ACTIVE": ConditionEntry(
                parent_field_name="WS-STATUS",
                values=[ConditionValue(from_val="A")],
            ),
        }
        index = ConditionNameIndex(entries)
        entry = index.lookup("STATUS-ACTIVE")
        assert entry.parent_field_name == "WS-STATUS"
        assert len(entry.values) == 1

    def test_lookup_missing(self):
        index = ConditionNameIndex({})
        entry = index.lookup("NONEXISTENT")
        assert entry.parent_field_name == ""
        assert entry.values == []

    def test_has_condition(self):
        entries = {
            "IS-ACTIVE": ConditionEntry(
                parent_field_name="WS-FLAG",
                values=[ConditionValue(from_val="1")],
            ),
        }
        index = ConditionNameIndex(entries)
        assert index.has_condition("IS-ACTIVE")
        assert not index.has_condition("IS-INACTIVE")

    def test_empty_index(self):
        index = ConditionNameIndex({})
        assert not index.has_condition("ANYTHING")
        assert index.entries == {}


class TestBuildConditionIndex:
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
        index = build_condition_index(fields)
        assert index.has_condition("STATUS-ACTIVE")
        assert index.has_condition("STATUS-INACTIVE")
        assert index.lookup("STATUS-ACTIVE").parent_field_name == "WS-STATUS"

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
        index = build_condition_index(fields)
        assert index.lookup("IS-ACTIVE").parent_field_name == "WS-STATUS"
        assert index.lookup("IS-CREDIT").parent_field_name == "WS-TYPE"

    def test_builds_empty_from_fields_without_conditions(self):
        fields = {
            "WS-AMOUNT": _make_field_layout("WS-AMOUNT", conditions=[]),
        }
        index = build_condition_index(fields)
        assert index.entries == {}

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
        index = build_condition_index(fields)
        entry = index.lookup("VALID-CODE")
        assert len(entry.values) == 3
        assert entry.values[2].is_range
