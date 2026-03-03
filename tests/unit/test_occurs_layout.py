"""Tests for OCCURS support in data layout computation."""

from interpreter.cobol.asg_types import CobolField
from interpreter.cobol.cobol_types import CobolDataCategory
from interpreter.cobol.data_layout import build_data_layout


class TestElementaryOccurs:
    def test_elementary_occurs_multiplies_length(self):
        """PIC 9(4) OCCURS 5 → byte_length=20, element_size=4, occurs_count=5."""
        fields = [
            CobolField(
                name="WS-TBL",
                level=77,
                pic="9(4)",
                usage="DISPLAY",
                offset=0,
                occurs=5,
                element_size=4,
            ),
        ]
        layout = build_data_layout(fields)
        assert layout.total_bytes == 20
        fl = layout.fields["WS-TBL"]
        assert fl.byte_length == 20
        assert fl.occurs_count == 5
        assert fl.element_size == 4

    def test_non_occurs_field_unaffected(self):
        """Non-OCCURS fields retain normal byte_length."""
        fields = [
            CobolField(
                name="WS-PLAIN",
                level=77,
                pic="9(4)",
                usage="DISPLAY",
                offset=0,
            ),
        ]
        layout = build_data_layout(fields)
        fl = layout.fields["WS-PLAIN"]
        assert fl.byte_length == 4
        assert fl.occurs_count == 0

    def test_occurs_with_following_field(self):
        """OCCURS field followed by a non-OCCURS field gets correct offsets."""
        fields = [
            CobolField(
                name="WS-TBL",
                level=77,
                pic="9(4)",
                usage="DISPLAY",
                offset=0,
                occurs=3,
                element_size=4,
            ),
            CobolField(
                name="WS-AFTER",
                level=77,
                pic="9(2)",
                usage="DISPLAY",
                offset=0,
            ),
        ]
        layout = build_data_layout(fields)
        assert layout.total_bytes == 14  # 4*3 + 2
        assert layout.fields["WS-TBL"].byte_length == 12
        assert layout.fields["WS-AFTER"].byte_length == 2


class TestGroupOccurs:
    def test_group_occurs_multiplies_total(self):
        """Group item with OCCURS 3 containing 2-byte child → 6 bytes total."""
        fields = [
            CobolField(
                name="WS-GROUP",
                level=1,
                pic="",
                usage="DISPLAY",
                offset=0,
                occurs=3,
                element_size=2,
                children=[
                    CobolField(
                        name="WS-ITEM",
                        level=5,
                        pic="9(2)",
                        usage="DISPLAY",
                        offset=0,
                    ),
                ],
            ),
        ]
        layout = build_data_layout(fields)
        assert layout.total_bytes == 6
        assert layout.fields["WS-GROUP"].byte_length == 6
        assert layout.fields["WS-GROUP"].occurs_count == 3
        assert layout.fields["WS-GROUP"].element_size == 2
        # Child field has its own layout (first element)
        assert layout.fields["WS-ITEM"].byte_length == 2
        assert layout.fields["WS-ITEM"].offset == 0


class TestCobolFieldOccursSerialization:
    def test_from_dict_with_occurs(self):
        """CobolField.from_dict correctly parses occurs and element_size."""
        data = {
            "name": "WS-TBL",
            "level": 77,
            "pic": "9(4)",
            "usage": "DISPLAY",
            "offset": 0,
            "occurs": 5,
            "element_size": 4,
        }
        field = CobolField.from_dict(data)
        assert field.occurs == 5
        assert field.element_size == 4

    def test_from_dict_without_occurs(self):
        """CobolField.from_dict defaults occurs to 0."""
        data = {
            "name": "WS-A",
            "level": 77,
            "pic": "9(4)",
            "usage": "DISPLAY",
            "offset": 0,
        }
        field = CobolField.from_dict(data)
        assert field.occurs == 0
        assert field.element_size == 0

    def test_to_dict_with_occurs(self):
        """CobolField.to_dict includes occurs and element_size when nonzero."""
        field = CobolField(
            name="WS-TBL",
            level=77,
            pic="9(4)",
            usage="DISPLAY",
            offset=0,
            occurs=5,
            element_size=4,
        )
        d = field.to_dict()
        assert d["occurs"] == 5
        assert d["element_size"] == 4

    def test_to_dict_without_occurs(self):
        """CobolField.to_dict omits occurs and element_size when zero."""
        field = CobolField(
            name="WS-A",
            level=77,
            pic="9(4)",
            usage="DISPLAY",
            offset=0,
        )
        d = field.to_dict()
        assert "occurs" not in d
        assert "element_size" not in d
