"""UNSTRING's examination of the source as IR (ANSI X3.23-1985 UNSTRING general rules).

Examination starts at the pointer. For each receiver in turn, the characters up
to the nearest delimiter occurrence go to it; where several delimiters match at
one position the first written wins, and an ALL delimiter takes the whole run
of its contiguous occurrences. Without delimiters each receiver takes as many
characters as its size. Examination stops when the source is exhausted or every
receiver has been acted on. The overflow condition arises when the pointer is
below 1 or past the source before examination, or when characters remain
unexamined after the last receiver. The receivers and delimiters are known at
lowering time, so each receiver's examination is emitted in turn.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from functools import partial

from interpreter.cobol.cobol_constants import BuiltinName
from interpreter.cobol.ir_emitter import IrEmitter
from interpreter.cobol.unstring_ir_outcome import UnstringIrOutcome
from interpreter.cobol.unstring_ir_piece import UnstringIrPiece
from interpreter.cobol.unstring_ir_state import UnstringIrState
from interpreter.ir import CodeLabel
from interpreter.register import Register
from interpreter.var_name import VarName

type Delimiter = tuple[Register, bool]
type _PieceVars = tuple[VarName, VarName, VarName]
type _Receivers = tuple[Sequence[Delimiter], Sequence[int], Sequence[_PieceVars]]


def emit_unstring(
    e: IrEmitter,
    source: Register,
    pointer: Register,
    receiving: tuple[Sequence[Delimiter], Sequence[int]],
) -> UnstringIrOutcome:
    """Examine ``source`` from ``pointer`` for receivers of the given sizes,
    split at the delimiters (each with its ALL flag) when there are any."""
    delimiters, sizes = receiving
    size = e.call(BuiltinName.LENGTH, source)
    scanner = UnstringScanEmitter(
        e=e,
        state=UnstringIrState(
            source=source,
            size=size,
            position=e.var("unstring_position", e.binop("-", pointer, e.int_(1))),
            acted=e.var("unstring_acted", e.int_(0)),
        ),
    )
    ends = (
        e.var("unstring_pointer", pointer),
        e.var("unstring_overflow", e.bool_(True)),
    )
    pieces = tuple(_piece_vars(e) for _ in sizes)
    scanner.examine_from((pointer, ends), (delimiters, sizes, pieces))
    return scanner.outcome(ends, pieces)


def _piece_vars(e: IrEmitter) -> _PieceVars:
    return (
        e.var("unstring_text", e.text("")),
        e.var("unstring_delimiter", e.text("")),
        e.var("unstring_count", e.int_(0)),
    )


@dataclass(frozen=True)
class UnstringScanEmitter:
    """Emits the IR of one UNSTRING's examination of its source, receiver by
    receiver, over the examination state."""

    e: IrEmitter
    state: UnstringIrState

    def examine_from(
        self, start: tuple[Register, tuple[VarName, VarName]], receivers: _Receivers
    ) -> None:
        """Examine unless the pointer is below 1 or past the source."""
        e = self.e
        pointer, ends = start
        done = e.label("unstring_done")
        e.skip_if(e.binop("<", pointer, e.int_(1)), done)
        e.skip_if(e.binop(">", pointer, self.state.size), done)
        self._examine(ends, receivers)
        e.place(done)

    def _examine(self, ends: tuple[VarName, VarName], receivers: _Receivers) -> None:
        delimiters, sizes, pieces = receivers
        examined = self.e.label("unstring_examined")
        for index, (receiver_size, piece) in enumerate(zip(sizes, pieces, strict=True)):
            self.e.skip_if(
                self.e.binop(">=", self.e.load(self.state.position), self.state.size),
                examined,
            )
            self._receive((delimiters, receiver_size), piece)
            self.e.store(self.state.acted, self.e.int_(index + 1))
        self.e.place(examined)
        pointer, overflow = ends
        position = self.e.load(self.state.position)
        self.e.store(pointer, self.e.binop("+", position, self.e.int_(1)))
        self.e.store(overflow, self.e.binop("<", position, self.state.size))

    def _receive(
        self, split: tuple[Sequence[Delimiter], int], piece: _PieceVars
    ) -> None:
        delimiters, receiver_size = split
        if delimiters:
            self._receive_delimited(delimiters, piece)
            return
        text, _delimiter, count = piece
        at = self.e.load(self.state.position)
        taken = self.e.call(
            BuiltinName.STRING_SLICE, self.state.source, at, self.e.int_(receiver_size)
        )
        taken_count = self.e.call(BuiltinName.LENGTH, taken)
        self.e.store(text, taken)
        self.e.store(count, taken_count)
        self.e.store(self.state.position, self.e.binop("+", at, taken_count))

    def _receive_delimited(
        self, delimiters: Sequence[Delimiter], piece: _PieceVars
    ) -> None:
        """The characters before the nearest delimiter, which then ends them."""
        e, state = self.e, self.state
        at = e.load(state.position)
        nearest = (
            e.var("unstring_nearest", state.size),
            e.var("unstring_winner", e.int_(-1)),
        )
        rest = e.call(
            BuiltinName.STRING_SLICE, state.source, at, e.binop("-", state.size, at)
        )
        for index, delimiter in enumerate(delimiters):
            self._offer((rest, at), delimiter[0], nearest, index)
        start = e.load(nearest[0])
        self._take((at, start), piece)
        self._end_delimiter(delimiters, (start, e.load(nearest[1])), piece)

    def _take(self, bounds: tuple[Register, Register], piece: _PieceVars) -> None:
        e = self.e
        at, start = bounds
        text, _delimiter, count = piece
        taken = e.call(
            BuiltinName.STRING_SLICE, self.state.source, at, e.binop("-", start, at)
        )
        e.store(text, taken)
        e.store(count, e.call(BuiltinName.LENGTH, taken))

    def _offer(
        self,
        rest: tuple[Register, Register],
        delimiter: Register,
        nearest: tuple[VarName, VarName],
        index: int,
    ) -> None:
        """Make this delimiter's first occurrence the nearest when it is nearer
        than every delimiter written before it."""
        e = self.e
        remaining, at = rest
        skip = e.label("unstring_skip")
        e.skip_if(e.binop("<", e.call(BuiltinName.LENGTH, delimiter), e.int_(1)), skip)
        found = e.call(BuiltinName.STRING_FIND, remaining, delimiter)
        e.skip_if(e.binop("<", found, e.int_(0)), skip)
        self._improve(e.binop("+", at, found), nearest, (index, skip))

    def _improve(
        self,
        candidate: Register,
        nearest: tuple[VarName, VarName],
        offered: tuple[int, CodeLabel],
    ) -> None:
        e = self.e
        best, winner = nearest
        index, skip = offered
        e.skip_if(e.binop(">=", candidate, e.load(best)), skip)
        e.store(best, candidate)
        e.store(winner, e.int_(index))
        e.place(skip)

    def _end_delimiter(
        self,
        delimiters: Sequence[Delimiter],
        found: tuple[Register, Register],
        piece: _PieceVars,
    ) -> None:
        """Record the winning delimiter and move past it (past its whole run for
        ALL); with no delimiter found the examination is at the end."""
        start, winner = found
        received = self.e.label("unstring_received")
        for index, delimiter in enumerate(delimiters):
            other = self.e.label("unstring_other")
            self.e.skip_if(self.e.binop("!=", winner, self.e.int_(index)), other)
            self._past_delimiter(delimiter, start, piece)
            self.e.jump(received)
            self.e.place(other)
        self.e.store(self.state.position, start)
        self.e.place(received)

    def _past_delimiter(
        self, delimiter: Delimiter, start: Register, piece: _PieceVars
    ) -> None:
        e = self.e
        text, all_occurrences = delimiter
        _text, delimiter_in, _count = piece
        e.store(delimiter_in, text)
        width = e.call(BuiltinName.LENGTH, text)
        e.store(self.state.position, e.binop("+", start, width))
        if all_occurrences:
            e.loop("unstring_run", partial(self._run_step, (text, width)))

    def _run_step(
        self, delimiter: tuple[Register, Register], _head: CodeLabel, done: CodeLabel
    ) -> None:
        e, state = self.e, self.state
        text, width = delimiter
        at = e.load(state.position)
        following = e.call(BuiltinName.STRING_SLICE, state.source, at, width)
        e.skip_if(e.binop("!=", following, text), done)
        e.store(state.position, e.binop("+", at, width))

    def outcome(
        self, ends: tuple[VarName, VarName], pieces: Sequence[_PieceVars]
    ) -> UnstringIrOutcome:
        e = self.e
        pointer, overflow = ends
        return UnstringIrOutcome(
            pointer=e.load(pointer),
            overflow=e.load(overflow),
            acted=e.load(self.state.acted),
            pieces=tuple(
                UnstringIrPiece(
                    text=e.load(text), delimiter=e.load(found), count=e.load(count)
                )
                for text, found, count in pieces
            ),
        )
