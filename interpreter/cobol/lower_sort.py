"""SORT, MERGE, RELEASE and RETURN lowering: the sort file is a sequential work file
that the USING files or the input procedure's RELEASEs fill, that is put in key
order, and that the GIVING files copy or the output procedure's RETURNs read."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from functools import partial

from cobol_asg.cobol_statements import (
    CloseStatement,
    MergeStatement,
    OpenStatement,
    PerformStatement,
    ProcedureRange,
    ReadStatement,
    ReleaseStatement,
    ReturnStatement,
    SortStatement,
    WriteStatement,
)
from cobol_asg.collating_sequence_phrase import CollatingSequencePhrase
from cobol_asg.file_enums import FileOrganization, OpenMode
from cobol_asg.program_collation import ProgramCollation
from cobol_asg.sort_files import SortFiles
from cobol_asg.sort_key import SortKey
from interpreter.cobol.collating_sequences import collating_sequence_of
from interpreter.cobol.data_layout import FieldLayout
from interpreter.cobol.emit_context import EmitContext
from interpreter.cobol.file_frame import FileFrame
from interpreter.cobol.file_state import file_state
from interpreter.cobol.file_verb_ir import FileVerbIr, emit_closed
from interpreter.cobol.ir_emitter import IrEmitter
from interpreter.cobol.lower_io import lower_close, lower_open, lower_read, lower_write
from interpreter.cobol.lower_perform import emit_perform_branch
from interpreter.cobol.prime_key import PrimeKey
from interpreter.cobol.program_object import program_name
from interpreter.cobol.sectioned_layout import MaterialisedSectionedLayout
from interpreter.cobol.sort_field import SortField
from interpreter.cobol.sort_key_layout import sort_key_encoding
from interpreter.cobol.sort_ordering import SortOrdering
from interpreter.cobol.sort_pass_ir import SortPassIr


def _nothing() -> None:
    return


def _first_record(ctx: EmitContext, sort_file: str) -> str:
    return next(
        record
        for record, selected in ctx._asg.file_record_to_select.items()
        if selected == sort_file.upper()
    )


@dataclass(frozen=True)
class _SortLowering:
    """One SORT's lowering: its work file filled, ordered and drained."""

    ctx: EmitContext
    stmt: SortStatement
    materialised: MaterialisedSectionedLayout

    def lower(self) -> None:
        self._open(OpenMode.OUTPUT, self.stmt.file_name)
        self._fill()
        self._order()
        emit_closed(
            IrEmitter(self.ctx, self.stmt.span),
            file_state(program_name(self.ctx._asg), self.stmt.file_name),
            False,
        )
        self._drain()

    def _passes(self) -> SortPassIr:
        e = IrEmitter(self.ctx, self.stmt.span)
        return SortPassIr(e, e.text(program_name(self.ctx._asg)))

    def _open(self, mode: OpenMode, filename: str) -> None:
        lower_open(
            self.ctx,
            OpenStatement(mode_groups=[(mode, [filename])], span=self.stmt.span),
            self.materialised,
        )

    def _close(self, filename: str) -> None:
        lower_close(
            self.ctx,
            CloseStatement(files=[filename], span=self.stmt.span),
            self.materialised,
        )

    def _verb(self, filename: str) -> FileVerbIr:
        e = IrEmitter(self.ctx, self.stmt.span)
        program = program_name(self.ctx._asg)
        return FileVerbIr(e, file_state(program, filename), e.text(program))

    def _if_opened(self, filename: str, transfer: Callable[[], None]) -> None:
        v = self._verb(filename)
        v.when(v.open_(), lambda: self._transferred(v, filename, transfer))

    def _transferred(
        self, v: FileVerbIr, filename: str, transfer: Callable[[], None]
    ) -> None:
        v.either(v.absent(), _nothing, transfer)
        self._close(filename)

    def _copy_in(self, filename: str) -> None:
        self._open(OpenMode.INPUT, filename)
        self._if_opened(
            filename, partial(self._passes().copy, filename, self.stmt.file_name)
        )

    def _copy_out(self, filename: str) -> None:
        self._open(OpenMode.OUTPUT, filename)
        self._if_opened(
            filename, partial(self._passes().copy, self.stmt.file_name, filename)
        )

    def _perform(self, procedure: ProcedureRange) -> None:
        emit_perform_branch(
            self.ctx,
            PerformStatement(
                target=procedure.target.paragraph,
                target_section=procedure.target.section,
                thru=procedure.thru.paragraph,
                thru_section=procedure.thru.section,
                span=self.stmt.span,
            ),
            self.materialised,
        )

    def _reading(self, emit: Callable[[], None]) -> None:
        self._open(OpenMode.INPUT, self.stmt.file_name)
        emit()
        self._close(self.stmt.file_name)

    def _fill(self) -> None:
        match self.stmt.source:
            case SortFiles() as files:
                _ = [self._copy_in(filename) for filename in files.names]
            case ProcedureRange() as procedure:
                self._perform(procedure)

    def _drain(self) -> None:
        match self.stmt.sink:
            case SortFiles() as files:
                _ = [
                    self._reading(partial(self._copy_out, filename))
                    for filename in files.names
                ]
            case ProcedureRange() as procedure:
                self._reading(partial(self._perform, procedure))

    def _sort_field(self, key: SortKey, record: FieldLayout) -> SortField:
        layout, _ = self.materialised.resolve(key.key.name, key.key.qualifiers)
        return SortField(
            offset=layout.offset - record.offset,
            length=layout.byte_length,
            encoding=sort_key_encoding(layout),
            direction=key.direction,
        )

    def _weights(self) -> tuple[int, ...]:
        match self.stmt.collating_sequence:
            case CollatingSequencePhrase() as phrase:
                alphabet = phrase.alphanumeric_alphabet(self.ctx.alphabets)
                return collating_sequence_of(alphabet).weights
            case ProgramCollation():
                return self.ctx.collating_sequence.weights

    def _order(self) -> None:
        record, _ = self.materialised.resolve(
            _first_record(self.ctx, self.stmt.file_name)
        )
        self._passes().order(
            FileFrame(
                self.stmt.file_name,
                FileOrganization.SEQUENTIAL,
                PrimeKey(),
                False,
                record.byte_length,
            ),
            SortOrdering(
                tuple(self._sort_field(key, record) for key in self.stmt.keys),
                self._weights(),
            ),
        )


