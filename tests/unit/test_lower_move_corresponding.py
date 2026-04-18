"""Unit tests for lower_move_corresponding lowering function."""

from __future__ import annotations

from unittest.mock import MagicMock

from interpreter.cobol.asg_types import CobolField
from interpreter.cobol.cobol_statements import MoveCorrespondingStatement
from interpreter.cobol.data_layout import DataLayout, build_data_layout
from interpreter.cobol.features import CobolFeature
from interpreter.cobol.lower_arithmetic import lower_move_corresponding
from tests.covers import covers


def _make_layout_with_groups() -> DataLayout:
    """WS-SRC(WS-A:X(5), WS-B:X(5)) and WS-DST(WS-A:X(5), WS-C:X(5))."""
    return build_data_layout(
        [
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
                offset=10,
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
    )


class TestLowerMoveCorresponding:
    @covers(CobolFeature.MOVE_CORRESPONDING)
    def test_matched_fields_emit_decode_encode_pair(self):
        layout = _make_layout_with_groups()
        ctx = MagicMock()
        ctx.emit_decode_field.return_value = "decoded_reg"
        ctx.emit_to_string.return_value = "str_reg"
        ctx.resolve_field_ref_from.side_effect = [
            MagicMock(offset_reg="src_off"),
            MagicMock(offset_reg="dst_off"),
        ]
        stmt = MoveCorrespondingStatement(source="WS-SRC", targets=["WS-DST"])

        lower_move_corresponding(ctx, stmt, layout, "region_r0")

        assert ctx.emit_decode_field.call_count == 1
        assert ctx.emit_to_string.call_count == 1
        assert ctx.emit_encode_and_write.call_count == 1

    @covers(CobolFeature.MOVE_CORRESPONDING)
    def test_unmatched_fields_are_not_copied(self):
        layout = _make_layout_with_groups()
        ctx = MagicMock()
        ctx.resolve_field_ref_from.return_value = MagicMock(offset_reg="off")
        ctx.emit_decode_field.return_value = "d"
        ctx.emit_to_string.return_value = "s"
        stmt = MoveCorrespondingStatement(source="WS-SRC", targets=["WS-DST"])

        lower_move_corresponding(ctx, stmt, layout, "region_r0")

        # Only WS-A matches; WS-B (src) and WS-C (dst) do not
        assert ctx.emit_decode_field.call_count == 1
        assert ctx.emit_encode_and_write.call_count == 1

    @covers(CobolFeature.MOVE_CORRESPONDING)
    def test_multiple_targets_each_receive_copy(self):
        layout = build_data_layout(
            [
                CobolField(
                    name="WS-SRC",
                    level=1,
                    pic="",
                    usage="DISPLAY",
                    offset=0,
                    children=[
                        CobolField(
                            name="WS-X",
                            level=5,
                            pic="9(3)",
                            usage="DISPLAY",
                            offset=0,
                        ),
                    ],
                ),
                CobolField(
                    name="WS-DST1",
                    level=1,
                    pic="",
                    usage="DISPLAY",
                    offset=3,
                    children=[
                        CobolField(
                            name="WS-X",
                            level=5,
                            pic="9(3)",
                            usage="DISPLAY",
                            offset=0,
                        ),
                    ],
                ),
                CobolField(
                    name="WS-DST2",
                    level=1,
                    pic="",
                    usage="DISPLAY",
                    offset=6,
                    children=[
                        CobolField(
                            name="WS-X",
                            level=5,
                            pic="9(3)",
                            usage="DISPLAY",
                            offset=0,
                        ),
                    ],
                ),
            ]
        )
        ctx = MagicMock()
        ctx.resolve_field_ref_from.return_value = MagicMock(offset_reg="off")
        ctx.emit_decode_field.return_value = "d"
        ctx.emit_to_string.return_value = "s"
        stmt = MoveCorrespondingStatement(
            source="WS-SRC", targets=["WS-DST1", "WS-DST2"]
        )

        lower_move_corresponding(ctx, stmt, layout, "region_r0")

        assert ctx.emit_encode_and_write.call_count == 2

    @covers(CobolFeature.MOVE_CORRESPONDING)
    def test_no_matching_names_emits_nothing(self):
        layout = build_data_layout(
            [
                CobolField(
                    name="WS-SRC",
                    level=1,
                    pic="",
                    usage="DISPLAY",
                    offset=0,
                    children=[
                        CobolField(
                            name="WS-P",
                            level=5,
                            pic="X(2)",
                            usage="DISPLAY",
                            offset=0,
                        ),
                    ],
                ),
                CobolField(
                    name="WS-DST",
                    level=1,
                    pic="",
                    usage="DISPLAY",
                    offset=2,
                    children=[
                        CobolField(
                            name="WS-Q",
                            level=5,
                            pic="X(2)",
                            usage="DISPLAY",
                            offset=0,
                        ),
                    ],
                ),
            ]
        )
        ctx = MagicMock()
        stmt = MoveCorrespondingStatement(source="WS-SRC", targets=["WS-DST"])

        lower_move_corresponding(ctx, stmt, layout, "region_r0")

        ctx.emit_decode_field.assert_not_called()
        ctx.emit_encode_and_write.assert_not_called()
