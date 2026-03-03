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
from interpreter.cobol.cobol_expression import (
    BinOpNode,
    ExprNode,
    FieldRefNode,
    LiteralNode,
    parse_expression,
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
from interpreter.cobol.cobol_types import CobolDataCategory
from interpreter.cobol.data_layout import DataLayout, FieldLayout, build_data_layout
from interpreter.cobol.emit_context import EmitContext
from interpreter.cobol.field_resolution import (
    ResolvedFieldRef,
    parse_subscript_notation,
)
from interpreter.cobol.figurative_constants import translate_cobol_figurative
from interpreter.cobol.ir_encoders import (
    build_inspect_replace_ir,
    build_inspect_tally_ir,
    build_string_split_ir,
)
from interpreter.frontend import Frontend
from interpreter.frontend_observer import FrontendObserver, NullFrontendObserver
from interpreter.ir import IRInstruction, Opcode

logger = logging.getLogger(__name__)

_ARITHMETIC_OPS = {
    "ADD": "+",
    "SUBTRACT": "-",
    "MULTIPLY": "*",
    "DIVIDE": "/",
}

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

    def _lower_move(
        self,
        stmt: MoveStatement,
        layout: DataLayout,
        region_reg: str,
    ) -> None:
        """MOVE X TO Y: decode X, encode as Y's type, write to Y's region."""
        ctx = self._ctx
        target_ref = ctx.resolve_field_ref(stmt.target, layout, region_reg)

        if ctx.has_field(stmt.source, layout):
            source_ref = ctx.resolve_field_ref(stmt.source, layout, region_reg)
            decoded_reg = ctx.emit_decode_field(
                region_reg, source_ref.fl, source_ref.offset_reg
            )
            value_str_reg = ctx.emit_to_string(decoded_reg)
        else:
            value_str_reg = ctx.const_to_reg(str(stmt.source))

        ctx.emit_encode_and_write(
            region_reg, target_ref.fl, value_str_reg, target_ref.offset_reg
        )

    # ── Arithmetic ─────────────────────────────────────────────────

    def _lower_arithmetic(
        self,
        stmt: ArithmeticStatement,
        layout: DataLayout,
        region_reg: str,
    ) -> None:
        """ADD/SUBTRACT/MULTIPLY/DIVIDE X TO/FROM/BY/INTO Y [GIVING Z]."""
        ctx = self._ctx
        if stmt.giving:
            self._lower_arithmetic_giving(stmt, layout, region_reg)
            return

        target_ref = ctx.resolve_field_ref(stmt.target, layout, region_reg)

        if ctx.has_field(stmt.source, layout):
            source_ref = ctx.resolve_field_ref(stmt.source, layout, region_reg)
            src_decoded = ctx.emit_decode_field(
                region_reg, source_ref.fl, source_ref.offset_reg
            )
        else:
            src_decoded = ctx.const_to_reg(float(stmt.source))

        tgt_decoded = ctx.emit_decode_field(
            region_reg, target_ref.fl, target_ref.offset_reg
        )

        op = _ARITHMETIC_OPS[stmt.op]
        result_reg = ctx.fresh_reg()
        ctx.emit(
            Opcode.BINOP,
            result_reg=result_reg,
            operands=[op, tgt_decoded, src_decoded],
        )

        result_str_reg = ctx.emit_to_string(result_reg)
        ctx.emit_encode_and_write(
            region_reg, target_ref.fl, result_str_reg, target_ref.offset_reg
        )

    def _lower_arithmetic_giving(
        self,
        stmt: ArithmeticStatement,
        layout: DataLayout,
        region_reg: str,
    ) -> None:
        """MULTIPLY/DIVIDE X BY/INTO Y GIVING Z."""
        ctx = self._ctx

        def _decode_operand(name: str) -> str:
            if ctx.has_field(name, layout):
                ref = ctx.resolve_field_ref(name, layout, region_reg)
                return ctx.emit_decode_field(region_reg, ref.fl, ref.offset_reg)
            return ctx.const_to_reg(float(name))

        left_reg = _decode_operand(stmt.source)
        right_reg = _decode_operand(stmt.target)

        op = _ARITHMETIC_OPS[stmt.op]
        result_reg = ctx.fresh_reg()
        ctx.emit(
            Opcode.BINOP,
            result_reg=result_reg,
            operands=[op, left_reg, right_reg],
        )

        for giving_name in stmt.giving:
            giving_ref = ctx.resolve_field_ref(giving_name, layout, region_reg)
            result_str_reg = ctx.emit_to_string(result_reg)
            ctx.emit_encode_and_write(
                region_reg, giving_ref.fl, result_str_reg, giving_ref.offset_reg
            )

    def _lower_compute(
        self,
        stmt: ComputeStatement,
        layout: DataLayout,
        region_reg: str,
    ) -> None:
        """COMPUTE target(s) = arithmetic-expression."""
        ctx = self._ctx
        expr_tree = parse_expression(stmt.expression)
        result_reg = self._lower_expr_node(expr_tree, layout, region_reg)

        result_str_reg = ctx.emit_to_string(result_reg)
        for target_name in stmt.targets:
            if not ctx.has_field(target_name, layout):
                logger.warning("COMPUTE target %s not found in layout", target_name)
                continue
            target_ref = ctx.resolve_field_ref(target_name, layout, region_reg)
            ctx.emit_encode_and_write(
                region_reg, target_ref.fl, result_str_reg, target_ref.offset_reg
            )

    def _lower_expr_node(
        self,
        node: ExprNode,
        layout: DataLayout,
        region_reg: str,
    ) -> str:
        """Walk an expression tree node and emit IR. Returns result register."""
        ctx = self._ctx
        if isinstance(node, LiteralNode):
            return ctx.const_to_reg(ctx.parse_literal(node.value))
        if isinstance(node, FieldRefNode):
            if ctx.has_field(node.name, layout):
                ref = ctx.resolve_field_ref(node.name, layout, region_reg)
                return ctx.emit_decode_field(region_reg, ref.fl, ref.offset_reg)
            return ctx.const_to_reg(ctx.parse_literal(node.name))
        if isinstance(node, BinOpNode):
            left_reg = self._lower_expr_node(node.left, layout, region_reg)
            right_reg = self._lower_expr_node(node.right, layout, region_reg)
            result_reg = ctx.fresh_reg()
            ctx.emit(
                Opcode.BINOP,
                result_reg=result_reg,
                operands=[node.op, left_reg, right_reg],
            )
            return result_reg
        logger.warning("Unknown expression node type: %s", type(node).__name__)
        return ctx.const_to_reg(0)

    # ── IF ─────────────────────────────────────────────────────────

    def _lower_if(
        self,
        stmt: IfStatement,
        layout: DataLayout,
        region_reg: str,
    ) -> None:
        """IF condition ... [ELSE ...] END-IF."""
        ctx = self._ctx
        cond_reg = self._lower_condition(stmt.condition, layout, region_reg)
        true_label = ctx.fresh_label("if_true")
        false_label = ctx.fresh_label("if_false")
        end_label = ctx.fresh_label("if_end")

        ctx.emit(
            Opcode.BRANCH_IF,
            operands=[cond_reg],
            label=f"{true_label},{false_label}",
        )

        ctx.emit(Opcode.LABEL, label=true_label)
        for child in stmt.children:
            self._lower_statement(child, layout, region_reg)
        ctx.emit(Opcode.BRANCH, label=end_label)

        ctx.emit(Opcode.LABEL, label=false_label)
        for child in stmt.else_children:
            self._lower_statement(child, layout, region_reg)
        ctx.emit(Opcode.BRANCH, label=end_label)

        ctx.emit(Opcode.LABEL, label=end_label)

    # ── PERFORM ────────────────────────────────────────────────────

    def _lower_perform(
        self,
        stmt: PerformStatement,
        layout: DataLayout,
        region_reg: str,
    ) -> None:
        """PERFORM paragraph-name [THRU paragraph-name] [TIMES|UNTIL|VARYING]."""
        if stmt.children and stmt.spec is None:
            for child in stmt.children:
                self._lower_statement(child, layout, region_reg)
            return

        if stmt.target and stmt.spec is None:
            self._emit_perform_branch(stmt, layout, region_reg)
            return

        if isinstance(stmt.spec, PerformTimesSpec):
            self._lower_perform_times(stmt, layout, region_reg)
        elif isinstance(stmt.spec, PerformUntilSpec):
            self._lower_perform_until(stmt, layout, region_reg)
        elif isinstance(stmt.spec, PerformVaryingSpec):
            self._lower_perform_varying(stmt, layout, region_reg)
        else:
            logger.warning("PERFORM with unknown spec: %s", stmt.spec)

    def _resolve_perform_target(self, stmt: PerformStatement) -> tuple[str, str]:
        """Resolve branch-target label and continuation-key label for PERFORM."""
        target = stmt.target
        section_paras = self._ctx.section_paragraphs

        if target in section_paras:
            branch_label = f"section_{target}"
            thru = stmt.thru
            if thru and thru in section_paras:
                continuation_key = f"section_{thru}_end"
            else:
                continuation_key = f"section_{target}_end"
            return branch_label, continuation_key

        thru_name = stmt.thru if stmt.thru else target
        branch_label = f"para_{target}"
        continuation_key = f"para_{thru_name}_end"
        return branch_label, continuation_key

    def _emit_perform_branch(
        self,
        stmt: PerformStatement,
        layout: DataLayout,
        region_reg: str,
    ) -> None:
        """Emit SET_CONTINUATION + BRANCH + return LABEL for a simple procedure PERFORM."""
        ctx = self._ctx
        branch_label, continuation_key = self._resolve_perform_target(stmt)
        return_label = ctx.fresh_label("perform_return")
        ctx.emit(
            Opcode.SET_CONTINUATION,
            operands=[continuation_key, return_label],
        )
        ctx.emit(Opcode.BRANCH, label=branch_label)
        ctx.emit(Opcode.LABEL, label=return_label)

    def _lower_perform_body(
        self,
        stmt: PerformStatement,
        layout: DataLayout,
        region_reg: str,
    ) -> None:
        """Emit the body of a PERFORM loop — inline children or procedure branch."""
        if stmt.children:
            for child in stmt.children:
                self._lower_statement(child, layout, region_reg)
        elif stmt.target:
            self._emit_perform_branch(stmt, layout, region_reg)

    def _lower_perform_times(
        self,
        stmt: PerformStatement,
        layout: DataLayout,
        region_reg: str,
    ) -> None:
        """PERFORM ... TIMES — counter-based loop."""
        ctx = self._ctx
        spec = stmt.spec
        assert isinstance(spec, PerformTimesSpec)

        counter_var = ctx.fresh_label("__perform_ctr")
        loop_label = ctx.fresh_label("perform_times_loop")
        body_label = ctx.fresh_label("perform_times_body")
        exit_label = ctx.fresh_label("perform_times_exit")

        zero_reg = ctx.const_to_reg(0)
        ctx.emit(Opcode.STORE_VAR, operands=[counter_var, zero_reg])

        if ctx.has_field(spec.times, layout):
            times_ref = ctx.resolve_field_ref(spec.times, layout, region_reg)
            times_reg = ctx.emit_decode_field(
                region_reg, times_ref.fl, times_ref.offset_reg
            )
        else:
            times_reg = ctx.const_to_reg(ctx.parse_literal(spec.times))

        ctx.emit(Opcode.LABEL, label=loop_label)
        ctr_reg = ctx.fresh_reg()
        ctx.emit(Opcode.LOAD_VAR, result_reg=ctr_reg, operands=[counter_var])
        cond_reg = ctx.fresh_reg()
        ctx.emit(
            Opcode.BINOP,
            result_reg=cond_reg,
            operands=[">=", ctr_reg, times_reg],
        )
        ctx.emit(
            Opcode.BRANCH_IF,
            operands=[cond_reg],
            label=f"{exit_label},{body_label}",
        )

        ctx.emit(Opcode.LABEL, label=body_label)
        self._lower_perform_body(stmt, layout, region_reg)

        ctr_reg2 = ctx.fresh_reg()
        ctx.emit(Opcode.LOAD_VAR, result_reg=ctr_reg2, operands=[counter_var])
        one_reg = ctx.const_to_reg(1)
        inc_reg = ctx.fresh_reg()
        ctx.emit(Opcode.BINOP, result_reg=inc_reg, operands=["+", ctr_reg2, one_reg])
        ctx.emit(Opcode.STORE_VAR, operands=[counter_var, inc_reg])
        ctx.emit(Opcode.BRANCH, label=loop_label)

        ctx.emit(Opcode.LABEL, label=exit_label)

    def _lower_perform_until(
        self,
        stmt: PerformStatement,
        layout: DataLayout,
        region_reg: str,
    ) -> None:
        """PERFORM ... UNTIL — condition-based loop."""
        ctx = self._ctx
        spec = stmt.spec
        assert isinstance(spec, PerformUntilSpec)

        loop_label = ctx.fresh_label("perform_until_loop")
        body_label = ctx.fresh_label("perform_until_body")
        exit_label = ctx.fresh_label("perform_until_exit")

        if spec.test_before:
            ctx.emit(Opcode.LABEL, label=loop_label)
            cond_reg = self._lower_condition(spec.condition, layout, region_reg)
            ctx.emit(
                Opcode.BRANCH_IF,
                operands=[cond_reg],
                label=f"{exit_label},{body_label}",
            )
            ctx.emit(Opcode.LABEL, label=body_label)
            self._lower_perform_body(stmt, layout, region_reg)
            ctx.emit(Opcode.BRANCH, label=loop_label)
            ctx.emit(Opcode.LABEL, label=exit_label)
        else:
            ctx.emit(Opcode.LABEL, label=loop_label)
            self._lower_perform_body(stmt, layout, region_reg)
            cond_reg = self._lower_condition(spec.condition, layout, region_reg)
            ctx.emit(
                Opcode.BRANCH_IF,
                operands=[cond_reg],
                label=f"{exit_label},{loop_label}",
            )
            ctx.emit(Opcode.LABEL, label=exit_label)

    def _lower_perform_varying(
        self,
        stmt: PerformStatement,
        layout: DataLayout,
        region_reg: str,
    ) -> None:
        """PERFORM ... VARYING — counter variable loop with FROM/BY/UNTIL."""
        ctx = self._ctx
        spec = stmt.spec
        assert isinstance(spec, PerformVaryingSpec)

        loop_label = ctx.fresh_label("perform_varying_loop")
        body_label = ctx.fresh_label("perform_varying_body")
        exit_label = ctx.fresh_label("perform_varying_exit")

        if ctx.has_field(spec.varying_var, layout):
            varying_ref = ctx.resolve_field_ref(spec.varying_var, layout, region_reg)
            from_str_reg = ctx.const_to_reg(str(spec.varying_from))
            ctx.emit_encode_and_write(
                region_reg, varying_ref.fl, from_str_reg, varying_ref.offset_reg
            )

        if spec.test_before:
            ctx.emit(Opcode.LABEL, label=loop_label)
            cond_reg = self._lower_condition(spec.condition, layout, region_reg)
            ctx.emit(
                Opcode.BRANCH_IF,
                operands=[cond_reg],
                label=f"{exit_label},{body_label}",
            )
            ctx.emit(Opcode.LABEL, label=body_label)
            self._lower_perform_body(stmt, layout, region_reg)
            self._emit_varying_increment(spec, layout, region_reg)
            ctx.emit(Opcode.BRANCH, label=loop_label)
            ctx.emit(Opcode.LABEL, label=exit_label)
        else:
            ctx.emit(Opcode.LABEL, label=loop_label)
            self._lower_perform_body(stmt, layout, region_reg)
            self._emit_varying_increment(spec, layout, region_reg)
            cond_reg = self._lower_condition(spec.condition, layout, region_reg)
            ctx.emit(
                Opcode.BRANCH_IF,
                operands=[cond_reg],
                label=f"{exit_label},{loop_label}",
            )
            ctx.emit(Opcode.LABEL, label=exit_label)

    def _emit_varying_increment(
        self,
        spec: PerformVaryingSpec,
        layout: DataLayout,
        region_reg: str,
    ) -> None:
        """Emit IR to increment the VARYING variable by the BY value."""
        ctx = self._ctx
        if not ctx.has_field(spec.varying_var, layout):
            logger.warning("VARYING variable %s not found in layout", spec.varying_var)
            return

        varying_ref = ctx.resolve_field_ref(spec.varying_var, layout, region_reg)
        val_reg = ctx.emit_decode_field(
            region_reg, varying_ref.fl, varying_ref.offset_reg
        )

        by_reg = ctx.const_to_reg(ctx.parse_literal(spec.varying_by))
        new_val_reg = ctx.fresh_reg()
        ctx.emit(
            Opcode.BINOP,
            result_reg=new_val_reg,
            operands=["+", val_reg, by_reg],
        )

        new_str_reg = ctx.emit_to_string(new_val_reg)
        ctx.emit_encode_and_write(
            region_reg, varying_ref.fl, new_str_reg, varying_ref.offset_reg
        )

    # ── DISPLAY, STOP RUN, GO TO ──────────────────────────────────

    def _lower_display(
        self,
        stmt: DisplayStatement,
        layout: DataLayout,
        region_reg: str,
    ) -> None:
        """DISPLAY field-or-literal."""
        ctx = self._ctx
        operand = stmt.operand

        if isinstance(operand, str) and ctx.has_field(operand, layout):
            ref = ctx.resolve_field_ref(operand, layout, region_reg)
            decoded_reg = ctx.emit_decode_field(region_reg, ref.fl, ref.offset_reg)
            display_reg = ctx.emit_to_string(decoded_reg)
        else:
            display_reg = ctx.const_to_reg(str(operand))

        ctx.emit(
            Opcode.CALL_FUNCTION,
            result_reg=ctx.fresh_reg(),
            operands=["print", display_reg],
        )

    def _lower_stop_run(
        self,
        stmt: StopRunStatement,
        layout: DataLayout,
        region_reg: str,
    ) -> None:
        """STOP RUN."""
        ctx = self._ctx
        zero_reg = ctx.fresh_reg()
        ctx.emit(Opcode.CONST, result_reg=zero_reg, operands=[0])
        ctx.emit(Opcode.RETURN, operands=[zero_reg])

    def _lower_goto(
        self,
        stmt: GotoStatement,
        layout: DataLayout,
        region_reg: str,
    ) -> None:
        """GO TO paragraph-name."""
        self._ctx.emit(Opcode.BRANCH, label=f"para_{stmt.target}")

    # ── EVALUATE ───────────────────────────────────────────────────

    def _lower_evaluate(
        self,
        stmt: EvaluateStatement,
        layout: DataLayout,
        region_reg: str,
    ) -> None:
        """EVALUATE subject WHEN value ..."""
        ctx = self._ctx
        end_label = ctx.fresh_label("eval_end")

        for child in stmt.children:
            if isinstance(child, WhenStatement) and child.condition:
                if stmt.subject:
                    full_condition = f"{stmt.subject} = {child.condition}"
                else:
                    full_condition = child.condition
                cond_reg = self._lower_condition(full_condition, layout, region_reg)
                when_true = ctx.fresh_label("when_true")
                when_false = ctx.fresh_label("when_false")
                ctx.emit(
                    Opcode.BRANCH_IF,
                    operands=[cond_reg],
                    label=f"{when_true},{when_false}",
                )
                ctx.emit(Opcode.LABEL, label=when_true)
                for grandchild in child.children:
                    self._lower_statement(grandchild, layout, region_reg)
                ctx.emit(Opcode.BRANCH, label=end_label)
                ctx.emit(Opcode.LABEL, label=when_false)
            elif isinstance(child, WhenOtherStatement):
                for grandchild in child.children:
                    self._lower_statement(grandchild, layout, region_reg)

        ctx.emit(Opcode.LABEL, label=end_label)

    # ── CONTINUE, EXIT, INITIALIZE, SET ────────────────────────────

    def _lower_continue(
        self,
        stmt: ContinueStatement,
        layout: DataLayout,
        region_reg: str,
    ) -> None:
        """CONTINUE — no-op, emit nothing."""
        pass

    def _lower_exit(
        self,
        stmt: ExitStatement,
        layout: DataLayout,
        region_reg: str,
    ) -> None:
        """EXIT — no-op sentinel, emit nothing."""
        pass

    def _lower_initialize(
        self,
        stmt: InitializeStatement,
        layout: DataLayout,
        region_reg: str,
    ) -> None:
        """INITIALIZE field1 field2 — reset to type-appropriate defaults."""
        ctx = self._ctx
        for operand in stmt.operands:
            if not ctx.has_field(operand, layout):
                logger.warning("INITIALIZE target %s not found in layout", operand)
                continue
            ref = ctx.resolve_field_ref(operand, layout, region_reg)
            td = ref.fl.type_descriptor
            if td.category == CobolDataCategory.ALPHANUMERIC:
                default = " " * td.total_digits
            else:
                default = "0"
            ctx.emit_field_encode(region_reg, ref.fl, default, ref.offset_reg)

    def _lower_set(
        self,
        stmt: SetStatement,
        layout: DataLayout,
        region_reg: str,
    ) -> None:
        """SET target TO value / SET target UP|DOWN BY value."""
        ctx = self._ctx
        if stmt.set_type == "TO":
            value_str = stmt.values[0] if stmt.values else "0"
            for target_name in stmt.targets:
                if not ctx.has_field(target_name, layout):
                    logger.warning("SET target %s not found in layout", target_name)
                    continue
                target_ref = ctx.resolve_field_ref(target_name, layout, region_reg)
                value_str_reg = ctx.const_to_reg(str(value_str))
                ctx.emit_encode_and_write(
                    region_reg, target_ref.fl, value_str_reg, target_ref.offset_reg
                )
        elif stmt.set_type == "BY":
            step_val = stmt.values[0] if stmt.values else "1"
            op = "+" if stmt.by_type == "UP" else "-"
            for target_name in stmt.targets:
                if not ctx.has_field(target_name, layout):
                    logger.warning("SET target %s not found in layout", target_name)
                    continue
                target_ref = ctx.resolve_field_ref(target_name, layout, region_reg)
                tgt_decoded = ctx.emit_decode_field(
                    region_reg, target_ref.fl, target_ref.offset_reg
                )
                step_reg = ctx.const_to_reg(ctx.parse_literal(step_val))
                result_reg = ctx.fresh_reg()
                ctx.emit(
                    Opcode.BINOP,
                    result_reg=result_reg,
                    operands=[op, tgt_decoded, step_reg],
                )
                result_str_reg = ctx.emit_to_string(result_reg)
                ctx.emit_encode_and_write(
                    region_reg, target_ref.fl, result_str_reg, target_ref.offset_reg
                )

    # ── STRING, UNSTRING, INSPECT ─────────────────────────────────

    def _lower_string(
        self,
        stmt: StringStatement,
        layout: DataLayout,
        region_reg: str,
    ) -> None:
        """STRING ... DELIMITED BY ... INTO target."""
        ctx = self._ctx
        part_regs: list[str] = []
        for sending in stmt.sendings:
            if ctx.has_field(sending.value, layout):
                source_ref = ctx.resolve_field_ref(sending.value, layout, region_reg)
                decoded_reg = ctx.emit_decode_field(
                    region_reg, source_ref.fl, source_ref.offset_reg
                )
                src_str_reg = ctx.emit_to_string(decoded_reg)
            else:
                src_str_reg = ctx.const_to_reg(str(sending.value))

            if sending.delimited_by == "SIZE":
                part_regs.append(src_str_reg)
            else:
                delim_reg = ctx.const_to_reg(
                    translate_cobol_figurative(str(sending.delimited_by))
                )
                find_pos = ctx.fresh_reg()
                ctx.emit(
                    Opcode.CALL_FUNCTION,
                    result_reg=find_pos,
                    operands=["__string_find", src_str_reg, delim_reg],
                )
                parts = ctx.fresh_reg()
                ctx.emit(
                    Opcode.CALL_FUNCTION,
                    result_reg=parts,
                    operands=["__string_split", src_str_reg, delim_reg],
                )
                first_part = ctx.fresh_reg()
                ctx.emit(
                    Opcode.CALL_FUNCTION,
                    result_reg=first_part,
                    operands=["__list_get", parts, 0],
                )
                part_regs.append(first_part)

        if not part_regs:
            concat_reg = ctx.const_to_reg("")
        elif len(part_regs) == 1:
            concat_reg = part_regs[0]
        else:
            concat_reg = part_regs[0]
            for next_reg in part_regs[1:]:
                new_concat = ctx.fresh_reg()
                ctx.emit(
                    Opcode.CALL_FUNCTION,
                    result_reg=new_concat,
                    operands=["__string_concat_pair", concat_reg, next_reg],
                )
                concat_reg = new_concat

        if stmt.into and ctx.has_field(stmt.into, layout):
            target_ref = ctx.resolve_field_ref(stmt.into, layout, region_reg)
            ctx.emit_encode_and_write(
                region_reg, target_ref.fl, concat_reg, target_ref.offset_reg
            )
        else:
            logger.warning("STRING INTO target %s not found in layout", stmt.into)

    def _lower_unstring(
        self,
        stmt: UnstringStatement,
        layout: DataLayout,
        region_reg: str,
    ) -> None:
        """UNSTRING source DELIMITED BY ... INTO targets."""
        ctx = self._ctx
        if ctx.has_field(stmt.source, layout):
            source_ref = ctx.resolve_field_ref(stmt.source, layout, region_reg)
            decoded_reg = ctx.emit_decode_field(
                region_reg, source_ref.fl, source_ref.offset_reg
            )
            src_str_reg = ctx.emit_to_string(decoded_reg)
        else:
            src_str_reg = ctx.const_to_reg(str(stmt.source))

        delimiter = translate_cobol_figurative(str(stmt.delimited_by))
        delim_reg = ctx.const_to_reg(delimiter)
        ir = build_string_split_ir(f"unstring_split_{stmt.source}")
        parts_reg = ctx.inline_ir(
            ir, {"%p_source": src_str_reg, "%p_delimiter": delim_reg}
        )

        for i, target_name in enumerate(stmt.into):
            if not ctx.has_field(target_name, layout):
                logger.warning(
                    "UNSTRING INTO target %s not found in layout", target_name
                )
                continue
            target_ref = ctx.resolve_field_ref(target_name, layout, region_reg)
            idx_reg = ctx.const_to_reg(i)
            part_reg = ctx.fresh_reg()
            ctx.emit(
                Opcode.CALL_FUNCTION,
                result_reg=part_reg,
                operands=["__list_get", parts_reg, idx_reg],
            )
            ctx.emit_encode_and_write(
                region_reg, target_ref.fl, part_reg, target_ref.offset_reg
            )

    def _lower_inspect(
        self,
        stmt: InspectStatement,
        layout: DataLayout,
        region_reg: str,
    ) -> None:
        """INSPECT source TALLYING|REPLACING ..."""
        ctx = self._ctx
        if not ctx.has_field(stmt.source, layout):
            logger.warning("INSPECT source %s not found in layout", stmt.source)
            return
        source_ref = ctx.resolve_field_ref(stmt.source, layout, region_reg)
        source_fl = source_ref.fl
        decoded_reg = ctx.emit_decode_field(
            region_reg, source_fl, source_ref.offset_reg
        )
        src_str_reg = ctx.emit_to_string(decoded_reg)

        if stmt.inspect_type == "TALLYING":
            self._lower_inspect_tallying(stmt, src_str_reg, layout, region_reg)
        elif stmt.inspect_type == "REPLACING":
            self._lower_inspect_replacing(
                stmt, src_str_reg, source_fl, layout, region_reg
            )

    def _lower_inspect_tallying(
        self,
        stmt: InspectStatement,
        src_str_reg: str,
        layout: DataLayout,
        region_reg: str,
    ) -> None:
        """INSPECT TALLYING — count pattern occurrences and write to tally target."""
        ctx = self._ctx
        total_count_reg = ctx.const_to_reg(0)

        for tally_for in stmt.tallying_for:
            pattern_reg = ctx.const_to_reg(str(tally_for.pattern))
            mode_reg = ctx.const_to_reg(tally_for.mode.lower())
            ir = build_inspect_tally_ir(f"inspect_tally_{stmt.source}")
            count_reg = ctx.inline_ir(
                ir,
                {
                    "%p_source": src_str_reg,
                    "%p_pattern": pattern_reg,
                    "%p_mode": mode_reg,
                },
            )
            new_total = ctx.fresh_reg()
            ctx.emit(
                Opcode.BINOP,
                result_reg=new_total,
                operands=["+", total_count_reg, count_reg],
            )
            total_count_reg = new_total

        if stmt.tallying_target and ctx.has_field(stmt.tallying_target, layout):
            tally_ref = ctx.resolve_field_ref(stmt.tallying_target, layout, region_reg)
            count_str_reg = ctx.emit_to_string(total_count_reg)
            ctx.emit_encode_and_write(
                region_reg, tally_ref.fl, count_str_reg, tally_ref.offset_reg
            )

    def _lower_inspect_replacing(
        self,
        stmt: InspectStatement,
        src_str_reg: str,
        source_fl: FieldLayout,
        layout: DataLayout,
        region_reg: str,
    ) -> None:
        """INSPECT REPLACING — apply replacements and write back."""
        ctx = self._ctx
        current_str_reg = src_str_reg

        for replacing in stmt.replacings:
            from_reg = ctx.const_to_reg(str(replacing.from_pattern))
            to_reg = ctx.const_to_reg(str(replacing.to_pattern))
            mode_reg = ctx.const_to_reg(replacing.mode.lower())
            ir = build_inspect_replace_ir(f"inspect_replace_{stmt.source}")
            new_str_reg = ctx.inline_ir(
                ir,
                {
                    "%p_source": current_str_reg,
                    "%p_from": from_reg,
                    "%p_to": to_reg,
                    "%p_mode": mode_reg,
                },
            )
            current_str_reg = new_str_reg

        ctx.emit_encode_and_write(region_reg, source_fl, current_str_reg)

    # ── SEARCH ────────────────────────────────────────────────────

    def _lower_search(
        self,
        stmt: SearchStatement,
        layout: DataLayout,
        region_reg: str,
    ) -> None:
        """SEARCH table VARYING index WHEN cond ... AT END ..."""
        ctx = self._ctx
        loop_label = ctx.fresh_label("search_loop")
        end_label = ctx.fresh_label("search_end")
        at_end_label = ctx.fresh_label("search_at_end")
        increment_label = ctx.fresh_label("search_incr")

        max_iterations = 256
        counter_var = ctx.fresh_label("__search_ctr")
        zero_reg = ctx.const_to_reg(0)
        ctx.emit(Opcode.STORE_VAR, operands=[counter_var, zero_reg])

        max_reg = ctx.const_to_reg(max_iterations)

        ctx.emit(Opcode.LABEL, label=loop_label)

        ctr_reg = ctx.fresh_reg()
        ctx.emit(Opcode.LOAD_VAR, result_reg=ctr_reg, operands=[counter_var])
        bound_cond = ctx.fresh_reg()
        ctx.emit(
            Opcode.BINOP,
            result_reg=bound_cond,
            operands=[">=", ctr_reg, max_reg],
        )
        body_label = ctx.fresh_label("search_body")
        ctx.emit(
            Opcode.BRANCH_IF,
            operands=[bound_cond],
            label=f"{at_end_label},{body_label}",
        )

        ctx.emit(Opcode.LABEL, label=body_label)
        for when in stmt.whens:
            if not when.condition:
                continue
            cond_reg = self._lower_condition(when.condition, layout, region_reg)
            when_true = ctx.fresh_label("search_when_true")
            when_next = ctx.fresh_label("search_when_next")
            ctx.emit(
                Opcode.BRANCH_IF,
                operands=[cond_reg],
                label=f"{when_true},{when_next}",
            )
            ctx.emit(Opcode.LABEL, label=when_true)
            for child in when.children:
                self._lower_statement(child, layout, region_reg)
            ctx.emit(Opcode.BRANCH, label=end_label)
            ctx.emit(Opcode.LABEL, label=when_next)

        ctx.emit(Opcode.BRANCH, label=increment_label)
        ctx.emit(Opcode.LABEL, label=increment_label)

        if stmt.varying and ctx.has_field(stmt.varying, layout):
            varying_ref = ctx.resolve_field_ref(stmt.varying, layout, region_reg)
            decoded_reg = ctx.emit_decode_field(
                region_reg, varying_ref.fl, varying_ref.offset_reg
            )
            one_reg = ctx.const_to_reg(1)
            inc_reg = ctx.fresh_reg()
            ctx.emit(
                Opcode.BINOP, result_reg=inc_reg, operands=["+", decoded_reg, one_reg]
            )
            str_reg = ctx.emit_to_string(inc_reg)
            ctx.emit_encode_and_write(
                region_reg, varying_ref.fl, str_reg, varying_ref.offset_reg
            )

        ctr_reg2 = ctx.fresh_reg()
        ctx.emit(Opcode.LOAD_VAR, result_reg=ctr_reg2, operands=[counter_var])
        one_ctr = ctx.const_to_reg(1)
        inc_ctr = ctx.fresh_reg()
        ctx.emit(Opcode.BINOP, result_reg=inc_ctr, operands=["+", ctr_reg2, one_ctr])
        ctx.emit(Opcode.STORE_VAR, operands=[counter_var, inc_ctr])
        ctx.emit(Opcode.BRANCH, label=loop_label)

        ctx.emit(Opcode.LABEL, label=at_end_label)
        for child in stmt.at_end:
            self._lower_statement(child, layout, region_reg)

        ctx.emit(Opcode.LABEL, label=end_label)

    # ── CALL, ALTER, ENTRY, CANCEL ────────────────────────────────

    def _lower_call(
        self,
        stmt: CallStatement,
        layout: DataLayout,
        region_reg: str,
    ) -> None:
        """CALL 'program' USING params — symbolic subprogram invocation."""
        ctx = self._ctx
        arg_regs: list[str] = []
        for param in stmt.using:
            if ctx.has_field(param.name, layout):
                ref = ctx.resolve_field_ref(param.name, layout, region_reg)
                arg_regs.append(
                    ctx.emit_decode_field(region_reg, ref.fl, ref.offset_reg)
                )
            else:
                arg_regs.append(ctx.const_to_reg(param.name))

        result_reg = ctx.fresh_reg()
        ctx.emit(
            Opcode.CALL_FUNCTION,
            result_reg=result_reg,
            operands=[stmt.program, *arg_regs],
        )

        if stmt.giving and ctx.has_field(stmt.giving, layout):
            giving_ref = ctx.resolve_field_ref(stmt.giving, layout, region_reg)
            str_reg = ctx.emit_to_string(result_reg)
            ctx.emit_encode_and_write(
                region_reg, giving_ref.fl, str_reg, giving_ref.offset_reg
            )

        logger.info("CALL %s with %d params (symbolic)", stmt.program, len(stmt.using))

    def _lower_alter(
        self,
        stmt: AlterStatement,
        layout: DataLayout,
        region_reg: str,
    ) -> None:
        """ALTER para-1 TO PROCEED TO para-2."""
        ctx = self._ctx
        for pt in stmt.proceed_tos:
            target_reg = ctx.const_to_reg(f"para_{pt.target}")
            ctx.emit(Opcode.STORE_VAR, operands=[f"__alter_{pt.source}", target_reg])
            logger.info("ALTER %s TO PROCEED TO %s", pt.source, pt.target)

    def _lower_entry(
        self,
        stmt: EntryStatement,
        layout: DataLayout,
        region_reg: str,
    ) -> None:
        """ENTRY 'name' — alternate entry point for a subprogram."""
        if stmt.entry_name:
            self._ctx.emit(Opcode.LABEL, label=f"entry_{stmt.entry_name}")
            logger.info("ENTRY %s", stmt.entry_name)

    def _lower_cancel(
        self,
        stmt: CancelStatement,
        layout: DataLayout,
        region_reg: str,
    ) -> None:
        """CANCEL program — no-op for static analysis."""
        for prog in stmt.programs:
            logger.info("CANCEL %s (no-op for static analysis)", prog)

    # ── I/O Statements ───────────────────────────────────────────

    def _lower_accept(
        self,
        stmt: AcceptStatement,
        layout: DataLayout,
        region_reg: str,
    ) -> None:
        """ACCEPT target [FROM device] — read input via __cobol_accept."""
        ctx = self._ctx
        device_reg = ctx.const_to_reg(stmt.from_device)
        result_reg = ctx.fresh_reg()
        ctx.emit(
            Opcode.CALL_FUNCTION,
            result_reg=result_reg,
            operands=["__cobol_accept", device_reg],
        )
        if stmt.target and ctx.has_field(stmt.target, layout):
            target_ref = ctx.resolve_field_ref(stmt.target, layout, region_reg)
            str_reg = ctx.emit_to_string(result_reg)
            ctx.emit_encode_and_write(
                region_reg, target_ref.fl, str_reg, target_ref.offset_reg
            )
        logger.info("ACCEPT %s FROM %s", stmt.target, stmt.from_device)

    def _lower_open(
        self,
        stmt: OpenStatement,
        layout: DataLayout,
        region_reg: str,
    ) -> None:
        """OPEN mode file1 file2 ... — open files via __cobol_open_file."""
        ctx = self._ctx
        for filename in stmt.files:
            fn_reg = ctx.const_to_reg(filename)
            mode_reg = ctx.const_to_reg(stmt.mode)
            result_reg = ctx.fresh_reg()
            ctx.emit(
                Opcode.CALL_FUNCTION,
                result_reg=result_reg,
                operands=["__cobol_open_file", fn_reg, mode_reg],
            )
            logger.info("OPEN %s %s", stmt.mode, filename)

    def _lower_close(
        self,
        stmt: CloseStatement,
        layout: DataLayout,
        region_reg: str,
    ) -> None:
        """CLOSE file1 file2 ... — close files via __cobol_close_file."""
        ctx = self._ctx
        for filename in stmt.files:
            fn_reg = ctx.const_to_reg(filename)
            result_reg = ctx.fresh_reg()
            ctx.emit(
                Opcode.CALL_FUNCTION,
                result_reg=result_reg,
                operands=["__cobol_close_file", fn_reg],
            )
            logger.info("CLOSE %s", filename)

    def _lower_read(
        self,
        stmt: ReadStatement,
        layout: DataLayout,
        region_reg: str,
    ) -> None:
        """READ file-name [INTO target] — read record via __cobol_read_record."""
        ctx = self._ctx
        fn_reg = ctx.const_to_reg(stmt.file_name)
        result_reg = ctx.fresh_reg()
        ctx.emit(
            Opcode.CALL_FUNCTION,
            result_reg=result_reg,
            operands=["__cobol_read_record", fn_reg],
        )
        if stmt.into and ctx.has_field(stmt.into, layout):
            target_ref = ctx.resolve_field_ref(stmt.into, layout, region_reg)
            str_reg = ctx.emit_to_string(result_reg)
            ctx.emit_encode_and_write(
                region_reg, target_ref.fl, str_reg, target_ref.offset_reg
            )
        logger.info("READ %s INTO %s", stmt.file_name, stmt.into or "(none)")

    def _lower_write(
        self,
        stmt: WriteStatement,
        layout: DataLayout,
        region_reg: str,
    ) -> None:
        """WRITE record-name [FROM field] — write record via __cobol_write_record."""
        ctx = self._ctx
        if stmt.from_field and ctx.has_field(stmt.from_field, layout):
            from_ref = ctx.resolve_field_ref(stmt.from_field, layout, region_reg)
            decoded_reg = ctx.emit_decode_field(
                region_reg, from_ref.fl, from_ref.offset_reg
            )
            data_reg = ctx.emit_to_string(decoded_reg)
        else:
            data_reg = ctx.const_to_reg(stmt.from_field or stmt.record_name)

        fn_reg = ctx.const_to_reg(stmt.record_name)
        result_reg = ctx.fresh_reg()
        ctx.emit(
            Opcode.CALL_FUNCTION,
            result_reg=result_reg,
            operands=["__cobol_write_record", fn_reg, data_reg],
        )
        logger.info("WRITE %s FROM %s", stmt.record_name, stmt.from_field or "(none)")

    def _lower_rewrite(
        self,
        stmt: RewriteStatement,
        layout: DataLayout,
        region_reg: str,
    ) -> None:
        """REWRITE record-name [FROM field] — rewrite record via __cobol_rewrite_record."""
        ctx = self._ctx
        if stmt.from_field and ctx.has_field(stmt.from_field, layout):
            from_ref = ctx.resolve_field_ref(stmt.from_field, layout, region_reg)
            decoded_reg = ctx.emit_decode_field(
                region_reg, from_ref.fl, from_ref.offset_reg
            )
            data_reg = ctx.emit_to_string(decoded_reg)
        else:
            data_reg = ctx.const_to_reg(stmt.from_field or stmt.record_name)

        fn_reg = ctx.const_to_reg(stmt.record_name)
        result_reg = ctx.fresh_reg()
        ctx.emit(
            Opcode.CALL_FUNCTION,
            result_reg=result_reg,
            operands=["__cobol_rewrite_record", fn_reg, data_reg],
        )
        logger.info("REWRITE %s FROM %s", stmt.record_name, stmt.from_field or "(none)")

    def _lower_start(
        self,
        stmt: StartStatement,
        layout: DataLayout,
        region_reg: str,
    ) -> None:
        """START file-name [KEY ...] — position file via __cobol_start_file."""
        ctx = self._ctx
        fn_reg = ctx.const_to_reg(stmt.file_name)
        key_reg = ctx.const_to_reg(stmt.key or "")
        result_reg = ctx.fresh_reg()
        ctx.emit(
            Opcode.CALL_FUNCTION,
            result_reg=result_reg,
            operands=["__cobol_start_file", fn_reg, key_reg],
        )
        logger.info("START %s KEY %s", stmt.file_name, stmt.key or "(none)")

    def _lower_delete(
        self,
        stmt: DeleteStatement,
        layout: DataLayout,
        region_reg: str,
    ) -> None:
        """DELETE file-name — delete record via __cobol_delete_record."""
        ctx = self._ctx
        fn_reg = ctx.const_to_reg(stmt.file_name)
        result_reg = ctx.fresh_reg()
        ctx.emit(
            Opcode.CALL_FUNCTION,
            result_reg=result_reg,
            operands=["__cobol_delete_record", fn_reg],
        )
        logger.info("DELETE %s", stmt.file_name)

    # ── Condition Lowering ─────────────────────────────────────────

    def _lower_condition(
        self,
        condition: str,
        layout: DataLayout,
        region_reg: str,
    ) -> str:
        """Lower a simple condition string to a register holding a boolean."""
        ctx = self._ctx
        parts = condition.split()
        if len(parts) >= 3:
            left_name = parts[0]
            if parts[1] == "NOT" and len(parts) >= 4:
                op = "!="
                right_val = parts[3]
            else:
                op_map = {">": ">", "<": "<", ">=": ">=", "<=": "<=", "=": "=="}
                op = op_map.get(parts[1], "==")
                right_val = parts[2]

            if ctx.has_field(left_name, layout):
                left_ref = ctx.resolve_field_ref(left_name, layout, region_reg)
                left_reg = ctx.emit_decode_field(
                    region_reg, left_ref.fl, left_ref.offset_reg
                )
            else:
                left_reg = ctx.const_to_reg(ctx.parse_literal(left_name))

            right_parsed = ctx.parse_literal(right_val)
            if isinstance(right_parsed, str) and ctx.has_field(right_parsed, layout):
                right_ref = ctx.resolve_field_ref(right_parsed, layout, region_reg)
                right_reg = ctx.emit_decode_field(
                    region_reg, right_ref.fl, right_ref.offset_reg
                )
            else:
                right_reg = ctx.const_to_reg(right_parsed)

            result = ctx.fresh_reg()
            ctx.emit(
                Opcode.BINOP,
                result_reg=result,
                operands=[op, left_reg, right_reg],
            )
            return result

        result = ctx.fresh_reg()
        ctx.emit(Opcode.CONST, result_reg=result, operands=[True])
        return result
