"""PHP-specific expression lowerers -- pure functions taking (ctx, node)."""

from __future__ import annotations
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from interpreter.ir import SpreadArguments, CodeLabel

import logging
from interpreter.frontends.context import TreeSitterEmitContext

from interpreter.operator_kind import resolve_binop
from interpreter.var_name import VarName
from interpreter.field_name import FieldName
from interpreter.func_name import FuncName
from interpreter.instructions import (
    Binop,
    Branch,
    BranchIf,
    CallFunction,
    CallMethod,
    CallUnknown,
    Const,
    DeclVar,
    Label_,
    LoadField,
    LoadIndex,
    LoadVar,
    NewArray,
    NewObject,
    Return_,
    StoreField,
    StoreIndex,
    StoreVar,
)
from interpreter import constants
from interpreter.frontends.common.expressions import (
    lower_const_literal,
    extract_call_args_unwrap,
)
from interpreter.frontends.php.node_types import PHPNodeType
from interpreter.register import Register
from interpreter.types.type_expr import scalar

logger = logging.getLogger(__name__)

_NON_INTERPOLATION_TYPES = frozenset(
    {PHPNodeType.STRING_CONTENT, PHPNodeType.ESCAPE_SEQUENCE}
)


def lower_php_variable(ctx: TreeSitterEmitContext, node) -> Register:
    """Lower PHP variable ($x) as LOAD_VAR."""
    var_name = ctx.node_text(node)
    reg = ctx.fresh_reg()
    ctx.emit_inst(LoadVar(result_reg=reg, name=VarName(var_name)), node=node)
    return reg


def _lower_php_interpolated_children(
    ctx: TreeSitterEmitContext, children, node
) -> Register:
    """Shared logic: decompose string_content / variable_name / expr children into CONST + BINOP '+'.

    Used by both encapsed_string and heredoc_body.
    NOTE: PHP ``dynamic_variable_name`` (``${$var}``) is not registered in
    ``_EXPR_DISPATCH`` and falls back to SYMBOLIC -- variable-variable
    indirection cannot be statically lowered.
    """
    parts: list[str] = [
        _lower_interpolated_child(ctx, child)
        for child in children
        if _is_interpolation_relevant(child)
    ]
    return _lower_interpolated_string_parts(ctx, parts, node)


def _is_interpolation_relevant(child) -> bool:
    """Return True if the child should contribute to interpolation."""
    return (
        child.type == PHPNodeType.STRING_CONTENT
        or child.type == PHPNodeType.VARIABLE_NAME
        or child.is_named
    )


def _lower_interpolated_child(ctx: TreeSitterEmitContext, child) -> Register:
    """Lower a single interpolation child to a register."""
    if child.type == PHPNodeType.STRING_CONTENT:
        frag_reg = ctx.fresh_reg()
        ctx.emit_inst(
            Const(result_reg=frag_reg, value=ctx.node_text(child)), node=child
        )
        return frag_reg
    if child.type == PHPNodeType.VARIABLE_NAME:
        return lower_php_variable(ctx, child)
    return ctx.lower_expr(child)


def _lower_interpolated_string_parts(
    ctx: TreeSitterEmitContext, parts: list[str], node
) -> Register:
    """Concatenate parts with BINOP '+'."""
    if not parts:
        reg = ctx.fresh_reg()
        ctx.emit_inst(Const(result_reg=reg, value=""), node=node)
        return reg
    result = parts[0]
    for part in parts[1:]:
        new_reg = ctx.fresh_reg()
        ctx.emit_inst(
            Binop(
                result_reg=new_reg, operator=resolve_binop("+"), left=result, right=part
            ),
            node=node,
        )
        result = new_reg
    return result


def lower_php_encapsed_string(ctx: TreeSitterEmitContext, node) -> Register:
    """Lower PHP double-quoted string, decomposing interpolation into CONST + LOAD_VAR + BINOP '+'."""
    has_interpolation = any(
        c.is_named and c.type not in _NON_INTERPOLATION_TYPES for c in node.children
    )
    if not has_interpolation:
        return lower_const_literal(ctx, node)
    return _lower_php_interpolated_children(ctx, node.children, node)


