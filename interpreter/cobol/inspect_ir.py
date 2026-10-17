"""The INSPECT statement's scan as IR (ANSI X3.23-1985 INSPECT general rules).

The inspected item is examined left to right once. At each position the
phrases are tried in the order written; the first that matches there, inside
its own BEFORE / AFTER region, is applied and the scan resumes after the
matched characters. The loop finds each phrase's nearest match at or after the
cursor and applies the nearest, the first written winning a tie, which is the
same scan without stepping over the positions where nothing matches.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence
from functools import partial, reduce

from interpreter.cobol.cobol_constants import BuiltinName
from interpreter.cobol.inspect_loop import InspectLoop
from interpreter.cobol.inspect_mode import InspectMode
from interpreter.cobol.inspect_phrase_registers import InspectPhraseRegisters
from interpreter.cobol.inspect_phrase_scan import InspectPhraseScan
from interpreter.cobol.ir_emitter import IrEmitter
from interpreter.ir import CodeLabel
from interpreter.register import Register
from interpreter.var_name import NO_VAR_NAME, VarName

type MatchAction = Callable[[int, InspectPhraseScan, Register], None]


def emit_inspect_tally(
    e: IrEmitter,
    source: Register,
    phrases: Sequence[InspectPhraseRegisters],
    counters: int,
) -> Register:
    """A list of how many matches each TALLYING identifier gains."""
    counts = tuple(e.var("inspect_tally", e.int_(0)) for _ in range(counters))

    def tally(_index: int, scan: InspectPhraseScan, _position: Register) -> None:
        count = counts[scan.phrase.counter]
        e.store(count, e.binop("+", e.load(count), e.int_(1)))

    _emit_scan(e, source, _prepared(e, source, phrases), tally)
    return reduce(
        lambda listed, counter: e.call(
            BuiltinName.LIST_SET, listed, e.int_(counter), e.load(counts[counter])
        ),
        range(counters),
        e.call(BuiltinName.MAKE_LIST, e.int_(counters), e.int_(0)),
    )


def emit_inspect_replace(
    e: IrEmitter, source: Register, phrases: Sequence[InspectPhraseRegisters]
) -> Register:
    """``source`` with every matched run replaced by its phrase's BY value."""
    scans = _prepared(e, source, phrases)
    fitted = tuple(_fitted_replacement(e, scan) for scan in scans)
    text = e.var("inspect_text", source)

    def replace(index: int, scan: InspectPhraseScan, position: Register) -> None:
        e.store(
            text,
            e.call(
                BuiltinName.STRING_SPLICE,
                e.load(text),
                position,
                scan.length,
                fitted[index],
            ),
        )

    _emit_scan(e, source, scans, replace)
    return e.load(text)


def emit_inspect_convert(
    e: IrEmitter,
    source: Register,
    conversion: tuple[Register, Register],
    bounds: tuple[Register, Register],
) -> Register:
    """CONVERTING: each character of the FROM operand inside the region becomes
    the TO operand's character at the position of its first occurrence."""
    start, end = _region(e, source, bounds)
    text = e.var("inspect_text", source)
    at = e.var("inspect_at", start)
    e.loop("convert", partial(_convert_step, e, (source, text), (at, end), conversion))
    return e.load(text)


def _region(
    e: IrEmitter, source: Register, bounds: tuple[Register, Register]
) -> tuple[Register, Register]:
    after, before = bounds
    size = e.call(BuiltinName.LENGTH, source)
    start = _region_start(e, source, size, after)
    return start, _region_end(e, source, size, start, before)


def _convert_step(
    e: IrEmitter,
    texts: tuple[Register, VarName],
    bounds: tuple[VarName, Register],
    conversion: tuple[Register, Register],
    _head: CodeLabel,
    done: CodeLabel,
) -> None:
    at, end = bounds
    position = e.load(at)
    e.skip_if(e.binop(">=", position, end), done)
    _convert_one(e, texts, position, conversion)
    e.store(at, e.binop("+", position, e.int_(1)))


def _convert_one(
    e: IrEmitter,
    texts: tuple[Register, VarName],
    position: Register,
    conversion: tuple[Register, Register],
) -> None:
    source, text = texts
    from_chars, to_chars = conversion
    one = e.int_(1)
    found = e.call(
        BuiltinName.STRING_FIND,
        from_chars,
        e.call(BuiltinName.STRING_SLICE, source, position, one),
    )
    keep = e.label("convert_keep")
    e.skip_if(e.binop("<", found, e.int_(0)), keep)
    e.skip_if(e.binop(">=", found, e.call(BuiltinName.LENGTH, to_chars)), keep)
    replacement = e.call(BuiltinName.STRING_SLICE, to_chars, found, one)
    e.store(
        text,
        e.call(BuiltinName.STRING_SPLICE, e.load(text), position, one, replacement),
    )
    e.place(keep)


