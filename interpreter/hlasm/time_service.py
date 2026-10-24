# pyright: standard
"""SVC 11 in IR: the TOD clock as the time of day in R0 (binary hundredths when the format bits of R1's low byte are 1, else packed HHMMSSth; the GMT and ERRET flag bits are ignored) and the packed 0CYYDDDF date in R1; no zone offset is applied."""

from functools import reduce

from interpreter.hlasm.hlasm_constants import (
    NIBBLE_BITS,
    SVC_PARAMETER_REGISTER,
    TOD_CLOCK_BUILTIN,
)
from interpreter.hlasm.hlasm_emitter import HlasmEmitter
from interpreter.operator_kind import BinopKind
from interpreter.register import Register

MICROSECOND_SHIFT = 52
MICROSECONDS_PER_DAY = 86_400_000_000
MICROSECONDS_PER_HUNDREDTH = 10_000
TIME_REGISTER = 0
FORMAT_MASK = 0x03
RETURN_CODE_REGISTER = 15
BINARY_FORMAT = 1
DAYS_BEFORE_1900 = 693_595
DAYS_PER_400_YEARS = 146_097
DAYS_PER_100_YEARS = 36_524
DAYS_PER_4_YEARS = 1_461
DAYS_PER_YEAR = 365
LONG_CYCLE_COUNT = 4
TIME_DIGITS = 8
DATE_DIGITS = 7
DATE_SIGN = 0xF
FIRST_CENTURY = 19


def _op(
    emitter: HlasmEmitter, operator: BinopKind, left: Register, right: int
) -> Register:
    return emitter.binop(operator, left, emitter.int_(right))


def _packed(emitter: HlasmEmitter, value: Register, digits: int) -> Register:
    nibbles = (
        _op(
            emitter,
            BinopKind.LSHIFT,
            _op(
                emitter,
                BinopKind.MOD,
                _op(emitter, BinopKind.FLOOR_DIV, value, 10**i),
                10,
            ),
            NIBBLE_BITS * i,
        )
        for i in range(digits)
    )
    return reduce(
        lambda left, right: emitter.binop(BinopKind.BIT_OR, left, right), nibbles
    )


def _sum(emitter: HlasmEmitter, terms: tuple[Register, ...]) -> Register:
    return reduce(lambda left, right: emitter.binop(BinopKind.ADD, left, right), terms)


def _scaled(emitter: HlasmEmitter, value: Register, scale: int) -> Register:
    return _op(emitter, BinopKind.MUL, value, scale)


def _decimal_time(emitter: HlasmEmitter, hundredths: Register) -> Register:
    hours = _op(emitter, BinopKind.FLOOR_DIV, hundredths, 360_000)
    minutes = _op(
        emitter, BinopKind.MOD, _op(emitter, BinopKind.FLOOR_DIV, hundredths, 6_000), 60
    )
    seconds = _op(
        emitter, BinopKind.MOD, _op(emitter, BinopKind.FLOOR_DIV, hundredths, 100), 60
    )
    fraction = _op(emitter, BinopKind.MOD, hundredths, 100)
    hhmmssth = _sum(
        emitter,
        (
            _scaled(emitter, hours, 1_000_000),
            _scaled(emitter, minutes, 10_000),
            _scaled(emitter, seconds, 100),
            fraction,
        ),
    )
    return _packed(emitter, hhmmssth, TIME_DIGITS)


def _rest(
    emitter: HlasmEmitter, days: Register, count: Register, cycle: int
) -> tuple[Register, Register]:
    return count, emitter.binop(BinopKind.SUB, days, _scaled(emitter, count, cycle))


def _cycles(
    emitter: HlasmEmitter, days: Register, cycle: int
) -> tuple[Register, Register]:
    return _rest(emitter, days, _op(emitter, BinopKind.FLOOR_DIV, days, cycle), cycle)


def _short_cycles(
    emitter: HlasmEmitter, days: Register, cycle: int
) -> tuple[Register, Register]:
    whole = _op(emitter, BinopKind.FLOOR_DIV, days, cycle)
    last_day = _op(emitter, BinopKind.FLOOR_DIV, days, LONG_CYCLE_COUNT * cycle)
    return _rest(emitter, days, emitter.binop(BinopKind.SUB, whole, last_day), cycle)


def _date(emitter: HlasmEmitter, days_since_1900: Register) -> Register:
    since_year_1 = _op(emitter, BinopKind.ADD, days_since_1900, DAYS_BEFORE_1900)
    four_hundreds, in_400 = _cycles(emitter, since_year_1, DAYS_PER_400_YEARS)
    hundreds, in_100 = _short_cycles(emitter, in_400, DAYS_PER_100_YEARS)
    fours, in_4 = _cycles(emitter, in_100, DAYS_PER_4_YEARS)
    ones, in_year = _short_cycles(emitter, in_4, DAYS_PER_YEAR)
    year = _sum(
        emitter,
        (
            _scaled(emitter, four_hundreds, 400),
            _scaled(emitter, hundreds, 100),
            _scaled(emitter, fours, 4),
            ones,
            emitter.int_(1),
        ),
    )
    century = _op(
        emitter,
        BinopKind.SUB,
        _op(emitter, BinopKind.FLOOR_DIV, year, 100),
        FIRST_CENTURY,
    )
    cyyddd = _sum(
        emitter,
        (
            _scaled(emitter, century, 100_000),
            _scaled(emitter, _op(emitter, BinopKind.MOD, year, 100), 1_000),
            in_year,
            emitter.int_(1),
        ),
    )
    packed = _op(
        emitter, BinopKind.LSHIFT, _packed(emitter, cyyddd, DATE_DIGITS), NIBBLE_BITS
    )
    return _op(emitter, BinopKind.BIT_OR, packed, DATE_SIGN)


def time_words(
    emitter: HlasmEmitter, tod: Register
) -> tuple[Register, Register, Register]:
    microseconds = _op(emitter, BinopKind.RSHIFT, tod, MICROSECOND_SHIFT)
    days = _op(emitter, BinopKind.FLOOR_DIV, microseconds, MICROSECONDS_PER_DAY)
    hundredths = _op(
        emitter,
        BinopKind.FLOOR_DIV,
        _op(emitter, BinopKind.MOD, microseconds, MICROSECONDS_PER_DAY),
        MICROSECONDS_PER_HUNDREDTH,
    )
    return _decimal_time(emitter, hundredths), hundredths, _date(emitter, days)


def emit_time(emitter: HlasmEmitter) -> None:
    decimal, binary, date = time_words(emitter, emitter.call(TOD_CLOCK_BUILTIN, ()))
    code = _op(
        emitter,
        BinopKind.BIT_AND,
        emitter.load_gr32(SVC_PARAMETER_REGISTER),
        FORMAT_MASK,
    )
    form = _op(emitter, BinopKind.EQ, code, BINARY_FORMAT)
    difference = emitter.binop(BinopKind.SUB, binary, decimal)
    chosen = emitter.binop(
        BinopKind.ADD, decimal, emitter.binop(BinopKind.MUL, difference, form)
    )
    emitter.store_gr32(TIME_REGISTER, chosen)
    emitter.store_gr32(SVC_PARAMETER_REGISTER, date)
    emitter.store_gr32(RETURN_CODE_REGISTER, emitter.int_(0))
