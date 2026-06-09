"""Tests for COBOL data layout builder."""

from interpreter.cobol.asg_types import CobolField
from interpreter.cobol.cobol_types import CobolDataCategory
from interpreter.cobol.data_layout import build_data_layout
from interpreter.cobol.features import CobolFeature
from tests.covers import covers, NotLanguageFeature


class TestBuildDataLayoutSingleField:
    @covers(NotLanguageFeature.INFRASTRUCTURE)
    def test_single_elementary_field(self):
        fields = [
            CobolField(name="WS-A", level=77, pic="9(5)", usage="DISPLAY", offset=0),
        ]
        layout = build_data_layout(fields)
        assert layout.total_bytes == 5
        fl = layout.lookup("WS-A")
        assert fl is not None
        assert fl.offset == 0
        assert fl.byte_length == 5
        assert fl.type_descriptor.category == CobolDataCategory.ZONED_DECIMAL
        assert fl.type_descriptor.total_digits == 5

    @covers(NotLanguageFeature.INFRASTRUCTURE)
    def test_comp3_field(self):
        fields = [
            CobolField(name="WS-B", level=77, pic="S9(5)V99", usage="COMP-3", offset=0),
        ]
        layout = build_data_layout(fields)
        fl = layout.lookup("WS-B")
        assert fl is not None
        assert fl.type_descriptor.category == CobolDataCategory.COMP3
        assert fl.type_descriptor.total_digits == 7
        assert fl.type_descriptor.decimal_digits == 2
        assert fl.byte_length == 4  # (7 // 2) + 1

    @covers(NotLanguageFeature.INFRASTRUCTURE)
    def test_alphanumeric_field(self):
        fields = [
            CobolField(name="WS-C", level=77, pic="X(10)", usage="DISPLAY", offset=0),
        ]
        layout = build_data_layout(fields)
        fl = layout.lookup("WS-C")
        assert fl is not None
        assert fl.type_descriptor.category == CobolDataCategory.ALPHANUMERIC
        assert fl.byte_length == 10


class TestBuildDataLayoutGroup:
    @covers(NotLanguageFeature.INFRASTRUCTURE)
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
        # WS-DATE is a group — use lookup_group for structural check
        date_grp = layout.lookup_group("WS-DATE")
        assert date_grp.total_bytes == 8
        # Children are leaves — use lookup()
        assert layout.lookup("WS-YEAR").offset == 0  # type: ignore[union-attr]
        assert layout.lookup("WS-YEAR").byte_length == 4  # type: ignore[union-attr]
        assert layout.lookup("WS-MONTH").offset == 4  # type: ignore[union-attr]
        assert layout.lookup("WS-MONTH").byte_length == 2  # type: ignore[union-attr]
        assert layout.lookup("WS-DAY").offset == 6  # type: ignore[union-attr]
        assert layout.lookup("WS-DAY").byte_length == 2  # type: ignore[union-attr]


