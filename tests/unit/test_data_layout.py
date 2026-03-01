"""Tests for COBOL data layout builder."""

from interpreter.cobol.asg_types import CobolField
from interpreter.cobol.cobol_types import CobolDataCategory
from interpreter.cobol.data_layout import build_data_layout


class TestBuildDataLayoutSingleField:
    def test_single_elementary_field(self):
        fields = [
            CobolField(name="WS-A", level=77, pic="9(5)", usage="DISPLAY", offset=0),
        ]
        layout = build_data_layout(fields)
        assert layout.total_bytes == 5
        assert "WS-A" in layout.fields
        fl = layout.fields["WS-A"]
        assert fl.offset == 0
        assert fl.byte_length == 5
        assert fl.type_descriptor.category == CobolDataCategory.ZONED_DECIMAL
        assert fl.type_descriptor.total_digits == 5

    def test_comp3_field(self):
        fields = [
            CobolField(name="WS-B", level=77, pic="S9(5)V99", usage="COMP-3", offset=0),
        ]
        layout = build_data_layout(fields)
        fl = layout.fields["WS-B"]
        assert fl.type_descriptor.category == CobolDataCategory.COMP3
        assert fl.type_descriptor.total_digits == 7
        assert fl.type_descriptor.decimal_digits == 2
        assert fl.byte_length == 4  # (7 // 2) + 1

    def test_alphanumeric_field(self):
        fields = [
            CobolField(name="WS-C", level=77, pic="X(10)", usage="DISPLAY", offset=0),
        ]
        layout = build_data_layout(fields)
        fl = layout.fields["WS-C"]
        assert fl.type_descriptor.category == CobolDataCategory.ALPHANUMERIC
        assert fl.byte_length == 10


class TestBuildDataLayoutGroup:
    def test_group_with_children(self):
        fields = [
            CobolField(
                name="WS-DATE",
                level=1,
                pic="",
                usage="DISPLAY",
                offset=0,
                children=[
                    CobolField(
                        name="WS-YEAR", level=5, pic="9(4)", usage="DISPLAY", offset=0
                    ),
                    CobolField(
                        name="WS-MONTH", level=5, pic="99", usage="DISPLAY", offset=4
                    ),
                    CobolField(
                        name="WS-DAY", level=5, pic="99", usage="DISPLAY", offset=6
                    ),
                ],
            ),
        ]
        layout = build_data_layout(fields)
        assert layout.total_bytes == 8
        assert layout.fields["WS-DATE"].byte_length == 8
        assert layout.fields["WS-YEAR"].offset == 0
        assert layout.fields["WS-YEAR"].byte_length == 4
        assert layout.fields["WS-MONTH"].offset == 4
        assert layout.fields["WS-MONTH"].byte_length == 2
        assert layout.fields["WS-DAY"].offset == 6
        assert layout.fields["WS-DAY"].byte_length == 2


class TestBuildDataLayoutRedefines:
    def test_redefines_shares_offset(self):
        fields = [
            CobolField(
                name="WS-DATE",
                level=1,
                pic="",
                usage="DISPLAY",
                offset=0,
                children=[
                    CobolField(
                        name="WS-YEAR", level=5, pic="9(4)", usage="DISPLAY", offset=0
                    ),
                    CobolField(
                        name="WS-MONTH", level=5, pic="99", usage="DISPLAY", offset=4
                    ),
                    CobolField(
                        name="WS-DAY", level=5, pic="99", usage="DISPLAY", offset=6
                    ),
                ],
            ),
            CobolField(
                name="WS-DATE-NUM",
                level=1,
                pic="9(8)",
                usage="DISPLAY",
                offset=0,
                redefines="WS-DATE",
            ),
        ]
        layout = build_data_layout(fields)
        # REDEFINES does not increase total size
        assert layout.total_bytes == 8
        assert layout.fields["WS-DATE-NUM"].offset == 0
        assert layout.fields["WS-DATE-NUM"].byte_length == 8
        assert layout.fields["WS-DATE-NUM"].redefines == "WS-DATE"


class TestBuildDataLayoutMultipleTopLevel:
    def test_multiple_independent_fields(self):
        fields = [
            CobolField(name="WS-A", level=77, pic="9(5)", usage="DISPLAY", offset=0),
            CobolField(name="WS-B", level=77, pic="X(10)", usage="DISPLAY", offset=0),
        ]
        layout = build_data_layout(fields)
        assert layout.total_bytes == 15
        assert len(layout.fields) == 2


class TestBuildDataLayoutNestedGroups:
    def test_nested_group(self):
        fields = [
            CobolField(
                name="WS-REC",
                level=1,
                pic="",
                usage="DISPLAY",
                offset=0,
                children=[
                    CobolField(
                        name="WS-HEADER",
                        level=5,
                        pic="",
                        usage="DISPLAY",
                        offset=0,
                        children=[
                            CobolField(
                                name="WS-ID",
                                level=10,
                                pic="9(3)",
                                usage="DISPLAY",
                                offset=0,
                            ),
                            CobolField(
                                name="WS-TYPE",
                                level=10,
                                pic="X(2)",
                                usage="DISPLAY",
                                offset=3,
                            ),
                        ],
                    ),
                    CobolField(
                        name="WS-BODY",
                        level=5,
                        pic="X(20)",
                        usage="DISPLAY",
                        offset=5,
                    ),
                ],
            ),
        ]
        layout = build_data_layout(fields)
        assert layout.total_bytes == 25
        assert layout.fields["WS-HEADER"].byte_length == 5
        assert layout.fields["WS-ID"].offset == 0
        assert layout.fields["WS-TYPE"].offset == 3
        assert layout.fields["WS-BODY"].offset == 5


class TestBuildDataLayoutFieldValue:
    def test_field_with_initial_value(self):
        fields = [
            CobolField(
                name="WS-CTR",
                level=77,
                pic="9(3)",
                usage="DISPLAY",
                offset=0,
                value="0",
            ),
        ]
        layout = build_data_layout(fields)
        assert layout.fields["WS-CTR"].value == "0"
