"""PointerLowering — ADDRESS OF, pointer stores and LINKAGE rebinding for one statement."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass

from cobol_asg.cobol_expression import JsonExpr, expr_from_dict
from cobol_asg.cobol_statements import SetStatement
from cobol_asg.operand_kind import OperandKind
from cobol_asg.set_operand import SetOperand
from cobol_asg.source_span import SourceSpan
from cobol_memory.field_extent import FieldExtent
from cobol_memory.region_id import RegionId
from interpreter.cobol.cobol_constants import BuiltinName
from interpreter.cobol.emit_context import EmitContext
from interpreter.cobol.field_resolution import ResolvedFieldRef
from interpreter.cobol.linkage_binding import LinkageBinding
from interpreter.cobol.lower_data_division import linkage_delta_var, linkage_region_var
from interpreter.cobol.sectioned_layout import MaterialisedSectionedLayout
from interpreter.func_name import FuncName
from interpreter.instructions import AllocRegion, Binop, CallFunction, LoadVar, StoreVar
from interpreter.operator_kind import resolve_binop
from interpreter.register import Register

_NOT_REBINDABLE = "SET ADDRESS OF {name}: only a LINKAGE 01 or 77 item can be rebound"


@dataclass(frozen=True)
class PointerLowering:
    """Lowers pointer operations for one statement: its context, layout and span."""

    ctx: EmitContext
    materialised: MaterialisedSectionedLayout
    span: SourceSpan | None

    def address_of(
        self, name: str, qualifiers: Sequence[str], subscripts: Sequence[JsonExpr]
    ) -> Register:
        """The item's address: its region register plus its offset."""
        ref, region_reg = self.ctx.resolve_field_ref(
            name,
            self.materialised,
            tuple(qualifiers),
            subscripts=tuple(expr_from_dict(s) for s in subscripts),
            span=self.span,
        )
        address = self.ctx.fresh_reg()
        self.ctx.emit_inst(
            Binop(
                result_reg=address,
                operator=resolve_binop("+"),
                left=region_reg,
                right=ref.offset_reg,
            ),
            span=self.span,
        )
        return address

    def address_argument(
        self, name: str, extent: FieldExtent
    ) -> tuple[Register, Register]:
        """ADDRESS OF an item as a CALL argument: a fresh copy holding the address
        as the addressing mode's binary, and its offset 0."""
        width = self.ctx.addressing_mode.pointer_type.byte_length
        copy = self.ctx.fresh_reg()
        self.ctx.emit_inst(
            AllocRegion(
                result_reg=copy, size_reg=self.ctx.const_to_reg(width, span=self.span)
            ),
            span=self.span,
        )
        zero = self.ctx.const_to_reg(0, span=self.span)
        self.write_address(copy, zero, self.address_of(name, (), ()), width, extent)
        return copy, zero

    def address(self, operand: SetOperand) -> Register:
        """ADDRESS OF an item, NULL, or the contents of a POINTER item."""
        if operand.kind is OperandKind.ADDRESS_OF:
            return self.address_of(operand.name, operand.qualifiers, operand.subscripts)
        if operand.kind is OperandKind.FIGURATIVE:
            return self.ctx.const_to_reg(0, span=self.span)
        return self.read(operand)

    def read(self, operand: SetOperand) -> Register:
        ref, region_reg = self.resolve(operand)
        return self.ctx.emit_decode_field(
            region_reg, ref.fl, ref.offset_reg, extent=ref.extent, span=self.span
        )

    def resolve(self, operand: SetOperand) -> tuple[ResolvedFieldRef, Register]:
        return self.ctx.resolve_field_ref(
            operand.name,
            self.materialised,
            operand.qualifiers,
            subscripts=tuple(expr_from_dict(s) for s in operand.subscripts),
            span=self.span,
        )

    def store(self, operand: SetOperand, address: Register) -> None:
        """Write an address into a POINTER item as the addressing mode's binary;
        one too large for the item raises in the encoding."""
        ref, region_reg = self.resolve(operand)
        self.write_address(
            region_reg, ref.offset_reg, address, ref.fl.byte_length, ref.extent
        )

    def write_address(
        self,
        region_reg: Register,
        offset_reg: Register,
        address: Register,
        width: int,
        extent: FieldExtent,
    ) -> None:
        data = self.ctx.fresh_reg()
        self.ctx.emit_inst(
            CallFunction(
                result_reg=data,
                func_name=FuncName(BuiltinName.INT_TO_BINARY_BYTES),
                args=(
                    address,
                    self.ctx.const_to_reg(width, span=self.span),
                    self.ctx.const_to_reg(True, span=self.span),
                ),
            ),
            span=self.span,
        )
        self.ctx._emit_write_region(
            region_reg, offset_reg, data, width, extent, span=self.span
        )

    def set_one(self, target: SetOperand, address: Register) -> None:
        if target.kind is OperandKind.ADDRESS_OF:
            self.rebind(target, address)
            return
        self.store(target, address)

    def rebind(self, target: SetOperand, address: Register) -> None:
        """Rebind a LINKAGE 01 or 77 item to ``address``: its region register
        becomes the address and its shift puts the item's static start there, in
        its variables and in the registers every later access reads."""
        binding = self.rebindable(target)
        delta = self.ctx.const_to_reg(-binding.start, span=self.span)
        region_var = linkage_region_var(binding.name)
        delta_var = linkage_delta_var(binding.name)
        self.ctx.emit_inst(StoreVar(name=region_var, value_reg=address), span=self.span)
        self.ctx.emit_inst(StoreVar(name=delta_var, value_reg=delta), span=self.span)
        self.ctx.emit_inst(
            LoadVar(result_reg=binding.region_reg, name=region_var), span=self.span
        )
        self.ctx.emit_inst(
            LoadVar(result_reg=binding.delta_reg, name=delta_var), span=self.span
        )

    def rebindable(self, target: SetOperand) -> LinkageBinding:
        """The binding SET ADDRESS OF ``target`` rebinds: a LINKAGE 01 or 77 item's."""
        fl, _, region = self.materialised.resolve_with_region(
            target.name, target.qualifiers
        )
        if region is not RegionId.LINKAGE:
            raise ValueError(_NOT_REBINDABLE.format(name=target.name))
        binding = self.materialised.linkage_binding(fl)
        if binding.name.upper() != target.name.upper():
            raise ValueError(_NOT_REBINDABLE.format(name=target.name))
        return binding

    def step(self, operand: SetOperand) -> Register:
        """A SET ... BY amount: a data item's value or a literal."""
        if operand.kind is not OperandKind.REF:
            return self.ctx.const_to_reg(
                self.ctx.parse_literal(operand.text), span=self.span
            )
        return self.read(operand)

    def move(self, stmt: SetStatement) -> None:
        """SET p UP|DOWN BY n: each target's address moved by n bytes."""
        amount = self.step(stmt.values[0])
        operator = resolve_binop("+" if stmt.by_type == "UP" else "-")
        for target in stmt.targets:
            moved = self.ctx.fresh_reg()
            self.ctx.emit_inst(
                Binop(
                    result_reg=moved,
                    operator=operator,
                    left=self.read(target),
                    right=amount,
                ),
                span=self.span,
            )
            self.store(target, moved)
