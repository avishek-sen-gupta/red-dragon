"""Numeric editing as IR: the characters a numeric-edited item shows for a value, laid out by its PICTURE."""

from __future__ import annotations

from collections.abc import Callable, Iterable, Mapping
from dataclasses import dataclass
from functools import reduce
from itertools import accumulate, groupby

from cobol_asg.cobol_types import CobolTypeDescriptor
from cobol_asg.edit_cell import EditCell
from cobol_asg.edit_cell_kind import EditCellKind
from cobol_asg.edit_picture import edit_plan
from cobol_asg.edit_plan import EditPlan
from cobol_asg.edit_slot import EditSlot
from interpreter.cobol.cobol_constants import BuiltinName
from interpreter.cobol.ir_emitter import IrEmitter
from interpreter.register import Register

_NEGATIVE_SIGN = "-"
_NUMERALS = "0123456789"
_SIGN_SYMBOLS = frozenset("+-")
_NO_TRAILING_SIGN = "  "


@dataclass(frozen=True)
class _EditFacts:
    """The run-time facts every cell reads: the digit characters, whether each
    integer digit is nonzero, whether any integer digit before each one is, and
    whether the value is negative."""

    plan: EditPlan
    chars: tuple[Register, ...]
    seen: tuple[Register, ...]
    firsts: Mapping[int, Register]
    negative: Register


def emit_numeric_edit(
    e: IrEmitter, value: Register, td: CobolTypeDescriptor
) -> Register:
    plan = edit_plan(td.pic_string, td.currency, td.decimal_point_is_comma)
    number = e.call(BuiltinName.COBOL_PARSE_NUMBER, value)
    if not plan.all_suppressible:
        return _edited(e, (value, number), plan, td.scale)
    return e.choose(
        "edit_zero",
        e.text(plan.zero_image),
        e.binop("==", number, e.int_(0)),
        lambda: _edited(e, (value, number), plan, td.scale),
    )


def _edited(
    e: IrEmitter, operand: tuple[Register, Register], plan: EditPlan, scale: int
) -> Register:
    facts = _facts(e, operand, plan, scale)
    image = reduce(
        lambda text, piece: e.call(BuiltinName.STRING_CONCAT_PAIR, text, piece),
        (_piece(e, facts, run) for _, run in groupby(plan.cells, _is_fixed)),
    )
    if not plan.trailing_sign:
        return image
    return e.call(
        BuiltinName.STRING_CONCAT_PAIR,
        image,
        _signed_text(e, facts.negative, plan.trailing_sign, _NO_TRAILING_SIGN),
    )


def _is_fixed(cell: EditCell) -> bool:
    return cell.kind == EditCellKind.FIXED and cell.slot == EditSlot.NONE


def _piece(e: IrEmitter, facts: _EditFacts, run: Iterable[EditCell]) -> Register:
    cells = tuple(run)
    if _is_fixed(cells[0]):
        return e.text("".join(cell.char for cell in cells))
    return reduce(
        lambda text, cell: e.call(
            BuiltinName.STRING_CONCAT_PAIR, text, _cell(e, facts, cell)
        ),
        cells[1:],
        _cell(e, facts, cells[0]),
    )


def _facts(
    e: IrEmitter, operand: tuple[Register, Register], plan: EditPlan, scale: int
) -> _EditFacts:
    value, number = operand
    digits = e.call(
        BuiltinName.COBOL_PREPARE_DIGITS,
        value,
        e.int_(plan.digit_count),
        e.int_(plan.fraction_digits),
        e.bool_(False),
        e.int_(scale),
    )
    values = tuple(
        e.call(BuiltinName.LIST_GET, digits, e.int_(index))
        for index in range(plan.digit_count)
    )
    numerals, one, zero = e.text(_NUMERALS), e.int_(1), e.int_(0)
    nonzero = tuple(
        e.binop("!=", digit, zero) for digit in values[: plan.integer_digits]
    )
    seen = tuple(
        accumulate(
            nonzero,
            lambda before, digit: e.binop("or", before, digit),
            initial=e.bool_(False),
        )
    )
    return _EditFacts(
        plan=plan,
        chars=tuple(
            e.call(BuiltinName.STRING_SLICE, numerals, digit, one) for digit in values
        ),
        seen=seen,
        firsts={
            digit: e.binop(
                "and", nonzero[digit], e.binop("==", seen[digit], e.bool_(False))
            )
            for digit in plan.float_digits
        },
        negative=e.binop("<", number, zero),
    )


def _cell(e: IrEmitter, facts: _EditFacts, cell: EditCell) -> Register:
    if cell.slot == EditSlot.NONE:
        return _CELLS[cell.kind](e, facts, cell)
    return e.choose(
        "edit_float",
        _float_symbol(e, facts),
        _SLOTS[cell.slot](e, facts, cell),
        lambda: _CELLS[cell.kind](e, facts, cell),
    )


def _float_symbol(e: IrEmitter, facts: _EditFacts) -> Register:
    symbol = facts.plan.float_symbol
    if symbol not in _SIGN_SYMBOLS:
        return e.text(symbol)
    return _sign(e, facts, EditCell(kind=EditCellKind.SIGN, char=_shown(symbol)))


def _shown(symbol: str) -> str:
    return symbol if symbol == "+" else " "


def _signed_text(
    e: IrEmitter, negative: Register, when_negative: str, otherwise: str
) -> Register:
    return e.choose(
        "edit_sign", e.text(when_negative), negative, lambda: e.text(otherwise)
    )


def _before_digit(e: IrEmitter, facts: _EditFacts, cell: EditCell) -> Register:
    return facts.firsts[cell.slot_digit]


def _float_end(e: IrEmitter, facts: _EditFacts, cell: EditCell) -> Register:
    floating = reduce(
        lambda any_first, first: e.binop("or", any_first, first),
        facts.firsts.values(),
        e.bool_(False),
    )
    return e.binop("==", floating, e.bool_(False))


def _fixed(e: IrEmitter, facts: _EditFacts, cell: EditCell) -> Register:
    return e.text(cell.char)


def _sign(e: IrEmitter, facts: _EditFacts, cell: EditCell) -> Register:
    return _signed_text(e, facts.negative, _NEGATIVE_SIGN, cell.char)


def _digit(e: IrEmitter, facts: _EditFacts, cell: EditCell) -> Register:
    return facts.chars[cell.digits_before]


def _suppressed(e: IrEmitter, facts: _EditFacts, cell: EditCell) -> Register:
    return e.choose(
        "edit_digit",
        facts.chars[cell.digits_before],
        facts.seen[cell.digits_before + 1],
        lambda: e.text(facts.plan.fill),
    )


def _insertion(e: IrEmitter, facts: _EditFacts, cell: EditCell) -> Register:
    return e.choose(
        "edit_insertion",
        e.text(cell.char),
        facts.seen[cell.digits_before],
        lambda: e.text(facts.plan.fill),
    )


_CellEmitter = Callable[[IrEmitter, _EditFacts, EditCell], Register]

_CELLS: Mapping[EditCellKind, _CellEmitter] = {
    EditCellKind.FIXED: _fixed,
    EditCellKind.SIGN: _sign,
    EditCellKind.DIGIT: _digit,
    EditCellKind.SUPPRESSED: _suppressed,
    EditCellKind.INSERTION: _insertion,
}

_SLOTS: Mapping[EditSlot, _CellEmitter] = {
    EditSlot.BEFORE_DIGIT: _before_digit,
    EditSlot.FLOAT_END: _float_end,
}
