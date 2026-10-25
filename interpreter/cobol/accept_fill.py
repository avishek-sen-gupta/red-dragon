"""Emits ACCEPT's transfer as IR: input records are concatenated until the receiving
area is full or the input ends, and the area takes the first ``length`` characters."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

from infrastructure.zos.access_methods.access_result import AccessCondition
from interpreter.cobol.cobol_constants import BuiltinName
from interpreter.cobol.ir_emitter import IrEmitter
from interpreter.ir import CodeLabel
from interpreter.register import Register
from interpreter.var_name import VarName


@dataclass(frozen=True)
class AcceptFill:
    """One ACCEPT FROM ``device`` into an area of ``length`` characters."""

    e: IrEmitter
    device: str
    length: int

    def emit(self, program: Register, store: Callable[[Register], None]) -> None:
        received = self.e.var("accept_received", self.e.text(""))
        accepted = self.e.var("accept_any", self.e.bool_(False))
        self.e.loop(
            "accept",
            lambda head, done: self._record(program, (received, accepted), head, done),
        )
        stored, skipped = self.e.label("accept_store"), self.e.label("accept_none")
        self.e.branch_if(self.e.load(accepted), stored, skipped)
        self.e.place(stored)
        store(
            self.e.call(
                BuiltinName.STRING_SLICE,
                self.e.load(received),
                self.e.int_(0),
                self.e.int_(self.length),
            )
        )
        self.e.jump(skipped)
        self.e.place(skipped)

    def _record(
        self,
        program: Register,
        state: tuple[VarName, VarName],
        head: CodeLabel,
        done: CodeLabel,
    ) -> None:
        received, accepted = state
        raw = self.e.call("__cobol_accept", self.e.text(self.device))
        got = self.e.label("accept_record")
        self.e.branch_if(
            self.e.binop(
                "==",
                self.e.call("__cobol_io_outcome", raw, program),
                self.e.int_(AccessCondition.OK.position()),
            ),
            got,
            done,
        )
        self.e.place(got)
        self.e.store(
            received,
            self.e.call(
                BuiltinName.STRING_CONCAT_PAIR,
                self.e.load(received),
                self.e.call("__cobol_io_data", raw, program),
            ),
        )
        self.e.store(accepted, self.e.bool_(True))
        self.e.branch_if(
            self.e.binop(
                ">=",
                self.e.call(BuiltinName.LENGTH, self.e.load(received)),
                self.e.int_(self.length),
            ),
            done,
            head,
        )
