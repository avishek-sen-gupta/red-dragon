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
from dataclasses import dataclass
from functools import partial, reduce

from interpreter.cobol.cobol_constants import BuiltinName
from interpreter.cobol.inspect_converting import InspectConverting
from interpreter.cobol.inspect_loop import InspectLoop
from interpreter.cobol.inspect_matching import InspectMatching, MatchAction
from interpreter.cobol.inspect_mode import InspectMode
from interpreter.cobol.inspect_phrase_registers import InspectPhraseRegisters
from interpreter.cobol.inspect_phrase_scan import InspectPhraseScan
from interpreter.cobol.ir_emitter import IrEmitter
from interpreter.ir import CodeLabel
from interpreter.register import Register
from interpreter.var_name import NO_VAR_NAME, VarName


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

    scanner = _scanner(e, source)
    scanner.scan(scanner.prepared(phrases), tally)
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
    scanner = _scanner(e, source)
    scans = scanner.prepared(phrases)
    fitted = tuple(scanner.fitted_replacement(scan) for scan in scans)
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

    scanner.scan(scans, replace)
    return e.load(text)


def emit_inspect_convert(
    e: IrEmitter,
    source: Register,
    conversion: tuple[Register, Register],
    bounds: tuple[Register, Register],
) -> Register:
    """CONVERTING: each character of the FROM operand inside the region becomes
    the TO operand's character at the position of its first occurrence."""
    return _scanner(e, source).convert(conversion, bounds)


def _scanner(e: IrEmitter, source: Register) -> InspectScanEmitter:
    return InspectScanEmitter(
        e=e, source=source, size=e.call(BuiltinName.LENGTH, source), one=e.int_(1)
    )


