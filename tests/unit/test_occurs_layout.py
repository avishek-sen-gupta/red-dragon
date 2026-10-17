"""Tests for OCCURS support in data layout computation."""

from cobol_asg.asg_types import CobolField
from interpreter.cobol.data_layout import build_data_layout
from tests.covers import NotLanguageFeature, covers


class TestElementaryOccurs:
    @covers(NotLanguageFeature.INFRASTRUCTURE)
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
        fl = layout.lookup("WS-TBL")
        assert fl is not None
        assert fl.byte_length == 20
        assert fl.occurs_count == 5
        assert fl.element_size == 4

    @covers(NotLanguageFeature.INFRASTRUCTURE)
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
        fl = layout.lookup("WS-PLAIN")
        assert fl is not None
        assert fl.byte_length == 4
        assert fl.occurs_count == 0

    @covers(NotLanguageFeature.INFRASTRUCTURE)
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
        assert layout.lookup("WS-TBL").byte_length == 12  # type: ignore[union-attr]
        assert layout.lookup("WS-AFTER").byte_length == 2  # type: ignore[union-attr]


class TestGroupOccurs:
    @covers(NotLanguageFeature.INFRASTRUCTURE)
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
        grp = layout.lookup_group("WS-GROUP")
        assert grp.total_bytes == 6
        assert grp.occurs_count == 3
        assert grp.element_size == 2
        # Child field
        item = layout.lookup("WS-ITEM")
        assert item is not None
        assert item.byte_length == 2
        assert item.offset == 0


class TestCobolFieldOccursSerialization:
    @covers(NotLanguageFeature.INFRASTRUCTURE)
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

    @covers(NotLanguageFeature.INFRASTRUCTURE)
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

    @covers(NotLanguageFeature.INFRASTRUCTURE)
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

    @covers(NotLanguageFeature.INFRASTRUCTURE)
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


class TestInitialisedOccurrences:
    @covers(NotLanguageFeature.INFRASTRUCTURE)
    def test_a_valued_item_is_placed_at_every_occurrence_of_every_table(self):
        """A VALUE under OCCURS 2 and on its own OCCURS 3 lands six times, one
        element wide each, at offset + row * 4 + column * 1."""
        fields = [
            CobolField(
                name="WS-GRID",
                level=1,
                pic="",
                usage="DISPLAY",
                offset=0,
                children=[
                    CobolField(
                        name="WS-LINE",
                        level=3,
                        pic="",
                        usage="DISPLAY",
                        offset=0,
                        occurs=2,
                        element_size=4,
                        children=[
                            CobolField(
                                name="WS-TAG",
                                level=5,
                                pic="X",
                                usage="DISPLAY",
                                offset=0,
                                value="T",
                            ),
                            CobolField(
                                name="WS-CELL",
                                level=5,
                                pic="X",
                                usage="DISPLAY",
                                offset=1,
                                occurs=3,
                                element_size=1,
                                value="Q",
                            ),
                        ],
                    ),
                ],
            ),
        ]
        layout = build_data_layout(fields)

        def placed(name: str) -> list[tuple[int, int, str, int]]:
            (match,) = layout.qualified_matches(name, ())
            return [
                (fl.offset, fl.byte_length, fl.value, fl.occurs_count)
                for fl in match.initialised_occurrences
            ]

        assert (placed("WS-TAG"), placed("WS-CELL")) == (
            [(0, 1, "T", 0), (4, 1, "T", 0)],
            [(c, 1, "Q", 0) for c in (1, 2, 3, 5, 6, 7)],
        )
