"""COBOL frontend — lowers ProLeap JSON ASG to RedDragon IR.

Direct Frontend subclass (not BaseFrontend) since COBOL does not
use tree-sitter. Consumes CobolASG from the ProLeap bridge and
produces IR instructions for the VM.
"""

from __future__ import annotations

import logging
from typing import Any

from interpreter.cobol.asg_types import (
    CobolASG,
    CobolParagraph,
    CobolSection,
)
from interpreter.cobol.condition_lowering import (
    lower_condition,
)
from interpreter.cobol.lower_arithmetic import (
    lower_arithmetic as _lower_arithmetic_fn,
    lower_compute as _lower_compute_fn,
    lower_continue as _lower_continue_fn,
    lower_display as _lower_display_fn,
    lower_evaluate as _lower_evaluate_fn,
    lower_exit as _lower_exit_fn,
    lower_goto as _lower_goto_fn,
    lower_if as _lower_if_fn,
    lower_initialize as _lower_initialize_fn,
    lower_move as _lower_move_fn,
    lower_set as _lower_set_fn,
    lower_stop_run as _lower_stop_run_fn,
)
from interpreter.cobol.lower_call import (
    lower_alter as _lower_alter_fn,
    lower_call as _lower_call_fn,
    lower_cancel as _lower_cancel_fn,
    lower_entry as _lower_entry_fn,
)
from interpreter.cobol.lower_io import (
    lower_accept as _lower_accept_fn,
    lower_close as _lower_close_fn,
    lower_delete as _lower_delete_fn,
    lower_open as _lower_open_fn,
    lower_read as _lower_read_fn,
    lower_rewrite as _lower_rewrite_fn,
    lower_start as _lower_start_fn,
    lower_write as _lower_write_fn,
)
from interpreter.cobol.lower_perform import lower_perform as _lower_perform_fn
from interpreter.cobol.lower_search import lower_search as _lower_search_fn
from interpreter.cobol.lower_string_inspect import (
    lower_inspect as _lower_inspect_fn,
    lower_string as _lower_string_fn,
    lower_unstring as _lower_unstring_fn,
)
from interpreter.cobol.cobol_statements import (
    AcceptStatement,
    AlterStatement,
    ArithmeticStatement,
    CallStatement,
    CancelStatement,
    CloseStatement,
    CobolStatementType,
    ComputeStatement,
    ContinueStatement,
    DisplayStatement,
    EntryStatement,
    EvaluateStatement,
    ExitStatement,
    GotoStatement,
    IfStatement,
    InitializeStatement,
    InspectStatement,
    MoveStatement,
    OpenStatement,
    PerformStatement,
    PerformTimesSpec,
    PerformUntilSpec,
    PerformVaryingSpec,
    ReadStatement,
    SearchStatement,
    SetStatement,
    StopRunStatement,
    StringStatement,
    UnstringStatement,
    WhenOtherStatement,
    WhenStatement,
    WriteStatement,
    RewriteStatement,
    StartStatement,
    DeleteStatement,
)
from interpreter.cobol.data_layout import build_data_layout
from interpreter.cobol.emit_context import EmitContext
from interpreter.cobol.field_resolution import (
    ResolvedFieldRef,
    parse_subscript_notation,
)
from interpreter.frontend import Frontend
from interpreter.frontend_observer import FrontendObserver, NullFrontendObserver
from interpreter.ir import IRInstruction, Opcode

logger = logging.getLogger(__name__)

# Re-export for backward compatibility (used by test_occurs_frontend.py)
_parse_subscript_notation = parse_subscript_notation


def _dispatch_statement(
    ctx: EmitContext,
    stmt: CobolStatementType,
    layout: DataLayout,
    region_reg: str,
) -> None:
    """Route a statement to its lowering function.

    This is the dispatch callback injected into EmitContext.
    During incremental extraction, it delegates back to
    CobolFrontend._lower_statement via a closure.
    """
    raise NotImplementedError("Should not be called directly")


