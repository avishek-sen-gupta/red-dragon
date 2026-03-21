"""Kotlin-specific declaration lowerers -- pure functions taking (ctx, node)."""

from __future__ import annotations

from interpreter.frontends.context import TreeSitterEmitContext

from interpreter.ir import Opcode
from interpreter import constants
from interpreter.frontends.kotlin.node_types import KotlinNodeType as KNT
from interpreter.frontends.type_extraction import (
    extract_normalized_type_from_child,
)
from interpreter.frontends.common.declarations import (
    FieldInit,
    emit_field_initializers,
    emit_synthetic_init,
)
from interpreter.type_expr import ScalarType
from interpreter.frontends.common.property_accessors import register_property_accessor

# -- property declaration ----------------------------------------------


def _extract_property_name(ctx: TreeSitterEmitContext, var_decl_node) -> str:
    """Extract name from variable_declaration -> simple_identifier."""
    id_node = next(
        (c for c in var_decl_node.children if c.type == KNT.SIMPLE_IDENTIFIER),
        None,
    )
    return ctx.node_text(id_node) if id_node else "__unknown"


def _find_property_value(ctx: TreeSitterEmitContext, node) -> object | None:
    """Find the value expression after '=' in a property_declaration."""
    found_eq = False
    for child in node.children:
        if found_eq and child.is_named:
            return child
        if ctx.node_text(child) == "=":
            found_eq = True
    return None


def _lower_multi_variable_destructure(
    ctx: TreeSitterEmitContext, multi_var_node, parent_node
) -> None:
    """Lower `val (a, b) = expr` -- emit LOAD_INDEX + STORE_VAR per element."""
    value_node = _find_property_value(ctx, parent_node)
    if value_node:
        val_reg = ctx.lower_expr(value_node)
    else:
        val_reg = ctx.fresh_reg()
        ctx.emit(
            Opcode.CONST,
            result_reg=val_reg,
            operands=[ctx.constants.none_literal],
        )

    var_decls = [
        c for c in multi_var_node.children if c.type == KNT.VARIABLE_DECLARATION
    ]
    for i, var_decl in enumerate(var_decls):
        var_name = _extract_property_name(ctx, var_decl)
        idx_reg = ctx.fresh_reg()
        ctx.emit(Opcode.CONST, result_reg=idx_reg, operands=[str(i)])
        elem_reg = ctx.fresh_reg()
        ctx.emit(
            Opcode.LOAD_INDEX,
            result_reg=elem_reg,
            operands=[val_reg, idx_reg],
            node=var_decl,
        )
        ctx.emit(
            Opcode.DECL_VAR,
            operands=[var_name, elem_reg],
            node=parent_node,
        )


def lower_property_decl(ctx: TreeSitterEmitContext, node) -> None:
    multi_var_decl = next(
        (c for c in node.children if c.type == KNT.MULTI_VARIABLE_DECLARATION),
        None,
    )

    if multi_var_decl is not None:
        _lower_multi_variable_destructure(ctx, multi_var_decl, node)
        return

    var_decl = next(
        (c for c in node.children if c.type == KNT.VARIABLE_DECLARATION),
        None,
    )
    raw_name = _extract_property_name(ctx, var_decl) if var_decl else "__unknown"
    var_name = ctx.declare_block_var(raw_name)

    # Extract type from the variable_declaration child
    type_hint = (
        extract_normalized_type_from_child(
            ctx, var_decl, (KNT.USER_TYPE, KNT.NULLABLE_TYPE), ctx.type_map
        )
        if var_decl
        else ""
    )

    # Find the value expression: skip keywords, type annotations, '='
    value_node = _find_property_value(ctx, node)

    if value_node:
        val_reg = ctx.lower_expr(value_node)
    else:
        val_reg = ctx.fresh_reg()
        ctx.emit(
            Opcode.CONST,
            result_reg=val_reg,
            operands=[ctx.constants.none_literal],
        )
    ctx.emit(
        Opcode.DECL_VAR,
        operands=[var_name, val_reg],
        node=node,
    )
    ctx.seed_var_type(var_name, type_hint)


# -- function declaration ----------------------------------------------


