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
    ArithmeticStatement,
    CobolStatementType,
    ComputeStatement,
    ContinueStatement,
    DisplayStatement,
    EvaluateStatement,
    ExitStatement,
    GotoStatement,
    IfStatement,
    InitializeStatement,
    InspectStatement,
    MoveStatement,
    PerformStatement,
    PerformTimesSpec,
    PerformUntilSpec,
    PerformVaryingSpec,
    SetStatement,
    StopRunStatement,
    StringStatement,
    UnstringStatement,
    WhenOtherStatement,
    WhenStatement,
)
from interpreter.cobol.cobol_types import CobolDataCategory
from interpreter.cobol.data_layout import DataLayout, FieldLayout, build_data_layout
from interpreter.cobol.ir_encoders import (
    build_decode_alphanumeric_ir,
    build_decode_comp3_ir,
    build_decode_zoned_ir,
    build_encode_alphanumeric_ir,
    build_encode_comp3_ir,
    build_encode_zoned_ir,
    build_inspect_replace_ir,
    build_inspect_tally_ir,
    build_string_split_ir,
)
from interpreter.cobol.data_filters import align_decimal, left_adjust
from interpreter.frontend import Frontend
from interpreter.ir import IRInstruction, Opcode

logger = logging.getLogger(__name__)

_ARITHMETIC_OPS = {
    "ADD": "+",
    "SUBTRACT": "-",
    "MULTIPLY": "*",
    "DIVIDE": "/",
}