def lower_php_heredoc(ctx: TreeSitterEmitContext, node) -> Register:
    """Lower PHP heredoc (<<<EOT ... EOT), decomposing interpolation inside heredoc_body."""
    body = next((c for c in node.children if c.type == PHPNodeType.HEREDOC_BODY), None)
    if body is None:
        return lower_const_literal(ctx, node)

    has_interpolation = any(
        c.is_named and c.type not in _NON_INTERPOLATION_TYPES for c in body.children
    )
    if not has_interpolation:
        return lower_const_literal(ctx, node)
    return _lower_php_interpolated_children(ctx, body.children, node)


def lower_php_func_call(ctx: TreeSitterEmitContext, node) -> Register:
    """Lower function_call_expression: name(args) or dynamic call."""
    func_node = node.child_by_field_name(ctx.constants.call_function_field)
    args_node = node.child_by_field_name(ctx.constants.call_arguments_field)
    arg_regs = extract_call_args_unwrap(ctx, args_node) if args_node else []

    if func_node and func_node.type in (PHPNodeType.NAME, PHPNodeType.QUALIFIED_NAME):
        func_name = ctx.node_text(func_node)
        reg = ctx.fresh_reg()
        ctx.emit_inst(
            CallFunction(
                result_reg=reg, func_name=FuncName(func_name), args=tuple(arg_regs)
            ),
            node=node,
        )
        return reg

    # Dynamic call target
    target_reg = ctx.lower_expr(func_node) if func_node else ctx.fresh_reg()
    reg = ctx.fresh_reg()
    ctx.emit_inst(
        CallUnknown(result_reg=reg, target_reg=target_reg, args=tuple(arg_regs)),
        node=node,
    )
    return reg


def lower_php_method_call(ctx: TreeSitterEmitContext, node) -> Register:
    """Lower $obj->method(args) as CALL_METHOD."""
    obj_node = node.child_by_field_name(ctx.constants.attr_object_field)
    name_node = node.child_by_field_name("name")
    args_node = node.child_by_field_name(ctx.constants.call_arguments_field)
    arg_regs = extract_call_args_unwrap(ctx, args_node) if args_node else []

    obj_reg = ctx.lower_expr(obj_node) if obj_node else ctx.fresh_reg()
    method_name = ctx.node_text(name_node) if name_node else "unknown"
    reg = ctx.fresh_reg()
    ctx.emit_inst(
        CallMethod(
            result_reg=reg,
            obj_reg=obj_reg,
            method_name=FuncName(method_name),
            args=tuple(arg_regs),
        ),
        node=node,
    )
    return reg


def lower_php_member_access(ctx: TreeSitterEmitContext, node) -> Register:
    """Lower $obj->field as LOAD_FIELD."""
    obj_node = node.child_by_field_name(ctx.constants.attr_object_field)
    name_node = node.child_by_field_name("name")
    if obj_node is None or name_node is None:
        return lower_const_literal(ctx, node)
    obj_reg = ctx.lower_expr(obj_node)
    field_name = ctx.node_text(name_node)
    reg = ctx.fresh_reg()
    ctx.emit_inst(
        LoadField(result_reg=reg, obj_reg=obj_reg, field_name=FieldName(field_name)),
        node=node,
    )
    return reg


def lower_php_subscript(ctx: TreeSitterEmitContext, node) -> Register:
    """Lower $arr[idx] as LOAD_INDEX."""
    children = [c for c in node.children if c.is_named]
    if len(children) < 2:
        return lower_const_literal(ctx, node)
    obj_reg = ctx.lower_expr(children[0])
    idx_reg = ctx.lower_expr(children[1])
    reg = ctx.fresh_reg()
    ctx.emit_inst(
        LoadIndex(result_reg=reg, arr_reg=obj_reg, index_reg=idx_reg), node=node
    )
    return reg


def lower_php_assignment_expr(ctx: TreeSitterEmitContext, node) -> Register:
    """Lower assignment expression ($x = expr)."""
    left = node.child_by_field_name(ctx.constants.assign_left_field)
    right = node.child_by_field_name(ctx.constants.assign_right_field)
    val_reg = ctx.lower_expr(right)
    lower_php_store_target(ctx, left, val_reg, node)
    return val_reg