class TestGroupLengthFromPlacedExtent:
    """A group's byte length is derived from its children's PLACED extents
    (compiler-assigned offsets), not from summing our own length estimates.

    When a child's own computed length over-reaches the next sibling's
    compiler-assigned offset (e.g. an edited-PIC field our PIC parser sizes
    differently than the real compiler), the group must not over-count and
    overlap the following sibling. (CardDemo COACTUPC WS-MISC-STORAGE overlapped
    WS-LITERALS by 9 bytes, clobbering LIT-THISPGM's VALUE.)"""

    @covers(NotLanguageFeature.INFRASTRUCTURE)
    def test_group_total_does_not_overlap_next_sibling(self):
        # Two sibling 05 groups under a 01. The compiler placed the SECOND group
        # at offset 20 (so the FIRST occupies exactly 20 bytes), but the first
        # group's children, summed, would compute to 24 bytes (an edited-PIC
        # over-estimate). The group total must clamp to the placed extent (20).
        fields = [
            CobolField(
                name="REC",
                level=1,
                pic="",
                usage="DISPLAY",
                offset=0,
                children=[
                    CobolField(
                        name="GRP-A",
                        level=5,
                        pic="",
                        usage="DISPLAY",
                        offset=0,
                        children=[
                            CobolField(
                                name="A1",
                                level=10,
                                pic="X(10)",
                                usage="DISPLAY",
                                offset=0,
                            ),
                            # Compiler placed A2 at offset 10 within GRP-A but
                            # GRP-B (next sibling) starts at 20, so A2 spans only
                            # 10 bytes even though its PIC would parse to 14.
                            CobolField(
                                name="A2",
                                level=10,
                                pic="+ZZZ,ZZZ,ZZ9.99",
                                usage="DISPLAY",
                                offset=10,
                            ),
                        ],
                    ),
                    CobolField(
                        name="GRP-B",
                        level=5,
                        pic="",
                        usage="DISPLAY",
                        offset=20,
                        children=[
                            CobolField(
                                name="B1",
                                level=10,
                                pic="X(5)",
                                usage="DISPLAY",
                                offset=0,
                            ),
                        ],
                    ),
                ],
            ),
        ]
        layout = build_data_layout(fields)
        grp_b = layout.lookup_group("GRP-B")
        rec = layout.lookup_group("REC")
        # GRP-B is placed at 20 (so GRP-A spans exactly 20 bytes). REC's total
        # must reflect the compiler-placed extent: GRP-A clamped to GRP-B's
        # offset (20) + GRP-B (5) = 25 — NOT 21 (A2 over-reach) + 5 = 26. The
        # parent total is what INITIALIZE/MOVE use, and what overlapped the next
        # 01 in the CardDemo regression.
        assert grp_b.offset == 20
        assert rec.total_bytes == 25, (
            f"REC total {rec.total_bytes} (expected 25); GRP-A over-reach was "
            f"not clamped to GRP-B's placed offset"
        )

    @covers(NotLanguageFeature.INFRASTRUCTURE)
    def test_simple_group_length_unchanged(self):
        # No over-reach: a plain group still totals its children's bytes.
        fields = [
            CobolField(
                name="G",
                level=1,
                pic="",
                usage="DISPLAY",
                offset=0,
                children=[
                    CobolField(
                        name="X", level=5, pic="X(4)", usage="DISPLAY", offset=0
                    ),
                    CobolField(
                        name="Y", level=5, pic="X(6)", usage="DISPLAY", offset=4
                    ),
                ],
            ),
        ]
        layout = build_data_layout(fields)
        assert layout.lookup_group("G").total_bytes == 10


class TestEnclosingOccursElementSize:
    """A leaf nested inside an OCCURS group is subscripted with the GROUP's
    element_size as the stride, not the leaf's own byte_length (CardDemo
    CDEMO-MENU-OPT-PGMNAME(WS-OPTION) regression)."""

    def _menu_layout(self):
        # 01 TBL.  05 ENTRY OCCURS 3.  10 NUM 9(2). 10 PGM X(8). 10 USR X(1).
        # element_size = 2 + 8 + 1 = 11
        fields = [
            CobolField(
                name="TBL",
                level=1,
                pic="",
                usage="DISPLAY",
                offset=0,
                children=[
                    CobolField(
                        name="ENTRY",
                        level=5,
                        pic="",
                        usage="DISPLAY",
                        offset=0,
                        occurs=3,
                        element_size=11,
                        children=[
                            CobolField(
                                name="NUM",
                                level=10,
                                pic="9(2)",
                                usage="DISPLAY",
                                offset=0,
                            ),
                            CobolField(
                                name="PGM",
                                level=10,
                                pic="X(8)",
                                usage="DISPLAY",
                                offset=2,
                            ),
                            CobolField(
                                name="USR",
                                level=10,
                                pic="X(1)",
                                usage="DISPLAY",
                                offset=10,
                            ),
                        ],
                    ),
                ],
            ),
        ]
        return build_data_layout(fields)

    @covers(NotLanguageFeature.INFRASTRUCTURE)
    def test_leaf_inside_occurs_group_returns_group_element_size(self):
        layout = self._menu_layout()
        # PGM lives inside ENTRY OCCURS (element_size 11), so subscripting PGM
        # must stride by 11, not by PGM's own 8 bytes.
        assert layout.enclosing_occurs_element_size("PGM") == 11
        assert layout.enclosing_occurs_element_size("NUM") == 11
        assert layout.enclosing_occurs_element_size("USR") == 11

    @covers(NotLanguageFeature.INFRASTRUCTURE)
    def test_field_not_in_occurs_returns_zero(self):
        fields = [
            CobolField(name="WS-A", level=77, pic="X(5)", usage="DISPLAY", offset=0),
        ]
        layout = build_data_layout(fields)
        assert layout.enclosing_occurs_element_size("WS-A") == 0

    @covers(NotLanguageFeature.INFRASTRUCTURE)
    def test_occurs_group_itself_returns_its_element_size(self):
        layout = self._menu_layout()
        assert layout.enclosing_occurs_element_size("ENTRY") == 11


