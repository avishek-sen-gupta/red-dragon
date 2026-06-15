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
from collections.abc import Sequence
from typing import TYPE_CHECKING, Any, Callable

if TYPE_CHECKING:
    from interpreter.cobol.cobol_expression import ExprNode
    from interpreter.cobol.asg_types import CobolASG

from interpreter.cobol.red_dragon_extension_strategy import (
    RedDragonExtensionLoweringStrategy,
)
from interpreter.cobol.alphanumeric import encode_hex_literal, parse_hex_literal
from interpreter.cobol.cobol_constants import BuiltinName, ByteConstants
from interpreter.cobol.cobol_types import CobolDataCategory, CobolTypeDescriptor
from interpreter.cobol.condition_name_index import ConditionNameIndex
from interpreter.cobol.data_filters import align_decimal, left_adjust
from interpreter.cobol.data_layout import DataLayout, FieldLayout
from interpreter.cobol.figurative_constants import (
    COBOL_FIGURATIVE_CONSTANTS,
    COBOL_RAW_FIGURATIVE_BYTES,
)
from interpreter.cobol.sectioned_layout import MaterialisedSectionedLayout
from interpreter.frontend_observer import FrontendObserver
from interpreter.cobol.field_resolution import ResolvedFieldRef
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
from interpreter.func_name import FuncName
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

# Type alias for the dispatch callback signature.
# Any is CobolStatementType — avoided here to prevent a circular import via statement_dispatch.
DispatchFn = Callable[
    ["EmitContext", Any, "MaterialisedSectionedLayout"], None
]  # Any: CobolStatementType, circular-import boundary