@dataclass(frozen=True)
class InspectScanEmitter:
    """Emits the IR of one INSPECT over the inspected characters: the phrase
    regions, the CONVERTING loop, and the scan in which the phrases compete."""

    e: IrEmitter
    source: Register
    size: Register
    one: Register

    def convert(
        self, conversion: tuple[Register, Register], bounds: tuple[Register, Register]
    ) -> Register:
        e = self.e
        after, before = bounds
        start = self._region_start(after)
        from_chars, to_chars = conversion
        converting = InspectConverting(
            from_chars=from_chars,
            to_chars=to_chars,
            end=self._region_end(start, before),
            text=e.var("inspect_text", self.source),
            at=e.var("inspect_at", start),
        )
        e.loop("convert", partial(self._convert_step, converting))
        return e.load(converting.text)

    def _convert_step(
        self, converting: InspectConverting, _head: CodeLabel, done: CodeLabel
    ) -> None:
        e = self.e
        position = e.load(converting.at)
        e.skip_if(e.binop(">=", position, converting.end), done)
        self._convert_one(converting, position)
        e.store(converting.at, e.binop("+", position, self.one))

    def _convert_one(self, converting: InspectConverting, position: Register) -> None:
        e = self.e
        found = e.call(
            BuiltinName.STRING_FIND,
            converting.from_chars,
            e.call(BuiltinName.STRING_SLICE, self.source, position, self.one),
        )
        keep = e.label("convert_keep")
        e.skip_if(e.binop("<", found, e.int_(0)), keep)
        e.skip_if(
            e.binop(">=", found, e.call(BuiltinName.LENGTH, converting.to_chars)), keep
        )
        replacement = e.call(
            BuiltinName.STRING_SLICE, converting.to_chars, found, self.one
        )
        e.store(
            converting.text,
            e.call(
                BuiltinName.STRING_SPLICE,
                e.load(converting.text),
                position,
                self.one,
                replacement,
            ),
        )
        e.place(keep)

    def prepared(
        self, phrases: Sequence[InspectPhraseRegisters]
    ) -> tuple[InspectPhraseScan, ...]:
        return tuple(self._prepare(phrase) for phrase in phrases)

    def _prepare(self, phrase: InspectPhraseRegisters) -> InspectPhraseScan:
        e = self.e
        start = self._region_start(phrase.after)
        return InspectPhraseScan(
            phrase=phrase,
            start=start,
            end=self._region_end(start, phrase.before),
            length=(
                self.one
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

    def _region_start(self, after: Register) -> Register:
        """Just past the first AFTER occurrence; the end when it does not occur."""
        e = self.e
        if not after.is_present():
            return e.int_(0)
        found = e.call(BuiltinName.STRING_FIND, self.source, after)
        return e.choose(
            "inspect_start",
            self.size,
            e.binop("<", found, e.int_(0)),
            lambda: e.binop("+", found, e.call(BuiltinName.LENGTH, after)),
        )

    def _region_end(self, start: Register, before: Register) -> Register:
        """The first BEFORE occurrence at or after the start; the end when none."""
        e = self.e
        if not before.is_present():
            return self.size
        rest = e.call(
            BuiltinName.STRING_SLICE, self.source, start, e.binop("-", self.size, start)
        )
        found = e.call(BuiltinName.STRING_FIND, rest, before)
        return e.choose(
            "inspect_end",
            self.size,
            e.binop("<", found, e.int_(0)),
            lambda: e.binop("+", start, found),
        )

    def fitted_replacement(self, scan: InspectPhraseScan) -> Register:
        """The BY value sized to the matched characters: a one-character BY
        (a figurative constant) fills them all."""
        e = self.e
        by = scan.phrase.replacement
        fitted = e.var(
            "inspect_by", e.call(BuiltinName.STRING_SLICE, by, e.int_(0), scan.length)
        )
        filled = e.label("inspect_filled")
        e.skip_if(e.binop("!=", e.call(BuiltinName.LENGTH, by), self.one), filled)
        e.store(fitted, by)
        e.loop("inspect_fill", partial(self._fill_step, fitted, scan))
        e.place(filled)
        return e.load(fitted)

    def _fill_step(
        self,
        fitted: VarName,
        scan: InspectPhraseScan,
        _head: CodeLabel,
        done: CodeLabel,
    ) -> None:
        e = self.e
        current = e.load(fitted)
        e.skip_if(e.binop(">=", e.call(BuiltinName.LENGTH, current), scan.length), done)
        e.store(
            fitted,
            e.call(BuiltinName.STRING_CONCAT_PAIR, current, scan.phrase.replacement),
        )

    def scan(self, scans: Sequence[InspectPhraseScan], act: MatchAction) -> None:
        e = self.e
        matching = InspectMatching(
            scans=tuple(scans),
            indexes=tuple(e.int_(index) for index in range(len(scans))),
            act=act,
            cursor=e.var("inspect_cursor", e.int_(0)),
        )
        e.loop("inspect", partial(self._scan_step, matching))

    def _scan_step(
        self, matching: InspectMatching, head: CodeLabel, done: CodeLabel
    ) -> None:
        """One match: every phrase offers its nearest, and the nearest is applied."""
        e = self.e
        loop = InspectLoop(
            matching=matching,
            best=e.var("inspect_best", self.size),
            winner=e.var("inspect_winner", e.int_(-1)),
            head=head,
        )
        at = e.load(matching.cursor)
        for index, scan in enumerate(matching.scans):
            self._offer(loop, scan, at, matching.indexes[index])
        position = e.load(loop.best)
        e.skip_if(e.binop(">=", position, self.size), done)
        self._dispatch(loop, position)

    def _offer(
        self,
        loop: InspectLoop,
        scan: InspectPhraseScan,
        at: Register,
        index: Register,
    ) -> None:
        """Make the phrase's nearest match at or after ``at`` the best, when it is
        nearer than the best offered by the phrases before it."""
        e = self.e
        skip = e.label("inspect_skip")
        candidate = _OFFERS[scan.phrase.mode](self, scan, at, skip)
        e.skip_if(e.binop(">=", candidate, e.load(loop.best)), skip)
        e.store(loop.best, candidate)
        e.store(loop.winner, index)
        e.place(skip)

    def offer_found(
        self, scan: InspectPhraseScan, at: Register, skip: CodeLabel
    ) -> Register:
        e = self.e
        if scan.first_done.is_present():
            e.skip_if(e.load(scan.first_done), skip)
        e.skip_if(e.binop("<", scan.length, self.one), skip)
        origin = self._origin(at, scan.start)
        window = e.call(
            BuiltinName.STRING_SLICE,
            self.source,
            origin,
            e.binop("-", scan.end, origin),
        )
        found = e.call(BuiltinName.STRING_FIND, window, scan.phrase.pattern)
        e.skip_if(e.binop("<", found, e.int_(0)), skip)
        return e.binop("+", origin, found)

    def offer_leading(
        self, scan: InspectPhraseScan, at: Register, skip: CodeLabel
    ) -> Register:
        e = self.e
        expected = e.load(scan.leading_at)
        e.skip_if(e.binop("<", scan.length, self.one), skip)
        e.skip_if(e.binop("<", expected, at), skip)
        e.skip_if(e.binop(">", e.binop("+", expected, scan.length), scan.end), skip)
        piece = e.call(BuiltinName.STRING_SLICE, self.source, expected, scan.length)
        e.skip_if(e.binop("!=", piece, scan.phrase.pattern), skip)
        return expected

    def offer_characters(
        self, scan: InspectPhraseScan, at: Register, skip: CodeLabel
    ) -> Register:
        e = self.e
        origin = self._origin(at, scan.start)
        e.skip_if(e.binop(">=", origin, scan.end), skip)
        return origin

    def _origin(self, at: Register, start: Register) -> Register:
        """The later of the cursor and the phrase's region start."""
        e = self.e
        return e.choose("inspect_origin", at, e.binop(">=", at, start), lambda: start)

    def _dispatch(self, loop: InspectLoop, position: Register) -> None:
        """Apply the winning phrase's action and resume the scan after its match;
        the last phrase's arm falls through to the loop's return to its head."""
        e = self.e
        winner = e.load(loop.winner)
        last = len(loop.matching.scans) - 1
        for index in range(last):
            other = e.label("inspect_other")
            e.skip_if(e.binop("!=", winner, loop.matching.indexes[index]), other)
            self._apply(loop, index, position)
            e.jump(loop.head)
            e.place(other)
        self._apply(loop, last, position)

    def _apply(self, loop: InspectLoop, index: int, position: Register) -> None:
        e = self.e
        scan = loop.matching.scans[index]
        loop.matching.act(index, scan, position)
        after = e.binop("+", position, scan.length)
        e.store(loop.matching.cursor, after)
        if scan.leading_at.is_present():
            e.store(scan.leading_at, after)
        if scan.first_done.is_present():
            e.store(scan.first_done, e.bool_(True))


type _Offer = Callable[
    [InspectScanEmitter, InspectPhraseScan, Register, CodeLabel], Register
]

_OFFERS: Mapping[InspectMode, _Offer] = {
    InspectMode.ALL: InspectScanEmitter.offer_found,
    InspectMode.FIRST: InspectScanEmitter.offer_found,
    InspectMode.LEADING: InspectScanEmitter.offer_leading,
    InspectMode.CHARACTERS: InspectScanEmitter.offer_characters,
}
