"""C#-specific expression lowerers -- pure functions taking (ctx, node)."""

from __future__ import annotations

from interpreter.frontends.context import TreeSitterEmitContext

from interpreter.ir import Opcode
from interpreter import constants
from interpreter.frontends.common.expressions import (
    extract_call_args_unwrap,
    lower_const_literal,
    lower_interpolated_string_parts,
)
from interpreter.frontends.csharp.node_types import CSharpNodeType as NT
from interpreter.frontends.type_extraction import (
    extract_normalized_type,
)
from interpreter.type_expr import ScalarType


def lower_invocation(ctx: TreeSitterEmitContext, node) -> str:
    """Lower invocation_expression (function field, arguments field)."""
    func_node = node.child_by_field_name(ctx.constants.call_function_field)
    args_node = node.child_by_field_name(ctx.constants.call_arguments_field)
    arg_regs = extract_call_args_unwrap(ctx, args_node) if args_node else []

    if func_node and func_node.type == NT.MEMBER_ACCESS_EXPRESSION:
        obj_node = func_node.child_by_field_name("expression")
        name_node = func_node.child_by_field_name("name")
        if obj_node and name_node:
            obj_reg = ctx.lower_expr(obj_node)
            method_name = ctx.node_text(name_node)
            reg = ctx.fresh_reg()
            ctx.emit(
                Opcode.CALL_METHOD,
                result_reg=reg,
                operands=[obj_reg, method_name] + arg_regs,
                node=node,
            )
            return reg

    if func_node and func_node.type == NT.IDENTIFIER:
        func_name = ctx.node_text(func_node)
        reg = ctx.fresh_reg()
        ctx.emit(
            Opcode.CALL_FUNCTION,
            result_reg=reg,
            operands=[func_name] + arg_regs,
            node=node,
        )
        return reg

    # Dynamic / unknown call target
    if func_node:
        target_reg = ctx.lower_expr(func_node)
    else:
        target_reg = ctx.fresh_reg()
        ctx.emit(
            Opcode.SYMBOLIC,
            result_reg=target_reg,
            operands=["unknown_call_target"],
        )
    reg = ctx.fresh_reg()
    ctx.emit(
        Opcode.CALL_UNKNOWN,
        result_reg=reg,
        operands=[target_reg] + arg_regs,
        node=node,
    )
    return reg


def lower_object_creation(ctx: TreeSitterEmitContext, node) -> str:
    type_node = node.child_by_field_name("type")
    args_node = node.child_by_field_name(ctx.constants.call_arguments_field)
    arg_regs = extract_call_args_unwrap(ctx, args_node) if args_node else []
    type_name = ctx.node_text(type_node) if type_node else "Object"
    reg = ctx.fresh_reg()
    ctx.emit(
        Opcode.CALL_FUNCTION,
        result_reg=reg,
        operands=[type_name] + arg_regs,
        node=node,
    )
    ctx.seed_register_type(reg, ScalarType(type_name))
    return reg


def lower_member_access(ctx: TreeSitterEmitContext, node) -> str:
    obj_node = node.child_by_field_name("expression")
    name_node = node.child_by_field_name("name")
    if obj_node is None or name_node is None:
        return lower_const_literal(ctx, node)
    obj_reg = ctx.lower_expr(obj_node)
    field_name = ctx.node_text(name_node)
    reg = ctx.fresh_reg()
    ctx.emit(
        Opcode.LOAD_FIELD,
        result_reg=reg,
        operands=[obj_reg, field_name],
        node=node,
    )
    return reg


def _extract_bracket_index(ctx: TreeSitterEmitContext, bracket_node) -> str:
    """Unwrap bracketed_argument_list -> argument -> inner expression."""
    if bracket_node is None:
        reg = ctx.fresh_reg()
        ctx.emit(
            Opcode.SYMBOLIC,
            result_reg=reg,
            operands=["unknown_index"],
        )
        return reg
    if bracket_node.type == NT.BRACKETED_ARGUMENT_LIST:
        args = [c for c in bracket_node.children if c.is_named]
        if args:
            inner = args[0]
            # argument node wraps the actual expression
            if inner.type == NT.ARGUMENT:
                expr_children = [c for c in inner.children if c.is_named]
                return (
                    ctx.lower_expr(expr_children[0])
                    if expr_children
                    else ctx.lower_expr(inner)
                )
            return ctx.lower_expr(inner)
        reg = ctx.fresh_reg()
        ctx.emit(
            Opcode.SYMBOLIC,
            result_reg=reg,
            operands=["unknown_index"],
        )
        return reg
    return ctx.lower_expr(bracket_node)