class TestBuildDataLayoutOccursDependingOnMixedCase:
    """OCCURS 0 TO n DEPENDING ON variable-length subordinate fields, declared
    in mixed case (the CardDemo CSUTLDTC Vstring pattern). COBOL identifiers are
    case-insensitive, so the upper-case PROCEDURE references must resolve against
    the mixed-case layout keys. red-dragon-p7qe."""

    def _vstring_layout(self):
        # 01 WS-DATE-TO-TEST.
        #   02 Vstring-length S9(4) BINARY @0 (2 bytes).
        #   02 Vstring-text @2.
        #      03 Vstring-char X OCCURS 0 TO 256 DEPENDING ON Vstring-length @0.
        # 01 WS-AFTER X(4) @258 (after the MAX-length ODO array).
        return build_data_layout(
            [
                CobolField(
                    name="WS-DATE-TO-TEST",
                    level=1,
                    pic="",
                    usage="DISPLAY",
                    offset=0,
                    children=[
                        CobolField(
                            name="Vstring-length",
                            level=2,
                            pic="S9(4)",
                            usage="COMP",
                            offset=0,
                        ),
                        CobolField(
                            name="Vstring-text",
                            level=2,
                            pic="",
                            usage="DISPLAY",
                            offset=2,
                            children=[
                                CobolField(
                                    name="Vstring-char",
                                    level=3,
                                    pic="X",
                                    usage="DISPLAY",
                                    offset=0,
                                    occurs=256,
                                    element_size=1,
                                    occurs_depending_on="Vstring-length",
                                ),
                            ],
                        ),
                    ],
                ),
                CobolField(
                    name="WS-AFTER", level=1, pic="X(4)", usage="DISPLAY", offset=258
                ),
            ]
        )

    @covers(CobolFeature.OCCURS_DEPENDING_ON)
    def test_odo_fields_resolve_case_insensitively(self):
        """The mixed-case length + ODO element resolve under upper-case names."""
        layout = self._vstring_layout()
        length = layout.lookup("VSTRING-LENGTH")
        assert length is not None
        assert length.offset == 0
        char = layout.lookup("VSTRING-CHAR")
        assert char is not None
        # The ODO element is laid out at MAX (256 elements) starting at offset 2.
        assert char.offset == 2
        assert char.occurs_count == 256
        assert char.element_size == 1
        assert char.occurs_depending_on == "Vstring-length"

    @covers(CobolFeature.OCCURS_DEPENDING_ON)
    def test_trailing_field_offset_is_past_max_odo_array(self):
        """A field following the ODO item sits past the MAX-length array."""
        layout = self._vstring_layout()
        after = layout.lookup("WS-AFTER")
        assert after is not None
        # 2 (length) + 256 (Vstring-char OCCURS at max) = 258.
        assert after.offset == 258

    @covers(CobolFeature.OCCURS_DEPENDING_ON)
    def test_odo_group_lookup_case_insensitive(self):
        """The enclosing ODO group resolves under an upper-case query too."""
        layout = self._vstring_layout()
        grp = layout.lookup_group("VSTRING-TEXT")
        assert grp.offset == 2