def _emit_this_param(ctx: TreeSitterEmitContext) -> None:
    """Emit ``SYMBOLIC param:this`` + ``STORE_VAR this`` for instance methods."""
    param_reg = ctx.fresh_reg()
    class_type = ScalarType(ctx._current_class_name)
    ctx.emit(
        Opcode.SYMBOLIC,
        result_reg=param_reg,
        operands=[f"{constants.PARAM_PREFIX}this"],
    )
    ctx.seed_register_type(param_reg, class_type)
    ctx.seed_param_type("this", class_type)
    ctx.emit(
        Opcode.DECL_VAR,
        operands=["this", param_reg],
    )
    ctx.seed_var_type("this", class_type)


def _lower_kotlin_params(ctx: TreeSitterEmitContext, params_node) -> None:
    children = params_node.children
    param_index = 0
    i = 0
    while i < len(children):
        child = children[i]
        if child.type == KNT.PARAMETER:
            id_node = next(
                (c for c in child.children if c.type == KNT.SIMPLE_IDENTIFIER),
                None,
            )
            if id_node:
                pname = ctx.node_text(id_node)
                type_hint = extract_normalized_type_from_child(
                    ctx, child, (KNT.USER_TYPE, KNT.NULLABLE_TYPE), ctx.type_map
                )
                ctx.emit(
                    Opcode.SYMBOLIC,
                    result_reg=ctx.fresh_reg(),
                    operands=[f"{constants.PARAM_PREFIX}{pname}"],
                    node=child,
                )
                ctx.seed_register_type(f"%{ctx.reg_counter - 1}", type_hint)
                ctx.seed_param_type(pname, type_hint)
                ctx.emit(
                    Opcode.DECL_VAR,
                    operands=[pname, f"%{ctx.reg_counter - 1}"],
                )
                ctx.seed_var_type(pname, type_hint)
                # Kotlin default values are siblings: parameter = value
                if (
                    i + 2 < len(children)
                    and children[i + 1].type == "="
                    and children[i + 1].child_count == 0
                ):
                    default_value_node = children[i + 2]
                    from interpreter.frontends.common.default_params import (
                        emit_default_param_guard,
                    )

                    emit_default_param_guard(
                        ctx, pname, param_index, default_value_node
                    )
                    i += 2  # skip = and default value
                param_index += 1
        i += 1


def _lower_function_body(ctx: TreeSitterEmitContext, body_node) -> str:
    """Lower function_body which wraps the actual block or expression.

    Returns the register of the last expression if the body is
    expression-bodied (e.g. ``fun f() = 42``), otherwise returns empty string.
    """
    last_reg = ""
    for child in body_node.children:
        if child.type in ("{", "}", "="):
            continue
        if child.is_named:
            is_stmt = (
                ctx.stmt_dispatch.get(child.type) is not None
                or child.type in ctx.constants.block_node_types
            )
            if is_stmt:
                ctx.lower_stmt(child)
                last_reg = ""
            else:
                last_reg = ctx.lower_expr(child)
    return last_reg


def lower_function_decl(
    ctx: TreeSitterEmitContext, node, inject_this: bool = False
) -> None:
    name_node = next(
        (c for c in node.children if c.type == KNT.SIMPLE_IDENTIFIER),
        None,
    )
    params_node = next(
        (c for c in node.children if c.type == KNT.FUNCTION_VALUE_PARAMETERS),
        None,
    )
    body_node = next(
        (c for c in node.children if c.type == KNT.FUNCTION_BODY),
        None,
    )

    func_name = ctx.node_text(name_node) if name_node else "__anon"
    func_label = ctx.fresh_label(f"{constants.FUNC_LABEL_PREFIX}{func_name}")
    end_label = ctx.fresh_label(f"end_{func_name}")

    return_hint = extract_normalized_type_from_child(
        ctx, node, (KNT.USER_TYPE, KNT.NULLABLE_TYPE), ctx.type_map
    )

    ctx.emit(Opcode.BRANCH, label=end_label, node=node)
    ctx.emit(Opcode.LABEL, label=func_label)
    ctx.seed_func_return_type(func_label, return_hint)

    if inject_this:
        _emit_this_param(ctx)

    if params_node:
        _lower_kotlin_params(ctx, params_node)

    expr_reg = ""
    if body_node:
        expr_reg = _lower_function_body(ctx, body_node)

    if expr_reg:
        ctx.emit(Opcode.RETURN, operands=[expr_reg])
    else:
        none_reg = ctx.fresh_reg()
        ctx.emit(
            Opcode.CONST,
            result_reg=none_reg,
            operands=[ctx.constants.default_return_value],
        )
        ctx.emit(Opcode.RETURN, operands=[none_reg])
    ctx.emit(Opcode.LABEL, label=end_label)

    func_reg = ctx.fresh_reg()
    ctx.emit_func_ref(func_name, func_label, result_reg=func_reg)
    ctx.emit(Opcode.DECL_VAR, operands=[func_name, func_reg])