def _prepared(
    e: IrEmitter, source: Register, phrases: Sequence[InspectPhraseRegisters]
) -> tuple[InspectPhraseScan, ...]:
    size = e.call(BuiltinName.LENGTH, source)
    return tuple(_prepare(e, source, size, phrase) for phrase in phrases)


def _prepare(
    e: IrEmitter, source: Register, size: Register, phrase: InspectPhraseRegisters
) -> InspectPhraseScan:
    start = _region_start(e, source, size, phrase.after)
    return InspectPhraseScan(
        phrase=phrase,
        start=start,
        end=_region_end(e, source, size, start, phrase.before),
        length=(
            e.int_(1)
            if phrase.mode == InspectMode.CHARACTERS
            else e.call(BuiltinName.LENGTH, phrase.pattern)
        ),
        leading_at=(
            e.var("inspect_leading", start)
            if phrase.mode == InspectMode.LEADING
            else NO_VAR_NAME
        ),
        first_done=(
            e.var("inspect_first", e.bool_(False))
            if phrase.mode == InspectMode.FIRST
            else NO_VAR_NAME
        ),
    )


def _region_start(
    e: IrEmitter, source: Register, size: Register, after: Register
) -> Register:
    """Just past the first AFTER occurrence; the end when it does not occur."""
    if not after.is_present():
        return e.int_(0)
    found = e.call(BuiltinName.STRING_FIND, source, after)
    return e.choose(
        "inspect_start",
        size,
        e.binop("<", found, e.int_(0)),
        lambda: e.binop("+", found, e.call(BuiltinName.LENGTH, after)),
    )


def _region_end(
    e: IrEmitter, source: Register, size: Register, start: Register, before: Register
) -> Register:
    """The first BEFORE occurrence at or after the start; the end when none."""
    if not before.is_present():
        return size
    rest = e.call(BuiltinName.STRING_SLICE, source, start, e.binop("-", size, start))
    found = e.call(BuiltinName.STRING_FIND, rest, before)
    return e.choose(
        "inspect_end",
        size,
        e.binop("<", found, e.int_(0)),
        lambda: e.binop("+", start, found),
    )


def _fitted_replacement(e: IrEmitter, scan: InspectPhraseScan) -> Register:
    """The BY value sized to the matched characters: a one-character BY
    (a figurative constant) fills them all."""
    by = scan.phrase.replacement
    fitted = e.var(
        "inspect_by", e.call(BuiltinName.STRING_SLICE, by, e.int_(0), scan.length)
    )
    filled = e.label("inspect_filled")
    e.skip_if(e.binop("!=", e.call(BuiltinName.LENGTH, by), e.int_(1)), filled)
    e.store(fitted, by)
    e.loop("inspect_fill", partial(_fill_step, e, fitted, (by, scan.length)))
    e.place(filled)
    return e.load(fitted)


def _fill_step(
    e: IrEmitter,
    fitted: VarName,
    sizing: tuple[Register, Register],
    _head: CodeLabel,
    done: CodeLabel,
) -> None:
    by, length = sizing
    current = e.load(fitted)
    e.skip_if(e.binop(">=", e.call(BuiltinName.LENGTH, current), length), done)
    e.store(fitted, e.call(BuiltinName.STRING_CONCAT_PAIR, current, by))


def _emit_scan(
    e: IrEmitter,
    source: Register,
    scans: Sequence[InspectPhraseScan],
    act: MatchAction,
) -> None:
    shared = (
        source,
        e.call(BuiltinName.LENGTH, source),
        e.int_(1),
        e.var("inspect_cursor", e.int_(0)),
    )
    indexes = tuple(e.int_(index) for index in range(len(scans)))
    e.loop("inspect", partial(_scan_step, e, shared, (scans, indexes), act))


def _scan_step(
    e: IrEmitter,
    shared: tuple[Register, Register, Register, VarName],
    phrases: tuple[Sequence[InspectPhraseScan], Sequence[Register]],
    act: MatchAction,
    head: CodeLabel,
    done: CodeLabel,
) -> None:
    """One match: every phrase offers its nearest, and the nearest is applied."""
    source, size, one, cursor = shared
    scans, indexes = phrases
    loop = InspectLoop(
        source=source,
        size=size,
        one=one,
        cursor=cursor,
        best=e.var("inspect_best", size),
        winner=e.var("inspect_winner", e.int_(-1)),
        head=head,
    )
    at = e.load(cursor)
    for index, scan in enumerate(scans):
        _offer(e, loop, scan, at, indexes[index])
    position = e.load(loop.best)
    e.skip_if(e.binop(">=", position, size), done)
    _dispatch(e, loop, scans, (indexes, position), act)