class EmitContext:
    """Shared state and emit primitives for COBOL IR lowering."""

    def __init__(
        self,
        dispatch_fn: DispatchFn,
        observer: FrontendObserver | None = None,
        condition_index: ConditionNameIndex = ConditionNameIndex({}),
        extension_strategies: Sequence[RedDragonExtensionLoweringStrategy] = (),
        asg: "CobolASG | None" = None,
    ) -> None:
        from interpreter.cobol.asg_types import CobolASG as _CobolASG

        self._dispatch_fn = dispatch_fn
        self._observer = observer
        self._condition_index = condition_index
        self._extension_strategies = tuple(extension_strategies)
        self._asg: _CobolASG = asg if asg is not None else _CobolASG()
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

    @property
    def extension_strategies(self) -> tuple[RedDragonExtensionLoweringStrategy, ...]:
        return self._extension_strategies

    # ── Core Primitives ───────────────────────────────────────────

    def fresh_reg(self) -> Register:
        name = Register(f"%{self._reg_counter}")
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

    def emit_inst(self, inst: InstructionBase) -> InstructionBase:
        """Emit a typed instruction directly."""
        self._instructions.append(inst)
        return inst

    def const_to_reg(self, value: Any) -> Register:
        """Emit a CONST and return its register."""
        reg = self.fresh_reg()
        self.emit_inst(Const(result_reg=reg, value=value))
        return reg

    def inline_ir(
        self,
        ir_instructions: Sequence[InstructionBase],
        param_regs: dict[str, Register],
    ) -> Register:
        """Inline a generated IR function body, mapping parameter registers.

        Returns the register holding the return value.
        """
        reg_map: dict[str, Register] = dict(param_regs)
        return_reg: Register = NO_REGISTER

        def remap(r: Register) -> Register:
            mapped = reg_map.get(str(r))
            return mapped if mapped is not None else r

        for inst in ir_instructions:
            if isinstance(inst, Label_):
                continue
            if isinstance(inst, Return_):
                if inst.value_reg is not None:
                    resolved = remap(inst.value_reg)
                    resolved_str = str(resolved)
                    if resolved_str.startswith("%"):
                        return_reg = resolved
                    else:
                        return_reg = self.const_to_reg(resolved_str)
                continue

            # Allocate fresh result register and record the mapping
            if inst.result_reg.is_present():
                new_result = self.fresh_reg()
                reg_map[str(inst.result_reg)] = new_result
            else:
                new_result = NO_REGISTER

            # Remap all register operands, then override result_reg with the fresh one
            remapped = inst.map_registers(remap)
            remapped = dataclasses.replace(remapped, result_reg=new_result)
            self.emit_inst(remapped)

        return return_reg

    # ── Statement Dispatch ────────────────────────────────────────

    def lower_statement(
        self, stmt: Any, materialised: MaterialisedSectionedLayout
    ) -> None:  # Any: CobolStatementType, circular-import boundary
        """Dispatch a statement through the injected callback."""
        self._dispatch_fn(self, stmt, materialised)

    # ── Field Reference Resolution ────────────────────────────────

    def resolve_field_ref(
        self,
        name: str,
        materialised: MaterialisedSectionedLayout,
        qualifiers: tuple[str, ...] = (),
        subscripts: tuple["ExprNode", ...] = (),
    ) -> tuple[ResolvedFieldRef, Register]:
        """Resolve a field reference that may contain subscript notation.

        Returns (ResolvedFieldRef, region_register) — the region register is
        determined by which DATA DIVISION section owns the field.

        ``qualifiers`` (``OF``/``IN`` ancestor group names) disambiguate a
        duplicated elementary name (CardDemo CSUTLDTC's two Vstring groups).

        ``name`` is always the bare base name (both feeders — the ProLeap bridge
        and the CICS parser — emit structured subscripts, never ``"NAME(SUB)"``
        strings). ``subscripts`` carries the index expressions as structured
        ``ExprNode``s (literal / field-ref / binop / ...); each is evaluated by the
        expression lowerer, so arithmetic and nested subscripts resolve to their
        real value rather than the old default-1 string-parse fallback
        (red-dragon-l445). A single subscript is supported; two or more raise
        ``NotImplementedError`` (multi-dimensional offset arithmetic is
        red-dragon-cqwx). See red-dragon-6ddr.
        """
        # Deferred import: condition_lowering imports EmitContext, so a top-level
        # import would cycle.
        from interpreter.cobol.condition_lowering import lower_expr_node

        if subscripts:
            if len(subscripts) > 1:
                raise NotImplementedError(
                    f"multi-dimensional subscript not supported for {name!r} "
                    f"({len(subscripts)} subscripts); see red-dragon-cqwx"
                )
            subscript_node = next(iter(subscripts))
        else:
            subscript_node = None
        base_name = name
        fl, region_reg = materialised.resolve(base_name, qualifiers)

        if subscript_node is None:
            offset_reg = self.fresh_reg()
            self.emit_inst(Const(result_reg=offset_reg, value=fl.offset))
            return ResolvedFieldRef(fl=fl, offset_reg=offset_reg), region_reg

        # Evaluate the structured subscript expression to a 1-based index register.
        idx_reg = lower_expr_node(self, subscript_node, materialised)

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

        # Subscript stride vs. accessed-element width.
        #  * stride: how far apart successive occurrences sit.
        #  * access_len: how many bytes one occurrence of THIS field spans.
        # A field that itself carries OCCURS strides by (and accesses) its own
        # element_size. A leaf nested inside an OCCURS group strides by the
        # group's element_size (e.g. CDEMO-MENU-OPT-PGMNAME(idx) strides by the
        # whole CDEMO-MENU-OPT entry, 46 bytes) but accesses only the leaf's own
        # width (8 bytes for PGMNAME X(8)).
        if fl.occurs_count > 0 and fl.element_size > 0:
            elem_size = fl.element_size
            access_len = fl.element_size
        else:
            group_stride = materialised.subscript_stride(base_name)
            access_len = fl.byte_length
            elem_size = group_stride if group_stride > 0 else fl.byte_length
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
            byte_length=access_len,
            redefines=fl.redefines,
            value=fl.value,
        )
        return ResolvedFieldRef(fl=element_fl, offset_reg=final_offset_reg), region_reg

    def has_field(self, name: str, materialised: MaterialisedSectionedLayout) -> bool:
        """Check if a name (possibly subscripted) refers to a known field."""
        return materialised.has_field(name)

    def group_leaf_names(
        self, group_name: str, materialised: MaterialisedSectionedLayout
    ) -> list[str]:
        """Leaf field names of a symbolic-map group (for SEND/RECEIVE MAP lowering)."""
        return materialised.group_leaf_names(group_name)

    def resolve_field_ref_from(
        self, fl: FieldLayout, region_reg: Register
    ) -> ResolvedFieldRef:
        """Resolve a FieldLayout to a ResolvedFieldRef without a name lookup.

        Used when the FieldLayout is already known (e.g. MOVE CORRESPONDING).
        """
        offset_reg = self.fresh_reg()
        self.emit_inst(Const(result_reg=offset_reg, value=fl.offset))
        return ResolvedFieldRef(fl=fl, offset_reg=offset_reg)

    # ── Field Encode / Decode ─────────────────────────────────────

    def emit_field_encode(
        self,
        region_reg: Register,
        fl: FieldLayout,
        value: str,
        offset_reg: Register = NO_REGISTER,
    ) -> None:
        """Emit IR to encode a value and write it to the region."""
        encoded_reg = self.emit_encode_value(fl, value)
        if not offset_reg.is_present():
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

    def emit_encode_value(self, fl: FieldLayout, value: str) -> Register:
        """Emit inline IR to encode a value per the field's type. Returns result register."""
        td = fl.type_descriptor
        if td.blank_when_zero and self._is_zero_value(value):
            return self._emit_ebcdic_spaces(fl.byte_length)
        if td.category == CobolDataCategory.ALPHANUMERIC:
            raw = parse_hex_literal(value)
            if raw is not None:
                return self._emit_hex_literal_bytes(raw, fl.byte_length)
            # A figurative VALUE (SPACES / ZEROS / LOW-VALUES / ...) fills the
            # WHOLE field with its fill character, not the literal keyword text
            # (e.g. PIC X(52) VALUE SPACES is 52 spaces, not "SPACES" + padding).
            # Gated on value_is_figurative so a quoted literal VALUE 'SPACE' is
            # left verbatim. red-dragon-zuhj: surfaced via INSPECT CONVERTING.
            if fl.value_is_figurative and value in COBOL_FIGURATIVE_CONSTANTS:
                if value in COBOL_RAW_FIGURATIVE_BYTES:
                    result = self.fresh_reg()
                    self.emit_inst(
                        Const(
                            result_reg=result,
                            value=[COBOL_RAW_FIGURATIVE_BYTES[value]] * fl.byte_length,
                        )
                    )
                    return result
                return self.emit_encode_alphanumeric(
                    fl.name,
                    COBOL_FIGURATIVE_CONSTANTS[value] * fl.byte_length,
                    td.total_digits,
                    justified_right=td.justified_right,
                )
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

    def _emit_hex_literal_bytes(self, raw: bytes, byte_length: int) -> Register:
        """Emit a Const holding raw hex-literal bytes padded to the field length.

        COBOL hex literals (X'nn') denote raw bytes and bypass ASCII→EBCDIC
        translation; they are stored verbatim into the field region.
        """
        padded = encode_hex_literal(raw, byte_length)
        result = self.fresh_reg()
        self.emit_inst(Const(result_reg=result, value=list(padded)))
        return result

    def emit_fill_raw_byte(
        self,
        region_reg: Register,
        fl: FieldLayout,
        fill_byte: int,
        offset_reg: Register = NO_REGISTER,
    ) -> None:
        """Fill a field's whole region slot with a single raw byte, verbatim.

        Used for MOVE HIGH-VALUES / LOW-VALUES, whose semantics are raw 0xFF /
        0x00 in every receiver position — they must bypass the ASCII→EBCDIC
        alphanumeric encoder (which would corrupt \\xff into 0x6F). The byte is
        written as a literal list of ``byte_length`` copies (red-dragon-raxa).
        """
        result = self.fresh_reg()
        self.emit_inst(Const(result_reg=result, value=[fill_byte] * fl.byte_length))
        if not offset_reg.is_present():
            offset_reg = self.fresh_reg()
            self.emit_inst(Const(result_reg=offset_reg, value=fl.offset))
        self.emit_inst(
            WriteRegion(
                region_reg=region_reg,
                offset_reg=offset_reg,
                length=fl.byte_length,
                value_reg=result,
            ),
        )

    def _emit_ebcdic_spaces(self, byte_length: int) -> Register:
        """Emit IR to create a list of EBCDIC spaces (0x40). Returns result register."""
        length_reg = self.const_to_reg(byte_length)
        space_reg = self.const_to_reg(ByteConstants.EBCDIC_SPACE)
        result = self.fresh_reg()
        self.emit_inst(
            CallFunction(
                result_reg=result,
                func_name=FuncName(BuiltinName.MAKE_LIST),
                args=(length_reg, space_reg),
            ),
        )
        return result

    def emit_encode_alphanumeric(
        self,
        field_name: str,
        value: str,
        length: int,
        justified_right: bool = False,
    ) -> Register:
        """Emit inline alphanumeric encoding IR. Returns result register."""
        value_reg = self.fresh_reg()
        self.emit_inst(Const(result_reg=value_reg, value=f'"{value}"'))

        if justified_right:
            ir = build_encode_alphanumeric_justified_ir(
                f"enc_alpha_just_{field_name}", length
            )
        else:
            ir = build_encode_alphanumeric_ir(f"enc_alpha_{field_name}", length)
        return self.inline_ir(ir, {"%p_value": value_reg})

    def emit_encode_float(
        self, field_name: str, value: str, td: CobolTypeDescriptor
    ) -> Register:
        """Emit inline float encoding IR for COMP-1/COMP-2. Returns result register."""
        float_val = float(value)
        value_reg = self.fresh_reg()
        self.emit_inst(Const(result_reg=value_reg, value=float_val))

        ir = build_encode_float_ir(f"enc_float_{field_name}", td.byte_length)
        return self.inline_ir(ir, {"%p_float_value": value_reg})

    def emit_encode_numeric(
        self, field_name: str, value: str, td: CobolTypeDescriptor
    ) -> Register:
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
        self, region_reg: Register, fl: FieldLayout, offset_reg: Register = NO_REGISTER
    ) -> Register:
        """Emit IR to load and decode a field from the region. Returns decoded value register."""
        if not offset_reg.is_present():
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
        if td.category in (
            CobolDataCategory.ALPHANUMERIC,
            CobolDataCategory.NUMERIC_EDITED,
        ):
            # A numeric-edited field's stored content is its formatted character
            # string; read it back as characters (its display form).
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

    def emit_decode_zoned_display(
        self, region_reg: Register, fl: FieldLayout, offset_reg: Register = NO_REGISTER
    ) -> Register:
        """Emit IR to read a zoned (USAGE DISPLAY) numeric field's raw character
        representation, decoded as alphanumeric (its zoned digit characters).

        Unlike emit_decode_field — which decodes a zoned field to a numeric value
        and so loses leading zeros/width — this returns the sending field's actual
        digit characters (e.g. PIC 9(11) value 11 -> "00000000011"). Used by MOVE
        when a numeric-DISPLAY source feeds an alphanumeric receiver, where COBOL
        moves the sending field's characters left-justified (red-dragon-0fqr).
        """
        if not offset_reg.is_present():
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
        ir = build_decode_alphanumeric_ir(f"dec_zoned_disp_{fl.name}")
        return self.inline_ir(ir, {"%p_data": data_reg})

    # ── String Conversion Helpers ─────────────────────────────────

    def emit_to_string(self, value_reg: Register) -> Register:
        """Emit IR to convert a value to a string."""
        result = self.fresh_reg()
        self.emit_inst(
            CallFunction(
                result_reg=result,
                func_name=FuncName("str"),
                args=(value_reg,),
            ),
        )
        return result

    def _emit_blank_when_zero_wrap(
        self, encoded_reg: Register, value_str_reg: Register, byte_length: int
    ) -> Register:
        """Wrap encoded bytes with BLANK WHEN ZERO check via builtin."""
        result = self.fresh_reg()
        length_reg = self.const_to_reg(byte_length)
        self.emit_inst(
            CallFunction(
                result_reg=result,
                func_name=FuncName(BuiltinName.COBOL_BLANK_WHEN_ZERO),
                args=(encoded_reg, value_str_reg, length_reg),
            ),
        )
        return result

    def emit_encode_from_string(
        self, fl: FieldLayout, value_str_reg: Register
    ) -> Register:
        """Emit encoding IR from a string value register."""
        td = fl.type_descriptor
        if td.category == CobolDataCategory.NUMERIC_EDITED:
            # Apply the edit mask to the numeric value, then store the resulting
            # character string as alphanumeric (the formatted bytes ARE the
            # field's content). Mirrors GnuCOBOL's cob_move_edited.
            formatted_reg = self.fresh_reg()
            pic_reg = self.const_to_reg(f'"{td.pic_string}"')
            self.emit_inst(
                CallFunction(
                    result_reg=formatted_reg,
                    func_name=FuncName(BuiltinName.COBOL_APPLY_EDIT_PICTURE),
                    args=(value_str_reg, pic_reg),
                ),
            )
            ir = build_encode_alphanumeric_ir(f"enc_edited_{fl.name}", td.total_digits)
            return self.inline_ir(ir, {"%p_value": formatted_reg})

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
                    func_name=FuncName("float"),
                    args=(value_str_reg,),
                ),
            )
            ir = build_encode_float_ir(f"enc_float_{fl.name}", td.byte_length)
            encoded = self.inline_ir(ir, {"%p_float_value": float_reg})
            if td.blank_when_zero:
                return self._emit_blank_when_zero_wrap(
                    encoded, value_str_reg, fl.byte_length
                )
            return encoded

        if td.category == CobolDataCategory.BINARY:
            # BINARY stores as a raw big-endian integer whose range is determined
            # by byte width (2/4/8), not decimal digit count. Decimal truncation
            # via COBOL_PREPARE_DIGITS would zero out values that exceed the digit
            # count (e.g. 50000 in PIC 9(4) → "0000" → 0). Convert the string
            # directly to int and pack as bytes instead.
            float_reg = self.fresh_reg()
            self.emit_inst(
                CallFunction(
                    result_reg=float_reg,
                    func_name=FuncName("float"),
                    args=(value_str_reg,),
                ),
            )
            int_reg = self.fresh_reg()
            self.emit_inst(
                CallFunction(
                    result_reg=int_reg,
                    func_name=FuncName("int"),
                    args=(float_reg,),
                ),
            )
            byte_count_reg = self.const_to_reg(td.byte_length)
            signed_reg = self.const_to_reg(td.signed)
            result = self.fresh_reg()
            self.emit_inst(
                CallFunction(
                    result_reg=result,
                    func_name=FuncName(BuiltinName.INT_TO_BINARY_BYTES),
                    args=(int_reg, byte_count_reg, signed_reg),
                ),
            )
            return result

        encoded = self.emit_numeric_encode_from_string(fl, value_str_reg)
        if td.blank_when_zero:
            return self._emit_blank_when_zero_wrap(
                encoded, value_str_reg, fl.byte_length
            )
        return encoded

    def emit_numeric_encode_from_string(
        self, fl: FieldLayout, value_str_reg: Register
    ) -> Register:
        """Emit IR to parse a string into digits + sign, then encode numerically."""
        td = fl.type_descriptor
        total_digits_reg = self.const_to_reg(td.total_digits)
        decimal_digits_reg = self.const_to_reg(td.decimal_digits)
        signed_reg = self.const_to_reg(td.signed)
        digits_reg = self.fresh_reg()
        self.emit_inst(
            CallFunction(
                result_reg=digits_reg,
                func_name=FuncName(BuiltinName.COBOL_PREPARE_DIGITS),
                args=(
                    value_str_reg,
                    total_digits_reg,
                    decimal_digits_reg,
                    signed_reg,
                ),
            ),
        )

        signed_reg2 = self.const_to_reg(td.signed)
        sign_reg = self.fresh_reg()
        self.emit_inst(
            CallFunction(
                result_reg=sign_reg,
                func_name=FuncName(BuiltinName.COBOL_PREPARE_SIGN),
                args=(value_str_reg, signed_reg2),
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
        region_reg: Register,
        fl: FieldLayout,
        value_str_reg: Register,
        offset_reg: Register = NO_REGISTER,
    ) -> None:
        """Encode a string value and write it to the field's region slot."""
        encoded_reg = self.emit_encode_from_string(fl, value_str_reg)
        if not offset_reg.is_present():
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
        self, condition: dict, materialised: MaterialisedSectionedLayout
    ) -> Register:
        """Lower a condition — delegates to condition_lowering module."""
        from interpreter.cobol.condition_lowering import (
            lower_condition as _lower_condition,
        )

        return _lower_condition(self, condition, materialised, self._condition_index)

    # ── File I/O Status Helper ────────────────────────────────────

    def emit_file_status_update(
        self,
        file_name: str,
        status_reg: Register,
        materialised: MaterialisedSectionedLayout,
    ) -> None:
        """Write I/O status code to the FILE STATUS variable if declared."""
        from interpreter.cobol.cobol_statements import (
            FileControlEntry,
        )  # avoid circular at module level

        fce: "FileControlEntry | None" = next(
            (e for e in self._asg.file_control if e.file_name == file_name), None
        )
        if fce is None or not fce.file_status_var:
            return
        if not materialised.has_field(fce.file_status_var):
            return
        target_ref, target_rr = self.resolve_field_ref(
            fce.file_status_var, materialised
        )
        str_reg = self.emit_to_string(status_reg)
        self.emit_encode_and_write(
            target_rr, target_ref.fl, str_reg, target_ref.offset_reg
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
