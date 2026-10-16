"""Tests for COBOL data layout builder."""

import pytest

from cobol_asg.asg_types import CobolField
from cobol_asg.cobol_types import CobolDataCategory
from cobol_asg.ref_mod import RefModOperand
from interpreter.cobol.data_layout import (
    CobolAmbiguousReferenceError,
    DataLayout,
    OccursTable,
    build_data_layout,
    build_index_layout,
    record_length,
)
from interpreter.cobol.features import CobolFeature
from tests.covers import NotLanguageFeature, covers


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
        assert _innermost_stride(layout, "PGM") == 11
        assert _innermost_stride(layout, "NUM") == 11
        assert _innermost_stride(layout, "USR") == 11

    @covers(NotLanguageFeature.INFRASTRUCTURE)
    def test_field_not_in_occurs_returns_zero(self):
        fields = [
            CobolField(name="WS-A", level=77, pic="X(5)", usage="DISPLAY", offset=0),
        ]
        layout = build_data_layout(fields)
        assert layout.qualified_matches("WS-A", ())[0].tables == ()

    @covers(NotLanguageFeature.INFRASTRUCTURE)
    def test_occurs_group_itself_returns_its_element_size(self):
        layout = self._menu_layout()
        assert _innermost_stride(layout, "ENTRY") == 11


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
    def test_a_group_tables_storage_carries_its_depending_on_object(self):
        table = CobolField(
            name="ENT",
            level=5,
            pic="",
            usage="DISPLAY",
            offset=2,
            occurs=6,
            element_size=2,
            occurs_depending_on="LEN",
            children=[_leaf("KY", 0, pic="99")],
        )
        layout = build_data_layout(
            [
                CobolField(name="LEN", level=1, pic="99", usage="DISPLAY", offset=0),
                CobolField(
                    name="TBL",
                    level=1,
                    pic="",
                    usage="DISPLAY",
                    offset=2,
                    children=[table],
                ),
            ]
        )
        storage = layout.lookup_as_storage("ENT")
        assert storage is not None
        assert (storage.occurs_count, storage.occurs_depending_on) == (6, "LEN")
        assert layout.lookup_as_storage("TBL").occurs_depending_on == ""

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


class TestAmbiguousBareNameLookup:
    @covers(NotLanguageFeature.INFRASTRUCTURE)
    def test_ambiguous_name_at_two_levels_raises(self):
        """A bare name declared at two different nesting levels is ambiguous."""
        fields = [
            CobolField(name="WS-ID", level=1, pic="9(3)", usage="DISPLAY", offset=0),
            CobolField(
                name="WS-SUB",
                level=1,
                pic="",
                usage="DISPLAY",
                offset=3,
                children=[
                    CobolField(
                        name="WS-ID", level=5, pic="9(3)", usage="DISPLAY", offset=3
                    ),
                ],
            ),
        ]
        layout = build_data_layout(fields)
        with pytest.raises(CobolAmbiguousReferenceError, match="WS-ID"):
            layout.lookup("WS-ID")

    @covers(NotLanguageFeature.INFRASTRUCTURE)
    def test_unambiguous_name_still_resolves(self):
        """A unique bare name resolves normally, even alongside an unrelated
        ambiguous name elsewhere in the same layout."""
        fields = [
            CobolField(name="WS-ID", level=1, pic="9(3)", usage="DISPLAY", offset=0),
            CobolField(
                name="WS-SUB",
                level=1,
                pic="",
                usage="DISPLAY",
                offset=3,
                children=[
                    CobolField(
                        name="WS-ID", level=5, pic="9(3)", usage="DISPLAY", offset=3
                    ),
                    CobolField(
                        name="WS-UNIQUE",
                        level=5,
                        pic="X(4)",
                        usage="DISPLAY",
                        offset=6,
                    ),
                ],
            ),
        ]
        layout = build_data_layout(fields)
        fl = layout.lookup("WS-UNIQUE")
        assert fl is not None
        assert fl.byte_length == 4
        assert fl.type_descriptor.category == CobolDataCategory.ALPHANUMERIC


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
                renames_from=RefModOperand(name="WS-FIRST"),
            ),
        ]
        layout = build_data_layout(fields)
        fl = layout.lookup_as_storage("WS-ALIAS", ("WS-REC",))
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
                renames_from=RefModOperand(name="WS-A"),
                renames_thru=RefModOperand(name="WS-C"),
            ),
        ]
        layout = build_data_layout(fields)
        fl = layout.lookup_as_storage("WS-SPAN")
        assert fl is not None
        assert fl.offset == 0  # WS-A offset
        assert fl.byte_length == 15  # 0 + 5 + 3 + 7 = 15 (through end of WS-C)
        assert fl.renames_from == "WS-A"
        assert fl.renames_thru == "WS-C"
        # RENAMES does not increase total_bytes
        assert layout.total_bytes == 15

    @covers(NotLanguageFeature.INFRASTRUCTURE)
    def test_renames_belongs_to_and_resolves_within_its_preceding_record(self):
        def renames(name: str, start: str, *qualifiers: str) -> CobolField:
            return CobolField(
                name=name,
                level=66,
                pic="",
                usage="DISPLAY",
                offset=0,
                renames_from=RefModOperand(name=start, qualifiers=qualifiers),
            )

        layout = build_data_layout(
            [
                _group(
                    "R1", 0, _leaf("A", 0, "XX"), _group("G", 2, _leaf("B", 0, "X(3)"))
                ),
                renames("ALIAS", "G"),
                _group("R2", 5, _leaf("A", 0, "X(4)"), _group("G", 4, _leaf("B", 0))),
                renames("ALIAS", "A", "R2"),
            ]
        )

        def extent(*qualifiers: str) -> tuple[int, int]:
            (match,) = layout.qualified_matches("ALIAS", qualifiers)
            return match.storage.offset, match.storage.byte_length

        assert (extent("R1"), extent("R2")) == ((2, 3), (5, 4))
        with pytest.raises(CobolAmbiguousReferenceError, match="'ALIAS'"):
            layout.qualified_matches("ALIAS", ())


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


