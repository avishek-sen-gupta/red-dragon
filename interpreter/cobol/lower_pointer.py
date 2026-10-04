"""Pointer SET lowering: SET p TO address, SET ADDRESS OF lk TO address, SET p UP|DOWN BY n."""

from __future__ import annotations

from cobol_asg.cobol_statements import SetStatement
from cobol_asg.operand_kind import OperandKind
from interpreter.cobol.emit_context import EmitContext
from interpreter.cobol.pointer_lowering import PointerLowering
from interpreter.cobol.sectioned_layout import MaterialisedSectionedLayout


def is_pointer_set(
    ctx: EmitContext, stmt: SetStatement, materialised: MaterialisedSectionedLayout
) -> bool:
    """A SET whose targets are ADDRESS OF items or POINTER items."""
    return any(
        target.kind is OperandKind.ADDRESS_OF
        or (
            ctx.has_field(target.name, materialised)
            and materialised.resolve_with_region(target.name, target.qualifiers)[
                0
            ].holds_address
        )
        for target in stmt.targets
    )


def lower_pointer_set(
    ctx: EmitContext, stmt: SetStatement, materialised: MaterialisedSectionedLayout
) -> None:
    """SET p TO address, SET ADDRESS OF lk TO address, SET p UP|DOWN BY n."""
    pointers = PointerLowering(ctx, materialised, stmt.span)
    if stmt.set_type == "BY":
        pointers.move(stmt)
        return
    address = pointers.address(stmt.values[0])
    for target in stmt.targets:
        pointers.set_one(target, address)