class CobolFrontend(Frontend):
    """Lowers COBOL ASG (from ProLeap bridge) to RedDragon IR.

    Architecture: The ProLeap bridge (separate Java repo) parses COBOL
    source and emits JSON ASG. This frontend consumes that ASG and
    produces IR instructions.
    """

    def __init__(self, cobol_parser: Any):
        self._parser = cobol_parser
        self._reg_counter = 0
        self._label_counter = 0
        self._instructions: list[IRInstruction] = []

    def lower(self, tree: Any, source: bytes) -> list[IRInstruction]:
        """Lower COBOL source to IR via the ProLeap bridge.

        Args:
            tree: Unused (COBOL does not use tree-sitter). Pass None.
            source: Raw COBOL source bytes.

        Returns:
            List of IR instructions.
        """
        self._reg_counter = 0
        self._label_counter = 0
        self._instructions = []

        asg = self._parser.parse(source)
        layout = build_data_layout(asg.data_fields)

        self._emit(Opcode.LABEL, label="entry")

        region_reg = self._lower_data_division(layout)
        self._lower_procedure_division(asg, layout, region_reg)

        logger.info(
            "COBOL frontend produced %d IR instructions", len(self._instructions)
        )
        return self._instructions

    def _fresh_reg(self) -> str:
        name = f"%r{self._reg_counter}"
        self._reg_counter += 1
        return name

    def _fresh_label(self, prefix: str) -> str:
        name = f"{prefix}_{self._label_counter}"
        self._label_counter += 1
        return name

    def _emit(
        self,
        opcode: Opcode,
        *,
        result_reg: str = "",
        operands: list[Any] = [],
        label: str = "",
    ) -> None:
        inst = IRInstruction(
            opcode=opcode,
            result_reg=result_reg or None,
            operands=operands,
            label=label or None,
        )
        self._instructions.append(inst)

    # ── DATA DIVISION ──────────────────────────────────────────────

    def _lower_data_division(self, layout: DataLayout) -> str:
        """Emit ALLOC_REGION + initial VALUE encodings. Returns region register."""
        region_reg = self._fresh_reg()
        self._emit(
            Opcode.ALLOC_REGION,
            result_reg=region_reg,
            operands=[layout.total_bytes],
        )

        fields_with_values = [fl for fl in layout.fields.values() if fl.value]
        for fl in fields_with_values:
            self._emit_field_encode(region_reg, fl, fl.value)

        logger.debug(
            "Data Division: allocated %d bytes, initialized %d fields",
            layout.total_bytes,
            len(fields_with_values),
        )
        return region_reg

    def _emit_field_encode(self, region_reg: str, fl: FieldLayout, value: str) -> None:
        """Emit IR to encode a value and write it to the region."""
        encoded_reg = self._emit_encode_value(fl, value)
        offset_reg = self._fresh_reg()
        self._emit(Opcode.CONST, result_reg=offset_reg, operands=[fl.offset])
        self._emit(
            Opcode.WRITE_REGION,
            operands=[region_reg, offset_reg, fl.byte_length, encoded_reg],
        )

    def _emit_encode_value(self, fl: FieldLayout, value: str) -> str:
        """Emit inline IR to encode a value per the field's type. Returns result register."""
        td = fl.type_descriptor
        if td.category == CobolDataCategory.ALPHANUMERIC:
            return self._emit_encode_alphanumeric(fl.name, value, td.total_digits)
        return self._emit_encode_numeric(fl.name, value, td)

    def _emit_encode_alphanumeric(
        self, field_name: str, value: str, length: int
    ) -> str:
        """Emit inline alphanumeric encoding IR. Returns result register."""
        value_reg = self._fresh_reg()
        self._emit(Opcode.CONST, result_reg=value_reg, operands=[value])

        ir = build_encode_alphanumeric_ir(f"enc_alpha_{field_name}", length)
        return self._inline_ir(ir, {"%p_value": value_reg})

    def _emit_encode_numeric(
        self, field_name: str, value: str, td: "CobolTypeDescriptor"
    ) -> str:
        """Emit inline numeric encoding IR. Returns result register."""
        negative = value.startswith("-")
        clean = value.lstrip("+-")

        integer_digits = td.total_digits - td.decimal_digits
        if td.decimal_digits > 0:
            digit_str = align_decimal(clean, integer_digits, td.decimal_digits)
        else:
            digit_str = left_adjust(clean.replace(".", ""), td.total_digits)

        digits = [int(ch) if ch.isdigit() else 0 for ch in digit_str]

        if not td.signed:
            sign_nibble = 0x0F
        elif negative and any(d != 0 for d in digits):
            sign_nibble = 0x0D
        else:
            sign_nibble = 0x0C

        digits_reg = self._fresh_reg()
        self._emit(Opcode.CONST, result_reg=digits_reg, operands=[digits])

        sign_reg = self._fresh_reg()
        self._emit(Opcode.CONST, result_reg=sign_reg, operands=[sign_nibble])

        if td.category == CobolDataCategory.ZONED_DECIMAL:
            ir = build_encode_zoned_ir(f"enc_zoned_{field_name}", td.total_digits)
        else:
            ir = build_encode_comp3_ir(f"enc_comp3_{field_name}", td.total_digits)

        return self._inline_ir(
            ir, {"%p_digits": digits_reg, "%p_sign_nibble": sign_reg}
        )

    def _emit_decode_field(self, region_reg: str, fl: FieldLayout) -> str:
        """Emit IR to load and decode a field from the region. Returns decoded value register."""
        offset_reg = self._fresh_reg()
        self._emit(Opcode.CONST, result_reg=offset_reg, operands=[fl.offset])

        data_reg = self._fresh_reg()
        self._emit(
            Opcode.LOAD_REGION,
            result_reg=data_reg,
            operands=[region_reg, offset_reg, fl.byte_length],
        )

        td = fl.type_descriptor
        if td.category == CobolDataCategory.ALPHANUMERIC:
            ir = build_decode_alphanumeric_ir(f"dec_alpha_{fl.name}")
        elif td.category == CobolDataCategory.ZONED_DECIMAL:
            ir = build_decode_zoned_ir(
                f"dec_zoned_{fl.name}", td.total_digits, td.decimal_digits
            )
        else:
            ir = build_decode_comp3_ir(
                f"dec_comp3_{fl.name}", td.total_digits, td.decimal_digits
            )

        return self._inline_ir(ir, {"%p_data": data_reg})

    def _inline_ir(
        self, ir_instructions: list[IRInstruction], param_regs: dict[str, str]
    ) -> str:
        """Inline a generated IR function body, mapping parameter registers.

        Returns the register holding the return value.
        """
        reg_map: dict[str, str] = dict(param_regs)
        return_reg = ""

        for inst in ir_instructions:
            if inst.opcode == Opcode.LABEL:
                continue
            if inst.opcode == Opcode.RETURN:
                resolved_operand = self._resolve_inline_operand(
                    inst.operands[0], reg_map
                )
                return_reg = (
                    resolved_operand
                    if isinstance(resolved_operand, str)
                    and resolved_operand.startswith("%")
                    else self._const_to_reg(resolved_operand)
                )
                continue

            mapped_operands = [
                self._resolve_inline_operand(op, reg_map) for op in inst.operands
            ]

            new_result = self._fresh_reg() if inst.result_reg else ""
            if inst.result_reg:
                reg_map[inst.result_reg] = new_result

            self._emit(
                inst.opcode,
                result_reg=new_result,
                operands=mapped_operands,
                label=inst.label or "",
            )

        return return_reg

    def _resolve_inline_operand(self, operand: Any, reg_map: dict[str, str]) -> Any:
        """Resolve an operand through the register mapping."""
        if isinstance(operand, str) and operand.startswith("%"):
            return reg_map.get(operand, operand)
        return operand

    def _const_to_reg(self, value: Any) -> str:
        """Emit a CONST and return its register."""
        reg = self._fresh_reg()
        self._emit(Opcode.CONST, result_reg=reg, operands=[value])
        return reg

    # ── PROCEDURE DIVISION ─────────────────────────────────────────

    def _lower_procedure_division(
        self,
        asg: CobolASG,
        layout: DataLayout,
        region_reg: str,
    ) -> None:
        """Lower all sections and standalone paragraphs."""
        # Build section → paragraph-names lookup for section-level PERFORM
        self._section_paragraphs: dict[str, list[str]] = {
            section.name: [p.name for p in section.paragraphs]
            for section in asg.sections
        }

        # Emit inline code for standalone paragraphs first
        for para in asg.paragraphs:
            self._lower_paragraph(para, layout, region_reg)

        # Emit sections (each section's paragraphs are labeled blocks)
        for section in asg.sections:
            self._lower_section(section, layout, region_reg)

    def _lower_section(
        self,
        section: CobolSection,
        layout: DataLayout,
        region_reg: str,
    ) -> None:
        self._emit(Opcode.LABEL, label=f"section_{section.name}")
        for para in section.paragraphs:
            self._lower_paragraph(para, layout, region_reg)
        # Emit section end continuation point so PERFORM SECTION works
        self._emit(
            Opcode.RESUME_CONTINUATION,
            operands=[f"section_{section.name}_end"],
        )

    def _lower_paragraph(
        self,
        para: CobolParagraph,
        layout: DataLayout,
        region_reg: str,
    ) -> None:
        self._emit(Opcode.LABEL, label=f"para_{para.name}")
        for stmt in para.statements:
            self._lower_statement(stmt, layout, region_reg)
        self._emit(Opcode.RESUME_CONTINUATION, operands=[f"para_{para.name}_end"])

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
        else:
            logger.warning("Unhandled COBOL statement type: %s", type(stmt).__name__)

    def _lower_move(
        self,
        stmt: MoveStatement,
        layout: DataLayout,
        region_reg: str,
    ) -> None:
        """MOVE X TO Y: decode X, encode as Y's type, write to Y's region."""
        target_fl = layout.fields[stmt.target]

        if stmt.source in layout.fields:
            source_fl = layout.fields[stmt.source]
            decoded_reg = self._emit_decode_field(region_reg, source_fl)
            value_str_reg = self._emit_to_string(decoded_reg)
        else:
            value_str_reg = self._const_to_reg(str(stmt.source))

        encoded_reg = self._emit_encode_from_string(target_fl, value_str_reg)

        offset_reg = self._fresh_reg()
        self._emit(Opcode.CONST, result_reg=offset_reg, operands=[target_fl.offset])
        self._emit(
            Opcode.WRITE_REGION,
            operands=[region_reg, offset_reg, target_fl.byte_length, encoded_reg],
        )

    def _lower_arithmetic(
        self,
        stmt: ArithmeticStatement,
        layout: DataLayout,
        region_reg: str,
    ) -> None:
        """ADD/SUBTRACT/MULTIPLY/DIVIDE X TO/FROM/BY/INTO Y."""
        target_fl = layout.fields[stmt.target]

        if stmt.source in layout.fields:
            source_fl = layout.fields[stmt.source]
            src_decoded = self._emit_decode_field(region_reg, source_fl)
        else:
            src_decoded = self._const_to_reg(float(stmt.source))

        tgt_decoded = self._emit_decode_field(region_reg, target_fl)

        op = _ARITHMETIC_OPS[stmt.op]
        result_reg = self._fresh_reg()
        self._emit(
            Opcode.BINOP,
            result_reg=result_reg,
            operands=[op, tgt_decoded, src_decoded],
        )

        result_str_reg = self._emit_to_string(result_reg)
        encoded_reg = self._emit_encode_from_string(target_fl, result_str_reg)

        offset_reg = self._fresh_reg()
        self._emit(Opcode.CONST, result_reg=offset_reg, operands=[target_fl.offset])
        self._emit(
            Opcode.WRITE_REGION,
            operands=[region_reg, offset_reg, target_fl.byte_length, encoded_reg],
        )

    def _lower_compute(
        self,
        stmt: ComputeStatement,
        layout: DataLayout,
        region_reg: str,
    ) -> None:
        """COMPUTE target(s) = arithmetic-expression.

        Parses the expression into a tree, walks it to emit IR, then
        writes the result to each target field.
        """
        expr_tree = parse_expression(stmt.expression)
        result_reg = self._lower_expr_node(expr_tree, layout, region_reg)

        result_str_reg = self._emit_to_string(result_reg)
        for target_name in stmt.targets:
            if target_name not in layout.fields:
                logger.warning("COMPUTE target %s not found in layout", target_name)
                continue
            target_fl = layout.fields[target_name]
            encoded_reg = self._emit_encode_from_string(target_fl, result_str_reg)
            offset_reg = self._fresh_reg()
            self._emit(Opcode.CONST, result_reg=offset_reg, operands=[target_fl.offset])
            self._emit(
                Opcode.WRITE_REGION,
                operands=[region_reg, offset_reg, target_fl.byte_length, encoded_reg],
            )

    def _lower_expr_node(
        self,
        node: ExprNode,
        layout: DataLayout,
        region_reg: str,
    ) -> str:
        """Walk an expression tree node and emit IR. Returns result register."""
        if isinstance(node, LiteralNode):
            return self._const_to_reg(self._parse_literal(node.value))
        if isinstance(node, FieldRefNode):
            if node.name in layout.fields:
                return self._emit_decode_field(region_reg, layout.fields[node.name])
            return self._const_to_reg(self._parse_literal(node.name))
        if isinstance(node, BinOpNode):
            left_reg = self._lower_expr_node(node.left, layout, region_reg)
            right_reg = self._lower_expr_node(node.right, layout, region_reg)
            result_reg = self._fresh_reg()
            self._emit(
                Opcode.BINOP,
                result_reg=result_reg,
                operands=[node.op, left_reg, right_reg],
            )
            return result_reg
        logger.warning("Unknown expression node type: %s", type(node).__name__)
        return self._const_to_reg(0)

    def _lower_if(
        self,
        stmt: IfStatement,
        layout: DataLayout,
        region_reg: str,
    ) -> None:
        """IF condition ... [ELSE ...] END-IF."""
        cond_reg = self._lower_condition(stmt.condition, layout, region_reg)
        true_label = self._fresh_label("if_true")
        false_label = self._fresh_label("if_false")
        end_label = self._fresh_label("if_end")

        self._emit(
            Opcode.BRANCH_IF,
            operands=[cond_reg],
            label=f"{true_label},{false_label}",
        )

        # THEN branch
        self._emit(Opcode.LABEL, label=true_label)
        for child in stmt.children:
            self._lower_statement(child, layout, region_reg)
        self._emit(Opcode.BRANCH, label=end_label)

        # ELSE branch (falls through to end_label if empty)
        self._emit(Opcode.LABEL, label=false_label)
        for child in stmt.else_children:
            self._lower_statement(child, layout, region_reg)
        self._emit(Opcode.BRANCH, label=end_label)

        self._emit(Opcode.LABEL, label=end_label)

    def _lower_perform(
        self,
        stmt: PerformStatement,
        layout: DataLayout,
        region_reg: str,
    ) -> None:
        """PERFORM paragraph-name [THRU paragraph-name] [TIMES|UNTIL|VARYING]."""
        if stmt.children and stmt.spec is None:
            # Simple inline PERFORM (no loop spec)
            for child in stmt.children:
                self._lower_statement(child, layout, region_reg)
            return

        if stmt.target and stmt.spec is None:
            # Simple procedure PERFORM (no loop spec)
            self._emit_perform_branch(stmt, layout, region_reg)
            return

        # Loop variants
        if isinstance(stmt.spec, PerformTimesSpec):
            self._lower_perform_times(stmt, layout, region_reg)
        elif isinstance(stmt.spec, PerformUntilSpec):
            self._lower_perform_until(stmt, layout, region_reg)
        elif isinstance(stmt.spec, PerformVaryingSpec):
            self._lower_perform_varying(stmt, layout, region_reg)
        else:
            logger.warning("PERFORM with unknown spec: %s", stmt.spec)

    def _resolve_perform_target(self, stmt: PerformStatement) -> tuple[str, str]:
        """Resolve branch-target label and continuation-key label for PERFORM.

        Returns (branch_label, continuation_key).
        Handles both paragraph and section targets.
        """
        target = stmt.target
        section_paras = getattr(self, "_section_paragraphs", {})

        if target in section_paras:
            # Section-level PERFORM
            branch_label = f"section_{target}"
            thru = stmt.thru
            if thru and thru in section_paras:
                continuation_key = f"section_{thru}_end"
            else:
                continuation_key = f"section_{target}_end"
            return branch_label, continuation_key

        # Paragraph-level PERFORM
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
        branch_label, continuation_key = self._resolve_perform_target(stmt)
        return_label = self._fresh_label("perform_return")
        self._emit(
            Opcode.SET_CONTINUATION,
            operands=[continuation_key, return_label],
        )
        self._emit(Opcode.BRANCH, label=branch_label)
        self._emit(Opcode.LABEL, label=return_label)

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
        spec = stmt.spec
        assert isinstance(spec, PerformTimesSpec)

        counter_var = self._fresh_label("__perform_ctr")
        loop_label = self._fresh_label("perform_times_loop")
        body_label = self._fresh_label("perform_times_body")
        exit_label = self._fresh_label("perform_times_exit")

        # Init counter = 0
        zero_reg = self._const_to_reg(0)
        self._emit(Opcode.STORE_VAR, operands=[counter_var, zero_reg])

        # Resolve times value (literal or field)
        if spec.times in layout.fields:
            times_reg = self._emit_decode_field(region_reg, layout.fields[spec.times])
        else:
            times_reg = self._const_to_reg(self._parse_literal(spec.times))

        # Loop header
        self._emit(Opcode.LABEL, label=loop_label)
        ctr_reg = self._fresh_reg()
        self._emit(Opcode.LOAD_VAR, result_reg=ctr_reg, operands=[counter_var])
        cond_reg = self._fresh_reg()
        self._emit(
            Opcode.BINOP,
            result_reg=cond_reg,
            operands=[">=", ctr_reg, times_reg],
        )
        self._emit(
            Opcode.BRANCH_IF,
            operands=[cond_reg],
            label=f"{exit_label},{body_label}",
        )

        # Body
        self._emit(Opcode.LABEL, label=body_label)
        self._lower_perform_body(stmt, layout, region_reg)

        # Increment counter
        ctr_reg2 = self._fresh_reg()
        self._emit(Opcode.LOAD_VAR, result_reg=ctr_reg2, operands=[counter_var])
        one_reg = self._const_to_reg(1)
        inc_reg = self._fresh_reg()
        self._emit(Opcode.BINOP, result_reg=inc_reg, operands=["+", ctr_reg2, one_reg])
        self._emit(Opcode.STORE_VAR, operands=[counter_var, inc_reg])
        self._emit(Opcode.BRANCH, label=loop_label)

        self._emit(Opcode.LABEL, label=exit_label)

    def _lower_perform_until(
        self,
        stmt: PerformStatement,
        layout: DataLayout,
        region_reg: str,
    ) -> None:
        """PERFORM ... UNTIL — condition-based loop."""
        spec = stmt.spec
        assert isinstance(spec, PerformUntilSpec)

        loop_label = self._fresh_label("perform_until_loop")
        body_label = self._fresh_label("perform_until_body")
        exit_label = self._fresh_label("perform_until_exit")

        if spec.test_before:
            # TEST BEFORE: check condition first
            self._emit(Opcode.LABEL, label=loop_label)
            cond_reg = self._lower_condition(spec.condition, layout, region_reg)
            self._emit(
                Opcode.BRANCH_IF,
                operands=[cond_reg],
                label=f"{exit_label},{body_label}",
            )
            self._emit(Opcode.LABEL, label=body_label)
            self._lower_perform_body(stmt, layout, region_reg)
            self._emit(Opcode.BRANCH, label=loop_label)
            self._emit(Opcode.LABEL, label=exit_label)
        else:
            # TEST AFTER: execute body first, then check condition
            self._emit(Opcode.LABEL, label=loop_label)
            self._lower_perform_body(stmt, layout, region_reg)
            cond_reg = self._lower_condition(spec.condition, layout, region_reg)
            self._emit(
                Opcode.BRANCH_IF,
                operands=[cond_reg],
                label=f"{exit_label},{loop_label}",
            )
            self._emit(Opcode.LABEL, label=exit_label)

    def _lower_perform_varying(
        self,
        stmt: PerformStatement,
        layout: DataLayout,
        region_reg: str,
    ) -> None:
        """PERFORM ... VARYING — counter variable loop with FROM/BY/UNTIL."""
        spec = stmt.spec
        assert isinstance(spec, PerformVaryingSpec)

        loop_label = self._fresh_label("perform_varying_loop")
        body_label = self._fresh_label("perform_varying_body")
        exit_label = self._fresh_label("perform_varying_exit")

        # Initialize varying variable: encode FROM value into field
        if spec.varying_var in layout.fields:
            varying_fl = layout.fields[spec.varying_var]
            from_str_reg = self._const_to_reg(str(spec.varying_from))
            self._emit_encode_and_write(region_reg, varying_fl, from_str_reg)

        if spec.test_before:
            # TEST BEFORE
            self._emit(Opcode.LABEL, label=loop_label)
            cond_reg = self._lower_condition(spec.condition, layout, region_reg)
            self._emit(
                Opcode.BRANCH_IF,
                operands=[cond_reg],
                label=f"{exit_label},{body_label}",
            )
            self._emit(Opcode.LABEL, label=body_label)
            self._lower_perform_body(stmt, layout, region_reg)
            self._emit_varying_increment(spec, layout, region_reg)
            self._emit(Opcode.BRANCH, label=loop_label)
            self._emit(Opcode.LABEL, label=exit_label)
        else:
            # TEST AFTER
            self._emit(Opcode.LABEL, label=loop_label)
            self._lower_perform_body(stmt, layout, region_reg)
            self._emit_varying_increment(spec, layout, region_reg)
            cond_reg = self._lower_condition(spec.condition, layout, region_reg)
            self._emit(
                Opcode.BRANCH_IF,
                operands=[cond_reg],
                label=f"{exit_label},{loop_label}",
            )
            self._emit(Opcode.LABEL, label=exit_label)

    def _emit_varying_increment(
        self,
        spec: PerformVaryingSpec,
        layout: DataLayout,
        region_reg: str,
    ) -> None:
        """Emit IR to increment the VARYING variable by the BY value."""
        if spec.varying_var not in layout.fields:
            logger.warning("VARYING variable %s not found in layout", spec.varying_var)
            return

        varying_fl = layout.fields[spec.varying_var]

        # Decode current value
        val_reg = self._emit_decode_field(region_reg, varying_fl)

        # Add BY step
        by_reg = self._const_to_reg(self._parse_literal(spec.varying_by))
        new_val_reg = self._fresh_reg()
        self._emit(
            Opcode.BINOP,
            result_reg=new_val_reg,
            operands=["+", val_reg, by_reg],
        )

        # Encode back
        new_str_reg = self._emit_to_string(new_val_reg)
        self._emit_encode_and_write(region_reg, varying_fl, new_str_reg)

    def _emit_encode_and_write(
        self,
        region_reg: str,
        fl: FieldLayout,
        value_str_reg: str,
    ) -> None:
        """Encode a string value and write it to the field's region slot."""
        encoded_reg = self._emit_encode_from_string(fl, value_str_reg)
        offset_reg = self._fresh_reg()
        self._emit(Opcode.CONST, result_reg=offset_reg, operands=[fl.offset])
        self._emit(
            Opcode.WRITE_REGION,
            operands=[region_reg, offset_reg, fl.byte_length, encoded_reg],
        )

    def _lower_display(
        self,
        stmt: DisplayStatement,
        layout: DataLayout,
        region_reg: str,
    ) -> None:
        """DISPLAY field-or-literal."""
        operand = stmt.operand

        if isinstance(operand, str) and operand in layout.fields:
            fl = layout.fields[operand]
            decoded_reg = self._emit_decode_field(region_reg, fl)
            display_reg = self._emit_to_string(decoded_reg)
        else:
            display_reg = self._const_to_reg(str(operand))

        self._emit(
            Opcode.CALL_FUNCTION,
            result_reg=self._fresh_reg(),
            operands=["print", display_reg],
        )

    def _lower_stop_run(
        self,
        stmt: StopRunStatement,
        layout: DataLayout,
        region_reg: str,
    ) -> None:
        """STOP RUN."""
        zero_reg = self._fresh_reg()
        self._emit(Opcode.CONST, result_reg=zero_reg, operands=[0])
        self._emit(Opcode.RETURN, operands=[zero_reg])

    def _lower_goto(
        self,
        stmt: GotoStatement,
        layout: DataLayout,
        region_reg: str,
    ) -> None:
        """GO TO paragraph-name."""
        self._emit(Opcode.BRANCH, label=f"para_{stmt.target}")

    def _lower_evaluate(
        self,
        stmt: EvaluateStatement,
        layout: DataLayout,
        region_reg: str,
    ) -> None:
        """EVALUATE (lowered as chain of BRANCH_IF)."""
        end_label = self._fresh_label("eval_end")

        for child in stmt.children:
            if isinstance(child, WhenStatement) and child.condition:
                cond_reg = self._lower_condition(child.condition, layout, region_reg)
                when_true = self._fresh_label("when_true")
                when_false = self._fresh_label("when_false")
                self._emit(
                    Opcode.BRANCH_IF,
                    operands=[cond_reg],
                    label=f"{when_true},{when_false}",
                )
                self._emit(Opcode.LABEL, label=when_true)
                for grandchild in child.children:
                    self._lower_statement(grandchild, layout, region_reg)
                self._emit(Opcode.BRANCH, label=end_label)
                self._emit(Opcode.LABEL, label=when_false)
            elif isinstance(child, WhenOtherStatement):
                for grandchild in child.children:
                    self._lower_statement(grandchild, layout, region_reg)

        self._emit(Opcode.LABEL, label=end_label)

    # ── Tier 1: CONTINUE, EXIT, INITIALIZE, SET ────────────────────

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
        for operand in stmt.operands:
            if operand not in layout.fields:
                logger.warning("INITIALIZE target %s not found in layout", operand)
                continue
            fl = layout.fields[operand]
            td = fl.type_descriptor
            if td.category == CobolDataCategory.ALPHANUMERIC:
                default = " " * td.total_digits
            else:
                default = "0"
            self._emit_field_encode(region_reg, fl, default)

    def _lower_set(
        self,
        stmt: SetStatement,
        layout: DataLayout,
        region_reg: str,
    ) -> None:
        """SET target TO value / SET target UP|DOWN BY value."""
        if stmt.set_type == "TO":
            # SET target(s) TO value(s) — assign first value to all targets
            value_str = stmt.values[0] if stmt.values else "0"
            for target_name in stmt.targets:
                if target_name not in layout.fields:
                    logger.warning("SET target %s not found in layout", target_name)
                    continue
                target_fl = layout.fields[target_name]
                value_str_reg = self._const_to_reg(str(value_str))
                self._emit_encode_and_write(region_reg, target_fl, value_str_reg)
        elif stmt.set_type == "BY":
            # SET target UP|DOWN BY value — increment/decrement
            step_val = stmt.values[0] if stmt.values else "1"
            op = "+" if stmt.by_type == "UP" else "-"
            for target_name in stmt.targets:
                if target_name not in layout.fields:
                    logger.warning("SET target %s not found in layout", target_name)
                    continue
                target_fl = layout.fields[target_name]
                tgt_decoded = self._emit_decode_field(region_reg, target_fl)
                step_reg = self._const_to_reg(self._parse_literal(step_val))
                result_reg = self._fresh_reg()
                self._emit(
                    Opcode.BINOP,
                    result_reg=result_reg,
                    operands=[op, tgt_decoded, step_reg],
                )
                result_str_reg = self._emit_to_string(result_reg)
                self._emit_encode_and_write(region_reg, target_fl, result_str_reg)

    # ── Tier 2: STRING, UNSTRING, INSPECT ─────────────────────────

    def _lower_string(
        self,
        stmt: StringStatement,
        layout: DataLayout,
        region_reg: str,
    ) -> None:
        """STRING ... DELIMITED BY ... INTO target.

        For each sending: decode source, apply delimiter truncation.
        Concatenate all parts, encode and write to target.
        """
        part_regs: list[str] = []
        for sending in stmt.sendings:
            # Decode source field or use literal
            if sending.value in layout.fields:
                source_fl = layout.fields[sending.value]
                decoded_reg = self._emit_decode_field(region_reg, source_fl)
                src_str_reg = self._emit_to_string(decoded_reg)
            else:
                src_str_reg = self._const_to_reg(str(sending.value))

            if sending.delimited_by == "SIZE":
                # Use full string
                part_regs.append(src_str_reg)
            else:
                # Truncate at delimiter
                delim_reg = self._const_to_reg(str(sending.delimited_by))
                find_pos = self._fresh_reg()
                self._emit(
                    Opcode.CALL_FUNCTION,
                    result_reg=find_pos,
                    operands=["__string_find", src_str_reg, delim_reg],
                )
                # Use CALL_FUNCTION to slice: if pos >= 0, take [0:pos], else full
                # For simplicity, use __string_find result directly
                # and call a helper. But we don't have a conditional slice builtin.
                # We'll emit this as a CALL_FUNCTION to a string truncation builtin.
                # Actually, let's keep it simple: COBOL STRING with delimiter
                # truncates at the first occurrence. We can use __string_split
                # and take the first element.
                parts = self._fresh_reg()
                self._emit(
                    Opcode.CALL_FUNCTION,
                    result_reg=parts,
                    operands=["__string_split", src_str_reg, delim_reg],
                )
                first_part = self._fresh_reg()
                self._emit(
                    Opcode.CALL_FUNCTION,
                    result_reg=first_part,
                    operands=["__list_get", parts, 0],
                )
                part_regs.append(first_part)

        # Concatenate all parts
        if not part_regs:
            concat_reg = self._const_to_reg("")
        elif len(part_regs) == 1:
            concat_reg = part_regs[0]
        else:
            parts_list_reg = self._const_to_reg(part_regs)
            concat_reg = self._fresh_reg()
            self._emit(
                Opcode.CALL_FUNCTION,
                result_reg=concat_reg,
                operands=["__string_concat", parts_list_reg],
            )

        # Write to target
        if stmt.into and stmt.into in layout.fields:
            target_fl = layout.fields[stmt.into]
            self._emit_encode_and_write(region_reg, target_fl, concat_reg)
        else:
            logger.warning("STRING INTO target %s not found in layout", stmt.into)

    def _lower_unstring(
        self,
        stmt: UnstringStatement,
        layout: DataLayout,
        region_reg: str,
    ) -> None:
        """UNSTRING source DELIMITED BY ... INTO targets.

        Decode source, split by delimiter, write each part to target field.
        """
        # Decode source
        if stmt.source in layout.fields:
            source_fl = layout.fields[stmt.source]
            decoded_reg = self._emit_decode_field(region_reg, source_fl)
            src_str_reg = self._emit_to_string(decoded_reg)
        else:
            src_str_reg = self._const_to_reg(str(stmt.source))

        # Split by delimiter
        delim_reg = self._const_to_reg(str(stmt.delimited_by))
        ir = build_string_split_ir(f"unstring_split_{stmt.source}")
        parts_reg = self._inline_ir(
            ir, {"%p_source": src_str_reg, "%p_delimiter": delim_reg}
        )

        # Write each part to corresponding target
        for i, target_name in enumerate(stmt.into):
            if target_name not in layout.fields:
                logger.warning(
                    "UNSTRING INTO target %s not found in layout", target_name
                )
                continue
            target_fl = layout.fields[target_name]
            idx_reg = self._const_to_reg(i)
            part_reg = self._fresh_reg()
            self._emit(
                Opcode.CALL_FUNCTION,
                result_reg=part_reg,
                operands=["__list_get", parts_reg, idx_reg],
            )
            self._emit_encode_and_write(region_reg, target_fl, part_reg)

    def _lower_inspect(
        self,
        stmt: InspectStatement,
        layout: DataLayout,
        region_reg: str,
    ) -> None:
        """INSPECT source TALLYING|REPLACING ..."""
        if stmt.source not in layout.fields:
            logger.warning("INSPECT source %s not found in layout", stmt.source)
            return
        source_fl = layout.fields[stmt.source]
        decoded_reg = self._emit_decode_field(region_reg, source_fl)
        src_str_reg = self._emit_to_string(decoded_reg)

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
        total_count_reg = self._const_to_reg(0)

        for tally_for in stmt.tallying_for:
            pattern_reg = self._const_to_reg(str(tally_for.pattern))
            mode_reg = self._const_to_reg(tally_for.mode.lower())
            ir = build_inspect_tally_ir(f"inspect_tally_{stmt.source}")
            count_reg = self._inline_ir(
                ir,
                {
                    "%p_source": src_str_reg,
                    "%p_pattern": pattern_reg,
                    "%p_mode": mode_reg,
                },
            )
            new_total = self._fresh_reg()
            self._emit(
                Opcode.BINOP,
                result_reg=new_total,
                operands=["+", total_count_reg, count_reg],
            )
            total_count_reg = new_total

        # Write total count to tally target
        if stmt.tallying_target and stmt.tallying_target in layout.fields:
            tally_fl = layout.fields[stmt.tallying_target]
            count_str_reg = self._emit_to_string(total_count_reg)
            self._emit_encode_and_write(region_reg, tally_fl, count_str_reg)

    def _lower_inspect_replacing(
        self,
        stmt: InspectStatement,
        src_str_reg: str,
        source_fl: FieldLayout,
        layout: DataLayout,
        region_reg: str,
    ) -> None:
        """INSPECT REPLACING — apply replacements and write back."""
        current_str_reg = src_str_reg

        for replacing in stmt.replacings:
            from_reg = self._const_to_reg(str(replacing.from_pattern))
            to_reg = self._const_to_reg(str(replacing.to_pattern))
            mode_reg = self._const_to_reg(replacing.mode.lower())
            ir = build_inspect_replace_ir(f"inspect_replace_{stmt.source}")
            new_str_reg = self._inline_ir(
                ir,
                {
                    "%p_source": current_str_reg,
                    "%p_from": from_reg,
                    "%p_to": to_reg,
                    "%p_mode": mode_reg,
                },
            )
            current_str_reg = new_str_reg

        # Write modified string back to source field
        self._emit_encode_and_write(region_reg, source_fl, current_str_reg)

    # ── Condition Lowering ─────────────────────────────────────────

    def _lower_condition(
        self,
        condition: str,
        layout: DataLayout,
        region_reg: str,
    ) -> str:
        """Lower a simple condition string to a register holding a boolean.

        Supports: "field OP value" where OP is >, <, >=, <=, =, NOT =
        """
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

            if left_name in layout.fields:
                left_reg = self._emit_decode_field(region_reg, layout.fields[left_name])
            else:
                left_reg = self._const_to_reg(self._parse_literal(left_name))

            right_parsed = self._parse_literal(right_val)
            if isinstance(right_parsed, str) and right_parsed in layout.fields:
                right_reg = self._emit_decode_field(
                    region_reg, layout.fields[right_parsed]
                )
            else:
                right_reg = self._const_to_reg(right_parsed)

            result = self._fresh_reg()
            self._emit(
                Opcode.BINOP,
                result_reg=result,
                operands=[op, left_reg, right_reg],
            )
            return result

        # Fallback: treat entire condition as a boolean constant
        result = self._fresh_reg()
        self._emit(Opcode.CONST, result_reg=result, operands=[True])
        return result

    def _parse_literal(self, text: str) -> Any:
        """Parse a literal value from condition text."""
        try:
            return int(text)
        except ValueError:
            pass
        try:
            return float(text)
        except ValueError:
            pass
        return text

    # ── String Conversion Helpers ──────────────────────────────────

    def _emit_to_string(self, value_reg: str) -> str:
        """Emit IR to convert a value to a string."""
        result = self._fresh_reg()
        self._emit(
            Opcode.CALL_FUNCTION,
            result_reg=result,
            operands=["str", value_reg],
        )
        return result

    def _emit_encode_from_string(self, fl: FieldLayout, value_str_reg: str) -> str:
        """Emit encoding IR from a string value register."""
        td = fl.type_descriptor
        if td.category == CobolDataCategory.ALPHANUMERIC:
            ir = build_encode_alphanumeric_ir(f"enc_alpha_{fl.name}", td.total_digits)
            return self._inline_ir(ir, {"%p_value": value_str_reg})

        # For numeric types, we need to prepare digits and sign from the string
        return self._emit_numeric_encode_from_string(fl, value_str_reg)

    def _emit_numeric_encode_from_string(
        self, fl: FieldLayout, value_str_reg: str
    ) -> str:
        """Emit IR to parse a string into digits + sign, then encode numerically.

        Uses CALL_FUNCTION to built-in helpers for digit extraction.
        """
        td = fl.type_descriptor
        # Use __cobol_prepare_digits builtin to convert string to (digits, sign_nibble)
        digits_reg = self._fresh_reg()
        self._emit(
            Opcode.CALL_FUNCTION,
            result_reg=digits_reg,
            operands=[
                "__cobol_prepare_digits",
                value_str_reg,
                td.total_digits,
                td.decimal_digits,
                td.signed,
            ],
        )

        sign_reg = self._fresh_reg()
        self._emit(
            Opcode.CALL_FUNCTION,
            result_reg=sign_reg,
            operands=[
                "__cobol_prepare_sign",
                value_str_reg,
                td.signed,
            ],
        )

        if td.category == CobolDataCategory.ZONED_DECIMAL:
            ir = build_encode_zoned_ir(f"enc_zoned_{fl.name}", td.total_digits)
        else:
            ir = build_encode_comp3_ir(f"enc_comp3_{fl.name}", td.total_digits)

        return self._inline_ir(
            ir, {"%p_digits": digits_reg, "%p_sign_nibble": sign_reg}
        )