def lower_element_access(ctx: TreeSitterEmitContext, node) -> str:
    obj_node = node.child_by_field_name("expression")
    bracket_node = node.child_by_field_name("subscript")
    if obj_node is None:
        return lower_const_literal(ctx, node)
    obj_reg = ctx.lower_expr(obj_node)
    if bracket_node is None:
        bracket_node = next(
            (
                c
                for c in node.children
                if c.is_named and c.type == NT.BRACKETED_ARGUMENT_LIST
            ),
            None,
        )
    idx_reg = _extract_bracket_index(ctx, bracket_node)
    reg = ctx.fresh_reg()
    ctx.emit(
        Opcode.LOAD_INDEX,
        result_reg=reg,
        operands=[obj_reg, idx_reg],
        node=node,
    )
    return reg


def lower_initializer_expr(ctx: TreeSitterEmitContext, node) -> str:
    """Lower initializer_expression {a, b, c} as NEW_ARRAY + STORE_INDEX."""
    elems = [
        c
        for c in node.children
        if c.is_named and c.type not in (NT.LBRACE, NT.RBRACE, ",")
    ]
    arr_reg = ctx.fresh_reg()
    size_reg = ctx.fresh_reg()
    ctx.emit(Opcode.CONST, result_reg=size_reg, operands=[str(len(elems))])
    ctx.emit(
        Opcode.NEW_ARRAY,
        result_reg=arr_reg,
        operands=["list", size_reg],
        node=node,
    )
    for i, elem in enumerate(elems):
        val_reg = ctx.lower_expr(elem)
        idx_reg = ctx.fresh_reg()
        ctx.emit(Opcode.CONST, result_reg=idx_reg, operands=[str(i)])
        ctx.emit(Opcode.STORE_INDEX, operands=[arr_reg, idx_reg, val_reg])
    return arr_reg


def lower_assignment_expr(ctx: TreeSitterEmitContext, node) -> str:
    left = node.child_by_field_name(ctx.constants.assign_left_field)
    right = node.child_by_field_name(ctx.constants.assign_right_field)
    val_reg = ctx.lower_expr(right)
    lower_csharp_store_target(ctx, left, val_reg, node)
    return val_reg


def lower_cast_expr(ctx: TreeSitterEmitContext, node) -> str:
    value_node = node.child_by_field_name("value")
    if value_node:
        return ctx.lower_expr(value_node)
    children = [c for c in node.children if c.is_named]
    if len(children) >= 2:
        return ctx.lower_expr(children[-1])
    return lower_const_literal(ctx, node)


def lower_ternary(ctx: TreeSitterEmitContext, node) -> str:
    cond_node = node.child_by_field_name(ctx.constants.if_condition_field)
    true_node = node.child_by_field_name(ctx.constants.if_consequence_field)
    false_node = node.child_by_field_name(ctx.constants.if_alternative_field)

    cond_reg = ctx.lower_expr(cond_node)
    true_label = ctx.fresh_label("ternary_true")
    false_label = ctx.fresh_label("ternary_false")
    end_label = ctx.fresh_label("ternary_end")

    ctx.emit(
        Opcode.BRANCH_IF,
        operands=[cond_reg],
        label=f"{true_label},{false_label}",
    )
    ctx.emit(Opcode.LABEL, label=true_label)
    true_reg = ctx.lower_expr(true_node)
    result_var = f"__ternary_{ctx.label_counter}"
    ctx.emit(Opcode.DECL_VAR, operands=[result_var, true_reg])
    ctx.emit(Opcode.BRANCH, label=end_label)

    ctx.emit(Opcode.LABEL, label=false_label)
    false_reg = ctx.lower_expr(false_node)
    ctx.emit(Opcode.DECL_VAR, operands=[result_var, false_reg])
    ctx.emit(Opcode.BRANCH, label=end_label)

    ctx.emit(Opcode.LABEL, label=end_label)
    result_reg = ctx.fresh_reg()
    ctx.emit(Opcode.LOAD_VAR, result_reg=result_reg, operands=[result_var])
    return result_reg