def _indexed_table(
    table_name: str = "TBL-ROW",
    index_names: list[str] | None = None,
    occurs: int = 3,
) -> CobolField:
    return CobolField.from_dict(
        {
            "name": "TBL",
            "level": 1,
            "pic": "",
            "usage": "DISPLAY",
            "offset": 0,
            "children": [
                {
                    "name": table_name,
                    "level": 5,
                    "pic": "",
                    "usage": "DISPLAY",
                    "offset": 0,
                    "occurs": occurs,
                    "element_size": 3,
                    "indexed_by": index_names if index_names else ["TBL-IX"],
                    "children": [
                        {
                            "name": "TBL-KEY",
                            "level": 10,
                            "pic": "X(3)",
                            "usage": "DISPLAY",
                            "offset": 0,
                        }
                    ],
                }
            ],
        }
    )


class TestIndexItemLayout:
    @covers(CobolFeature.USAGE_INDEX)
    def test_indexed_by_allocates_a_four_byte_item_recording_its_table(self):
        """An INDEXED BY name becomes a real 4-byte item holding an occurrence NUMBER.

        Not the byte displacement IBM stores: nothing reads an index's raw bytes,
        and a program cannot legally observe the difference (REDEFINES of an index
        and a group MOVE of one are both errors).
        """
        layout = build_index_layout([_indexed_table()])
        index_layout = layout.lookup("TBL-IX")
        assert index_layout is not None
        assert index_layout.offset == 0
        assert index_layout.byte_length == 4
        assert layout.total_bytes == 4

    @covers(CobolFeature.USAGE_INDEX)
    def test_index_items_stay_out_of_the_record_they_index(self):
        """The record's own layout is byte-for-byte unchanged by INDEXED BY."""
        table = _indexed_table()
        record = build_data_layout([table])
        assert record.total_bytes == 9
        assert record.lookup("TBL-IX") is None
        assert record.index_owner == {}

    @covers(CobolFeature.USAGE_INDEX)
    def test_indexes_are_packed_across_sections_in_declaration_order(self):
        working_storage = [_indexed_table(index_names=["IX-A", "IX-B"])]
        linkage = [_indexed_table(table_name="LK-ROW", index_names=["IX-C"])]
        layout = build_index_layout(working_storage, linkage)
        assert [fl.offset for fl in layout.all_leaves()] == [0, 4, 8]
        assert layout.total_bytes == 12

    @covers(CobolFeature.USAGE_INDEX)
    def test_declared_casing_is_preserved_and_matched_ignoring_case(self):
        layout = build_index_layout(
            [_indexed_table(table_name="Tbl-Row", index_names=["Tbl-Ix"])]
        )
        assert "Tbl-Ix" in layout.fields
        assert layout.lookup("TBL-IX") is not None

    @covers(CobolFeature.SEARCH_LINEAR)
    def test_first_index_for_finds_a_format_1_searchs_implicit_index(self):
        layout = build_index_layout(
            [_indexed_table(table_name="Tbl-Row", index_names=["Tbl-Ix", "Tbl-Jx"])]
        )
        assert layout.first_index_for("TBL-ROW") == "Tbl-Ix"
        assert layout.first_index_for("NO-SUCH-TABLE") is None

    @covers(CobolFeature.SEARCH_VARYING)
    def test_is_index_of_names_only_the_tables_own_indexes(self):
        layout = build_index_layout(
            [
                _indexed_table(table_name="Tbl-Row", index_names=["Tbl-Ix", "Tbl-Jx"]),
                _indexed_table(table_name="Oth-Row", index_names=["Oth-Ix"]),
            ]
        )
        assert [
            layout.is_index_of("TBL-JX", "tbl-row"),
            layout.is_index_of("Tbl-Ix", "TBL-ROW"),
            layout.is_index_of("OTH-IX", "TBL-ROW"),
            layout.is_index_of("NO-SUCH-IX", "TBL-ROW"),
        ] == [True, True, False, False]


