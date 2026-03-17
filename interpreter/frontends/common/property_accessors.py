"""Common property accessor registration and emit helpers.

Reusable by any frontend that supports property getters/setters
(Kotlin, C#, JavaScript/TypeScript, Scala).
"""

from __future__ import annotations

from interpreter.frontends.context import TreeSitterEmitContext
from interpreter.ir import Opcode


def register_property_accessor(
    ctx: TreeSitterEmitContext, class_name: str, prop_name: str, kind: str
) -> None:
    """Record that *prop_name* on *class_name* has a custom accessor.

    *kind* is ``"get"`` or ``"set"``.
    """
    ctx.property_accessors.setdefault(class_name, {}).setdefault(
        prop_name, set()
    ).add(kind)


def has_property_accessor(
    ctx: TreeSitterEmitContext, class_name: str, prop_name: str, kind: str
) -> bool:
    """Check whether *prop_name* on *class_name* has a custom *kind* accessor."""
    return kind in ctx.property_accessors.get(class_name, {}).get(
        prop_name, set()
    )


def emit_field_load_or_getter(
    ctx: TreeSitterEmitContext,
    obj_reg: str,
    class_name: str,
    field_name: str,
    node,
) -> str:
    """Emit CALL_METHOD for getter if registered, otherwise plain LOAD_FIELD."""
    if has_property_accessor(ctx, class_name, field_name, "get"):
        reg = ctx.fresh_reg()
        ctx.emit(
            Opcode.CALL_METHOD,
            result_reg=reg,
            operands=[obj_reg, f"__get_{field_name}__"],
            node=node,
        )
        return reg
    reg = ctx.fresh_reg()
    ctx.emit(
        Opcode.LOAD_FIELD,
        result_reg=reg,
        operands=[obj_reg, field_name],
        node=node,
    )
    return reg


def emit_field_store_or_setter(
    ctx: TreeSitterEmitContext,
    obj_reg: str,
    class_name: str,
    field_name: str,
    val_reg: str,
    node,
) -> None:
    """Emit CALL_METHOD for setter if registered, otherwise plain STORE_FIELD."""
    if has_property_accessor(ctx, class_name, field_name, "set"):
        ctx.emit(
            Opcode.CALL_METHOD,
            result_reg=ctx.fresh_reg(),
            operands=[obj_reg, f"__set_{field_name}__", val_reg],
            node=node,
        )
        return
    ctx.emit(
        Opcode.STORE_FIELD,
        operands=[obj_reg, field_name, val_reg],
        node=node,
    )
