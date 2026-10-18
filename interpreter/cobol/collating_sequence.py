"""A collating sequence: the ordinal position of every native (EBCDIC) byte."""

from __future__ import annotations

from dataclasses import dataclass
from types import MappingProxyType

from interpreter.cobol.ebcdic_table import EbcdicTable
from interpreter.cobol.figurative_constants import COBOL_FIGURATIVE_CONSTANTS
from interpreter.cobol.program_figuratives import ProgramFiguratives

_HIGH_VALUE_NAMES = ("HIGH-VALUE", "HIGH-VALUES")
_LOW_VALUE_NAMES = ("LOW-VALUE", "LOW-VALUES")


def _character(byte: int) -> str:
    return chr(EbcdicTable.EBCDIC_TO_ASCII[byte])


@dataclass(frozen=True)
class CollatingSequence:
    """``weights[b]`` is native byte b's position; equal weights compare equal.

    ``first_bytes[p]`` is the native byte the ALPHABET clause names first for
    position p. ``low_value`` and ``high_value`` are the native bytes LOW-VALUE
    and HIGH-VALUE stand for.
    """

    weights: tuple[int, ...]
    first_bytes: tuple[int, ...]
    low_value: int
    high_value: int

    def ordinal_alphabets(self) -> tuple[str, str]:
        """Each character, and the character whose code is its position: translating
        a string through them gives one that orders as this sequence does."""
        native = "".join(_character(b) for b in range(len(self.weights)))
        return native, "".join(chr(w) for w in self.weights)

    def characters_by_position(self) -> tuple[str, ...]:
        """The character at each position, from the first: where characters share
        a position, the one the ALPHABET clause names first."""
        return tuple(_character(b) for b in self.first_bytes)

    def figuratives(self) -> ProgramFiguratives:
        high, low = _character(self.high_value), _character(self.low_value)
        return ProgramFiguratives(
            characters=MappingProxyType(
                {
                    **COBOL_FIGURATIVE_CONSTANTS,
                    **{name: high for name in _HIGH_VALUE_NAMES},
                    **{name: low for name in _LOW_VALUE_NAMES},
                }
            ),
            raw_bytes=MappingProxyType(
                {
                    **{name: self.high_value for name in _HIGH_VALUE_NAMES},
                    **{name: self.low_value for name in _LOW_VALUE_NAMES},
                }
            ),
        )
