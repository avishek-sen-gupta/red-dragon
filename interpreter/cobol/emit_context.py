"""EmitContext — shared mutable state and emit primitives for COBOL lowering.

All lowering functions receive an EmitContext and operate on it.  The context
holds the instruction buffer, register/label counters, section→paragraph
lookup, and convenience methods for emitting IR.

Circular dependency between lowering functions and the statement dispatcher
is broken by injecting a *dispatch callback* at construction time.
"""

from __future__ import annotations

import dataclasses
import logging
from typing import Any, Callable

from interpreter.cobol.cobol_constants import BuiltinName, ByteConstants
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
    build_decode_zoned_separate_ir,
    build_encode_alphanumeric_ir,
    build_encode_alphanumeric_justified_ir,
    build_encode_comp3_ir,
    build_encode_zoned_ir,
    build_encode_zoned_separate_ir,
    build_encode_binary_ir,
    build_decode_binary_ir,
    build_encode_float_ir,
    build_decode_float_ir,
)
from interpreter.operator_kind import resolve_binop
from interpreter.ir import Opcode, CodeLabel, NO_LABEL
from interpreter.instructions import (
    InstructionBase,
    Binop,
    CallFunction,
    Const,
    Instruction,
    Label_,
    LoadRegion,
    Return_,
    WriteRegion,
)
from interpreter.register import Register, NO_REGISTER

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
        self._instructions: list[InstructionBase] = []
        self._reg_counter: int = 0
        self._label_counter: int = 0
        self._section_paragraphs: dict[str, list[str]] = {}

    # ── Properties ────────────────────────────────────────────────

    @property
    def instructions(self) -> list[InstructionBase]:
        return self._instructions

    @property
    def section_paragraphs(self) -> dict[str, list[str]]:
        return self._section_paragraphs

    @section_paragraphs.setter
    def section_paragraphs(self, value: dict[str, list[str]]) -> None:
        self._section_paragraphs = value

    # ── Core Primitives ───────────────────────────────────────────

    def fresh_reg(self) -> Register:
        name = Register(f"%r{self._reg_counter}")
        self._reg_counter += 1
        return name

    def fresh_label(self, prefix: str) -> CodeLabel:
        name = CodeLabel(f"{prefix}_{self._label_counter}")
        self._label_counter += 1
        return name

    def fresh_name(self, prefix: str) -> str:
        """Generate a unique name string (for variables, not labels)."""
        name = f"{prefix}_{self._label_counter}"
        self._label_counter += 1
        return name

    def emit_inst(self, inst: Instruction) -> Instruction:
        """Emit a typed instruction directly."""
        self._instructions.append(inst)
        return inst

    def const_to_reg(self, value: Any) -> str:
        """Emit a CONST and return its register."""
        reg = self.fresh_reg()
        self.emit_inst(Const(result_reg=reg, value=value))
        return reg

    def inline_ir(
        self, ir_instructions: list[Instruction], param_regs: dict[str, str]
    ) -> str:
        """Inline a generated IR function body, mapping parameter registers.

        Returns the register holding the return value.
        """
        reg_map: dict[str, str] = dict(param_regs)
        return_reg = ""

        def remap(r: Register) -> Register:
            mapped = reg_map.get(str(r))
            return Register(str(mapped)) if mapped else r

        for inst in ir_instructions:
            if isinstance(inst, Label_):
                continue
            if isinstance(inst, Return_):
                resolved = remap(inst.value_reg)
                resolved_str = str(resolved)
                return_reg = (
                    resolved_str
                    if resolved_str.startswith("%")
                    else self.const_to_reg(resolved)
                )
                continue

            # Allocate fresh result register and record the mapping
            if inst.result_reg.is_present():
                new_result = self.fresh_reg()
                reg_map[str(inst.result_reg)] = str(new_result)
            else:
                new_result = NO_REGISTER

            # Remap all register operands, then override result_reg with the fresh one
            remapped = inst.map_registers(remap)
            remapped = dataclasses.replace(remapped, result_reg=new_result)
            self.emit_inst(remapped)

        return return_reg

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
            self.emit_inst(Const(result_reg=offset_reg, value=fl.offset))
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
        self.emit_inst(
            Binop(
                result_reg=idx_minus_one,
                operator=resolve_binop("-"),
                left=idx_reg,
                right=one_reg,
            ),
        )

        elem_size = fl.element_size if fl.element_size > 0 else fl.byte_length
        elem_size_reg = self.const_to_reg(elem_size)
        displacement = self.fresh_reg()
        self.emit_inst(
            Binop(
                result_reg=displacement,
                operator=resolve_binop("*"),
                left=idx_minus_one,
                right=elem_size_reg,
            ),
        )

        base_offset_reg = self.const_to_reg(fl.offset)
        final_offset_reg = self.fresh_reg()
        self.emit_inst(
            Binop(
                result_reg=final_offset_reg,
                operator=resolve_binop("+"),
                left=base_offset_reg,
                right=displacement,
            ),
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
            self.emit_inst(Const(result_reg=offset_reg, value=fl.offset))
        self.emit_inst(
            WriteRegion(
                region_reg=region_reg,
                offset_reg=offset_reg,
                length=fl.byte_length,
                value_reg=encoded_reg,
            ),
        )

    def emit_encode_value(self, fl: FieldLayout, value: str) -> str:
        """Emit inline IR to encode a value per the field's type. Returns result register."""
        td = fl.type_descriptor
        if td.blank_when_zero and self._is_zero_value(value):
            return self._emit_ebcdic_spaces(fl.byte_length)
        if td.category == CobolDataCategory.ALPHANUMERIC:
            return self.emit_encode_alphanumeric(
                fl.name, value, td.total_digits, justified_right=td.justified_right
            )
        if td.category in (CobolDataCategory.COMP1, CobolDataCategory.COMP2):
            return self.emit_encode_float(fl.name, value, td)
        return self.emit_encode_numeric(fl.name, value, td)

    def _is_zero_value(self, value: str) -> bool:
        """Check if a literal value is numerically zero."""
        try:
            return float(value) == 0.0
        except (ValueError, TypeError):
            return False

    def _emit_ebcdic_spaces(self, byte_length: int) -> str:
        """Emit IR to create a list of EBCDIC spaces (0x40). Returns result register."""
        length_reg = self.const_to_reg(byte_length)
        space_reg = self.const_to_reg(ByteConstants.EBCDIC_SPACE)
        result = self.fresh_reg()
        self.emit_inst(
            CallFunction(
                result_reg=result,
                func_name=BuiltinName.MAKE_LIST,
                args=(Register(str(length_reg)), Register(str(space_reg))),
            ),
        )
        return result

    def emit_encode_alphanumeric(
        self,
        field_name: str,
        value: str,
        length: int,
        justified_right: bool = False,
    ) -> str:
        """Emit inline alphanumeric encoding IR. Returns result register."""
        value_reg = self.fresh_reg()
        self.emit_inst(Const(result_reg=value_reg, value=value))

        if justified_right:
            ir = build_encode_alphanumeric_justified_ir(
                f"enc_alpha_just_{field_name}", length
            )
        else:
            ir = build_encode_alphanumeric_ir(f"enc_alpha_{field_name}", length)
        return self.inline_ir(ir, {"%p_value": value_reg})

    def emit_encode_float(self, field_name: str, value: str, td: Any) -> str:
        """Emit inline float encoding IR for COMP-1/COMP-2. Returns result register."""
        float_val = float(value)
        value_reg = self.fresh_reg()
        self.emit_inst(Const(result_reg=value_reg, value=float_val))

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
            sign_nibble = ByteConstants.SIGN_NIBBLE_UNSIGNED
        elif negative and any(d != 0 for d in digits):
            sign_nibble = ByteConstants.SIGN_NIBBLE_NEGATIVE
        else:
            sign_nibble = ByteConstants.SIGN_NIBBLE_POSITIVE

        digits_reg = self.fresh_reg()
        self.emit_inst(Const(result_reg=digits_reg, value=digits))

        sign_reg = self.fresh_reg()
        self.emit_inst(Const(result_reg=sign_reg, value=sign_nibble))

        if td.category == CobolDataCategory.ZONED_DECIMAL:
            if td.sign_separate:
                ir = build_encode_zoned_separate_ir(
                    f"enc_zoned_sep_{field_name}",
                    td.total_digits,
                    sign_leading=td.sign_leading,
                )
            else:
                ir = build_encode_zoned_ir(
                    f"enc_zoned_{field_name}",
                    td.total_digits,
                    sign_leading=td.sign_leading,
                )
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
            self.emit_inst(Const(result_reg=offset_reg, value=fl.offset))

        data_reg = self.fresh_reg()
        self.emit_inst(
            LoadRegion(
                result_reg=data_reg,
                region_reg=region_reg,
                offset_reg=offset_reg,
                length=fl.byte_length,
            ),
        )

        td = fl.type_descriptor
        if td.category == CobolDataCategory.ALPHANUMERIC:
            ir = build_decode_alphanumeric_ir(f"dec_alpha_{fl.name}")
        elif td.category == CobolDataCategory.ZONED_DECIMAL:
            if td.sign_separate:
                ir = build_decode_zoned_separate_ir(
                    f"dec_zoned_sep_{fl.name}",
                    td.total_digits,
                    td.decimal_digits,
                    sign_leading=td.sign_leading,
                )
            else:
                ir = build_decode_zoned_ir(
                    f"dec_zoned_{fl.name}",
                    td.total_digits,
                    td.decimal_digits,
                    sign_leading=td.sign_leading,
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
        self.emit_inst(
            CallFunction(
                result_reg=result,
                func_name="str",
                args=(Register(str(value_reg)),),
            ),
        )
        return result

    def _emit_blank_when_zero_wrap(
        self, encoded_reg: str, value_str_reg: str, byte_length: int
    ) -> str:
        """Wrap encoded bytes with BLANK WHEN ZERO check via builtin."""
        result = self.fresh_reg()
        length_reg = self.const_to_reg(byte_length)
        self.emit_inst(
            CallFunction(
                result_reg=result,
                func_name=BuiltinName.COBOL_BLANK_WHEN_ZERO,
                args=(
                    Register(str(encoded_reg)),
                    Register(str(value_str_reg)),
                    Register(str(length_reg)),
                ),
            ),
        )
        return result

    def emit_encode_from_string(self, fl: FieldLayout, value_str_reg: str) -> str:
        """Emit encoding IR from a string value register."""
        td = fl.type_descriptor
        if td.category == CobolDataCategory.ALPHANUMERIC:
            if td.justified_right:
                ir = build_encode_alphanumeric_justified_ir(
                    f"enc_alpha_just_{fl.name}", td.total_digits
                )
            else:
                ir = build_encode_alphanumeric_ir(
                    f"enc_alpha_{fl.name}", td.total_digits
                )
            return self.inline_ir(ir, {"%p_value": value_str_reg})

        if td.category in (CobolDataCategory.COMP1, CobolDataCategory.COMP2):
            # Convert string to float, then encode
            float_reg = self.fresh_reg()
            self.emit_inst(
                CallFunction(
                    result_reg=float_reg,
                    func_name="float",
                    args=(Register(str(value_str_reg)),),
                ),
            )
            ir = build_encode_float_ir(f"enc_float_{fl.name}", td.byte_length)
            encoded = self.inline_ir(ir, {"%p_float_value": float_reg})
            if td.blank_when_zero:
                return self._emit_blank_when_zero_wrap(
                    encoded, value_str_reg, fl.byte_length
                )
            return encoded

        encoded = self.emit_numeric_encode_from_string(fl, value_str_reg)
        if td.blank_when_zero:
            return self._emit_blank_when_zero_wrap(
                encoded, value_str_reg, fl.byte_length
            )
        return encoded

    def emit_numeric_encode_from_string(
        self, fl: FieldLayout, value_str_reg: str
    ) -> str:
        """Emit IR to parse a string into digits + sign, then encode numerically."""
        td = fl.type_descriptor
        total_digits_reg = self.const_to_reg(td.total_digits)
        decimal_digits_reg = self.const_to_reg(td.decimal_digits)
        signed_reg = self.const_to_reg(td.signed)
        digits_reg = self.fresh_reg()
        self.emit_inst(
            CallFunction(
                result_reg=digits_reg,
                func_name=BuiltinName.COBOL_PREPARE_DIGITS,
                args=(
                    Register(str(value_str_reg)),
                    Register(str(total_digits_reg)),
                    Register(str(decimal_digits_reg)),
                    Register(str(signed_reg)),
                ),
            ),
        )

        signed_reg2 = self.const_to_reg(td.signed)
        sign_reg = self.fresh_reg()
        self.emit_inst(
            CallFunction(
                result_reg=sign_reg,
                func_name=BuiltinName.COBOL_PREPARE_SIGN,
                args=(Register(str(value_str_reg)), Register(str(signed_reg2))),
            ),
        )

        if td.category == CobolDataCategory.ZONED_DECIMAL:
            if td.sign_separate:
                ir = build_encode_zoned_separate_ir(
                    f"enc_zoned_sep_{fl.name}",
                    td.total_digits,
                    sign_leading=td.sign_leading,
                )
            else:
                ir = build_encode_zoned_ir(
                    f"enc_zoned_{fl.name}",
                    td.total_digits,
                    sign_leading=td.sign_leading,
                )
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
            self.emit_inst(Const(result_reg=offset_reg, value=fl.offset))
        self.emit_inst(
            WriteRegion(
                region_reg=region_reg,
                offset_reg=offset_reg,
                length=fl.byte_length,
                value_reg=encoded_reg,
            ),
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