# -- class declaration -------------------------------------------------


def _collect_kotlin_field_init(ctx: TreeSitterEmitContext, node) -> FieldInit | None:
    """Extract (field_name, value_node) from a property_declaration, or None.

    Only collects properties with initializers (``var x: Int = 0``).
    """
    var_decl = next(
        (c for c in node.children if c.type == KNT.VARIABLE_DECLARATION),
        None,
    )
    if var_decl is None:
        return None
    name = _extract_property_name(ctx, var_decl)
    value_node = _find_property_value(ctx, node)
    if value_node is None:
        return None
    return (name, value_node)


def _emit_synthetic_getter(
    ctx: TreeSitterEmitContext, prop_name: str, getter_node
) -> None:
    """Emit a synthetic __get_<prop>__ method from a getter node."""
    func_name = f"__get_{prop_name}__"
    func_label = ctx.fresh_label(f"{constants.FUNC_LABEL_PREFIX}{func_name}")
    end_label = ctx.fresh_label(f"end_{func_name}")

    ctx.emit(Opcode.BRANCH, label=end_label, node=getter_node)
    ctx.emit(Opcode.LABEL, label=func_label)
    _emit_this_param(ctx)

    prev_backing = ctx._accessor_backing_field
    ctx._accessor_backing_field = prop_name

    body_node = next(
        (c for c in getter_node.children if c.type == KNT.FUNCTION_BODY), None
    )
    expr_reg = ""
    if body_node:
        expr_reg = _lower_function_body(ctx, body_node)

    ctx._accessor_backing_field = prev_backing

    if expr_reg:
        ctx.emit(Opcode.RETURN, operands=[expr_reg])
    else:
        none_reg = ctx.fresh_reg()
        ctx.emit(
            Opcode.CONST,
            result_reg=none_reg,
            operands=[ctx.constants.default_return_value],
        )
        ctx.emit(Opcode.RETURN, operands=[none_reg])
    ctx.emit(Opcode.LABEL, label=end_label)

    func_reg = ctx.fresh_reg()
    ctx.emit_func_ref(func_name, func_label, result_reg=func_reg)
    ctx.emit(Opcode.DECL_VAR, operands=[func_name, func_reg])


def _emit_synthetic_setter(
    ctx: TreeSitterEmitContext, prop_name: str, setter_node
) -> None:
    """Emit a synthetic __set_<prop>__ method from a setter node."""
    func_name = f"__set_{prop_name}__"
    func_label = ctx.fresh_label(f"{constants.FUNC_LABEL_PREFIX}{func_name}")
    end_label = ctx.fresh_label(f"end_{func_name}")

    ctx.emit(Opcode.BRANCH, label=end_label, node=setter_node)
    ctx.emit(Opcode.LABEL, label=func_label)
    _emit_this_param(ctx)

    param_name = "value"
    param_node = next(
        (c for c in setter_node.children if c.type == KNT.PARAMETER_WITH_OPTIONAL_TYPE),
        None,
    )
    if param_node:
        id_node = next(
            (c for c in param_node.children if c.type == KNT.SIMPLE_IDENTIFIER), None
        )
        if id_node:
            param_name = ctx.node_text(id_node)

    param_reg = ctx.fresh_reg()
    ctx.emit(
        Opcode.SYMBOLIC,
        result_reg=param_reg,
        operands=[f"{constants.PARAM_PREFIX}{param_name}"],
    )
    ctx.emit(Opcode.DECL_VAR, operands=[param_name, param_reg])

    prev_backing = ctx._accessor_backing_field
    ctx._accessor_backing_field = prop_name

    body_node = next(
        (c for c in setter_node.children if c.type == KNT.FUNCTION_BODY), None
    )
    if body_node:
        _lower_function_body(ctx, body_node)

    ctx._accessor_backing_field = prev_backing

    none_reg = ctx.fresh_reg()
    ctx.emit(
        Opcode.CONST,
        result_reg=none_reg,
        operands=[ctx.constants.default_return_value],
    )
    ctx.emit(Opcode.RETURN, operands=[none_reg])
    ctx.emit(Opcode.LABEL, label=end_label)

    func_reg = ctx.fresh_reg()
    ctx.emit_func_ref(func_name, func_label, result_reg=func_reg)
    ctx.emit(Opcode.DECL_VAR, operands=[func_name, func_reg])