def lower_sort(
    ctx: EmitContext, stmt: SortStatement, materialised: MaterialisedSectionedLayout
) -> None:
    _SortLowering(ctx, stmt, materialised).lower()


def lower_merge(
    ctx: EmitContext, stmt: MergeStatement, materialised: MaterialisedSectionedLayout
) -> None:
    lower_sort(
        ctx,
        SortStatement(
            file_name=stmt.file_name,
            keys=stmt.keys,
            collating_sequence=stmt.collating_sequence,
            source=stmt.using,
            sink=stmt.sink,
            span=stmt.span,
        ),
        materialised,
    )


def lower_release(
    ctx: EmitContext, stmt: ReleaseStatement, materialised: MaterialisedSectionedLayout
) -> None:
    lower_write(
        ctx,
        WriteStatement(
            record_name=stmt.record_name, from_field=stmt.from_field, span=stmt.span
        ),
        materialised,
    )


def lower_return(
    ctx: EmitContext, stmt: ReturnStatement, materialised: MaterialisedSectionedLayout
) -> None:
    lower_read(
        ctx,
        ReadStatement(
            file_name=stmt.file_name,
            into=stmt.into,
            at_end=list(stmt.at_end),
            not_at_end=list(stmt.not_at_end),
            span=stmt.span,
        ),
        materialised,
    )
