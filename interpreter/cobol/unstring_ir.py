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
    state = UnstringIrState(
        source=source,
        size=size,
        position=e.var("unstring_position", e.binop("-", pointer, e.int_(1))),
        acted=e.var("unstring_acted", e.int_(0)),
    )
    ends = (
        e.var("unstring_pointer", pointer),
        e.var("unstring_overflow", e.bool_(True)),
    )
    pieces = tuple(_piece_vars(e) for _ in sizes)
    _examine_from(e, state, (pointer, ends), (delimiters, sizes, pieces))
    return _outcome(e, state, ends, pieces)


def _examine_from(
    e: IrEmitter,
    state: UnstringIrState,
    start: tuple[Register, tuple[VarName, VarName]],
    receivers: tuple[Sequence[Delimiter], Sequence[int], Sequence[_PieceVars]],
) -> None:
    """Examine unless the pointer is below 1 or past the source."""
    pointer, ends = start
    done = e.label("unstring_done")
    e.skip_if(e.binop("<", pointer, e.int_(1)), done)
    e.skip_if(e.binop(">", pointer, state.size), done)
    _examine(e, state, ends, receivers)
    e.place(done)


def _piece_vars(e: IrEmitter) -> _PieceVars:
    return (
        e.var("unstring_text", e.text("")),
        e.var("unstring_delimiter", e.text("")),
        e.var("unstring_count", e.int_(0)),
    )


def _examine(
    e: IrEmitter,
    state: UnstringIrState,
    ends: tuple[VarName, VarName],
    receivers: tuple[Sequence[Delimiter], Sequence[int], Sequence[_PieceVars]],
) -> None:
    delimiters, sizes, pieces = receivers
    examined = e.label("unstring_examined")
    for index, (receiver_size, piece) in enumerate(zip(sizes, pieces, strict=True)):
        e.skip_if(e.binop(">=", e.load(state.position), state.size), examined)
        _receive(e, state, (delimiters, receiver_size), piece)
        e.store(state.acted, e.int_(index + 1))
    e.place(examined)
    pointer, overflow = ends
    position = e.load(state.position)
    e.store(pointer, e.binop("+", position, e.int_(1)))
    e.store(overflow, e.binop("<", position, state.size))


def _receive(
    e: IrEmitter,
    state: UnstringIrState,
    split: tuple[Sequence[Delimiter], int],
    piece: _PieceVars,
) -> None:
    delimiters, receiver_size = split
    if delimiters:
        _receive_delimited(e, state, delimiters, piece)
        return
    text, _delimiter, count = piece
    at = e.load(state.position)
    taken = e.call(BuiltinName.STRING_SLICE, state.source, at, e.int_(receiver_size))
    taken_count = e.call(BuiltinName.LENGTH, taken)
    e.store(text, taken)
    e.store(count, taken_count)
    e.store(state.position, e.binop("+", at, taken_count))


def _receive_delimited(
    e: IrEmitter,
    state: UnstringIrState,
    delimiters: Sequence[Delimiter],
    piece: _PieceVars,
) -> None:
    """The characters before the nearest delimiter, which then ends them."""
    at = e.load(state.position)
    nearest = (
        e.var("unstring_nearest", state.size),
        e.var("unstring_winner", e.int_(-1)),
    )
    rest = e.call(
        BuiltinName.STRING_SLICE, state.source, at, e.binop("-", state.size, at)
    )
    for index, delimiter in enumerate(delimiters):
        _offer(e, (rest, at), delimiter[0], nearest, index)
    start = e.load(nearest[0])
    _take(e, state, (at, start), piece)
    _end_delimiter(e, state, delimiters, (start, e.load(nearest[1])), piece)


def _take(
    e: IrEmitter,
    state: UnstringIrState,
    bounds: tuple[Register, Register],
    piece: _PieceVars,
) -> None:
    at, start = bounds
    text, _delimiter, count = piece
    taken = e.call(BuiltinName.STRING_SLICE, state.source, at, e.binop("-", start, at))
    e.store(text, taken)
    e.store(count, e.call(BuiltinName.LENGTH, taken))


def _offer(
    e: IrEmitter,
    rest: tuple[Register, Register],
    delimiter: Register,
    nearest: tuple[VarName, VarName],
    index: int,
) -> None:
    """Make this delimiter's first occurrence the nearest when it is nearer
    than every delimiter written before it."""
    remaining, at = rest
    skip = e.label("unstring_skip")
    e.skip_if(e.binop("<", e.call(BuiltinName.LENGTH, delimiter), e.int_(1)), skip)
    found = e.call(BuiltinName.STRING_FIND, remaining, delimiter)
    e.skip_if(e.binop("<", found, e.int_(0)), skip)
    _improve(e, e.binop("+", at, found), nearest, (index, skip))


def _improve(
    e: IrEmitter,
    candidate: Register,
    nearest: tuple[VarName, VarName],
    offered: tuple[int, CodeLabel],
) -> None:
    best, winner = nearest
    index, skip = offered
    e.skip_if(e.binop(">=", candidate, e.load(best)), skip)
    e.store(best, candidate)
    e.store(winner, e.int_(index))
    e.place(skip)


def _end_delimiter(
    e: IrEmitter,
    state: UnstringIrState,
    delimiters: Sequence[Delimiter],
    found: tuple[Register, Register],
    piece: _PieceVars,
) -> None:
    """Record the winning delimiter and move past it (past its whole run for
    ALL); with no delimiter found the examination is at the end."""
    start, winner = found
    received = e.label("unstring_received")
    for index, delimiter in enumerate(delimiters):
        other = e.label("unstring_other")
        e.skip_if(e.binop("!=", winner, e.int_(index)), other)
        _past_delimiter(e, state, delimiter, start, piece)
        e.jump(received)
        e.place(other)
    e.store(state.position, start)
    e.place(received)


def _past_delimiter(
    e: IrEmitter,
    state: UnstringIrState,
    delimiter: Delimiter,
    start: Register,
    piece: _PieceVars,
) -> None:
    text, all_occurrences = delimiter
    _text, delimiter_in, _count = piece
    e.store(delimiter_in, text)
    width = e.call(BuiltinName.LENGTH, text)
    e.store(state.position, e.binop("+", start, width))
    if all_occurrences:
        e.loop("unstring_run", partial(_run_step, e, state, (text, width)))


def _run_step(
    e: IrEmitter,
    state: UnstringIrState,
    delimiter: tuple[Register, Register],
    _head: CodeLabel,
    done: CodeLabel,
) -> None:
    text, width = delimiter
    at = e.load(state.position)
    following = e.call(BuiltinName.STRING_SLICE, state.source, at, width)
    e.skip_if(e.binop("!=", following, text), done)
    e.store(state.position, e.binop("+", at, width))


def _outcome(
    e: IrEmitter,
    state: UnstringIrState,
    ends: tuple[VarName, VarName],
    pieces: Sequence[_PieceVars],
) -> UnstringIrOutcome:
    pointer, overflow = ends
    return UnstringIrOutcome(
        pointer=e.load(pointer),
        overflow=e.load(overflow),
        acted=e.load(state.acted),
        pieces=tuple(
            UnstringIrPiece(
                text=e.load(text), delimiter=e.load(found), count=e.load(count)
            )
            for text, found, count in pieces
        ),
    )