def _lower_class_body_with_companions(
    ctx: TreeSitterEmitContext, node, primary_ctor_params: list[str] = []
) -> None:
    """Lower class_body, handling companion_object children specially.

    Collects field initializers from property declarations and emits
    a synthetic ``__init__`` constructor when field inits are present.
    Getter/setter sibling nodes are paired with the preceding property_declaration.
    """
    named_children = [c for c in node.children if c.is_named]

    field_inits: list[FieldInit] = [
        init
        for c in named_children
        if c.type == KNT.PROPERTY_DECLARATION
        for init in [_collect_kotlin_field_init(ctx, c)]
        if init is not None
    ]

    last_property_name = ""
    for child in named_children:
        if child.type == KNT.PROPERTY_DECLARATION:
            var_decl = next(
                (c for c in child.children if c.type == KNT.VARIABLE_DECLARATION), None
            )
            last_property_name = (
                _extract_property_name(ctx, var_decl) if var_decl else ""
            )
        elif child.type == KNT.GETTER and last_property_name:
            _emit_synthetic_getter(ctx, last_property_name, child)
            register_property_accessor(
                ctx, ctx._current_class_name, last_property_name, "get"
            )
            continue
        elif child.type == KNT.SETTER and last_property_name:
            _emit_synthetic_setter(ctx, last_property_name, child)
            register_property_accessor(
                ctx, ctx._current_class_name, last_property_name, "set"
            )
            continue

        if child.type == KNT.COMPANION_OBJECT:
            _lower_companion_object(ctx, child)
        elif child.type == KNT.FUNCTION_DECLARATION:
            lower_function_decl(ctx, child, inject_this=True)
        elif child.type == KNT.SECONDARY_CONSTRUCTOR:
            lower_secondary_constructor(ctx, child, primary_ctor_params, field_inits)
        elif (
            child.type == KNT.PROPERTY_DECLARATION
            and _collect_kotlin_field_init(ctx, child) is not None
        ):
            continue
        else:
            ctx.lower_stmt(child)

    if field_inits:
        emit_synthetic_init(ctx, field_inits)


def _lower_companion_object(ctx: TreeSitterEmitContext, node) -> None:
    """Lower companion object by lowering its class_body child as a block."""
    body_node = next(
        (c for c in node.children if c.type == KNT.CLASS_BODY),
        None,
    )
    if body_node:
        ctx.lower_block(body_node)


def _lower_enum_class_body(ctx: TreeSitterEmitContext, node) -> None:
    """Lower enum_class_body: create NEW_OBJECT + STORE_VAR for each entry."""
    for child in node.children:
        if child.type == KNT.ENUM_ENTRY:
            _lower_enum_entry(ctx, child)
        elif child.is_named and child.type not in ("{", "}", ",", ";"):
            ctx.lower_stmt(child)


def _lower_enum_entry(ctx: TreeSitterEmitContext, node) -> None:
    """Lower a single enum_entry as NEW_OBJECT('enum:Name') + STORE_VAR."""
    name_node = next(
        (c for c in node.children if c.type == KNT.SIMPLE_IDENTIFIER),
        None,
    )
    entry_name = ctx.node_text(name_node) if name_node else "__unknown_enum"
    reg = ctx.fresh_reg()
    ctx.emit(
        Opcode.NEW_OBJECT,
        result_reg=reg,
        operands=[f"enum:{entry_name}"],
        node=node,
    )
    ctx.emit(Opcode.DECL_VAR, operands=[entry_name, reg])


