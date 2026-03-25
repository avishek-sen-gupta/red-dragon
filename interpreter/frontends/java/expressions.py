"""Java-specific expression lowerers — pure functions taking (ctx, node)."""

from __future__ import annotations

from interpreter.frontends.context import TreeSitterEmitContext

from interpreter.instructions import (
    Branch,
    BranchIf,
    CallFunction,
    CallMethod,
    Const,
    DeclVar,
    Label_,
    LoadField,
    LoadIndex,
    LoadVar,
    NewArray,
    Return_,
    StoreField,
    StoreIndex,
    StoreVar,
    Symbolic,
    Throw_,
)
from interpreter import constants
from interpreter.frontends.common.expressions import (
    extract_call_args_unwrap,
    lower_const_literal,
    lower_store_target,
)
from interpreter.frontends.type_extraction import (
    extract_normalized_type,
)
from interpreter.frontends.java.node_types import JavaNodeType
from interpreter.types.type_expr import ScalarType, scalar
from interpreter.register import Register


def lower_method_invocation(ctx: TreeSitterEmitContext, node) -> Register:
    name_node = node.child_by_field_name("name")
    obj_node = node.child_by_field_name(ctx.constants.attr_object_field)
    args_node = node.child_by_field_name(ctx.constants.call_arguments_field)
    arg_regs = extract_call_args_unwrap(ctx, args_node) if args_node else []

    if obj_node:
        obj_reg = ctx.lower_expr(obj_node)
        method_name = ctx.node_text(name_node) if name_node else "unknown"
        reg = ctx.fresh_reg()
        ctx.emit_inst(
            CallMethod(
                result_reg=reg,
                obj_reg=obj_reg,
                method_name=method_name,
                args=tuple(arg_regs),
            ),
            node=node,
        )
        return reg

    func_name = ctx.node_text(name_node) if name_node else "unknown"
    reg = ctx.fresh_reg()
    ctx.emit_inst(
        CallFunction(result_reg=reg, func_name=func_name, args=tuple(arg_regs)),
        node=node,
    )
    return reg


def lower_object_creation(ctx: TreeSitterEmitContext, node) -> Register:
    type_node = node.child_by_field_name("type")
    args_node = node.child_by_field_name(ctx.constants.call_arguments_field)
    arg_regs = extract_call_args_unwrap(ctx, args_node) if args_node else []
    type_name = ctx.node_text(type_node) if type_node else "Object"
    reg = ctx.fresh_reg()
    ctx.emit_inst(
        CallFunction(result_reg=reg, func_name=type_name, args=tuple(arg_regs)),
        node=node,
    )
    ctx.seed_register_type(reg, ScalarType(type_name))
    return reg


def lower_field_access(ctx: TreeSitterEmitContext, node) -> Register:
    obj_node = node.child_by_field_name(ctx.constants.attr_object_field)
    field_node = node.child_by_field_name("field")
    if obj_node is None or field_node is None:
        return lower_const_literal(ctx, node)
    obj_reg = ctx.lower_expr(obj_node)
    field_name = ctx.node_text(field_node)
    reg = ctx.fresh_reg()
    ctx.emit_inst(
        LoadField(result_reg=reg, obj_reg=obj_reg, field_name=field_name), node=node
    )
    return reg


def lower_method_reference(ctx: TreeSitterEmitContext, node) -> Register:
    """Lower method_reference: Type::method or obj::method or Type::new."""
    obj_node = node.children[0]
    method_node = node.children[-1]
    obj_reg = ctx.lower_expr(obj_node)
    method_name = ctx.node_text(method_node)
    reg = ctx.fresh_reg()
    ctx.emit_inst(
        LoadField(result_reg=reg, obj_reg=obj_reg, field_name=method_name), node=node
    )
    return reg


def lower_scoped_identifier(ctx: TreeSitterEmitContext, node) -> Register:
    """Lower scoped_identifier (e.g., java.lang.System) as LOAD_VAR."""
    qualified_name = ctx.node_text(node)
    reg = ctx.fresh_reg()
    ctx.emit_inst(LoadVar(result_reg=reg, name=qualified_name), node=node)
    return reg


def lower_class_literal(ctx: TreeSitterEmitContext, node) -> Register:
    """Lower class_literal: Type.class -> LOAD_FIELD(type_reg, 'class')."""
    type_node = node.children[0]
    type_reg = ctx.lower_expr(type_node)
    reg = ctx.fresh_reg()
    ctx.emit_inst(
        LoadField(result_reg=reg, obj_reg=type_reg, field_name="class"), node=node
    )
    return reg