class TestBuildDataLayoutRedefines:
    @covers(NotLanguageFeature.INFRASTRUCTURE)
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
        assert layout.total_bytes == 8
        fl = layout.lookup("WS-DATE-NUM")
        assert fl is not None
        assert fl.offset == 0
        assert fl.byte_length == 8
        assert fl.redefines == "WS-DATE"


class TestBuildDataLayoutMultipleTopLevel:
    @covers(NotLanguageFeature.INFRASTRUCTURE)
    def test_multiple_independent_fields(self):
        fields = [
            CobolField(name="WS-A", level=77, pic="9(5)", usage="DISPLAY", offset=0),
            CobolField(name="WS-B", level=77, pic="X(10)", usage="DISPLAY", offset=0),
        ]
        layout = build_data_layout(fields)
        assert layout.total_bytes == 15
        assert sum(1 for _ in layout.all_leaves()) == 2


class TestBuildDataLayoutNestedGroups:
    @covers(NotLanguageFeature.INFRASTRUCTURE)
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
        header_grp = layout.lookup_group("WS-HEADER")
        assert header_grp.total_bytes == 5
        assert layout.lookup("WS-ID").offset == 0  # type: ignore[union-attr]
        assert layout.lookup("WS-TYPE").offset == 3  # type: ignore[union-attr]
        assert layout.lookup("WS-BODY").offset == 5  # type: ignore[union-attr]


class TestBuildDataLayoutCompTypes:
    @covers(NotLanguageFeature.INFRASTRUCTURE)
    def test_comp_field(self):
        """COMP field with PIC 9(5) -> 4 bytes (BINARY category)."""
        fields = [
            CobolField(name="WS-D", level=77, pic="9(5)", usage="COMP", offset=0),
        ]
        layout = build_data_layout(fields)
        fl = layout.lookup("WS-D")
        assert fl is not None
        assert fl.type_descriptor.category == CobolDataCategory.BINARY
        assert fl.type_descriptor.total_digits == 5
        assert fl.byte_length == 4

    @covers(NotLanguageFeature.INFRASTRUCTURE)
    def test_comp1_field_no_pic(self):
        """COMP-1 field has no PIC clause -> 4 bytes (single float)."""
        fields = [
            CobolField(name="WS-E", level=77, pic="", usage="COMP-1", offset=0),
        ]
        layout = build_data_layout(fields)
        fl = layout.lookup("WS-E")
        assert fl is not None
        assert fl.type_descriptor.category == CobolDataCategory.COMP1
        assert fl.byte_length == 4

    @covers(NotLanguageFeature.INFRASTRUCTURE)
    def test_comp2_field_no_pic(self):
        """COMP-2 field has no PIC clause -> 8 bytes (double float)."""
        fields = [
            CobolField(name="WS-F", level=77, pic="", usage="COMP-2", offset=0),
        ]
        layout = build_data_layout(fields)
        fl = layout.lookup("WS-F")
        assert fl is not None
        assert fl.type_descriptor.category == CobolDataCategory.COMP2
        assert fl.byte_length == 8

    @covers(NotLanguageFeature.INFRASTRUCTURE)
    def test_comp5_field(self):
        """COMP-5 field with PIC 9(4) -> 2 bytes (BINARY category)."""
        fields = [
            CobolField(name="WS-G", level=77, pic="9(4)", usage="COMP-5", offset=0),
        ]
        layout = build_data_layout(fields)
        fl = layout.lookup("WS-G")
        assert fl is not None
        assert fl.type_descriptor.category == CobolDataCategory.BINARY
        assert fl.byte_length == 2


class TestBuildDataLayoutOccursDependingOn:
    @covers(NotLanguageFeature.INFRASTRUCTURE)
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
        fl = layout.lookup("WS-TABLE")
        assert fl is not None
        assert fl.byte_length == 50  # 10 * 5 = max storage
        assert fl.occurs_count == 10
        assert fl.occurs_depending_on == "WS-COUNT"
        assert fl.occurs_min == 1

    @covers(NotLanguageFeature.INFRASTRUCTURE)
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
        fl = layout.lookup("WS-ITEMS")
        assert fl is not None
        assert fl.occurs_depending_on == "WS-COUNT"
        assert fl.occurs_min == 1
        assert fl.byte_length == 200  # 20 * 10