def _extract_kotlin_parents(ctx: TreeSitterEmitContext, node) -> list[str]:
    """Extract parent class/interface names from a Kotlin class_declaration."""
    parents: list[str] = []
    for child in node.children:
        if child.type == KNT.DELEGATION_SPECIFIER:
            # delegation_specifier may contain user_type → type_identifier,
            # or constructor_invocation → user_type → type_identifier
            type_id = next(
                (c for c in child.children if c.type == KNT.TYPE_IDENTIFIER),
                None,
            )
            if type_id:
                parents.append(ctx.node_text(type_id))
                continue
            # Look deeper: constructor_invocation → user_type → type_identifier
            for sub in child.children:
                inner_id = next(
                    (c for c in sub.children if c.type == KNT.TYPE_IDENTIFIER),
                    None,
                )
                if inner_id:
                    parents.append(ctx.node_text(inner_id))
                    break
                # One more level: user_type wrapping inside constructor_invocation
                for subsub in sub.children:
                    deep_id = next(
                        (c for c in subsub.children if c.type == KNT.TYPE_IDENTIFIER),
                        None,
                    )
                    if deep_id:
                        parents.append(ctx.node_text(deep_id))
                        break
                else:
                    continue
                break
    return parents


def _extract_primary_constructor_params(ctx: TreeSitterEmitContext, node) -> list[str]:
    """Extract field names from a Kotlin primary constructor's class_parameter nodes."""
    ctor_node = next(
        (c for c in node.children if c.type == KNT.PRIMARY_CONSTRUCTOR),
        None,
    )
    if ctor_node is None:
        return []
    return [
        ctx.node_text(
            next(c for c in param.children if c.type == KNT.SIMPLE_IDENTIFIER)
        )
        for param in ctor_node.children
        if param.type == KNT.CLASS_PARAMETER
    ]


def _emit_primary_constructor_init(
    ctx: TreeSitterEmitContext, param_names: list[str]
) -> None:
    """Emit a synthetic __init__ that takes primary constructor params and stores as fields."""
    func_name = "__init__"
    func_label = ctx.fresh_label(f"{constants.FUNC_LABEL_PREFIX}{func_name}")
    end_label = ctx.fresh_label(f"end_{func_name}")

    ctx.emit(Opcode.BRANCH, label=end_label)
    ctx.emit(Opcode.LABEL, label=func_label)

    # Declare each param and store as field on this
    for name in param_names:
        param_reg = ctx.fresh_reg()
        ctx.emit(Opcode.SYMBOLIC, result_reg=param_reg, operands=[f"param:{name}"])
        ctx.emit(Opcode.DECL_VAR, operands=[name, param_reg])

    for name in param_names:
        val_reg = ctx.fresh_reg()
        ctx.emit(Opcode.LOAD_VAR, result_reg=val_reg, operands=[name])
        this_reg = ctx.fresh_reg()
        ctx.emit(Opcode.LOAD_VAR, result_reg=this_reg, operands=["this"])
        ctx.emit(Opcode.STORE_FIELD, operands=[this_reg, name, val_reg])

    none_reg = ctx.fresh_reg()
    ctx.emit(
        Opcode.CONST,
        result_reg=none_reg,
        operands=[ctx.constants.default_return_value],
    )
    ctx.emit(Opcode.RETURN, operands=[none_reg])
    ctx.emit(Opcode.LABEL, label=end_label)

    func_reg = ctx.fresh_reg()
    ctx.emit_func_ref(func_name, func_label, result_reg=func_reg)
    ctx.emit(Opcode.DECL_VAR, operands=[func_name, func_reg])