def lower_typeof(ctx: TreeSitterEmitContext, node) -> str:
    """Lower typeof_expression: typeof(Type)."""
    named_children = [c for c in node.children if c.is_named]
    type_node = next(
        (c for c in named_children if c.type != NT.TYPEOF),
        named_children[0] if named_children else None,
    )
    type_name = ctx.node_text(type_node) if type_node else "Object"
    type_reg = ctx.fresh_reg()
    ctx.emit(Opcode.CONST, result_reg=type_reg, operands=[type_name])
    reg = ctx.fresh_reg()
    ctx.emit(
        Opcode.CALL_FUNCTION,
        result_reg=reg,
        operands=["typeof", type_reg],
        node=node,
    )
    return reg


def lower_is_expr(ctx: TreeSitterEmitContext, node) -> str:
    """Lower is_expression: operand is Type."""
    named_children = [c for c in node.children if c.is_named]
    operand_node = named_children[0] if named_children else None
    type_node = named_children[1] if len(named_children) > 1 else None

    obj_reg = ctx.lower_expr(operand_node) if operand_node else ctx.fresh_reg()
    type_reg = ctx.fresh_reg()
    type_name = ctx.node_text(type_node) if type_node else "Object"
    ctx.emit(Opcode.CONST, result_reg=type_reg, operands=[type_name])
    reg = ctx.fresh_reg()
    ctx.emit(
        Opcode.CALL_FUNCTION,
        result_reg=reg,
        operands=["is_check", obj_reg, type_reg],
        node=node,
    )
    return reg


def lower_as_expr(ctx: TreeSitterEmitContext, node) -> str:
    """Lower 'as' cast -- lower the left operand, treat cast as passthrough."""
    children = [c for c in node.children if c.is_named]
    if children:
        return ctx.lower_expr(children[0])
    return lower_const_literal(ctx, node)


def lower_declaration_pattern(ctx: TreeSitterEmitContext, node) -> str:
    """Lower `int i` declaration pattern -> CONST type + STORE_VAR binding."""
    named_children = [c for c in node.children if c.is_named]
    type_node = named_children[0] if named_children else None
    designation = named_children[1] if len(named_children) > 1 else None

    type_reg = ctx.fresh_reg()
    type_name = ctx.node_text(type_node) if type_node else "Object"
    ctx.emit(Opcode.CONST, result_reg=type_reg, operands=[type_name])

    if designation:
        var_name = ctx.node_text(designation)
        ctx.emit(
            Opcode.DECL_VAR,
            operands=[var_name, type_reg],
            node=node,
        )
    return type_reg


def lower_lambda(ctx: TreeSitterEmitContext, node) -> str:
    """Lower C# lambda: (params) => expr or (params) => { body }."""
    func_name = f"__lambda_{ctx.label_counter}"
    func_label = ctx.fresh_label(f"{constants.FUNC_LABEL_PREFIX}{func_name}")
    end_label = ctx.fresh_label("lambda_end")

    ctx.emit(Opcode.BRANCH, label=end_label)
    ctx.emit(Opcode.LABEL, label=func_label)

    # Lower parameters
    params_node = node.child_by_field_name(ctx.constants.func_params_field)
    if params_node:
        lower_csharp_params(ctx, params_node)

    # Lower body
    body_node = node.child_by_field_name(ctx.constants.func_body_field)
    if body_node and body_node.type == NT.BLOCK:
        ctx.lower_block(body_node)
    elif body_node:
        # Expression body -- evaluate and return
        body_reg = ctx.lower_expr(body_node)
        ctx.emit(Opcode.RETURN, operands=[body_reg])

    # Implicit return for block bodies (if no explicit return)
    if body_node and body_node.type == NT.BLOCK:
        none_reg = ctx.fresh_reg()
        ctx.emit(
            Opcode.CONST,
            result_reg=none_reg,
            operands=[ctx.constants.default_return_value],
        )
        ctx.emit(Opcode.RETURN, operands=[none_reg])

    ctx.emit(Opcode.LABEL, label=end_label)

    ref_reg = ctx.fresh_reg()
    ctx.emit(
        Opcode.CONST,
        result_reg=ref_reg,
        operands=[constants.FUNC_REF_TEMPLATE.format(name=func_name, label=func_label)],
        node=node,
    )
    return ref_reg


