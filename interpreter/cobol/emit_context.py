"""EmitContext — shared mutable state and emit primitives for COBOL lowering.

All lowering functions receive an EmitContext and operate on it.  The context
holds the instruction buffer, register/label counters, section→paragraph
lookup, and convenience methods for emitting IR.

Circular dependency between lowering functions and the statement dispatcher
is broken by injecting a *dispatch callback* at construction time.
"""

from __future__ import annotations

import logging
from typing import Any, Callable

from interpreter.cobol.cobol_types import CobolDataCategory
from interpreter.cobol.condition_name_index import ConditionNameIndex
from interpreter.cobol.data_filters import align_decimal, left_adjust
from interpreter.cobol.data_layout import DataLayout, FieldLayout
from interpreter.cobol.field_resolution import (
    ResolvedFieldRef,
    parse_subscript_notation,
)
from interpreter.cobol.ir_encoders import (
    build_decode_alphanumeric_ir,
    build_decode_comp3_ir,
    build_decode_zoned_ir,
    build_encode_alphanumeric_ir,
    build_encode_comp3_ir,
    build_encode_zoned_ir,
    build_encode_binary_ir,
    build_decode_binary_ir,
    build_encode_float_ir,
    build_decode_float_ir,
)
from interpreter.ir import IRInstruction, Opcode

logger = logging.getLogger(__name__)

# Type alias for the dispatch callback signature
DispatchFn = Callable[["EmitContext", Any, DataLayout, str], None]