class TestBuildDataLayoutSignClause:
    @covers(NotLanguageFeature.INFRASTRUCTURE)
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
        fl = layout.lookup("WS-AMT")
        assert fl is not None
        assert fl.type_descriptor.sign_separate is True
        assert fl.type_descriptor.sign_leading is False
        assert fl.byte_length == 6  # 5 digits + 1 sign byte
        assert fl.type_descriptor.byte_length == 6

    @covers(NotLanguageFeature.INFRASTRUCTURE)
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
        fl = layout.lookup("WS-AMT2")
        assert fl is not None
        assert fl.byte_length == 4  # 3 digits + 1 sign byte
        assert fl.sign_separate is True
        assert fl.sign_leading is True

    @covers(NotLanguageFeature.INFRASTRUCTURE)
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
        fl = layout.lookup("WS-AMT3")
        assert fl is not None
        assert fl.byte_length == 5  # embedded, no extra byte


class TestBuildDataLayoutRenames:
    @covers(NotLanguageFeature.INFRASTRUCTURE)
    def test_simple_renames(self):
        """Level 66 RENAMES single field — offset and length match the target."""
        fields = [
            CobolField(
                name="WS-REC",
                level=1,
                pic="",
                usage="DISPLAY",
                offset=0,
                children=[
                    CobolField(
                        name="WS-FIRST",
                        level=5,
                        pic="X(10)",
                        usage="DISPLAY",
                        offset=0,
                    ),
                    CobolField(
                        name="WS-LAST",
                        level=5,
                        pic="X(10)",
                        usage="DISPLAY",
                        offset=10,
                    ),
                ],
            ),
            CobolField(
                name="WS-ALIAS",
                level=66,
                pic="",
                usage="DISPLAY",
                offset=0,
                renames_from="WS-FIRST",
            ),
        ]
        layout = build_data_layout(fields)
        fl = layout.lookup("WS-ALIAS")
        assert fl is not None
        assert fl.offset == 0
        assert fl.byte_length == 10
        assert fl.renames_from == "WS-FIRST"
        assert fl.renames_thru == ""
        # RENAMES does not increase total_bytes
        assert layout.total_bytes == 20

    @covers(NotLanguageFeature.INFRASTRUCTURE)
    def test_renames_thru(self):
        """Level 66 RENAMES A THRU C — offset = A.offset, length spans through C."""
        fields = [
            CobolField(
                name="WS-REC",
                level=1,
                pic="",
                usage="DISPLAY",
                offset=0,
                children=[
                    CobolField(
                        name="WS-A",
                        level=5,
                        pic="X(5)",
                        usage="DISPLAY",
                        offset=0,
                    ),
                    CobolField(
                        name="WS-B",
                        level=5,
                        pic="X(3)",
                        usage="DISPLAY",
                        offset=5,
                    ),
                    CobolField(
                        name="WS-C",
                        level=5,
                        pic="X(7)",
                        usage="DISPLAY",
                        offset=8,
                    ),
                ],
            ),
            CobolField(
                name="WS-SPAN",
                level=66,
                pic="",
                usage="DISPLAY",
                offset=0,
                renames_from="WS-A",
                renames_thru="WS-C",
            ),
        ]
        layout = build_data_layout(fields)
        fl = layout.lookup("WS-SPAN")
        assert fl is not None
        assert fl.offset == 0  # WS-A offset
        assert fl.byte_length == 15  # 0 + 5 + 3 + 7 = 15 (through end of WS-C)
        assert fl.renames_from == "WS-A"
        assert fl.renames_thru == "WS-C"
        # RENAMES does not increase total_bytes
        assert layout.total_bytes == 15