def lower_lambda(ctx: TreeSitterEmitContext, node) -> Register:
    """Lower lambda_expression: (params) -> expr or (params) -> { body }."""
    func_label = ctx.fresh_label(f"{constants.FUNC_LABEL_PREFIX}__lambda")
    end_label = ctx.fresh_label("lambda_end")

    ctx.emit_inst(Branch(label=end_label), node=node)
    ctx.emit_inst(Label_(label=func_label))

    params_node = node.child_by_field_name(ctx.constants.func_params_field)
    if params_node:
        _lower_lambda_params(ctx, params_node)

    body_node = node.child_by_field_name(ctx.constants.func_body_field)
    if body_node and body_node.type == JavaNodeType.BLOCK:
        ctx.lower_block(body_node)
        none_reg = ctx.fresh_reg()
        ctx.emit_inst(
            Const(result_reg=none_reg, value=ctx.constants.default_return_value)
        )
        ctx.emit_inst(Return_(value_reg=none_reg))
    elif body_node:
        body_reg = ctx.lower_expr(body_node)
        ctx.emit_inst(Return_(value_reg=body_reg))

    ctx.emit_inst(Label_(label=end_label))

    ref_reg = ctx.fresh_reg()
    ctx.emit_func_ref("__lambda", func_label, result_reg=ref_reg, node=node)
    return ref_reg


def _lower_lambda_params(ctx: TreeSitterEmitContext, params_node) -> None:
    """Lower parameters for lambda expressions."""
    if params_node.type == JavaNodeType.FORMAL_PARAMETERS:
        lower_java_params(ctx, params_node)
    else:
        for child in params_node.children:
            if child.type == JavaNodeType.IDENTIFIER:
                pname = ctx.node_text(child)
                ctx.emit_inst(
                    Symbolic(
                        result_reg=ctx.fresh_reg(),
                        hint=f"{constants.PARAM_PREFIX}{pname}",
                    ),
                    node=child,
                )
                ctx.emit_inst(DeclVar(name=pname, value_reg=f"%{ctx.reg_counter - 1}"))


def lower_array_access(ctx: TreeSitterEmitContext, node) -> Register:
    arr_node = node.child_by_field_name("array")
    idx_node = node.child_by_field_name("index")
    if arr_node is None or idx_node is None:
        return lower_const_literal(ctx, node)
    arr_reg = ctx.lower_expr(arr_node)
    idx_reg = ctx.lower_expr(idx_node)
    reg = ctx.fresh_reg()
    ctx.emit_inst(
        LoadIndex(result_reg=reg, arr_reg=arr_reg, index_reg=idx_reg), node=node
    )
    return reg


def lower_array_creation(ctx: TreeSitterEmitContext, node) -> Register:
    """Lower array_creation_expression or standalone array_initializer."""
    # Handle standalone array_initializer: {1, 2, 3}
    if node.type == JavaNodeType.ARRAY_INITIALIZER:
        elements = [c for c in node.children if c.is_named]
        size_reg = ctx.fresh_reg()
        ctx.emit_inst(Const(result_reg=size_reg, value=str(len(elements))))
        arr_reg = ctx.fresh_reg()
        ctx.emit_inst(
            NewArray(result_reg=arr_reg, type_hint=scalar("array"), size_reg=size_reg),
            node=node,
        )
        for i, elem in enumerate(elements):
            idx_reg = ctx.fresh_reg()
            ctx.emit_inst(Const(result_reg=idx_reg, value=str(i)))
            val_reg = ctx.lower_expr(elem)
            ctx.emit_inst(
                StoreIndex(arr_reg=arr_reg, index_reg=idx_reg, value_reg=val_reg)
            )
        return arr_reg

    # array_creation_expression: look for array_initializer child
    init_node = next(
        (c for c in node.children if c.type == JavaNodeType.ARRAY_INITIALIZER),
        None,
    )
    if init_node is not None:
        elements = [c for c in init_node.children if c.is_named]
        size_reg = ctx.fresh_reg()
        ctx.emit_inst(Const(result_reg=size_reg, value=str(len(elements))))
        arr_reg = ctx.fresh_reg()
        ctx.emit_inst(
            NewArray(result_reg=arr_reg, type_hint=scalar("array"), size_reg=size_reg),
            node=node,
        )
        for i, elem in enumerate(elements):
            idx_reg = ctx.fresh_reg()
            ctx.emit_inst(Const(result_reg=idx_reg, value=str(i)))
            val_reg = ctx.lower_expr(elem)
            ctx.emit_inst(
                StoreIndex(arr_reg=arr_reg, index_reg=idx_reg, value_reg=val_reg)
            )
        return arr_reg

    # Sized array without initializer: new int[5]
    dims_node = next(
        (c for c in node.children if c.type == JavaNodeType.DIMENSIONS_EXPR),
        None,
    )
    if dims_node:
        dim_children = [c for c in dims_node.children if c.is_named]
        size_reg = ctx.lower_expr(dim_children[0]) if dim_children else ctx.fresh_reg()
    else:
        size_reg = ctx.fresh_reg()
        ctx.emit_inst(Const(result_reg=size_reg, value="0"))
    arr_reg = ctx.fresh_reg()
    ctx.emit_inst(
        NewArray(result_reg=arr_reg, type_hint=scalar("array"), size_reg=size_reg),
        node=node,
    )
    return arr_reg


