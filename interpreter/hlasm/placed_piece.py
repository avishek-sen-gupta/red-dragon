# pyright: standard
"""A piece of a DC operand at its offset in a section."""

from dataclasses import dataclass

from interpreter.hlasm.dc_encoding import DcPiece


@dataclass(frozen=True)
class PlacedPiece:
    section: str
    offset: int
    piece: DcPiece