class CobolFrontend(Frontend):
    """Lowers COBOL ASG (from ProLeap bridge) to RedDragon IR.

    Architecture: The ProLeap bridge (separate Java repo) parses COBOL
    source and emits JSON ASG. This frontend consumes that ASG and
    produces IR instructions.
    """

    def __init__(
        self,
        cobol_parser: Any,
        observer: FrontendObserver = NullFrontendObserver(),
    ):
        self._parser = cobol_parser
        self._observer = observer
        # Create a placeholder ctx; lower() creates the real one
        self._ctx = EmitContext(
            dispatch_fn=lambda ctx, stmt, layout, region_reg: self._lower_statement(
                stmt, layout, region_reg
            ),
            observer=observer,
        )

    # ── Test-compatibility property proxies ────────────────────────

    @property
    def _reg_counter(self) -> int:
        return self._ctx._reg_counter

    @_reg_counter.setter
    def _reg_counter(self, value: int) -> None:
        self._ctx._reg_counter = value

    @property
    def _label_counter(self) -> int:
        return self._ctx._label_counter

    @_label_counter.setter
    def _label_counter(self, value: int) -> None:
        self._ctx._label_counter = value

    @property
    def _instructions(self) -> list[IRInstruction]:
        return self._ctx._instructions

    @_instructions.setter
    def _instructions(self, value: list[IRInstruction]) -> None:
        self._ctx._instructions = value

    def _resolve_field_ref(
        self, name: str, layout: DataLayout, region_reg: str
    ) -> ResolvedFieldRef:
        return self._ctx.resolve_field_ref(name, layout, region_reg)

    def _has_field(self, name: str, layout: DataLayout) -> bool:
        return self._ctx.has_field(name, layout)

    # ── Main entry point ──────────────────────────────────────────

    def lower(self, source: bytes) -> list[IRInstruction]:
        """Lower COBOL source to IR via the ProLeap bridge."""
        self._ctx = EmitContext(
            dispatch_fn=lambda ctx, stmt, layout, region_reg: self._lower_statement(
                stmt, layout, region_reg
            ),
            observer=self._observer,
        )

        asg = self._parser.parse(source)
        layout = build_data_layout(asg.data_fields)

        self._ctx.emit(Opcode.LABEL, label="entry")

        region_reg = self._lower_data_division(layout)
        self._lower_procedure_division(asg, layout, region_reg)

        logger.info(
            "COBOL frontend produced %d IR instructions",
            len(self._ctx.instructions),
        )
        return self._ctx.instructions

    # ── DATA DIVISION ──────────────────────────────────────────────

    def _lower_data_division(self, layout: DataLayout) -> str:
        """Emit ALLOC_REGION + initial VALUE encodings. Returns region register."""
        ctx = self._ctx
        region_reg = ctx.fresh_reg()
        ctx.emit(
            Opcode.ALLOC_REGION,
            result_reg=region_reg,
            operands=[layout.total_bytes],
        )

        fields_with_values = [fl for fl in layout.fields.values() if fl.value]
        for fl in fields_with_values:
            ctx.emit_field_encode(region_reg, fl, fl.value)

        logger.debug(
            "Data Division: allocated %d bytes, initialized %d fields",
            layout.total_bytes,
            len(fields_with_values),
        )
        return region_reg

    # ── PROCEDURE DIVISION ─────────────────────────────────────────

    def _lower_procedure_division(
        self,
        asg: CobolASG,
        layout: DataLayout,
        region_reg: str,
    ) -> None:
        """Lower all sections and standalone paragraphs."""
        self._ctx.section_paragraphs = {
            section.name: [p.name for p in section.paragraphs]
            for section in asg.sections
        }

        for para in asg.paragraphs:
            self._lower_paragraph(para, layout, region_reg)

        for section in asg.sections:
            self._lower_section(section, layout, region_reg)

    def _lower_section(
        self,
        section: CobolSection,
        layout: DataLayout,
        region_reg: str,
    ) -> None:
        ctx = self._ctx
        ctx.emit(Opcode.LABEL, label=f"section_{section.name}")
        for para in section.paragraphs:
            self._lower_paragraph(para, layout, region_reg)
        ctx.emit(
            Opcode.RESUME_CONTINUATION,
            operands=[f"section_{section.name}_end"],
        )

    def _lower_paragraph(
        self,
        para: CobolParagraph,
        layout: DataLayout,
        region_reg: str,
    ) -> None:
        ctx = self._ctx
        ctx.emit(Opcode.LABEL, label=f"para_{para.name}")
        for stmt in para.statements:
            self._lower_statement(stmt, layout, region_reg)
        ctx.emit(Opcode.RESUME_CONTINUATION, operands=[f"para_{para.name}_end"])

    # ── Statement Dispatch ─────────────────────────────────────────

    def _lower_statement(
        self,
        stmt: CobolStatementType,
        layout: DataLayout,
        region_reg: str,
    ) -> None:
        if isinstance(stmt, MoveStatement):
            self._lower_move(stmt, layout, region_reg)
        elif isinstance(stmt, ArithmeticStatement):
            self._lower_arithmetic(stmt, layout, region_reg)
        elif isinstance(stmt, ComputeStatement):
            self._lower_compute(stmt, layout, region_reg)
        elif isinstance(stmt, IfStatement):
            self._lower_if(stmt, layout, region_reg)
        elif isinstance(stmt, PerformStatement):
            self._lower_perform(stmt, layout, region_reg)
        elif isinstance(stmt, DisplayStatement):
            self._lower_display(stmt, layout, region_reg)
        elif isinstance(stmt, StopRunStatement):
            self._lower_stop_run(stmt, layout, region_reg)
        elif isinstance(stmt, GotoStatement):
            self._lower_goto(stmt, layout, region_reg)
        elif isinstance(stmt, EvaluateStatement):
            self._lower_evaluate(stmt, layout, region_reg)
        elif isinstance(stmt, ContinueStatement):
            self._lower_continue(stmt, layout, region_reg)
        elif isinstance(stmt, ExitStatement):
            self._lower_exit(stmt, layout, region_reg)
        elif isinstance(stmt, InitializeStatement):
            self._lower_initialize(stmt, layout, region_reg)
        elif isinstance(stmt, SetStatement):
            self._lower_set(stmt, layout, region_reg)
        elif isinstance(stmt, StringStatement):
            self._lower_string(stmt, layout, region_reg)
        elif isinstance(stmt, UnstringStatement):
            self._lower_unstring(stmt, layout, region_reg)
        elif isinstance(stmt, InspectStatement):
            self._lower_inspect(stmt, layout, region_reg)
        elif isinstance(stmt, SearchStatement):
            self._lower_search(stmt, layout, region_reg)
        elif isinstance(stmt, CallStatement):
            self._lower_call(stmt, layout, region_reg)
        elif isinstance(stmt, AlterStatement):
            self._lower_alter(stmt, layout, region_reg)
        elif isinstance(stmt, EntryStatement):
            self._lower_entry(stmt, layout, region_reg)
        elif isinstance(stmt, CancelStatement):
            self._lower_cancel(stmt, layout, region_reg)
        elif isinstance(stmt, AcceptStatement):
            self._lower_accept(stmt, layout, region_reg)
        elif isinstance(stmt, OpenStatement):
            self._lower_open(stmt, layout, region_reg)
        elif isinstance(stmt, CloseStatement):
            self._lower_close(stmt, layout, region_reg)
        elif isinstance(stmt, ReadStatement):
            self._lower_read(stmt, layout, region_reg)
        elif isinstance(stmt, WriteStatement):
            self._lower_write(stmt, layout, region_reg)
        elif isinstance(stmt, RewriteStatement):
            self._lower_rewrite(stmt, layout, region_reg)
        elif isinstance(stmt, StartStatement):
            self._lower_start(stmt, layout, region_reg)
        elif isinstance(stmt, DeleteStatement):
            self._lower_delete(stmt, layout, region_reg)
        else:
            logger.warning("Unhandled COBOL statement type: %s", type(stmt).__name__)

    # ── MOVE ───────────────────────────────────────────────────────

    def _lower_move(self, stmt, layout, region_reg):
        _lower_move_fn(self._ctx, stmt, layout, region_reg)

    def _lower_arithmetic(self, stmt, layout, region_reg):
        _lower_arithmetic_fn(self._ctx, stmt, layout, region_reg)

    def _lower_compute(self, stmt, layout, region_reg):
        _lower_compute_fn(self._ctx, stmt, layout, region_reg)

    def _lower_if(self, stmt, layout, region_reg):
        _lower_if_fn(self._ctx, stmt, layout, region_reg)

    # ── PERFORM ────────────────────────────────────────────────────

    def _lower_perform(self, stmt, layout, region_reg):
        """PERFORM — delegates to lower_perform module."""
        _lower_perform_fn(self._ctx, stmt, layout, region_reg)

    def _lower_display(self, stmt, layout, region_reg):
        _lower_display_fn(self._ctx, stmt, layout, region_reg)

    def _lower_stop_run(self, stmt, layout, region_reg):
        _lower_stop_run_fn(self._ctx, stmt, layout, region_reg)

    def _lower_goto(self, stmt, layout, region_reg):
        _lower_goto_fn(self._ctx, stmt, layout, region_reg)

    def _lower_evaluate(self, stmt, layout, region_reg):
        _lower_evaluate_fn(self._ctx, stmt, layout, region_reg)

    def _lower_continue(self, stmt, layout, region_reg):
        _lower_continue_fn(self._ctx, stmt, layout, region_reg)

    def _lower_exit(self, stmt, layout, region_reg):
        _lower_exit_fn(self._ctx, stmt, layout, region_reg)

    def _lower_initialize(self, stmt, layout, region_reg):
        _lower_initialize_fn(self._ctx, stmt, layout, region_reg)

    def _lower_set(self, stmt, layout, region_reg):
        _lower_set_fn(self._ctx, stmt, layout, region_reg)

    def _lower_string(self, stmt, layout, region_reg):
        _lower_string_fn(self._ctx, stmt, layout, region_reg)

    def _lower_unstring(self, stmt, layout, region_reg):
        _lower_unstring_fn(self._ctx, stmt, layout, region_reg)

    def _lower_inspect(self, stmt, layout, region_reg):
        _lower_inspect_fn(self._ctx, stmt, layout, region_reg)

    def _lower_search(self, stmt, layout, region_reg):
        _lower_search_fn(self._ctx, stmt, layout, region_reg)

    def _lower_call(self, stmt, layout, region_reg):
        _lower_call_fn(self._ctx, stmt, layout, region_reg)

    def _lower_alter(self, stmt, layout, region_reg):
        _lower_alter_fn(self._ctx, stmt, layout, region_reg)

    def _lower_entry(self, stmt, layout, region_reg):
        _lower_entry_fn(self._ctx, stmt, layout, region_reg)

    def _lower_cancel(self, stmt, layout, region_reg):
        _lower_cancel_fn(self._ctx, stmt, layout, region_reg)

    def _lower_accept(self, stmt, layout, region_reg):
        _lower_accept_fn(self._ctx, stmt, layout, region_reg)

    def _lower_open(self, stmt, layout, region_reg):
        _lower_open_fn(self._ctx, stmt, layout, region_reg)

    def _lower_close(self, stmt, layout, region_reg):
        _lower_close_fn(self._ctx, stmt, layout, region_reg)

    def _lower_read(self, stmt, layout, region_reg):
        _lower_read_fn(self._ctx, stmt, layout, region_reg)

    def _lower_write(self, stmt, layout, region_reg):
        _lower_write_fn(self._ctx, stmt, layout, region_reg)

    def _lower_rewrite(self, stmt, layout, region_reg):
        _lower_rewrite_fn(self._ctx, stmt, layout, region_reg)

    def _lower_start(self, stmt, layout, region_reg):
        _lower_start_fn(self._ctx, stmt, layout, region_reg)

    def _lower_delete(self, stmt, layout, region_reg):
        _lower_delete_fn(self._ctx, stmt, layout, region_reg)