def lower_php_augmented_assignment_expr(ctx: TreeSitterEmitContext, node) -> Register:
    """Lower augmented assignment ($x += expr)."""
    left = node.child_by_field_name(ctx.constants.assign_left_field)
    right = node.child_by_field_name(ctx.constants.assign_right_field)
    op_node = [c for c in node.children if c.type not in (left.type, right.type)][0]
    op_text = ctx.node_text(op_node).rstrip("=")
    lhs_reg = ctx.lower_expr(left)
    rhs_reg = ctx.lower_expr(right)
    result = ctx.fresh_reg()
    ctx.emit_inst(
        Binop(
            result_reg=result,
            operator=resolve_binop(op_text),
            left=lhs_reg,
            right=rhs_reg,
        ),
        node=node,
    )
    lower_php_store_target(ctx, left, result, node)
    return result


def lower_php_store_target(
    ctx: TreeSitterEmitContext, target, val_reg: str, parent_node
) -> None:
    """Store to a PHP target: variable_name, member_access, subscript, or fallback."""
    if target.type in (PHPNodeType.VARIABLE_NAME, PHPNodeType.NAME):
        ctx.emit_inst(
            StoreVar(name=VarName(ctx.node_text(target)), value_reg=val_reg),
            node=parent_node,
        )
    elif target.type == PHPNodeType.MEMBER_ACCESS_EXPRESSION:
        obj_node = target.child_by_field_name(ctx.constants.attr_object_field)
        name_node = target.child_by_field_name("name")
        if obj_node and name_node:
            obj_reg = ctx.lower_expr(obj_node)
            ctx.emit_inst(
                StoreField(
                    obj_reg=obj_reg,
                    field_name=FieldName(ctx.node_text(name_node)),
                    value_reg=val_reg,
                ),
                node=parent_node,
            )
    elif target.type == PHPNodeType.SUBSCRIPT_EXPRESSION:
        children = [c for c in target.children if c.is_named]
        if len(children) >= 2:
            obj_reg = ctx.lower_expr(children[0])
            idx_reg = ctx.lower_expr(children[1])
            ctx.emit_inst(
                StoreIndex(arr_reg=obj_reg, index_reg=idx_reg, value_reg=val_reg),
                node=parent_node,
            )
    elif target.type == PHPNodeType.LIST_LITERAL:
        vars_ = [c for c in target.children if c.is_named]
        for i, var_node in enumerate(vars_):
            idx_reg = ctx.fresh_reg()
            ctx.emit_inst(Const(result_reg=idx_reg, value=i))
            elem_reg = ctx.fresh_reg()
            ctx.emit_inst(
                LoadIndex(result_reg=elem_reg, arr_reg=val_reg, index_reg=idx_reg),
                node=var_node,
            )
            lower_php_store_target(ctx, var_node, elem_reg, parent_node)
    else:
        ctx.emit_inst(
            StoreVar(name=VarName(ctx.node_text(target)), value_reg=val_reg),
            node=parent_node,
        )


def lower_php_cast(ctx: TreeSitterEmitContext, node) -> Register:
    """Lower (type) expr -- just lower the inner expression."""
    children = [c for c in node.children if c.is_named]
    if children:
        return ctx.lower_expr(children[-1])
    return lower_const_literal(ctx, node)


def lower_php_ternary(ctx: TreeSitterEmitContext, node) -> Register:
    """Lower ternary / conditional expression ($cond ? $a : $b)."""
    cond_node = node.child_by_field_name(ctx.constants.if_condition_field)
    true_node = node.child_by_field_name("body")
    false_node = node.child_by_field_name(ctx.constants.if_alternative_field)

    if cond_node is None:
        return lower_const_literal(ctx, node)

    cond_reg = ctx.lower_expr(cond_node)
    true_label = ctx.fresh_label("ternary_true")
    false_label = ctx.fresh_label("ternary_false")
    end_label = ctx.fresh_label("ternary_end")

    ctx.emit_inst(BranchIf(cond_reg=cond_reg, branch_targets=(true_label, false_label)))

    ctx.emit_inst(Label_(label=true_label))
    true_reg = ctx.lower_expr(true_node) if true_node else cond_reg
    result_var = f"__ternary_{ctx.label_counter}"
    ctx.emit_inst(DeclVar(name=VarName(result_var), value_reg=true_reg))
    ctx.emit_inst(Branch(label=end_label))

    ctx.emit_inst(Label_(label=false_label))
    false_reg = ctx.lower_expr(false_node) if false_node else ctx.fresh_reg()
    ctx.emit_inst(DeclVar(name=VarName(result_var), value_reg=false_reg))
    ctx.emit_inst(Branch(label=end_label))

    ctx.emit_inst(Label_(label=end_label))
    result_reg = ctx.fresh_reg()
    ctx.emit_inst(LoadVar(result_reg=result_reg, name=VarName(result_var)))
    return result_reg


