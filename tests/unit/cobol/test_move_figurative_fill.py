# pyright: standard
"""MOVE with COBOL figurative constants fills ALL receiver positions.

MOVE ZEROES TO PIC X(3) must produce '000' (0xF0F0F0), not '0  ' (0xF04040).
MOVE SPACES TO PIC X(4) must produce '    ' (0x40404040), not ' \x00\x00\x00'.

Before the fix, ``translate_cobol_figurative`` returned a single character and
the alphanumeric encoder left-justified it into the field — so only the first
byte was written and the rest remained as space-padding from the encoder.
"""

from __future__ import annotations

from interpreter.cobol.features import CobolFeature
from interpreter.run import run
from tests.covers import covers

_MOVE_ZEROES = """\
       IDENTIFICATION DIVISION.
       PROGRAM-ID. PROBEZERO.
       DATA DIVISION.
       WORKING-STORAGE SECTION.
       01  WS-RETCODE     PIC X(03) VALUE SPACES.
       01  WS-SINGLE      PIC X(01) VALUE SPACES.
       01  WS-NINE        PIC X(09) VALUE SPACES.
       PROCEDURE DIVISION.
           MOVE ZEROES TO WS-RETCODE.
           MOVE ZEROES TO WS-SINGLE.
           MOVE ZEROES TO WS-NINE.
           STOP RUN.
"""

_MOVE_SPACES = """\
       IDENTIFICATION DIVISION.
       PROGRAM-ID. PROBESPACE.
       DATA DIVISION.
       WORKING-STORAGE SECTION.
       01  WS-FIELD       PIC X(04) VALUE ZEROES.
       PROCEDURE DIVISION.
           MOVE SPACES TO WS-FIELD.
           STOP RUN.
"""


def _ws_bytes(vm, name: str) -> bytes:
    """Read raw bytes of a WS field by name from the VMState layout."""
    layout = vm.data_layout
    if name not in layout:
        return b""
    info = layout[name]
    off, length = info["offset"], info["length"]
    for key in vm.region_keys():
        rgn = bytes(vm.region_get(key))
        if len(rgn) >= off + length:
            return rgn[off : off + length]
    return b""


class TestMoveFigurativeConstantFillsAllPositions:
    """MOVE ZEROES / MOVE SPACES must fill every byte of the receiver field."""

    @covers(CobolFeature.PROLEAP_BRIDGE)
    def test_move_zeroes_fills_three_byte_x_field(self):
        """MOVE ZEROES TO PIC X(03) writes 0xF0 in all three bytes, not just one."""
        vm = run(_MOVE_ZEROES, language="cobol", max_steps=1_000)
        raw = _ws_bytes(vm, "WS-RETCODE")
        # EBCDIC '0' = 0xF0; all three bytes must be filled
        assert raw == bytes([0xF0, 0xF0, 0xF0]), (
            f"Expected 0xF0F0F0 ('000'), got {raw.hex()} — "
            "MOVE ZEROES only filled the first byte"
        )

    @covers(CobolFeature.PROLEAP_BRIDGE)
    def test_move_zeroes_fills_single_byte_x_field(self):
        """MOVE ZEROES TO PIC X(01) writes 0xF0."""
        vm = run(_MOVE_ZEROES, language="cobol", max_steps=1_000)
        raw = _ws_bytes(vm, "WS-SINGLE")
        assert raw == bytes([0xF0])

    @covers(CobolFeature.PROLEAP_BRIDGE)
    def test_move_zeroes_fills_nine_byte_x_field(self):
        """MOVE ZEROES TO PIC X(09) writes 0xF0 in all nine bytes."""
        vm = run(_MOVE_ZEROES, language="cobol", max_steps=1_000)
        raw = _ws_bytes(vm, "WS-NINE")
        assert raw == bytes([0xF0] * 9), f"Expected 9 x 0xF0, got {raw.hex()}"

    @covers(CobolFeature.PROLEAP_BRIDGE)
    def test_move_spaces_fills_four_byte_x_field(self):
        """MOVE SPACES TO PIC X(04) writes 0x40 (EBCDIC space) in all four bytes."""
        vm = run(_MOVE_SPACES, language="cobol", max_steps=1_000)
        raw = _ws_bytes(vm, "WS-FIELD")
        assert raw == bytes(
            [0x40] * 4
        ), f"Expected 4 x 0x40 (EBCDIC spaces), got {raw.hex()}"
