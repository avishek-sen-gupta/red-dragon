"""Emits a COBOL file verb as IR: its I-O status checks in order, the file primitive when
none refuses it, and the state the verb leaves (ANSI X3.23-1985 VI-1.3.5, the I-O status).
"""

from __future__ import annotations

from collections.abc import Callable, Sequence
from dataclasses import dataclass

from interpreter.cobol.access_result import AccessCondition
from interpreter.cobol.cobol_constants import BuiltinName
from interpreter.cobol.file_logic_status import FileLogicStatus
from interpreter.cobol.file_position import FilePosition
from interpreter.cobol.file_state import FileState
from interpreter.cobol.ir_emitter import IrEmitter
from interpreter.cobol.outcome_status import OUTCOME_STATUS
from interpreter.ir import CodeLabel
from interpreter.register import Register
from interpreter.var_name import VarName


@dataclass(frozen=True)
class Refusal:
    """A status a verb ends with, without its primitive, when ``holds`` emits true."""

    holds: Callable[[], Register]
    status: FileLogicStatus


@dataclass(frozen=True)
class VerbOutcome:
    """The variables a verb's status, record and relative record number land in."""

    status: VarName
    data: VarName
    number: VarName


@dataclass(frozen=True)
class FileVerbIr:
    """One file verb's IR over one file's state, all at one source span."""

    e: IrEmitter
    state: FileState
    program: Register

    def outcome(self) -> VerbOutcome:
        return VerbOutcome(
            status=VarName(self.e.ctx.fresh_name("io_status")),
            data=VarName(self.e.ctx.fresh_name("io_data")),
            number=VarName(self.e.ctx.fresh_name("io_number")),
        )

    def with_record(self, outcome: VerbOutcome) -> None:
        """No record until the primitive returns one."""
        self.e.store(outcome.data, self.e.text(""))

    def with_number(self, outcome: VerbOutcome) -> None:
        """No relative record number until the primitive returns one."""
        self.e.store(outcome.number, self.e.int_(0))

    def guarded(
        self,
        refusals: Sequence[Refusal],
        outcome: VerbOutcome,
        perform: Callable[[], None],
        after_refusal: Callable[[], None],
    ) -> None:
        refused, done = self.e.label("io_refused"), self.e.label("io_done")
        _ = [self._refuse_if(r, outcome, refused) for r in refusals]
        perform()
        self.e.jump(done)
        self.e.place(refused)
        after_refusal()
        self.e.jump(done)
        self.e.place(done)

    def _refuse_if(
        self, refusal: Refusal, outcome: VerbOutcome, refused: CodeLabel
    ) -> None:
        refuse, next_check = self.e.label("io_refuse"), self.e.label("io_check")
        self.e.branch_if(refusal.holds(), refuse, next_check)
        self.e.place(refuse)
        self.e.store(outcome.status, self.e.text(refusal.status.value))
        self.e.jump(refused)
        self.e.place(next_check)

    def called(self, primitive: str, outcome: VerbOutcome, *args: Register) -> Register:
        raw = self.e.call(primitive, *args, self.program)
        self.store_status(outcome, self.e.call("__cobol_io_outcome", raw, self.program))
        return raw

    def store_status(self, outcome: VerbOutcome, driver_outcome: Register) -> None:
        """The FILE STATUS the driver outcome reports."""
        done = self.e.label("io_mapped")
        _ = [
            self._map_if(outcome, driver_outcome, pair, done) for pair in OUTCOME_STATUS
        ]
        self.e.place(done)

    def _map_if(
        self,
        outcome: VerbOutcome,
        driver_outcome: Register,
        pair: tuple[AccessCondition, FileLogicStatus],
        done: CodeLabel,
    ) -> None:
        condition, status = pair
        hit, miss = self.e.label("io_outcome"), self.e.label("io_outcome_next")
        self.e.branch_if(
            self.e.binop("==", driver_outcome, self.e.text(condition.value)), hit, miss
        )
        self.e.place(hit)
        self.set_status(outcome, status)
        self.e.jump(done)
        self.e.place(miss)

    def keep_record(self, raw: Register, outcome: VerbOutcome) -> None:
        self.e.store(outcome.data, self.e.call("__cobol_io_data", raw, self.program))

    def keep_number(self, raw: Register, outcome: VerbOutcome) -> None:
        self.e.store(
            outcome.number,
            self.e.call("__cobol_io_record_number", raw, self.program),
        )

    def read_refused(self) -> Register:
        return self.e.load(self.state.read_refused)

    def write_refused(self) -> Register:
        return self.e.load(self.state.write_refused)

    def update_refused(self) -> Register:
        return self.e.load(self.state.update_refused)

    def closed(self) -> Register:
        return self.e.binop("==", self.e.load(self.state.mode), self.e.text(""))

    def open_(self) -> Register:
        return self.e.binop("!=", self.e.load(self.state.mode), self.e.text(""))

    def locked(self) -> Register:
        return self.e.load(self.state.locked)

    def position_is(self, position: FilePosition) -> Register:
        return self.e.binop(
            "==", self.e.load(self.state.position), self.e.text(position.value)
        )

    def position_is_not(self, position: FilePosition) -> Register:
        return self.e.binop(
            "!=", self.e.load(self.state.position), self.e.text(position.value)
        )

    def status_is(self, outcome: VerbOutcome, *codes: FileLogicStatus) -> Register:
        status = self.e.load(outcome.status)
        return self._any(
            [self.e.binop("==", status, self.e.text(c.value)) for c in codes]
        )

    def successful(self, outcome: VerbOutcome) -> Register:
        status = self.e.load(outcome.status)
        first = self.e.call(
            BuiltinName.STRING_SLICE, status, self.e.int_(0), self.e.int_(1)
        )
        return self.e.binop("==", first, self.e.text("0"))

    def set_position(self, position: FilePosition) -> None:
        self.e.store(self.state.position, self.e.text(position.value))

    def set_mode(self, mode: str) -> None:
        self.e.store(self.state.mode, self.e.text(mode))

    def absent(self) -> Register:
        return self.e.load(self.state.absent)

    def set_status(self, outcome: VerbOutcome, status: FileLogicStatus) -> None:
        self.e.store(outcome.status, self.e.text(status.value))

    def either(
        self,
        cond: Register,
        then: Callable[[], None],
        otherwise: Callable[[], None],
    ) -> None:
        do, other, done = (
            self.e.label("io_then"),
            self.e.label("io_else"),
            self.e.label("io_end"),
        )
        self.e.branch_if(cond, do, other)
        self.e.place(do)
        then()
        self.e.jump(done)
        self.e.place(other)
        otherwise()
        self.e.jump(done)
        self.e.place(done)

    def unless_absent(
        self,
        optional: bool,
        absent: Callable[[], None],
        present: Callable[[], None],
    ) -> None:
        """``present`` for a file the provider opened; for an OPTIONAL file it could
        also be ``absent`` instead, opened INPUT while missing."""
        if not optional:
            present()
            return
        self.either(self.absent(), absent, present)

    def when(self, cond: Register, then: Callable[[], None]) -> None:
        do, skip = self.e.label("io_when"), self.e.label("io_skip")
        self.e.branch_if(cond, do, skip)
        self.e.place(do)
        then()
        self.e.jump(skip)
        self.e.place(skip)

    def forget_current_record(self) -> None:
        self.when(
            self.position_is(FilePosition.CURRENT_RECORD),
            lambda: self.set_position(FilePosition.NO_CURRENT_RECORD),
        )

    def _any(self, tests: Sequence[Register]) -> Register:
        first, *rest = tests
        return (
            self._any([self.e.binop("or", first, rest[0]), *rest[1:]])
            if rest
            else first
        )


def emit_closed(e: IrEmitter, state: FileState, locked: bool) -> None:
    """A file's state when it is not open: no mode, no current record, every verb but
    OPEN refused, and locked when it was closed WITH LOCK."""
    e.store(state.mode, e.text(""))
    e.store(state.locked, e.bool_(locked))
    e.store(state.read_refused, e.bool_(True))
    e.store(state.write_refused, e.bool_(True))
    e.store(state.update_refused, e.bool_(True))
    e.store(state.position, e.text(FilePosition.NO_CURRENT_RECORD.value))
    e.store(state.absent, e.bool_(False))
    e.store(state.last_key, e.text(""))