def _group(
    name: str, offset: int, *children: CobolField, occurs: int = 0
) -> CobolField:
    size = sum(record_length(child) for child in children)
    return CobolField(
        name=name,
        level=2,
        pic="",
        usage="DISPLAY",
        offset=offset,
        children=list(children),
        occurs=occurs,
        element_size=size if occurs else 0,
    )


def _leaf(name: str, offset: int, pic: str = "X") -> CobolField:
    return CobolField(name=name, level=3, pic=pic, usage="DISPLAY", offset=offset)


def _innermost_stride(layout: DataLayout, name: str) -> int:
    (match,) = layout.qualified_matches(name, ())
    return match.tables[-1].element_size


class TestQualifiedResolution:
    """ISO 1989 qualification: each qualifier names a group containing the item
    named before it, intermediate levels may be skipped, and a reference is in
    error only when the qualifiers given still leave more than one candidate."""

    @covers(NotLanguageFeature.INFRASTRUCTURE)
    def test_every_qualifier_narrows_and_only_true_ambiguity_raises(self):
        layout = build_data_layout(
            [
                _group(
                    "REC",
                    0,
                    _group(
                        "L2A",
                        0,
                        _group("L1A", 0, _leaf("T", 0)),
                        _group("L1B", 1, _leaf("T", 0)),
                    ),
                    _group(
                        "L2B",
                        2,
                        _group("L1A", 0, _leaf("T", 0)),
                        _group("L1B", 1, _leaf("T", 0)),
                    ),
                    _group("G10", 4, _group("D3", 0, _leaf("X1", 0), _leaf("X2", 1))),
                    _group("G20", 6, _leaf("D3", 0, "99")),
                )
            ]
        )

        def offset(name: str, *qualifiers: str) -> int:
            (match,) = layout.qualified_matches(name, qualifiers)
            return match.storage.offset

        assert offset("T", "L1A", "L2B") == 2
        assert offset("T", "L1B", "L2A") == 1
        assert offset("t", "l1a", "l2a") == 0
        assert offset("T", "L1B", "L2B") == 3
        assert offset("T", "L1A", "L2B", "REC") == 2
        assert layout.qualified_matches("T", ("L2B", "L1A")) == ()
        assert offset("D3", "G10") == 4
        assert layout.qualified_matches("D3", ("G10",))[0].storage.byte_length == 2
        assert offset("D3", "G20") == 6
        assert layout.qualified_matches("T", ("NOWHERE",)) == ()
        with pytest.raises(CobolAmbiguousReferenceError, match="'T'"):
            layout.qualified_matches("T", ("L1A",))
        with pytest.raises(CobolAmbiguousReferenceError, match="'D3'"):
            layout.qualified_matches("D3", ("REC",))

    @covers(NotLanguageFeature.INFRASTRUCTURE)
    def test_a_qualified_match_carries_its_own_occurs_tables(self):
        layout = build_data_layout(
            [
                _group("G1", 0, _group("L2", 0, _leaf("ITM", 0, "X(2)"), occurs=2)),
                _group(
                    "G2",
                    4,
                    _group(
                        "L2", 0, _group("L3", 0, _leaf("ITM", 0), occurs=3), occurs=2
                    ),
                ),
            ]
        )
        (first,) = layout.qualified_matches("ITM", ("G1",))
        (second,) = layout.qualified_matches("ITM", ("L3", "L2", "G2"))
        assert first.tables == (OccursTable(0, 2, 2),)
        assert second.tables == (OccursTable(4, 3, 2), OccursTable(4, 1, 3))
        assert (first.record_extent, second.record_extent) == ((0, 4), (4, 6))