def lower_array_creation(ctx: TreeSitterEmitContext, node) -> str:
    """Lower array_creation_expression / implicit_array_creation_expression."""
    # Find initializer: initializer_expression for both explicit and implicit
    init_node = node.child_by_field_name("initializer")
    if init_node is None:
        init_node = next(
            (c for c in node.children if c.type == NT.INITIALIZER_EXPRESSION),
            None,
        )

    if init_node is not None:
        elements = [c for c in init_node.children if c.is_named]
        size_reg = ctx.fresh_reg()
        ctx.emit(Opcode.CONST, result_reg=size_reg, operands=[str(len(elements))])
        arr_reg = ctx.fresh_reg()
        ctx.emit(
            Opcode.NEW_ARRAY,
            result_reg=arr_reg,
            operands=["array", size_reg],
            node=node,
        )
        for i, elem in enumerate(elements):
            idx_reg = ctx.fresh_reg()
            ctx.emit(Opcode.CONST, result_reg=idx_reg, operands=[str(i)])
            val_reg = ctx.lower_expr(elem)
            ctx.emit(Opcode.STORE_INDEX, operands=[arr_reg, idx_reg, val_reg])
        return arr_reg

    # Sized array without initializer: new int[5]
    size_children = [
        c
        for c in node.children
        if c.is_named
        and c.type not in (NT.PREDEFINED_TYPE, NT.TYPE_IDENTIFIER, NT.ARRAY_TYPE)
    ]
    size_node = size_children[0] if size_children else None
    if size_node and size_node.type not in (NT.INITIALIZER_EXPRESSION,):
        size_reg = ctx.lower_expr(size_node)
    else:
        size_reg = ctx.fresh_reg()
        ctx.emit(Opcode.CONST, result_reg=size_reg, operands=["0"])
    arr_reg = ctx.fresh_reg()
    ctx.emit(
        Opcode.NEW_ARRAY,
        result_reg=arr_reg,
        operands=["array", size_reg],
        node=node,
    )
    return arr_reg


def lower_csharp_interpolated_string(ctx: TreeSitterEmitContext, node) -> str:
    """Lower C# $\"...{expr}...\" into CONST + expr + BINOP '+' chain."""
    has_interpolation = any(c.type == NT.INTERPOLATION for c in node.children)
    if not has_interpolation:
        return lower_const_literal(ctx, node)

    _INTERPOLATION_NOISE = frozenset(
        {
            NT.INTERPOLATION_BRACE,
            NT.INTERPOLATION_FORMAT_CLAUSE,
            NT.INTERPOLATION_ALIGNMENT_CLAUSE,
        }
    )

    parts: list[str] = []
    for child in node.children:
        if child.type == NT.STRING_CONTENT:
            frag_reg = ctx.fresh_reg()
            ctx.emit(
                Opcode.CONST,
                result_reg=frag_reg,
                operands=[ctx.node_text(child)],
                node=child,
            )
            parts.append(frag_reg)
        elif child.type == NT.INTERPOLATION:
            named = [
                c
                for c in child.children
                if c.is_named and c.type not in _INTERPOLATION_NOISE
            ]
            if named:
                parts.append(ctx.lower_expr(named[0]))
        # skip: interpolation_start, ", punctuation
    return lower_interpolated_string_parts(ctx, parts, node)


def lower_await_expr(ctx: TreeSitterEmitContext, node) -> str:
    """Lower await_expression as CALL_FUNCTION('await', expr)."""
    children = [c for c in node.children if c.is_named]
    if children:
        inner_reg = ctx.lower_expr(children[0])
    else:
        inner_reg = ctx.fresh_reg()
        ctx.emit(
            Opcode.CONST,
            result_reg=inner_reg,
            operands=[ctx.constants.none_literal],
        )
    reg = ctx.fresh_reg()
    ctx.emit(
        Opcode.CALL_FUNCTION,
        result_reg=reg,
        operands=["await", inner_reg],
        node=node,
    )
    return reg


def lower_conditional_access(ctx: TreeSitterEmitContext, node) -> str:
    """Lower obj?.Field as LOAD_FIELD (null-safety is semantic)."""
    named = [c for c in node.children if c.is_named]
    if len(named) < 2:
        return lower_const_literal(ctx, node)
    obj_reg = ctx.lower_expr(named[0])
    # The second named child is typically member_binding_expression
    binding_node = named[1]
    if binding_node.type == NT.MEMBER_BINDING_EXPRESSION:
        # Extract the field name from member_binding_expression
        field_node = next(
            (c for c in binding_node.children if c.type == NT.IDENTIFIER), None
        )
        field_name = ctx.node_text(field_node) if field_node else "unknown"
    else:
        field_name = ctx.node_text(binding_node)
    reg = ctx.fresh_reg()
    ctx.emit(
        Opcode.LOAD_FIELD,
        result_reg=reg,
        operands=[obj_reg, field_name],
        node=node,
    )
    return reg