def lower_php_throw_expr(ctx: TreeSitterEmitContext, node) -> Register:
    """Lower throw_expression when it appears in expression context."""
    from interpreter.frontends.common.exceptions import lower_raise_or_throw

    lower_raise_or_throw(ctx, node, keyword="throw")
    reg = ctx.fresh_reg()
    ctx.emit_inst(Const(result_reg=reg, value=ctx.constants.none_literal))
    return reg


def lower_php_object_creation(ctx: TreeSitterEmitContext, node) -> Register:
    """Lower ``new Foo(args)`` or ``new class { ... }``."""
    from interpreter.frontends.php.declarations import lower_php_class

    # Anonymous class: new class { ... }
    anon_node = next(
        (c for c in node.children if c.type == PHPNodeType.ANONYMOUS_CLASS), None
    )
    if anon_node is not None:
        # Lower the anonymous class body as a named class with synthetic name
        anon_name = f"__anon_class_{ctx.label_counter}"
        # Wrap the anonymous_class node so lower_php_class can process it
        # by setting a synthetic name and lowering the declaration_list body.
        _lower_php_anonymous_class(ctx, anon_node, anon_name)
        args_node = next(
            (c for c in node.children if c.type == PHPNodeType.ARGUMENTS), None
        )
        arg_regs = extract_call_args_unwrap(ctx, args_node) if args_node else []
        obj_reg = ctx.fresh_reg()
        ctx.emit_inst(
            NewObject(result_reg=obj_reg, type_hint=scalar(anon_name)), node=node
        )
        ctor_reg = ctx.fresh_reg()
        ctx.emit_inst(
            CallMethod(
                result_reg=ctor_reg,
                obj_reg=obj_reg,
                method_name=FuncName("__construct"),
                args=tuple(arg_regs),
            ),
            node=node,
        )
        return obj_reg

    # Named class: new Foo(args)
    name_node = node.child_by_field_name(ctx.constants.class_name_field)
    if name_node is None:
        name_node = next((c for c in node.children if c.type == PHPNodeType.NAME), None)
    args_node = next(
        (c for c in node.children if c.type == PHPNodeType.ARGUMENTS), None
    )
    arg_regs = extract_call_args_unwrap(ctx, args_node) if args_node else []
    type_name = ctx.node_text(name_node) if name_node else "Object"

    obj_reg = ctx.fresh_reg()
    ctx.emit_inst(NewObject(result_reg=obj_reg, type_hint=scalar(type_name)), node=node)
    ctor_reg = ctx.fresh_reg()
    ctx.emit_inst(
        CallMethod(
            result_reg=ctor_reg,
            obj_reg=obj_reg,
            method_name=FuncName("__construct"),
            args=tuple(arg_regs),
        ),
        node=node,
    )
    return obj_reg


def _lower_php_anonymous_class(
    ctx: TreeSitterEmitContext, anon_node, class_name: str
) -> None:
    """Lower an anonymous_class node as a class with a synthetic name."""
    from interpreter.frontends.php.declarations import (
        lower_php_method_decl,
        lower_php_property_declaration,
        _collect_php_field_inits,
        _emit_php_synthetic_constructor,
        _has_static_modifier,
        _is_php_constructor,
        _lower_php_constructor_with_field_inits,
    )

    body_node = next(
        (c for c in anon_node.children if c.type == PHPNodeType.DECLARATION_LIST),
        None,
    )
    class_label = ctx.fresh_label(f"{constants.CLASS_LABEL_PREFIX}{class_name}")
    end_label = ctx.fresh_label(f"{constants.END_CLASS_LABEL_PREFIX}{class_name}")

    ctx.emit_inst(Branch(label=end_label), node=anon_node)
    ctx.emit_inst(Label_(label=class_label))

    field_inits = []
    has_constructor = False
    if body_node:
        field_inits = [
            init
            for child in body_node.children
            if child.type == PHPNodeType.PROPERTY_DECLARATION
            and not _has_static_modifier(child)
            for init in _collect_php_field_inits(ctx, child)
        ]
        has_constructor = any(
            _is_php_constructor(ctx, child) for child in body_node.children
        )
        saved_class = ctx._current_class_name
        ctx._current_class_name = class_name
        for child in body_node.children:
            if child.type == PHPNodeType.METHOD_DECLARATION:
                if _is_php_constructor(ctx, child):
                    _lower_php_constructor_with_field_inits(ctx, child, field_inits)
                else:
                    lower_php_method_decl(ctx, child)
            elif child.is_named and child.type not in (
                PHPNodeType.VISIBILITY_MODIFIER,
                PHPNodeType.PROPERTY_DECLARATION,
            ):
                ctx.lower_stmt(child)
        ctx._current_class_name = saved_class

    if not has_constructor and field_inits:
        _emit_php_synthetic_constructor(ctx, field_inits)

    ctx.emit_inst(Label_(label=end_label))
    cls_reg = ctx.fresh_reg()
    ctx.emit_class_ref(class_name, class_label, [], result_reg=cls_reg)
    ctx.emit_inst(DeclVar(name=VarName(class_name), value_reg=cls_reg))