def lower_assignment_expr(ctx: TreeSitterEmitContext, node) -> Register:
    left = node.child_by_field_name(ctx.constants.assign_left_field)
    right = node.child_by_field_name(ctx.constants.assign_right_field)
    val_reg = ctx.lower_expr(right)
    lower_java_store_target(ctx, left, val_reg, node)
    return val_reg


def lower_java_store_target(
    ctx: TreeSitterEmitContext, target, val_reg: str, parent_node
) -> None:
    if target.type == JavaNodeType.IDENTIFIER:
        name = ctx.node_text(target)
        if ctx.symbol_table.resolve_field(ctx._current_class_name, name).name:
            this_reg = ctx.fresh_reg()
            ctx.emit_inst(LoadVar(result_reg=this_reg, name="this"))
            ctx.emit_inst(
                StoreField(obj_reg=this_reg, field_name=name, value_reg=val_reg),
                node=parent_node,
            )
        else:
            ctx.emit_inst(StoreVar(name=name, value_reg=val_reg), node=parent_node)
    elif target.type == JavaNodeType.FIELD_ACCESS:
        obj_node = target.child_by_field_name(ctx.constants.attr_object_field)
        field_node = target.child_by_field_name("field")
        if obj_node and field_node:
            obj_reg = ctx.lower_expr(obj_node)
            ctx.emit_inst(
                StoreField(
                    obj_reg=obj_reg,
                    field_name=ctx.node_text(field_node),
                    value_reg=val_reg,
                ),
                node=parent_node,
            )
    elif target.type == JavaNodeType.ARRAY_ACCESS:
        arr_node = target.child_by_field_name("array")
        idx_node = target.child_by_field_name("index")
        if arr_node and idx_node:
            arr_reg = ctx.lower_expr(arr_node)
            idx_reg = ctx.lower_expr(idx_node)
            ctx.emit_inst(
                StoreIndex(arr_reg=arr_reg, index_reg=idx_reg, value_reg=val_reg),
                node=parent_node,
            )
    else:
        ctx.emit_inst(
            StoreVar(name=ctx.node_text(target), value_reg=val_reg), node=parent_node
        )


def lower_cast_expr(ctx: TreeSitterEmitContext, node) -> Register:
    value_node = node.child_by_field_name("value")
    if value_node:
        return ctx.lower_expr(value_node)
    children = [c for c in node.children if c.is_named]
    if len(children) >= 2:
        return ctx.lower_expr(children[-1])
    return lower_const_literal(ctx, node)


def lower_instanceof(ctx: TreeSitterEmitContext, node) -> Register:
    """Lower instanceof_expression: operand instanceof Type [binding].

    Java 16+ type patterns: ``o instanceof String s`` binds ``s`` to
    the matched value after the type check.
    Java 16+ record patterns: ``o instanceof Point(int a, int b)``
    destructures via the Pattern ADT.
    """
    named_children = [c for c in node.children if c.is_named]
    operand_node = named_children[0] if named_children else None
    pattern_or_type_node = named_children[1] if len(named_children) > 1 else None

    obj_reg = ctx.lower_expr(operand_node) if operand_node else ctx.fresh_reg()

    # Record pattern: o instanceof Point(int a, int b)
    if pattern_or_type_node and pattern_or_type_node.type == "record_pattern":
        from interpreter.frontends.java.patterns import parse_java_pattern
        from interpreter.frontends.common.patterns import (
            compile_pattern_test,
            compile_pattern_bindings,
        )

        pattern = parse_java_pattern(ctx, pattern_or_type_node)
        test_reg = compile_pattern_test(ctx, obj_reg, pattern)
        compile_pattern_bindings(ctx, obj_reg, pattern)
        return test_reg

    # Simple type pattern: o instanceof String s
    type_node = pattern_or_type_node
    binding_node = named_children[2] if len(named_children) > 2 else None

    type_reg = ctx.fresh_reg()
    type_name = ctx.node_text(type_node) if type_node else "Object"
    ctx.emit_inst(Const(result_reg=type_reg, value=type_name))
    reg = ctx.fresh_reg()
    ctx.emit_inst(
        CallFunction(
            result_reg=reg,
            func_name="isinstance",
            args=(
                obj_reg,
                type_reg,
            ),
        ),
        node=node,
    )
    # Java 16+ type pattern binding: o instanceof String s → bind s = o
    if binding_node:
        binding_name = ctx.node_text(binding_node)
        if binding_name != "_":
            ctx.emit_inst(StoreVar(name=binding_name, value_reg=obj_reg), node=node)
    return reg