def lower_member_binding(ctx: TreeSitterEmitContext, node) -> str:
    """Lower .Field part of conditional access -- standalone fallback."""
    field_node = next((c for c in node.children if c.type == NT.IDENTIFIER), None)
    field_name = ctx.node_text(field_node) if field_node else "unknown"
    reg = ctx.fresh_reg()
    ctx.emit(
        Opcode.SYMBOLIC,
        result_reg=reg,
        operands=[f"member_binding:{field_name}"],
        node=node,
    )
    return reg


def lower_tuple_expr(ctx: TreeSitterEmitContext, node) -> str:
    """Lower tuple (a, b, c) as NEW_ARRAY with elements."""
    arguments = [c for c in node.children if c.type == NT.ARGUMENT]
    elem_regs = [
        ctx.lower_expr(next((gc for gc in arg.children if gc.is_named), arg))
        for arg in arguments
    ]

    size_reg = ctx.fresh_reg()
    ctx.emit(Opcode.CONST, result_reg=size_reg, operands=[str(len(elem_regs))])
    arr_reg = ctx.fresh_reg()
    ctx.emit(
        Opcode.NEW_ARRAY,
        result_reg=arr_reg,
        operands=["tuple", size_reg],
        node=node,
    )
    for i, elem_reg in enumerate(elem_regs):
        idx_reg = ctx.fresh_reg()
        ctx.emit(Opcode.CONST, result_reg=idx_reg, operands=[str(i)])
        ctx.emit(Opcode.STORE_INDEX, operands=[arr_reg, idx_reg, elem_reg])
    return arr_reg


def lower_is_pattern_expr(ctx: TreeSitterEmitContext, node) -> str:
    """Lower `x is int y` as CALL_FUNCTION('is_check', expr, type)."""
    named = [c for c in node.children if c.is_named]
    operand_node = named[0] if named else None
    pattern_node = named[1] if len(named) > 1 else None

    obj_reg = ctx.lower_expr(operand_node) if operand_node else ctx.fresh_reg()

    # Extract the type from the pattern
    type_name = ctx.node_text(pattern_node) if pattern_node else "Object"
    type_reg = ctx.fresh_reg()
    ctx.emit(Opcode.CONST, result_reg=type_reg, operands=[type_name])

    reg = ctx.fresh_reg()
    ctx.emit(
        Opcode.CALL_FUNCTION,
        result_reg=reg,
        operands=["is_check", obj_reg, type_reg],
        node=node,
    )
    return reg


def lower_implicit_object_creation(ctx: TreeSitterEmitContext, node) -> str:
    """Lower `new()` or `new() { ... }` as NEW_OBJECT + CALL_METHOD constructor."""
    args_node = node.child_by_field_name(ctx.constants.call_arguments_field)
    arg_regs = (
        [
            ctx.lower_expr(c)
            for c in args_node.children
            if c.is_named and c.type not in ("(", ")", ",")
        ]
        if args_node
        else []
    )
    obj_reg = ctx.fresh_reg()
    ctx.emit(
        Opcode.NEW_OBJECT,
        result_reg=obj_reg,
        operands=["__implicit"],
        node=node,
    )
    result_reg = ctx.fresh_reg()
    ctx.emit(
        Opcode.CALL_METHOD,
        result_reg=result_reg,
        operands=[obj_reg, "constructor"] + arg_regs,
        node=node,
    )
    return result_reg


def lower_query_expression(ctx: TreeSitterEmitContext, node) -> str:
    """Lower LINQ `from n in nums where ... select ...` as CALL_FUNCTION chain."""
    named_children = [c for c in node.children if c.is_named]
    arg_regs = [ctx.lower_expr(c) for c in named_children]
    reg = ctx.fresh_reg()
    ctx.emit(
        Opcode.CALL_FUNCTION,
        result_reg=reg,
        operands=["linq_query"] + arg_regs,
        node=node,
    )
    return reg