def lower_secondary_constructor(
    ctx: TreeSitterEmitContext,
    node,
    primary_ctor_params: list[str] = [],
    field_inits: list[FieldInit] = [],
) -> None:
    """Lower a Kotlin secondary constructor as an __init__ overload.

    Emits params, inlines the primary constructor's field stores from the
    delegation args (including field initializers), then lowers the optional body.
    """
    params_node = next(
        (c for c in node.children if c.type == KNT.FUNCTION_VALUE_PARAMETERS),
        None,
    )
    delegation_node = next(
        (c for c in node.children if c.type == KNT.CONSTRUCTOR_DELEGATION_CALL),
        None,
    )
    body_node = next(
        (c for c in node.children if c.type == KNT.STATEMENTS),
        None,
    )

    func_name = "__init__"
    func_label = ctx.fresh_label(f"{constants.FUNC_LABEL_PREFIX}{func_name}")
    end_label = ctx.fresh_label(f"end_{func_name}")

    ctx.emit(Opcode.BRANCH, label=end_label)
    ctx.emit(Opcode.LABEL, label=func_label)

    if params_node:
        _lower_kotlin_params(ctx, params_node)

    # Inline delegation: evaluate args and store as fields on this,
    # then replay field initializers (e.g. var doubled: Int = 0)
    if delegation_node:
        _emit_constructor_delegation(
            ctx, delegation_node, primary_ctor_params, field_inits
        )

    if body_node:
        ctx.lower_block(body_node)

    none_reg = ctx.fresh_reg()
    ctx.emit(
        Opcode.CONST,
        result_reg=none_reg,
        operands=[ctx.constants.default_return_value],
    )
    ctx.emit(Opcode.RETURN, operands=[none_reg])
    ctx.emit(Opcode.LABEL, label=end_label)

    func_reg = ctx.fresh_reg()
    ctx.emit_func_ref(func_name, func_label, result_reg=func_reg)
    ctx.emit(Opcode.DECL_VAR, operands=[func_name, func_reg])


def _emit_constructor_delegation(
    ctx: TreeSitterEmitContext,
    delegation_node,
    primary_ctor_params: list[str] = [],
    field_inits: list[FieldInit] = [],
) -> None:
    """Inline the full primary constructor body from delegation args.

    Evaluates each delegation arg and stores it as a field on ``this``,
    using the primary constructor's parameter names as field names.
    Then replays field initializers (e.g. ``var doubled: Int = 0``)
    so all fields exist on the heap object before the secondary
    constructor body runs.

    This avoids calling __init__ across frame boundaries where ``this``
    would not be accessible.
    """
    args_node = next(
        (c for c in delegation_node.children if c.type == KNT.VALUE_ARGUMENTS),
        None,
    )
    arg_regs = [
        ctx.lower_expr(next((gc for gc in arg.children if gc.is_named), arg))
        for arg in (args_node.children if args_node else [])
        if arg.type == KNT.VALUE_ARGUMENT
    ]
    this_reg = ctx.fresh_reg()
    ctx.emit(Opcode.LOAD_VAR, result_reg=this_reg, operands=["this"])
    for i, arg_reg in enumerate(arg_regs):
        field_name = primary_ctor_params[i] if i < len(primary_ctor_params) else str(i)
        ctx.emit(
            Opcode.STORE_FIELD,
            operands=[this_reg, field_name, arg_reg],
            node=delegation_node,
        )
    # Replay field initializers from class body (e.g. var doubled: Int = 0)
    if field_inits:
        emit_field_initializers(ctx, field_inits)


def lower_class_decl(ctx: TreeSitterEmitContext, node) -> None:
    name_node = next(
        (c for c in node.children if c.type == KNT.TYPE_IDENTIFIER),
        None,
    )
    body_node = next(
        (c for c in node.children if c.type in (KNT.CLASS_BODY, KNT.ENUM_CLASS_BODY)),
        None,
    )
    class_name = ctx.node_text(name_node) if name_node else "__anon_class"
    parents = _extract_kotlin_parents(ctx, node)
    for parent in parents:
        ctx.seed_interface_impl(class_name, parent)

    primary_ctor_params = _extract_primary_constructor_params(ctx, node)

    class_label = ctx.fresh_label(f"{constants.CLASS_LABEL_PREFIX}{class_name}")
    end_label = ctx.fresh_label(f"{constants.END_CLASS_LABEL_PREFIX}{class_name}")

    ctx.emit(Opcode.BRANCH, label=end_label, node=node)
    ctx.emit(Opcode.LABEL, label=class_label)
    if primary_ctor_params:
        _emit_primary_constructor_init(ctx, primary_ctor_params)
    if body_node:
        if body_node.type == KNT.ENUM_CLASS_BODY:
            _lower_enum_class_body(ctx, body_node)
        else:
            _lower_class_body_with_companions(ctx, body_node, primary_ctor_params)
    ctx.emit(Opcode.LABEL, label=end_label)

    cls_reg = ctx.fresh_reg()
    ctx.emit_class_ref(class_name, class_label, parents, result_reg=cls_reg)
    ctx.emit(Opcode.DECL_VAR, operands=[class_name, cls_reg])


