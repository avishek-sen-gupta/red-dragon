"""Emits a SORT's passes over its work file as IR on the file primitives: USING and
GIVING copy records file to file, and the ordering pass reads the work file, orders
its records with the one sort builtin, and writes them back."""

from __future__ import annotations

from dataclasses import dataclass

from cobol_asg.file_enums import OpenMode
from interpreter.cobol.access_result import AccessCondition
from interpreter.cobol.cobol_constants import BuiltinName
from interpreter.cobol.file_frame import FileFrame
from interpreter.cobol.ir_emitter import IrEmitter
from interpreter.cobol.sort_ordering import SortOrdering
from interpreter.data_value import DataRecord
from interpreter.instructions import Const
from interpreter.ir import CodeLabel
from interpreter.register import Register
from interpreter.types.type_expr import UNKNOWN
from interpreter.var_name import VarName


@dataclass(frozen=True)
class SortPassIr:
    """One SORT's work-file passes, every primitive call naming ``program``."""

    e: IrEmitter
    program: Register

    def copy(self, source: str, target: str) -> None:
        self.e.loop("sort_copy", lambda head, done: self._copied(source, target, done))

    def order(self, frame: FileFrame, ordering: SortOrdering) -> None:
        sort_file = frame.file_name
        self._reopen(frame, OpenMode.INPUT)
        records = self.e.var("sort_records", self.e.texts(()))
        self.e.loop(
            "sort_read",
            lambda head, done: self._collected(sort_file, records, done),
        )
        self._close(sort_file)
        self._open(sort_file, OpenMode.OUTPUT)
        ordered = self.e.var(
            "sort_ordered",
            self.e.call(
                BuiltinName.SORT_RECORDS,
                self.e.load(records),
                self._record(ordering.data()),
            ),
        )
        index = self.e.var("sort_index", self.e.int_(0))
        self.e.loop(
            "sort_write",
            lambda head, done: self._written(sort_file, (ordered, index), done),
        )
        self._close(sort_file)

    def _copied(self, source: str, target: str, done: CodeLabel) -> None:
        raw = self._read(source, done)
        self._write(target, self.e.call("__cobol_io_data", raw, self.program))

    def _collected(self, sort_file: str, records: VarName, done: CodeLabel) -> None:
        raw = self._read(sort_file, done)
        one = self.e.call(
            BuiltinName.LIST_SET,
            self.e.texts(("",)),
            self.e.int_(0),
            self.e.call("__cobol_io_data", raw, self.program),
        )
        self.e.store(
            records, self.e.call(BuiltinName.LIST_CONCAT, self.e.load(records), one)
        )

    def _written(
        self, sort_file: str, state: tuple[VarName, VarName], done: CodeLabel
    ) -> None:
        ordered, index = state
        more = self.e.label("sort_more")
        self.e.branch_if(
            self.e.binop(
                ">=",
                self.e.load(index),
                self.e.call(BuiltinName.LIST_LEN, self.e.load(ordered)),
            ),
            done,
            more,
        )
        self.e.place(more)
        self._write(
            sort_file,
            self.e.call(BuiltinName.LIST_GET, self.e.load(ordered), self.e.load(index)),
        )
        self.e.store(index, self.e.binop("+", self.e.load(index), self.e.int_(1)))

    def _read(self, filename: str, done: CodeLabel) -> Register:
        raw = self.e.call(
            "__cobol_read_record", self.e.text(filename), self.e.text(""), self.program
        )
        outcome = self.e.call("__cobol_io_outcome", raw, self.program)
        got = self.e.label("sort_got")
        self.e.branch_if(
            self.e.binop(
                "and",
                self.e.binop("!=", outcome, self.e.int_(AccessCondition.OK.position())),
                self.e.binop(
                    "!=",
                    outcome,
                    self.e.int_(AccessCondition.DUPLICATES_FOLLOW.position()),
                ),
            ),
            done,
            got,
        )
        self.e.place(got)
        return raw

    def _write(self, filename: str, data: Register) -> None:
        self.e.call(
            "__cobol_write_record",
            self.e.text(filename),
            data,
            self.e.text(""),
            self.program,
        )

    def _reopen(self, frame: FileFrame, mode: OpenMode) -> None:
        self._close(frame.file_name)
        self.e.call("__cobol_declare_file", self._record(frame.data()), self.program)
        self._open(frame.file_name, mode)

    def _open(self, filename: str, mode: OpenMode) -> None:
        self.e.call(
            "__cobol_open_file",
            self.e.text(filename),
            self.e.text(mode.value),
            self.program,
        )

    def _close(self, filename: str) -> None:
        self.e.call("__cobol_close_file", self.e.text(filename), self.program)

    def _record(self, value: DataRecord) -> Register:
        reg = self.e.ctx.fresh_reg()
        self.e.ctx.emit_inst(
            Const(result_reg=reg, value=value, type_expr=UNKNOWN), span=self.e.span
        )
        return reg