def lower_linq_clause(ctx: TreeSitterEmitContext, node) -> str:
    """Lower LINQ clause (from/select/where) -- lower named children only."""
    named_children = [c for c in node.children if c.is_named]
    last_reg = ctx.fresh_reg()
    ctx.emit(Opcode.CONST, result_reg=last_reg, operands=[ctx.constants.none_literal])
    for child in named_children:
        last_reg = ctx.lower_expr(child)
    return last_reg


def lower_csharp_store_target(
    ctx: TreeSitterEmitContext, target, val_reg: str, parent_node
) -> None:
    if target.type == NT.IDENTIFIER:
        ctx.emit(
            Opcode.STORE_VAR,
            operands=[ctx.node_text(target), val_reg],
            node=parent_node,
        )
    elif target.type == NT.MEMBER_ACCESS_EXPRESSION:
        obj_node = target.child_by_field_name("expression")
        name_node = target.child_by_field_name("name")
        if obj_node and name_node:
            obj_reg = ctx.lower_expr(obj_node)
            ctx.emit(
                Opcode.STORE_FIELD,
                operands=[obj_reg, ctx.node_text(name_node), val_reg],
                node=parent_node,
            )
    elif target.type == NT.ELEMENT_ACCESS_EXPRESSION:
        obj_node = target.child_by_field_name("expression")
        bracket_node = target.child_by_field_name("subscript")
        if obj_node:
            obj_reg = ctx.lower_expr(obj_node)
            if bracket_node is None:
                bracket_node = next(
                    (
                        c
                        for c in target.children
                        if c.is_named and c.type == NT.BRACKETED_ARGUMENT_LIST
                    ),
                    None,
                )
            idx_reg = _extract_bracket_index(ctx, bracket_node)
            ctx.emit(
                Opcode.STORE_INDEX,
                operands=[obj_reg, idx_reg, val_reg],
                node=parent_node,
            )
    else:
        ctx.emit(
            Opcode.STORE_VAR,
            operands=[ctx.node_text(target), val_reg],
            node=parent_node,
        )


# -- shared C# param helper (used by expressions + declarations) ------


def lower_csharp_params(ctx: TreeSitterEmitContext, params_node) -> None:
    """Lower C# formal parameters (parameter nodes)."""
    for child in params_node.children:
        if child.type == NT.PARAMETER:
            name_node = child.child_by_field_name("name")
            if name_node:
                pname = ctx.node_text(name_node)
                type_hint = extract_normalized_type(ctx, child, "type", ctx.type_map)
                param_reg = ctx.fresh_reg()
                ctx.emit(
                    Opcode.SYMBOLIC,
                    result_reg=param_reg,
                    operands=[f"{constants.PARAM_PREFIX}{pname}"],
                    node=child,
                )
                ctx.seed_register_type(param_reg, type_hint)
                ctx.seed_param_type(pname, type_hint)
                ctx.emit(
                    Opcode.DECL_VAR,
                    operands=[pname, param_reg],
                )
                ctx.seed_var_type(pname, type_hint)


# -- P1 gap handlers ------------------------------------------------------


def lower_checked_expr(ctx: TreeSitterEmitContext, node) -> str:
    """Lower checked(expr) / unchecked(expr) — just lower the inner expression."""
    named_children = [c for c in node.children if c.is_named]
    return (
        ctx.lower_expr(named_children[0])
        if named_children
        else lower_const_literal(ctx, node)
    )


def lower_range_expr(ctx: TreeSitterEmitContext, node) -> str:
    """Lower `0..5` or `..5` or `0..` as CALL_FUNCTION("range", start, end)."""
    named_children = [c for c in node.children if c.is_named]
    if len(named_children) >= 2:
        start_reg = ctx.lower_expr(named_children[0])
        end_reg = ctx.lower_expr(named_children[1])
    elif len(named_children) == 1:
        start_reg = ctx.lower_expr(named_children[0])
        end_reg = ctx.fresh_reg()
        ctx.emit(Opcode.CONST, result_reg=end_reg, operands=[""])
    else:
        start_reg = ctx.fresh_reg()
        ctx.emit(Opcode.CONST, result_reg=start_reg, operands=[""])
        end_reg = ctx.fresh_reg()
        ctx.emit(Opcode.CONST, result_reg=end_reg, operands=[""])
    reg = ctx.fresh_reg()
    ctx.emit(
        Opcode.CALL_FUNCTION,
        result_reg=reg,
        operands=["range", start_reg, end_reg],
        node=node,
    )
    return reg