# -- object declaration (singleton) ------------------------------------


def lower_object_decl(ctx: TreeSitterEmitContext, node) -> None:
    """Lower object declaration (Kotlin singleton) like a class."""
    name_node = next(
        (c for c in node.children if c.type == KNT.TYPE_IDENTIFIER),
        None,
    )
    body_node = next(
        (c for c in node.children if c.type == KNT.CLASS_BODY),
        None,
    )
    obj_name = ctx.node_text(name_node) if name_node else "__anon_object"

    obj_label = ctx.fresh_label(f"{constants.CLASS_LABEL_PREFIX}{obj_name}")
    end_label = ctx.fresh_label(f"{constants.END_CLASS_LABEL_PREFIX}{obj_name}")

    ctx.emit(Opcode.BRANCH, label=end_label, node=node)
    ctx.emit(Opcode.LABEL, label=obj_label)
    if body_node:
        ctx.lower_block(body_node)
    ctx.emit(Opcode.LABEL, label=end_label)

    inst_reg = ctx.fresh_reg()
    ctx.emit(
        Opcode.NEW_OBJECT,
        result_reg=inst_reg,
        operands=[obj_name],
        node=node,
    )
    ctx.emit(Opcode.DECL_VAR, operands=[obj_name, inst_reg])


# ---------------------------------------------------------------------------
# Symbol extraction (Phase 2)
# ---------------------------------------------------------------------------


def _extract_kotlin_primary_ctor_fields(primary_ctor) -> "dict[str, FieldInfo]":
    """Extract val/var params from a Kotlin primary_constructor as fields."""
    from interpreter.frontends.symbol_table import FieldInfo

    fields: dict[str, FieldInfo] = {}
    for child in primary_ctor.children:
        if child.type != KNT.CLASS_PARAMETER:
            continue
        # A class_parameter is a val/var param if it has binding_pattern_kind (val/var)
        has_val_var = any(c.type == KNT.BINDING_PATTERN_KIND for c in child.children)
        if not has_val_var:
            continue
        name_node = next(
            (c for c in child.children if c.type == KNT.SIMPLE_IDENTIFIER), None
        )
        type_node = next(
            (c for c in child.children if c.type in (KNT.USER_TYPE, KNT.NULLABLE_TYPE)),
            None,
        )
        if name_node is None:
            continue
        fname = name_node.text.decode()
        type_hint = type_node.text.decode() if type_node is not None else ""
        has_default = any(c.type == "=" for c in child.children)
        fields[fname] = FieldInfo(
            name=fname, type_hint=type_hint, has_initializer=has_default
        )
    return fields


