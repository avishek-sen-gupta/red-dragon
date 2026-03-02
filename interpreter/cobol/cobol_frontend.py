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
    CobolStatement,
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
        stmt: CobolStatement,
        layout: DataLayout,
        region_reg: str,
    ) -> None:
        dispatch = {
            "MOVE": self._lower_move,
            "ADD": self._lower_arithmetic,
            "SUBTRACT": self._lower_arithmetic,
            "MULTIPLY": self._lower_arithmetic,
            "DIVIDE": self._lower_arithmetic,
            "IF": self._lower_if,
            "PERFORM": self._lower_perform,
            "DISPLAY": self._lower_display,
            "STOP_RUN": self._lower_stop_run,
            "GOTO": self._lower_goto,
            "EVALUATE": self._lower_evaluate,
        }
        handler = dispatch.get(stmt.type)
        if handler:
            handler(stmt, layout, region_reg)
        else:
            logger.warning("Unhandled COBOL statement type: %s", stmt.type)

    def _lower_move(
        self,
        stmt: CobolStatement,
        layout: DataLayout,
        region_reg: str,
    ) -> None:
        """MOVE X TO Y: decode X, encode as Y's type, write to Y's region."""
        source_operand = stmt.operands[0]
        target_name = stmt.operands[1]
        target_fl = layout.fields[target_name]

        if isinstance(source_operand, str) and source_operand in layout.fields:
            source_fl = layout.fields[source_operand]
            decoded_reg = self._emit_decode_field(region_reg, source_fl)
            value_str_reg = self._emit_to_string(decoded_reg)
        else:
            value_str_reg = self._const_to_reg(str(source_operand))

        encoded_reg = self._emit_encode_from_string(target_fl, value_str_reg)

        offset_reg = self._fresh_reg()
        self._emit(Opcode.CONST, result_reg=offset_reg, operands=[target_fl.offset])
        self._emit(
            Opcode.WRITE_REGION,
            operands=[region_reg, offset_reg, target_fl.byte_length, encoded_reg],
        )

    def _lower_arithmetic(
        self,
        stmt: CobolStatement,
        layout: DataLayout,
        region_reg: str,
    ) -> None:
        """ADD/SUBTRACT/MULTIPLY/DIVIDE X TO/FROM/BY/INTO Y."""
        source_operand = stmt.operands[0]
        target_name = stmt.operands[1]
        target_fl = layout.fields[target_name]

        if isinstance(source_operand, str) and source_operand in layout.fields:
            source_fl = layout.fields[source_operand]
            src_decoded = self._emit_decode_field(region_reg, source_fl)
        else:
            src_decoded = self._const_to_reg(float(source_operand))

        tgt_decoded = self._emit_decode_field(region_reg, target_fl)

        op = _ARITHMETIC_OPS[stmt.type]
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

    def _lower_if(
        self,
        stmt: CobolStatement,
        layout: DataLayout,
        region_reg: str,
    ) -> None:
        """IF condition ... END-IF."""
        cond_reg = self._lower_condition(stmt.condition, layout, region_reg)
        true_label = self._fresh_label("if_true")
        end_label = self._fresh_label("if_end")

        self._emit(
            Opcode.BRANCH_IF,
            operands=[cond_reg],
            label=f"{true_label},{end_label}",
        )

        self._emit(Opcode.LABEL, label=true_label)
        for child in stmt.children:
            self._lower_statement(child, layout, region_reg)
        self._emit(Opcode.BRANCH, label=end_label)

        self._emit(Opcode.LABEL, label=end_label)

    def _lower_perform(
        self,
        stmt: CobolStatement,
        layout: DataLayout,
        region_reg: str,
    ) -> None:
        """PERFORM paragraph-name [THRU paragraph-name]."""
        if stmt.children:
            # Inline PERFORM (PERFORM ... END-PERFORM)
            for child in stmt.children:
                self._lower_statement(child, layout, region_reg)
            return

        para_name = stmt.operands[0]
        thru_name = stmt.thru if stmt.thru else para_name
        return_label = self._fresh_label("perform_return")

        self._emit(
            Opcode.SET_CONTINUATION,
            operands=[f"para_{thru_name}_end", return_label],
        )
        self._emit(Opcode.BRANCH, label=f"para_{para_name}")
        self._emit(Opcode.LABEL, label=return_label)

    def _lower_display(
        self,
        stmt: CobolStatement,
        layout: DataLayout,
        region_reg: str,
    ) -> None:
        """DISPLAY field-or-literal."""
        operand = stmt.operands[0]

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
        stmt: CobolStatement,
        layout: DataLayout,
        region_reg: str,
    ) -> None:
        """STOP RUN."""
        zero_reg = self._fresh_reg()
        self._emit(Opcode.CONST, result_reg=zero_reg, operands=[0])
        self._emit(Opcode.RETURN, operands=[zero_reg])

    def _lower_goto(
        self,
        stmt: CobolStatement,
        layout: DataLayout,
        region_reg: str,
    ) -> None:
        """GO TO paragraph-name."""
        para_name = stmt.operands[0]
        self._emit(Opcode.BRANCH, label=f"para_{para_name}")

    def _lower_evaluate(
        self,
        stmt: CobolStatement,
        layout: DataLayout,
        region_reg: str,
    ) -> None:
        """EVALUATE (lowered as chain of BRANCH_IF)."""
        end_label = self._fresh_label("eval_end")

        for child in stmt.children:
            if child.type == "WHEN" and child.condition:
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
            elif child.type == "WHEN_OTHER":
                for grandchild in child.children:
                    self._lower_statement(grandchild, layout, region_reg)

        self._emit(Opcode.LABEL, label=end_label)

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