def lower_php_array(ctx: TreeSitterEmitContext, node) -> Register:
    """Lower array_creation_expression: array(1, 2) or [1, 2] or ['k' => 'v'].

    Value-only elements: NEW_ARRAY + STORE_INDEX per element.
    Key-value elements: NEW_OBJECT + STORE_INDEX with key.
    """
    elements = [
        c for c in node.children if c.type == PHPNodeType.ARRAY_ELEMENT_INITIALIZER
    ]

    # Determine if associative (any element has =>)
    is_associative = any(
        any(ctx.node_text(sub) == "=>" for sub in elem.children) for elem in elements
    )

    if is_associative:
        return _lower_php_associative_array(ctx, node, elements)

    # Value-only: indexed array
    return _lower_php_indexed_array(ctx, node, elements)


def _lower_php_associative_array(
    ctx: TreeSitterEmitContext, node, elements: list
) -> Register:
    """Lower associative array as NEW_OBJECT + STORE_INDEX per key-value pair."""
    obj_reg = ctx.fresh_reg()
    ctx.emit_inst(NewObject(result_reg=obj_reg, type_hint=scalar("array")), node=node)
    for elem in elements:
        named = [c for c in elem.children if c.is_named]
        if len(named) >= 2:
            key_reg = ctx.lower_expr(named[0])
            val_reg = ctx.lower_expr(named[1])
            ctx.emit_inst(
                StoreIndex(arr_reg=obj_reg, index_reg=key_reg, value_reg=val_reg)
            )
        elif named:
            idx_reg = ctx.fresh_reg()
            ctx.emit_inst(Const(result_reg=idx_reg, value="0"))
            val_reg = ctx.lower_expr(named[0])
            ctx.emit_inst(
                StoreIndex(arr_reg=obj_reg, index_reg=idx_reg, value_reg=val_reg)
            )
    return obj_reg


def _lower_php_indexed_array(
    ctx: TreeSitterEmitContext, node, elements: list
) -> Register:
    """Lower indexed array as NEW_ARRAY + STORE_INDEX per element."""
    size_reg = ctx.fresh_reg()
    ctx.emit_inst(Const(result_reg=size_reg, value=str(len(elements))))
    arr_reg = ctx.fresh_reg()
    ctx.emit_inst(
        NewArray(result_reg=arr_reg, type_hint=scalar("array"), size_reg=size_reg),
        node=node,
    )
    for i, elem in enumerate(elements):
        named = [c for c in elem.children if c.is_named]
        val_reg = ctx.lower_expr(named[0]) if named else ctx.fresh_reg()
        idx_reg = ctx.fresh_reg()
        ctx.emit_inst(Const(result_reg=idx_reg, value=str(i)))
        ctx.emit_inst(StoreIndex(arr_reg=arr_reg, index_reg=idx_reg, value_reg=val_reg))
    return arr_reg


