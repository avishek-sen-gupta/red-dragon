"""The character each position of a numeric edit picture emits for one value."""

from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import dataclass
from itertools import accumulate

from cobol_asg.edit_picture_shape import EditPicture

_SIGN_SYMS = frozenset("+-")
_SUPPRESSION_SYMS = frozenset("Z*")
_INSERTION_SYMS = frozenset(",B0/")
_INSERTED_CHARS = {"B": " "}


@dataclass(frozen=True)
class EditRender:
    """One value laid over an edit picture's body, position by position."""

    picture: EditPicture
    body: tuple[str, ...]
    digits: Mapping[int, str]
    float_slot: int
    negative: bool

    def image(self) -> str:
        significant = self._significant_before()
        zoned = self._zoned_before()
        return "".join(
            self._cell(index, sym, significant[index], zoned[index])
            for index, sym in enumerate(self.body)
        )

    def _significant_before(self) -> tuple[bool, ...]:
        return tuple(
            accumulate(
                (self._opens_significance(i, sym) for i, sym in enumerate(self.body)),
                lambda seen, opens: seen or opens,
                initial=False,
            )
        )

    def _zoned_before(self) -> tuple[bool, ...]:
        return tuple(
            accumulate(
                (
                    sym in _SUPPRESSION_SYMS or i in self.picture.float_positions
                    for i, sym in enumerate(self.body)
                ),
                lambda seen, opens: seen or opens,
                initial=False,
            )
        )

    def _opens_significance(self, index: int, sym: str) -> bool:
        return sym in ".9" or self.digits.get(index, "0") != "0"

    def _cell(self, index: int, sym: str, significant: bool, zoned: bool) -> str:
        if index == self.float_slot:
            return self._float_symbol()
        if index in self.picture.float_positions:
            return self._float_position(index, significant)
        return _CELLS.get(sym, _verbatim)(self, index, sym, significant, zoned)

    def _float_symbol(self) -> str:
        symbol = self.picture.float_symbol
        return _sign_char(symbol, self.negative) if symbol in _SIGN_SYMS else symbol

    def _float_position(self, index: int, significant: bool) -> str:
        if index == self.picture.float_positions[0]:
            return self.picture.fill_char
        return self.suppressed_digit(index, significant)

    def suppressed_digit(self, index: int, significant: bool) -> str:
        digit = self.digits[index]
        return self.picture.fill_char if not significant and digit == "0" else digit


def _sign_char(symbol: str, negative: bool) -> str:
    if negative:
        return "-"
    return "+" if symbol == "+" else " "


def _sign(
    render: EditRender, index: int, sym: str, significant: bool, zoned: bool
) -> str:
    return _sign_char(sym, render.negative)


def _digit(
    render: EditRender, index: int, sym: str, significant: bool, zoned: bool
) -> str:
    return render.digits[index]


def _suppressed(
    render: EditRender, index: int, sym: str, significant: bool, zoned: bool
) -> str:
    return render.suppressed_digit(index, significant)


def _insertion(
    render: EditRender, index: int, sym: str, significant: bool, zoned: bool
) -> str:
    if zoned and not significant:
        return render.picture.fill_char
    return _INSERTED_CHARS.get(sym, sym)


def _verbatim(
    render: EditRender, index: int, sym: str, significant: bool, zoned: bool
) -> str:
    return sym


_CELLS: Mapping[str, Callable[[EditRender, int, str, bool, bool], str]] = {
    "+": _sign,
    "-": _sign,
    "9": _digit,
    **{sym: _suppressed for sym in _SUPPRESSION_SYMS},
    **{sym: _insertion for sym in _INSERTION_SYMS},
}