def _offer(
    e: IrEmitter,
    loop: InspectLoop,
    scan: InspectPhraseScan,
    at: Register,
    index: Register,
) -> None:
    """Make the phrase's nearest match at or after ``at`` the best, when it is
    nearer than the best offered by the phrases before it."""
    skip = e.label("inspect_skip")
    candidate = _OFFERS[scan.phrase.mode](e, loop, scan, at, skip)
    e.skip_if(e.binop(">=", candidate, e.load(loop.best)), skip)
    e.store(loop.best, candidate)
    e.store(loop.winner, index)
    e.place(skip)


def _offer_found(
    e: IrEmitter,
    loop: InspectLoop,
    scan: InspectPhraseScan,
    at: Register,
    skip: CodeLabel,
) -> Register:
    if scan.first_done.is_present():
        e.skip_if(e.load(scan.first_done), skip)
    e.skip_if(e.binop("<", scan.length, loop.one), skip)
    origin = _origin(e, at, scan.start)
    window = e.call(
        BuiltinName.STRING_SLICE,
        loop.source,
        origin,
        e.binop("-", scan.end, origin),
    )
    found = e.call(BuiltinName.STRING_FIND, window, scan.phrase.pattern)
    e.skip_if(e.binop("<", found, e.int_(0)), skip)
    return e.binop("+", origin, found)


def _offer_leading(
    e: IrEmitter,
    loop: InspectLoop,
    scan: InspectPhraseScan,
    at: Register,
    skip: CodeLabel,
) -> Register:
    expected = e.load(scan.leading_at)
    e.skip_if(e.binop("<", scan.length, loop.one), skip)
    e.skip_if(e.binop("<", expected, at), skip)
    e.skip_if(e.binop(">", e.binop("+", expected, scan.length), scan.end), skip)
    piece = e.call(BuiltinName.STRING_SLICE, loop.source, expected, scan.length)
    e.skip_if(e.binop("!=", piece, scan.phrase.pattern), skip)
    return expected


def _offer_characters(
    e: IrEmitter,
    loop: InspectLoop,
    scan: InspectPhraseScan,
    at: Register,
    skip: CodeLabel,
) -> Register:
    origin = _origin(e, at, scan.start)
    e.skip_if(e.binop(">=", origin, scan.end), skip)
    return origin


type _Offer = Callable[
    [IrEmitter, InspectLoop, InspectPhraseScan, Register, CodeLabel], Register
]

_OFFERS: Mapping[InspectMode, _Offer] = {
    InspectMode.ALL: _offer_found,
    InspectMode.FIRST: _offer_found,
    InspectMode.LEADING: _offer_leading,
    InspectMode.CHARACTERS: _offer_characters,
}


def _origin(e: IrEmitter, at: Register, start: Register) -> Register:
    """The later of the cursor and the phrase's region start."""
    return e.choose("inspect_origin", at, e.binop(">=", at, start), lambda: start)


def _dispatch(
    e: IrEmitter,
    loop: InspectLoop,
    scans: Sequence[InspectPhraseScan],
    chosen: tuple[Sequence[Register], Register],
    act: MatchAction,
) -> None:
    """Apply the winning phrase's action and resume the scan after its match;
    the last phrase's arm falls through to the loop's return to its head."""
    indexes, position = chosen
    winner = e.load(loop.winner)
    for index, scan in enumerate(scans[:-1]):
        other = e.label("inspect_other")
        e.skip_if(e.binop("!=", winner, indexes[index]), other)
        _apply(e, loop, (index, scan), position, act)
        e.jump(loop.head)
        e.place(other)
    _apply(e, loop, (len(scans) - 1, scans[-1]), position, act)


def _apply(
    e: IrEmitter,
    loop: InspectLoop,
    indexed: tuple[int, InspectPhraseScan],
    position: Register,
    act: MatchAction,
) -> None:
    index, scan = indexed
    act(index, scan, position)
    after = e.binop("+", position, scan.length)
    e.store(loop.cursor, after)
    if scan.leading_at.is_present():
        e.store(scan.leading_at, after)
    if scan.first_done.is_present():
        e.store(scan.first_done, e.bool_(True))