def lower_php_match_expression(ctx: TreeSitterEmitContext, node) -> Register:
    """Lower match(subject) { pattern => expr, default => expr } as if/else chain."""
    cond_node = node.child_by_field_name("condition")
    body_node = node.child_by_field_name("body")

    subject_reg = ctx.lower_expr(cond_node) if cond_node else ctx.fresh_reg()
    end_label = ctx.fresh_label("match_end")
    result_var = f"__match_{ctx.label_counter}"

    arms = (
        [
            c
            for c in body_node.children
            if c.type == PHPNodeType.MATCH_CONDITIONAL_EXPRESSION
        ]
        if body_node
        else []
    )
    default_arm = (
        next(
            (
                c
                for c in body_node.children
                if c.type == PHPNodeType.MATCH_DEFAULT_EXPRESSION
            ),
            None,
        )
        if body_node
        else None
    )

    for arm in arms:
        cond_list = arm.child_by_field_name("conditional_expressions")
        return_expr = arm.child_by_field_name("return_expression")

        arm_label = ctx.fresh_label("match_arm")
        next_label = ctx.fresh_label("match_next")

        if cond_list:
            patterns = [c for c in cond_list.children if c.is_named]
            if patterns:
                pattern_reg = ctx.lower_expr(patterns[0])
                cmp_reg = ctx.fresh_reg()
                ctx.emit_inst(
                    Binop(
                        result_reg=cmp_reg,
                        operator=resolve_binop("==="),
                        left=subject_reg,
                        right=pattern_reg,
                    ),
                    node=arm,
                )
                ctx.emit_inst(
                    BranchIf(cond_reg=cmp_reg, branch_targets=(arm_label, next_label))
                )
            else:
                ctx.emit_inst(Branch(label=arm_label))
        else:
            ctx.emit_inst(Branch(label=arm_label))

        ctx.emit_inst(Label_(label=arm_label))
        if return_expr:
            val_reg = ctx.lower_expr(return_expr)
            ctx.emit_inst(DeclVar(name=VarName(result_var), value_reg=val_reg))
        ctx.emit_inst(Branch(label=end_label))
        ctx.emit_inst(Label_(label=next_label))

    if default_arm:
        default_body = default_arm.child_by_field_name("return_expression")
        if default_body:
            val_reg = ctx.lower_expr(default_body)
            ctx.emit_inst(DeclVar(name=VarName(result_var), value_reg=val_reg))
        ctx.emit_inst(Branch(label=end_label))

    ctx.emit_inst(Label_(label=end_label))
    result_reg = ctx.fresh_reg()
    ctx.emit_inst(LoadVar(result_reg=result_reg, name=VarName(result_var)))
    return result_reg


def lower_php_arrow_function(ctx: TreeSitterEmitContext, node) -> Register:
    """Lower fn($x) => expr as a function definition with implicit return."""
    from interpreter.frontends.php.declarations import lower_php_params

    params_node = node.child_by_field_name(ctx.constants.func_params_field)
    body_node = node.child_by_field_name(ctx.constants.func_body_field)

    func_name = f"__arrow_{ctx.label_counter}"
    func_label = ctx.fresh_label(f"{constants.FUNC_LABEL_PREFIX}{func_name}")
    end_label = ctx.fresh_label(f"end_{func_name}")

    ctx.emit_inst(Branch(label=end_label))
    ctx.emit_inst(Label_(label=func_label))

    if params_node:
        lower_php_params(ctx, params_node)

    if body_node:
        val_reg = ctx.lower_expr(body_node)
        ctx.emit_inst(Return_(value_reg=val_reg))

    none_reg = ctx.fresh_reg()
    ctx.emit_inst(Const(result_reg=none_reg, value=ctx.constants.default_return_value))
    ctx.emit_inst(Return_(value_reg=none_reg))
    ctx.emit_inst(Label_(label=end_label))

    func_reg = ctx.fresh_reg()
    ctx.emit_func_ref(func_name, func_label, result_reg=func_reg)
    return func_reg


def lower_php_scoped_call(ctx: TreeSitterEmitContext, node) -> Register:
    """Lower ClassName::method(args) as CALL_METHOD on a ClassRef.

    Emits LOAD_VAR for the class name (which resolves to a ClassRef),
    then CALL_METHOD so that the static dispatch path in _handle_call_method
    picks it up via registry.class_methods.
    """
    scope_node = node.child_by_field_name("scope")
    name_node = node.child_by_field_name("name")
    args_node = node.child_by_field_name(ctx.constants.call_arguments_field)

    method_name = ctx.node_text(name_node) if name_node else "unknown"
    arg_regs = extract_call_args_unwrap(ctx, args_node) if args_node else []

    class_reg = ctx.fresh_reg()
    scope_name = ctx.node_text(scope_node) if scope_node else "Unknown"
    ctx.emit_inst(LoadVar(result_reg=class_reg, name=VarName(scope_name)), node=node)

    reg = ctx.fresh_reg()
    ctx.emit_inst(
        CallMethod(
            result_reg=reg,
            obj_reg=class_reg,
            method_name=FuncName(method_name),
            args=tuple(arg_regs),
        ),
        node=node,
    )
    return reg


