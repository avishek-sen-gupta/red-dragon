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


class TestBuildDataLayoutCompTypes:
    def test_comp_field(self):
        """COMP field with PIC 9(5) -> 4 bytes (BINARY category)."""
        fields = [
            CobolField(name="WS-D", level=77, pic="9(5)", usage="COMP", offset=0),
        ]
        layout = build_data_layout(fields)
        fl = layout.fields["WS-D"]
        assert fl.type_descriptor.category == CobolDataCategory.BINARY
        assert fl.type_descriptor.total_digits == 5
        assert fl.byte_length == 4

    def test_comp1_field_no_pic(self):
        """COMP-1 field has no PIC clause -> 4 bytes (single float)."""
        fields = [
            CobolField(name="WS-E", level=77, pic="", usage="COMP-1", offset=0),
        ]
        layout = build_data_layout(fields)
        fl = layout.fields["WS-E"]
        assert fl.type_descriptor.category == CobolDataCategory.COMP1
        assert fl.byte_length == 4

    def test_comp2_field_no_pic(self):
        """COMP-2 field has no PIC clause -> 8 bytes (double float)."""
        fields = [
            CobolField(name="WS-F", level=77, pic="", usage="COMP-2", offset=0),
        ]
        layout = build_data_layout(fields)
        fl = layout.fields["WS-F"]
        assert fl.type_descriptor.category == CobolDataCategory.COMP2
        assert fl.byte_length == 8

    def test_comp5_field(self):
        """COMP-5 field with PIC 9(4) -> 2 bytes (BINARY category)."""
        fields = [
            CobolField(name="WS-G", level=77, pic="9(4)", usage="COMP-5", offset=0),
        ]
        layout = build_data_layout(fields)
        fl = layout.fields["WS-G"]
        assert fl.type_descriptor.category == CobolDataCategory.BINARY
        assert fl.byte_length == 2


class TestBuildDataLayoutOccursDependingOn:
    def test_occurs_depending_on_uses_max_storage(self):
        """OCCURS DEPENDING ON allocates max (n) elements in layout."""
        fields = [
            CobolField(
                name="WS-TABLE",
                level=77,
                pic="X(5)",
                usage="DISPLAY",
                offset=0,
                occurs=10,
                element_size=5,
                occurs_depending_on="WS-COUNT",
                occurs_min=1,
            ),
        ]
        layout = build_data_layout(fields)
        fl = layout.fields["WS-TABLE"]
        assert fl.byte_length == 50  # 10 * 5 = max storage
        assert fl.occurs_count == 10
        assert fl.occurs_depending_on == "WS-COUNT"
        assert fl.occurs_min == 1

    def test_occurs_depending_on_propagated(self):
        """OCCURS DEPENDING ON fields propagate through layout."""
        fields = [
            CobolField(
                name="WS-REC",
                level=1,
                pic="",
                usage="DISPLAY",
                offset=0,
                children=[
                    CobolField(
                        name="WS-COUNT",
                        level=5,
                        pic="9(3)",
                        usage="DISPLAY",
                        offset=0,
                    ),
                    CobolField(
                        name="WS-ITEMS",
                        level=5,
                        pic="X(10)",
                        usage="DISPLAY",
                        offset=3,
                        occurs=20,
                        element_size=10,
                        occurs_depending_on="WS-COUNT",
                        occurs_min=1,
                    ),
                ],
            ),
        ]
        layout = build_data_layout(fields)
        fl = layout.fields["WS-ITEMS"]
        assert fl.occurs_depending_on == "WS-COUNT"
        assert fl.occurs_min == 1
        assert fl.byte_length == 200  # 20 * 10


class TestBuildDataLayoutSignClause:
    def test_sign_separate_adds_one_byte(self):
        """SIGN IS TRAILING SEPARATE adds 1 byte to zoned decimal storage."""
        fields = [
            CobolField(
                name="WS-AMT",
                level=77,
                pic="S9(5)",
                usage="DISPLAY",
                offset=0,
                sign_separate=True,
                sign_leading=False,
            ),
        ]
        layout = build_data_layout(fields)
        fl = layout.fields["WS-AMT"]
        assert fl.type_descriptor.sign_separate is True
        assert fl.type_descriptor.sign_leading is False
        assert fl.byte_length == 6  # 5 digits + 1 sign byte
        assert fl.type_descriptor.byte_length == 6

    def test_sign_leading_separate_adds_one_byte(self):
        """SIGN IS LEADING SEPARATE adds 1 byte."""
        fields = [
            CobolField(
                name="WS-AMT2",
                level=77,
                pic="S9(3)",
                usage="DISPLAY",
                offset=0,
                sign_separate=True,
                sign_leading=True,
            ),
        ]
        layout = build_data_layout(fields)
        fl = layout.fields["WS-AMT2"]
        assert fl.byte_length == 4  # 3 digits + 1 sign byte
        assert fl.sign_separate is True
        assert fl.sign_leading is True

    def test_sign_leading_embedded_same_size(self):
        """SIGN IS LEADING (no SEPARATE) — same byte length as trailing embedded."""
        fields = [
            CobolField(
                name="WS-AMT3",
                level=77,
                pic="S9(5)",
                usage="DISPLAY",
                offset=0,
                sign_leading=True,
                sign_separate=False,
            ),
        ]
        layout = build_data_layout(fields)
        fl = layout.fields["WS-AMT3"]
        assert fl.byte_length == 5  # embedded, no extra byte


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