class EmitContext:
    """Shared state and emit primitives for COBOL IR lowering."""

    def __init__(
        self,
        dispatch_fn: DispatchFn,
        observer: Any = None,
        condition_index: ConditionNameIndex = ConditionNameIndex({}),
    ) -> None:
        self._dispatch_fn = dispatch_fn
        self._observer = observer
        self._condition_index = condition_index
        self._instructions: list[IRInstruction] = []
        self._reg_counter: int = 0
        self._label_counter: int = 0
        self._section_paragraphs: dict[str, list[str]] = {}

    # ── Properties ────────────────────────────────────────────────

    @property
    def instructions(self) -> list[IRInstruction]:
        return self._instructions

    @property
    def section_paragraphs(self) -> dict[str, list[str]]:
        return self._section_paragraphs

    @section_paragraphs.setter
    def section_paragraphs(self, value: dict[str, list[str]]) -> None:
        self._section_paragraphs = value

    # ── Core Primitives ───────────────────────────────────────────

    def fresh_reg(self) -> str:
        name = f"%r{self._reg_counter}"
        self._reg_counter += 1
        return name

    def fresh_label(self, prefix: str) -> str:
        name = f"{prefix}_{self._label_counter}"
        self._label_counter += 1
        return name

    def emit(
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

    def const_to_reg(self, value: Any) -> str:
        """Emit a CONST and return its register."""
        reg = self.fresh_reg()
        self.emit(Opcode.CONST, result_reg=reg, operands=[value])
        return reg

    def inline_ir(
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
                resolved_operand = self.resolve_inline_operand(
                    inst.operands[0], reg_map
                )
                return_reg = (
                    resolved_operand
                    if isinstance(resolved_operand, str)
                    and resolved_operand.startswith("%")
                    else self.const_to_reg(resolved_operand)
                )
                continue

            mapped_operands = [
                self.resolve_inline_operand(op, reg_map) for op in inst.operands
            ]

            new_result = self.fresh_reg() if inst.result_reg else ""
            if inst.result_reg:
                reg_map[inst.result_reg] = new_result

            self.emit(
                inst.opcode,
                result_reg=new_result,
                operands=mapped_operands,
                label=inst.label or "",
            )

        return return_reg

    def resolve_inline_operand(self, operand: Any, reg_map: dict[str, str]) -> Any:
        """Resolve an operand through the register mapping."""
        if isinstance(operand, str) and operand.startswith("%"):
            return reg_map.get(operand, operand)
        return operand

    # ── Statement Dispatch ────────────────────────────────────────

    def lower_statement(self, stmt: Any, layout: DataLayout, region_reg: str) -> None:
        """Dispatch a statement through the injected callback."""
        self._dispatch_fn(self, stmt, layout, region_reg)

    # ── Field Reference Resolution ────────────────────────────────

    def resolve_field_ref(
        self, name: str, layout: DataLayout, region_reg: str
    ) -> ResolvedFieldRef:
        """Resolve a field reference that may contain subscript notation."""
        base_name, subscript = parse_subscript_notation(name)
        fl = layout.fields[base_name]

        if not subscript:
            offset_reg = self.fresh_reg()
            self.emit(Opcode.CONST, result_reg=offset_reg, operands=[fl.offset])
            return ResolvedFieldRef(fl=fl, offset_reg=offset_reg)

        # Resolve subscript value: literal or field
        try:
            idx_val = int(subscript)
            idx_reg = self.const_to_reg(idx_val)
        except ValueError:
            # Subscript is a field reference — decode it
            sub_base, _ = parse_subscript_notation(subscript)
            if sub_base in layout.fields:
                sub_fl = layout.fields[sub_base]
                idx_reg = self.emit_decode_field(region_reg, sub_fl)
            else:
                idx_reg = self.const_to_reg(1)
                logger.warning(
                    "Subscript field %s not found in layout, defaulting to 1",
                    subscript,
                )

        # Compute offset: fl.offset + (idx - 1) * element_size
        one_reg = self.const_to_reg(1)
        idx_minus_one = self.fresh_reg()
        self.emit(
            Opcode.BINOP,
            result_reg=idx_minus_one,
            operands=["-", idx_reg, one_reg],
        )

        elem_size = fl.element_size if fl.element_size > 0 else fl.byte_length
        elem_size_reg = self.const_to_reg(elem_size)
        displacement = self.fresh_reg()
        self.emit(
            Opcode.BINOP,
            result_reg=displacement,
            operands=["*", idx_minus_one, elem_size_reg],
        )

        base_offset_reg = self.const_to_reg(fl.offset)
        final_offset_reg = self.fresh_reg()
        self.emit(
            Opcode.BINOP,
            result_reg=final_offset_reg,
            operands=["+", base_offset_reg, displacement],
        )

        # For subscripted access, use element-level FieldLayout
        element_fl = FieldLayout(
            name=fl.name,
            type_descriptor=fl.type_descriptor,
            offset=fl.offset,
            byte_length=elem_size,
            redefines=fl.redefines,
            value=fl.value,
        )
        return ResolvedFieldRef(fl=element_fl, offset_reg=final_offset_reg)

    def has_field(self, name: str, layout: DataLayout) -> bool:
        """Check if a name (possibly subscripted) refers to a known field."""
        base_name, _ = parse_subscript_notation(name)
        return base_name in layout.fields

    # ── Field Encode / Decode ─────────────────────────────────────

    def emit_field_encode(
        self, region_reg: str, fl: FieldLayout, value: str, offset_reg: str = ""
    ) -> None:
        """Emit IR to encode a value and write it to the region."""
        encoded_reg = self.emit_encode_value(fl, value)
        if not offset_reg:
            offset_reg = self.fresh_reg()
            self.emit(Opcode.CONST, result_reg=offset_reg, operands=[fl.offset])
        self.emit(
            Opcode.WRITE_REGION,
            operands=[region_reg, offset_reg, fl.byte_length, encoded_reg],
        )

    def emit_encode_value(self, fl: FieldLayout, value: str) -> str:
        """Emit inline IR to encode a value per the field's type. Returns result register."""
        td = fl.type_descriptor
        if td.category == CobolDataCategory.ALPHANUMERIC:
            return self.emit_encode_alphanumeric(fl.name, value, td.total_digits)
        if td.category in (CobolDataCategory.COMP1, CobolDataCategory.COMP2):
            return self.emit_encode_float(fl.name, value, td)
        return self.emit_encode_numeric(fl.name, value, td)

    def emit_encode_alphanumeric(self, field_name: str, value: str, length: int) -> str:
        """Emit inline alphanumeric encoding IR. Returns result register."""
        value_reg = self.fresh_reg()
        self.emit(Opcode.CONST, result_reg=value_reg, operands=[value])

        ir = build_encode_alphanumeric_ir(f"enc_alpha_{field_name}", length)
        return self.inline_ir(ir, {"%p_value": value_reg})

    def emit_encode_float(self, field_name: str, value: str, td: Any) -> str:
        """Emit inline float encoding IR for COMP-1/COMP-2. Returns result register."""
        float_val = float(value)
        value_reg = self.fresh_reg()
        self.emit(Opcode.CONST, result_reg=value_reg, operands=[float_val])

        ir = build_encode_float_ir(f"enc_float_{field_name}", td.byte_length)
        return self.inline_ir(ir, {"%p_float_value": value_reg})

    def emit_encode_numeric(self, field_name: str, value: str, td: Any) -> str:
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

        digits_reg = self.fresh_reg()
        self.emit(Opcode.CONST, result_reg=digits_reg, operands=[digits])

        sign_reg = self.fresh_reg()
        self.emit(Opcode.CONST, result_reg=sign_reg, operands=[sign_nibble])

        if td.category == CobolDataCategory.ZONED_DECIMAL:
            ir = build_encode_zoned_ir(f"enc_zoned_{field_name}", td.total_digits)
        elif td.category == CobolDataCategory.BINARY:
            ir = build_encode_binary_ir(
                f"enc_bin_{field_name}",
                td.total_digits,
                td.byte_length,
                td.signed,
            )
        else:
            ir = build_encode_comp3_ir(f"enc_comp3_{field_name}", td.total_digits)

        return self.inline_ir(ir, {"%p_digits": digits_reg, "%p_sign_nibble": sign_reg})

    def emit_decode_field(
        self, region_reg: str, fl: FieldLayout, offset_reg: str = ""
    ) -> str:
        """Emit IR to load and decode a field from the region. Returns decoded value register."""
        if not offset_reg:
            offset_reg = self.fresh_reg()
            self.emit(Opcode.CONST, result_reg=offset_reg, operands=[fl.offset])

        data_reg = self.fresh_reg()
        self.emit(
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
        elif td.category == CobolDataCategory.BINARY:
            ir = build_decode_binary_ir(
                f"dec_bin_{fl.name}",
                td.byte_length,
                td.decimal_digits,
                td.signed,
            )
        elif td.category in (CobolDataCategory.COMP1, CobolDataCategory.COMP2):
            ir = build_decode_float_ir(f"dec_float_{fl.name}", td.byte_length)
        else:
            ir = build_decode_comp3_ir(
                f"dec_comp3_{fl.name}", td.total_digits, td.decimal_digits
            )

        return self.inline_ir(ir, {"%p_data": data_reg})

    # ── String Conversion Helpers ─────────────────────────────────

    def emit_to_string(self, value_reg: str) -> str:
        """Emit IR to convert a value to a string."""
        result = self.fresh_reg()
        self.emit(
            Opcode.CALL_FUNCTION,
            result_reg=result,
            operands=["str", value_reg],
        )
        return result

    def emit_encode_from_string(self, fl: FieldLayout, value_str_reg: str) -> str:
        """Emit encoding IR from a string value register."""
        td = fl.type_descriptor
        if td.category == CobolDataCategory.ALPHANUMERIC:
            ir = build_encode_alphanumeric_ir(f"enc_alpha_{fl.name}", td.total_digits)
            return self.inline_ir(ir, {"%p_value": value_str_reg})

        if td.category in (CobolDataCategory.COMP1, CobolDataCategory.COMP2):
            # Convert string to float, then encode
            float_reg = self.fresh_reg()
            self.emit(
                Opcode.CALL_FUNCTION,
                result_reg=float_reg,
                operands=["float", value_str_reg],
            )
            ir = build_encode_float_ir(f"enc_float_{fl.name}", td.byte_length)
            return self.inline_ir(ir, {"%p_float_value": float_reg})

        return self.emit_numeric_encode_from_string(fl, value_str_reg)

    def emit_numeric_encode_from_string(
        self, fl: FieldLayout, value_str_reg: str
    ) -> str:
        """Emit IR to parse a string into digits + sign, then encode numerically."""
        td = fl.type_descriptor
        digits_reg = self.fresh_reg()
        self.emit(
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

        sign_reg = self.fresh_reg()
        self.emit(
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
        elif td.category == CobolDataCategory.BINARY:
            ir = build_encode_binary_ir(
                f"enc_bin_{fl.name}",
                td.total_digits,
                td.byte_length,
                td.signed,
            )
        else:
            ir = build_encode_comp3_ir(f"enc_comp3_{fl.name}", td.total_digits)

        return self.inline_ir(ir, {"%p_digits": digits_reg, "%p_sign_nibble": sign_reg})

    def emit_encode_and_write(
        self,
        region_reg: str,
        fl: FieldLayout,
        value_str_reg: str,
        offset_reg: str = "",
    ) -> None:
        """Encode a string value and write it to the field's region slot."""
        encoded_reg = self.emit_encode_from_string(fl, value_str_reg)
        if not offset_reg:
            offset_reg = self.fresh_reg()
            self.emit(Opcode.CONST, result_reg=offset_reg, operands=[fl.offset])
        self.emit(
            Opcode.WRITE_REGION,
            operands=[region_reg, offset_reg, fl.byte_length, encoded_reg],
        )

    # ── Condition Lowering ───────────────────────────────────────

    def lower_condition(
        self, condition: str, layout: DataLayout, region_reg: str
    ) -> str:
        """Lower a condition — delegates to condition_lowering module."""
        from interpreter.cobol.condition_lowering import (
            lower_condition as _lower_condition,
        )

        return _lower_condition(
            self, condition, layout, region_reg, self._condition_index
        )

    # ── Parse Literal ─────────────────────────────────────────────

    def parse_literal(self, text: str) -> Any:
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