def lower_php_anonymous_function(ctx: TreeSitterEmitContext, node) -> Register:
    """Lower function($x) use ($y) { body } as anonymous function."""
    from interpreter.frontends.php.declarations import lower_php_params
    from interpreter.frontends.php.control_flow import lower_php_compound

    params_node = node.child_by_field_name(ctx.constants.func_params_field)
    body_node = node.child_by_field_name(ctx.constants.func_body_field)

    func_name = f"__anon_{ctx.label_counter}"
    func_label = ctx.fresh_label(f"{constants.FUNC_LABEL_PREFIX}{func_name}")
    end_label = ctx.fresh_label(f"end_{func_name}")

    ctx.emit_inst(Branch(label=end_label))
    ctx.emit_inst(Label_(label=func_label))

    if params_node:
        lower_php_params(ctx, params_node)

    if body_node:
        lower_php_compound(ctx, body_node)

    none_reg = ctx.fresh_reg()
    ctx.emit_inst(Const(result_reg=none_reg, value=ctx.constants.default_return_value))
    ctx.emit_inst(Return_(value_reg=none_reg))
    ctx.emit_inst(Label_(label=end_label))

    func_reg = ctx.fresh_reg()
    ctx.emit_func_ref(func_name, func_label, result_reg=func_reg)
    return func_reg


def lower_php_nullsafe_member_access(ctx: TreeSitterEmitContext, node) -> Register:
    """Lower $obj?->field as LOAD_FIELD (null-safety is semantic)."""
    obj_node = node.child_by_field_name(ctx.constants.attr_object_field)
    name_node = node.child_by_field_name("name")
    if obj_node is None or name_node is None:
        return lower_const_literal(ctx, node)
    obj_reg = ctx.lower_expr(obj_node)
    field_name = ctx.node_text(name_node)
    reg = ctx.fresh_reg()
    ctx.emit_inst(
        LoadField(result_reg=reg, obj_reg=obj_reg, field_name=FieldName(field_name)),
        node=node,
    )
    return reg


def lower_php_class_constant_access(ctx: TreeSitterEmitContext, node) -> Register:
    """Lower ClassName::CONST as LOAD_FIELD on the class."""
    named = [c for c in node.children if c.is_named]
    if len(named) < 2:
        return lower_const_literal(ctx, node)
    class_reg = ctx.lower_expr(named[0])
    const_name = ctx.node_text(named[1])
    reg = ctx.fresh_reg()
    ctx.emit_inst(
        LoadField(result_reg=reg, obj_reg=class_reg, field_name=FieldName(const_name)),
        node=node,
    )
    return reg


def lower_php_scoped_property_access(ctx: TreeSitterEmitContext, node) -> Register:
    """Lower ClassName::$prop as LOAD_FIELD on the class."""
    named = [c for c in node.children if c.is_named]
    if len(named) < 2:
        return lower_const_literal(ctx, node)
    class_reg = ctx.lower_expr(named[0])
    prop_name = ctx.node_text(named[1])
    reg = ctx.fresh_reg()
    ctx.emit_inst(
        LoadField(result_reg=reg, obj_reg=class_reg, field_name=FieldName(prop_name)),
        node=node,
    )
    return reg


def lower_php_yield(ctx: TreeSitterEmitContext, node) -> Register:
    """Lower yield $value as CALL_FUNCTION('yield', expr)."""
    named = [c for c in node.children if c.is_named]
    arg_regs = [ctx.lower_expr(c) for c in named]
    reg = ctx.fresh_reg()
    ctx.emit_inst(
        CallFunction(result_reg=reg, func_name=FuncName("yield"), args=tuple(arg_regs)),
        node=node,
    )
    return reg


def lower_php_reference_assignment(ctx: TreeSitterEmitContext, node) -> Register:
    """Lower $x = &$y as STORE_VAR (ignore reference semantics)."""
    left = node.child_by_field_name(ctx.constants.assign_left_field)
    right = node.child_by_field_name(ctx.constants.assign_right_field)
    val_reg = ctx.lower_expr(right) if right else ctx.fresh_reg()
    if left:
        lower_php_store_target(ctx, left, val_reg, node)
    return val_reg