def lower_ternary(ctx: TreeSitterEmitContext, node) -> Register:
    cond_node = node.child_by_field_name(ctx.constants.if_condition_field)
    true_node = node.child_by_field_name(ctx.constants.if_consequence_field)
    false_node = node.child_by_field_name(ctx.constants.if_alternative_field)

    cond_reg = ctx.lower_expr(cond_node)
    true_label = ctx.fresh_label("ternary_true")
    false_label = ctx.fresh_label("ternary_false")
    end_label = ctx.fresh_label("ternary_end")

    ctx.emit_inst(BranchIf(cond_reg=cond_reg, branch_targets=(true_label, false_label)))
    ctx.emit_inst(Label_(label=true_label))
    true_reg = ctx.lower_expr(true_node)
    result_var = f"__ternary_{ctx.label_counter}"
    ctx.emit_inst(DeclVar(name=result_var, value_reg=true_reg))
    ctx.emit_inst(Branch(label=end_label))

    ctx.emit_inst(Label_(label=false_label))
    false_reg = ctx.lower_expr(false_node)
    ctx.emit_inst(DeclVar(name=result_var, value_reg=false_reg))
    ctx.emit_inst(Branch(label=end_label))

    ctx.emit_inst(Label_(label=end_label))
    result_reg = ctx.fresh_reg()
    ctx.emit_inst(LoadVar(result_reg=result_reg, name=result_var))
    return result_reg


def lower_expr_stmt_as_expr(ctx: TreeSitterEmitContext, node) -> Register:
    """Lower expression_statement in expr context (e.g., inside switch expression)."""
    named_children = [c for c in node.children if c.is_named]
    if named_children:
        return ctx.lower_expr(named_children[0])
    return lower_const_literal(ctx, node)


def lower_throw_as_expr(ctx: TreeSitterEmitContext, node) -> Register:
    """Lower throw_statement in expr context (e.g., switch expression arm)."""
    named_children = [c for c in node.children if c.is_named]
    if named_children:
        val_reg = ctx.lower_expr(named_children[0])
    else:
        val_reg = ctx.fresh_reg()
        ctx.emit_inst(
            Const(result_reg=val_reg, value=ctx.constants.default_return_value)
        )
    ctx.emit_inst(Throw_(value_reg=val_reg), node=node)
    return val_reg


# ── shared Java param helper (used by expressions + declarations) ─────


def lower_java_params(ctx: TreeSitterEmitContext, params_node) -> None:
    for child in params_node.children:
        if child.type == JavaNodeType.FORMAL_PARAMETER:
            name_node = child.child_by_field_name("name")
            if name_node:
                pname = ctx.node_text(name_node)
                type_hint = extract_normalized_type(ctx, child, "type", ctx.type_map)
                param_reg = ctx.fresh_reg()
                ctx.emit_inst(
                    Symbolic(
                        result_reg=param_reg, hint=f"{constants.PARAM_PREFIX}{pname}"
                    ),
                    node=child,
                )
                ctx.seed_register_type(param_reg, type_hint)
                ctx.seed_param_type(pname, type_hint)
                ctx.emit_inst(DeclVar(name=pname, value_reg=f"%{ctx.reg_counter - 1}"))
                ctx.seed_var_type(pname, type_hint)
        elif child.type == JavaNodeType.SPREAD_PARAMETER:
            name_node = child.child_by_field_name("name")
            if name_node:
                pname = ctx.node_text(name_node)
                ctx.emit_inst(
                    Symbolic(
                        result_reg=ctx.fresh_reg(),
                        hint=f"{constants.PARAM_PREFIX}{pname}",
                    ),
                    node=child,
                )
                ctx.emit_inst(DeclVar(name=pname, value_reg=f"%{ctx.reg_counter - 1}"))