def _extract_kotlin_class(node) -> "tuple[str, ClassInfo] | None":
    """Extract a ClassInfo from a Kotlin class_declaration node."""
    from interpreter.frontends.symbol_table import ClassInfo, FieldInfo, FunctionInfo

    # Kotlin class_declaration uses type_identifier for name, not a "name" field
    name_node = next((c for c in node.children if c.type == KNT.TYPE_IDENTIFIER), None)
    if name_node is None:
        return None
    class_name = name_node.text.decode()

    # Parents from delegation_specifier > constructor_invocation > user_type > type_identifier
    def _kotlin_delegation_parent_name(ds_node) -> "str | None":
        for sub in ds_node.children:
            if sub.type == "constructor_invocation":
                user_type = next(
                    (c for c in sub.children if c.type == KNT.USER_TYPE), None
                )
                if user_type is not None:
                    tid = next(
                        (
                            c
                            for c in user_type.children
                            if c.type == KNT.TYPE_IDENTIFIER
                        ),
                        None,
                    )
                    if tid is not None:
                        return tid.text.decode()
            # direct user_type (interface delegation)
            if sub.type == KNT.USER_TYPE:
                tid = next(
                    (c for c in sub.children if c.type == KNT.TYPE_IDENTIFIER), None
                )
                if tid is not None:
                    return tid.text.decode()
        return None

    parents = tuple(
        name
        for child in node.children
        if child.type == KNT.DELEGATION_SPECIFIER
        for name in [_kotlin_delegation_parent_name(child)]
        if name is not None
    )

    fields: dict[str, FieldInfo] = {}

    # Extract primary constructor val/var params as fields
    primary_ctor = next(
        (c for c in node.children if c.type == KNT.PRIMARY_CONSTRUCTOR), None
    )
    if primary_ctor is not None:
        fields.update(_extract_kotlin_primary_ctor_fields(primary_ctor))

    body = next((c for c in node.children if c.type == KNT.CLASS_BODY), None)
    if body is None:
        return class_name, ClassInfo(
            name=class_name, fields=fields, methods={}, constants={}, parents=parents
        )

    methods: dict[str, FunctionInfo] = {}
    constants_map: dict[str, str] = {}

    for child in body.children:
        if child.type == KNT.PROPERTY_DECLARATION:
            # property_declaration: binding_pattern_kind variable_declaration [= expr]
            decl = next(
                (c for c in child.children if c.type == KNT.VARIABLE_DECLARATION), None
            )
            if decl is not None:
                pname_node = next(
                    (c for c in decl.children if c.type == KNT.SIMPLE_IDENTIFIER), None
                )
                ptype_node = next(
                    (
                        c
                        for c in decl.children
                        if c.type in (KNT.USER_TYPE, KNT.NULLABLE_TYPE)
                    ),
                    None,
                )
                if pname_node is not None:
                    fname = pname_node.text.decode()
                    type_hint = (
                        ptype_node.text.decode() if ptype_node is not None else ""
                    )
                    has_init = any(
                        not c.is_named and c.text == b"=" for c in child.children
                    )
                    fields[fname] = FieldInfo(
                        name=fname, type_hint=type_hint, has_initializer=has_init
                    )
        elif child.type == KNT.FUNCTION_DECLARATION:
            mname_node = next(
                (c for c in child.children if c.type == KNT.SIMPLE_IDENTIFIER), None
            )
            params_node = next(
                (c for c in child.children if c.type == KNT.FUNCTION_VALUE_PARAMETERS),
                None,
            )
            if mname_node is not None:
                mname = mname_node.text.decode()
                params = (
                    tuple(
                        pname.text.decode()
                        for p in params_node.children
                        if p.type == KNT.PARAMETER
                        for pname in [
                            next(
                                (
                                    c
                                    for c in p.children
                                    if c.type == KNT.SIMPLE_IDENTIFIER
                                ),
                                None,
                            )
                        ]
                        if pname is not None
                    )
                    if params_node is not None
                    else ()
                )
                ret_node = next(
                    (
                        c
                        for c in child.children
                        if c.type in (KNT.USER_TYPE, KNT.NULLABLE_TYPE)
                    ),
                    None,
                )
                return_type = ret_node.text.decode() if ret_node is not None else ""
                methods[mname] = FunctionInfo(
                    name=mname, params=params, return_type=return_type
                )

    return class_name, ClassInfo(
        name=class_name,
        fields=fields,
        methods=methods,
        constants=constants_map,
        parents=parents,
    )


def _collect_kotlin_classes(node, accumulator: "dict[str, ClassInfo]") -> None:
    """Recursively walk the AST and collect all class_declaration nodes."""
    from interpreter.frontends.symbol_table import ClassInfo

    if node.type == KNT.CLASS_DECLARATION:
        result = _extract_kotlin_class(node)
        if result is not None:
            class_name, class_info = result
            accumulator[class_name] = class_info
    for child in node.children:
        _collect_kotlin_classes(child, accumulator)


def extract_kotlin_symbols(root) -> "SymbolTable":
    """Walk the Kotlin AST and return a SymbolTable of all class definitions."""
    from interpreter.frontends.symbol_table import ClassInfo, SymbolTable

    classes: dict[str, ClassInfo] = {}
    _collect_kotlin_classes(root, classes)
    return SymbolTable(classes=classes)