class TestBuildDataLayoutBlankWhenZero:
    @covers(NotLanguageFeature.INFRASTRUCTURE)
    def test_blank_when_zero_propagated_to_type_descriptor(self):
        """BLANK WHEN ZERO field has blank_when_zero=True on type descriptor."""
        fields = [
            CobolField(
                name="WS-BWZ",
                level=77,
                pic="9(5)",
                usage="DISPLAY",
                offset=0,
                blank_when_zero=True,
            ),
        ]
        layout = build_data_layout(fields)
        fl = layout.lookup("WS-BWZ")
        assert fl is not None
        assert fl.type_descriptor.blank_when_zero is True
        assert fl.byte_length == 5  # storage unchanged

    @covers(NotLanguageFeature.INFRASTRUCTURE)
    def test_blank_when_zero_false_by_default(self):
        """Fields without BLANK WHEN ZERO have blank_when_zero=False."""
        fields = [
            CobolField(
                name="WS-PLAIN",
                level=77,
                pic="9(5)",
                usage="DISPLAY",
                offset=0,
            ),
        ]
        layout = build_data_layout(fields)
        fl = layout.lookup("WS-PLAIN")
        assert fl is not None
        assert fl.type_descriptor.blank_when_zero is False


class TestBuildDataLayoutFieldValue:
    @covers(NotLanguageFeature.INFRASTRUCTURE)
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
        fl = layout.lookup("WS-CTR")
        assert fl is not None
        assert fl.value == "0"


class TestBuildDataLayoutMoveCorresponding:
    @covers(NotLanguageFeature.INFRASTRUCTURE)
    def test_lookup_group_returns_datalayout(self):
        """lookup_group('WS-SRC') returns a DataLayout with direct leaf fields."""
        fields = [
            CobolField(
                name="WS-SRC",
                level=1,
                pic="",
                usage="DISPLAY",
                offset=0,
                children=[
                    CobolField(
                        name="WS-A", level=5, pic="X(5)", usage="DISPLAY", offset=0
                    ),
                    CobolField(
                        name="WS-B", level=5, pic="X(5)", usage="DISPLAY", offset=5
                    ),
                ],
            ),
            CobolField(
                name="WS-DST",
                level=1,
                pic="",
                usage="DISPLAY",
                offset=0,
                children=[
                    CobolField(
                        name="WS-A", level=5, pic="X(5)", usage="DISPLAY", offset=0
                    ),
                    CobolField(
                        name="WS-C", level=5, pic="X(5)", usage="DISPLAY", offset=5
                    ),
                ],
            ),
        ]
        layout = build_data_layout(fields)
        src = layout.lookup_group("WS-SRC")
        dst = layout.lookup_group("WS-DST")
        assert "WS-A" in src.fields
        assert "WS-B" in src.fields
        assert "WS-A" in dst.fields
        assert "WS-C" in dst.fields
        matching = src.fields.keys() & dst.fields.keys()
        assert matching == {"WS-A"}
        assert "WS-B" not in dst.fields
        assert "WS-C" not in src.fields

    @covers(NotLanguageFeature.INFRASTRUCTURE)
    def test_no_flat_dict_collision_same_child_name(self):
        """WS-SRC.WS-A and WS-DST.WS-A do not overwrite each other."""
        fields = [
            CobolField(
                name="WS-SRC",
                level=1,
                pic="",
                usage="DISPLAY",
                offset=0,
                children=[
                    CobolField(
                        name="WS-A", level=5, pic="X(3)", usage="DISPLAY", offset=0
                    ),
                ],
            ),
            CobolField(
                name="WS-DST",
                level=1,
                pic="",
                usage="DISPLAY",
                offset=3,
                children=[
                    CobolField(
                        name="WS-A", level=5, pic="9(4)", usage="DISPLAY", offset=0
                    ),
                ],
            ),
        ]
        layout = build_data_layout(fields)
        src_a = layout.lookup_group("WS-SRC").fields["WS-A"]
        dst_a = layout.lookup_group("WS-DST").fields["WS-A"]
        assert src_a.byte_length == 3
        assert dst_a.byte_length == 4
        assert src_a.offset == 0
        assert dst_a.offset == 3

    @covers(NotLanguageFeature.INFRASTRUCTURE)
    def test_lookup_returns_leaf_by_name(self):
        fields = [
            CobolField(
                name="WS-REC",
                level=1,
                pic="",
                usage="DISPLAY",
                offset=0,
                children=[
                    CobolField(
                        name="WS-X", level=5, pic="9(2)", usage="DISPLAY", offset=0
                    ),
                ],
            ),
        ]
        layout = build_data_layout(fields)
        fl = layout.lookup("WS-X")
        assert fl is not None
        assert fl.name == "WS-X"
        assert fl.byte_length == 2

    @covers(NotLanguageFeature.INFRASTRUCTURE)
    def test_all_leaves_yields_elementary_fields(self):
        fields = [
            CobolField(
                name="WS-REC",
                level=1,
                pic="",
                usage="DISPLAY",
                offset=0,
                children=[
                    CobolField(
                        name="WS-X", level=5, pic="9(2)", usage="DISPLAY", offset=0
                    ),
                    CobolField(
                        name="WS-Y", level=5, pic="X(3)", usage="DISPLAY", offset=2
                    ),
                ],
            ),
        ]
        layout = build_data_layout(fields)
        leaves = list(layout.all_leaves())
        names = {fl.name for fl in leaves}
        assert names == {"WS-X", "WS-Y"}


