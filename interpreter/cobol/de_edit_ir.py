"""De-editing as IR: the numeric value a numeric-edited image represents.

De-editing (ANSI X3.23-1985 MOVE; IBM Enterprise COBOL LR, "Elementary
moves"): each digit position contributes its digit, a suppressed or
check-protected one contributes zero, insertion characters are dropped, and the
value is negative when a sign position shows '-' or CR / DB is present. The
PICTURE fixes where each of those is, so only the image is read at run time.
"""

from __future__ import annotations

from functools import reduce

from cobol_asg.de_edit_plan import DeEditPlan
from interpreter.cobol.cobol_constants import BuiltinName
from interpreter.cobol.ir_emitter import IrEmitter
from interpreter.register import Register
from interpreter.var_name import VarName

_DIGITS = "0123456789"


def emit_de_edit(e: IrEmitter, image: Register, plan: DeEditPlan) -> Register:
    digits = e.text(_DIGITS)
    magnitude = reduce(
        lambda total, term: e.binop("+", total, _term(e, (image, digits), term)),
        plan.digit_terms,
        e.int_(0),
    )
    negative = e.var("de_edit_negative", e.bool_(False))
    for mark in plan.negative_marks:
        _check_mark(e, image, mark, negative)
    signed = e.choose(
        "de_edit_signed",
        magnitude,
        e.binop("==", e.load(negative), e.bool_(False)),
        lambda: e.binop("-", e.int_(0), magnitude),
    )
    return e.call(BuiltinName.COBOL_FROM_DIGITS, signed, e.int_(plan.scale))


def _term(
    e: IrEmitter, texts: tuple[Register, Register], term: tuple[int, int]
) -> Register:
    """The digit at the position times its place value; a character that is
    not a digit (a space, '*', a currency or sign symbol) counts as zero."""
    image, digits = texts
    position, place = term
    found = e.call(
        BuiltinName.STRING_FIND,
        digits,
        e.call(BuiltinName.STRING_SLICE, image, e.int_(position), e.int_(1)),
    )
    digit = e.choose(
        "de_edit_digit", found, e.binop(">=", found, e.int_(0)), lambda: e.int_(0)
    )
    return e.binop("*", digit, e.int_(place))


def _check_mark(
    e: IrEmitter, image: Register, mark: tuple[int, str], negative: VarName
) -> None:
    position, sign = mark
    shown = e.call(BuiltinName.STRING_SLICE, image, e.int_(position), e.int_(1))
    unsigned = e.label("de_edit_unsigned")
    e.skip_if(e.binop("!=", shown, e.text(sign)), unsigned)
    e.store(negative, e.bool_(True))
    e.place(unsigned)