def lower_php_dynamic_variable(ctx: TreeSitterEmitContext, node) -> Register:
    """Lower ``${x}`` -- unwrap to inner variable_name or expression."""
    named_children = [c for c in node.children if c.is_named]
    if named_children:
        return ctx.lower_expr(named_children[0])
    return lower_const_literal(ctx, node)


def lower_php_include(ctx: TreeSitterEmitContext, node) -> Register:
    """Lower ``include 'file.php'`` / ``require_once 'file.php'`` as CALL_FUNCTION."""
    keyword = node.type.replace("_expression", "")
    named_children = [c for c in node.children if c.is_named]
    arg_reg = ctx.lower_expr(named_children[0]) if named_children else ctx.fresh_reg()
    reg = ctx.fresh_reg()
    ctx.emit_inst(
        CallFunction(result_reg=reg, func_name=FuncName(keyword), args=(arg_reg,)),
        node=node,
    )
    return reg


def lower_php_nullsafe_method_call(ctx: TreeSitterEmitContext, node) -> Register:
    """Lower ``$obj?->method(args)`` like regular method call."""
    obj_node = node.child_by_field_name(ctx.constants.attr_object_field)
    name_node = node.child_by_field_name("name")
    args_node = node.child_by_field_name(ctx.constants.call_arguments_field)

    obj_reg = ctx.lower_expr(obj_node) if obj_node else ctx.fresh_reg()
    method_name = ctx.node_text(name_node) if name_node else "__unknown"
    arg_regs = (
        [
            ctx.lower_expr(c)
            for c in args_node.children
            if c.is_named
            and c.type
            not in (PHPNodeType.OPEN_PAREN, PHPNodeType.CLOSE_PAREN, PHPNodeType.COMMA)
        ]
        if args_node
        else []
    )
    reg = ctx.fresh_reg()
    ctx.emit_inst(
        CallMethod(
            result_reg=reg,
            obj_reg=obj_reg,
            method_name=FuncName(method_name),
            args=tuple(arg_regs),
        ),
        node=node,
    )
    return reg


def lower_php_print_intrinsic(ctx: TreeSitterEmitContext, node) -> Register:
    """Lower ``print $x`` as CALL_FUNCTION('print', arg)."""
    named_children = [c for c in node.children if c.is_named]
    arg_reg = ctx.lower_expr(named_children[0]) if named_children else ctx.fresh_reg()
    reg = ctx.fresh_reg()
    ctx.emit_inst(
        CallFunction(result_reg=reg, func_name=FuncName("print"), args=(arg_reg,)),
        node=node,
    )
    return reg


def lower_php_clone_expression(ctx: TreeSitterEmitContext, node) -> Register:
    """Lower ``clone $obj`` as CALL_FUNCTION('clone', arg)."""
    named_children = [c for c in node.children if c.is_named]
    arg_reg = ctx.lower_expr(named_children[0]) if named_children else ctx.fresh_reg()
    reg = ctx.fresh_reg()
    ctx.emit_inst(
        CallFunction(result_reg=reg, func_name=FuncName("clone"), args=(arg_reg,)),
        node=node,
    )
    return reg


def lower_php_variadic_unpacking(
    ctx: TreeSitterEmitContext, node
) -> str | SpreadArguments:
    """Lower ``...$arr`` as CALL_FUNCTION('spread', inner)."""
    from interpreter.frontends.common.expressions import lower_spread_arg

    return lower_spread_arg(ctx, node)


def lower_php_error_suppression(ctx: TreeSitterEmitContext, node) -> Register:
    """Lower @expr — just lower the inner expression (error suppression is a no-op for us)."""
    named_children = [c for c in node.children if c.is_named]
    return (
        ctx.lower_expr(named_children[0])
        if named_children
        else lower_const_literal(ctx, node)
    )


def lower_php_sequence_expression(ctx: TreeSitterEmitContext, node) -> Register:
    """Lower comma expression ($a = 1, $b = 2) -> evaluate all, return last."""
    children = [c for c in node.children if c.is_named]
    if not children:
        return lower_const_literal(ctx, node)
    last_reg = children[0]
    for child in children:
        last_reg = ctx.lower_expr(child)
    return last_reg