class TestBuildDataLayoutRedefinesComplex:
    @covers(NotLanguageFeature.INFRASTRUCTURE)
    def test_multiple_redefines_of_same_field(self):
        """B REDEFINES A, C REDEFINES A — both at A's offset; total_bytes unchanged."""
        fields = [
            CobolField(name="WS-A", level=77, pic="X(4)", usage="DISPLAY", offset=0),
            CobolField(
                name="WS-B",
                level=77,
                pic="9(4)",
                usage="DISPLAY",
                offset=0,
                redefines="WS-A",
            ),
            CobolField(
                name="WS-C",
                level=77,
                pic="X(4)",
                usage="DISPLAY",
                offset=0,
                redefines="WS-A",
            ),
        ]
        layout = build_data_layout(fields)
        assert layout.total_bytes == 4
        a = layout.lookup("WS-A")
        b = layout.lookup("WS-B")
        c = layout.lookup("WS-C")
        assert a is not None and a.offset == 0
        assert b is not None and b.offset == 0
        assert c is not None and c.offset == 0

    @covers(NotLanguageFeature.INFRASTRUCTURE)
    def test_chained_redefines(self):
        """A, B REDEFINES A, C REDEFINES B — C ends up at A's offset."""
        fields = [
            CobolField(name="WS-A", level=77, pic="X(4)", usage="DISPLAY", offset=0),
            CobolField(
                name="WS-B",
                level=77,
                pic="9(4)",
                usage="DISPLAY",
                offset=0,
                redefines="WS-A",
            ),
            CobolField(
                name="WS-C",
                level=77,
                pic="X(4)",
                usage="DISPLAY",
                offset=0,
                redefines="WS-B",
            ),
        ]
        layout = build_data_layout(fields)
        assert layout.total_bytes == 4
        assert layout.lookup("WS-C").offset == 0  # type: ignore[union-attr]

    @covers(NotLanguageFeature.INFRASTRUCTURE)
    def test_group_redefines_elementary(self):
        """A group B REDEFINES an elementary A — group gets A's offset."""
        fields = [
            CobolField(name="WS-A", level=77, pic="X(4)", usage="DISPLAY", offset=0),
            CobolField(
                name="WS-B",
                level=1,
                pic="",
                usage="DISPLAY",
                offset=0,
                redefines="WS-A",
                children=[
                    CobolField(
                        name="WS-B1",
                        level=5,
                        pic="X(2)",
                        usage="DISPLAY",
                        offset=0,
                    ),
                    CobolField(
                        name="WS-B2",
                        level=5,
                        pic="X(2)",
                        usage="DISPLAY",
                        offset=2,
                    ),
                ],
            ),
        ]
        layout = build_data_layout(fields)
        assert layout.total_bytes == 4
        b_layout = layout.lookup_group("WS-B")
        assert b_layout.offset == 0
