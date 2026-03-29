"""JavaScript-specific expression lowerers — pure functions taking (ctx, node)."""

from __future__ import annotations
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from interpreter.ir import SpreadArguments, CodeLabel

from interpreter.frontends.context import TreeSitterEmitContext

from interpreter import constants
from interpreter.frontends.common.expressions import lower_const_literal
from interpreter.frontends.javascript.node_types import JavaScriptNodeType as JSN
from interpreter.operator_kind import resolve_binop
from interpreter.register import Register
from interpreter.types.type_expr import scalar
from interpreter.field_name import FieldName
from interpreter.var_name import VarName
from interpreter.func_name import FuncName
from interpreter.instructions import (
    Const,
    LoadVar,
    DeclVar,
    StoreVar,
    Binop,
    CallFunction,
    CallMethod,
    CallUnknown,
    LoadField,
    LoadIndex,
    StoreField,
    StoreIndex,
    NewObject,
    Symbolic,
    Branch,
    BranchIf,
    Label_,
    Return_,
)


def _has_optional_chain(node) -> bool:
    """Check if a node contains an optional_chain (?.) child token."""
    return any(c.type == JSN.OPTIONAL_CHAIN for c in node.children)


def _emit_optional_guard(
    ctx: TreeSitterEmitContext, obj_reg: str, emit_access
) -> Register:
    """Wrap an access in a null guard: obj == None ? None : access(obj).

    emit_access is a callable that emits the access IR and returns the result register.
    """
    null_reg = ctx.fresh_reg()
    ctx.emit_inst(Const(result_reg=null_reg, value=ctx.constants.none_literal))
    cmp_reg = ctx.fresh_reg()
    ctx.emit_inst(
        Binop(
            result_reg=cmp_reg,
            operator=resolve_binop("=="),
            left=obj_reg,
            right=null_reg,
        )
    )

    null_label = ctx.fresh_label("optchain_null")
    access_label = ctx.fresh_label("optchain_access")
    end_label = ctx.fresh_label("optchain_end")
    result_var = f"__optchain_{ctx.label_counter}"

    ctx.emit_inst(BranchIf(cond_reg=cmp_reg, branch_targets=(null_label, access_label)))

    ctx.emit_inst(Label_(label=null_label))
    none_reg = ctx.fresh_reg()
    ctx.emit_inst(Const(result_reg=none_reg, value=ctx.constants.none_literal))
    ctx.emit_inst(DeclVar(name=VarName(result_var), value_reg=none_reg))
    ctx.emit_inst(Branch(label=end_label))

    ctx.emit_inst(Label_(label=access_label))
    access_reg = emit_access()
    ctx.emit_inst(DeclVar(name=VarName(result_var), value_reg=access_reg))
    ctx.emit_inst(Branch(label=end_label))

    ctx.emit_inst(Label_(label=end_label))
    result_reg = ctx.fresh_reg()
    ctx.emit_inst(LoadVar(result_reg=result_reg, name=VarName(result_var)))
    return result_reg


def lower_js_subscript(ctx: TreeSitterEmitContext, node) -> Register:
    obj_node = node.child_by_field_name(ctx.constants.attr_object_field)
    idx_node = node.child_by_field_name("index")
    if obj_node is None or idx_node is None:
        return lower_const_literal(ctx, node)
    obj_reg = ctx.lower_expr(obj_node)

    def emit_access():
        idx_reg = ctx.lower_expr(idx_node)
        reg = ctx.fresh_reg()
        ctx.emit_inst(
            LoadIndex(result_reg=reg, arr_reg=obj_reg, index_reg=idx_reg), node=node
        )
        return reg

    if _has_optional_chain(node):
        return _emit_optional_guard(ctx, obj_reg, emit_access)
    return emit_access()


def lower_js_attribute(ctx: TreeSitterEmitContext, node) -> Register:
    obj_node = node.child_by_field_name(ctx.constants.attr_object_field)
    prop_node = node.child_by_field_name("property")
    if obj_node is None or prop_node is None:
        return lower_const_literal(ctx, node)
    obj_reg = ctx.lower_expr(obj_node)
    field_name = ctx.node_text(prop_node)

    def emit_access():
        reg = ctx.fresh_reg()
        ctx.emit_inst(
            LoadField(
                result_reg=reg, obj_reg=obj_reg, field_name=FieldName(field_name)
            ),
            node=node,
        )
        return reg

    if _has_optional_chain(node):
        return _emit_optional_guard(ctx, obj_reg, emit_access)
    return emit_access()


def lower_js_call(ctx: TreeSitterEmitContext, node) -> Register:
    func_node = node.child_by_field_name(ctx.constants.call_function_field)
    args_node = node.child_by_field_name(ctx.constants.call_arguments_field)
    arg_regs = _extract_js_call_args(ctx, args_node) if args_node else []

    if func_node and func_node.type == JSN.MEMBER_EXPRESSION:
        obj_node = func_node.child_by_field_name(ctx.constants.attr_object_field)
        prop_node = func_node.child_by_field_name("property")
        if obj_node and prop_node:
            obj_reg = ctx.lower_expr(obj_node)
            method_name = ctx.node_text(prop_node)

            def emit_method_call():
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

            if _has_optional_chain(func_node):
                return _emit_optional_guard(ctx, obj_reg, emit_method_call)
            return emit_method_call()

    if func_node and func_node.type == JSN.IDENTIFIER:
        func_name = ctx.node_text(func_node)
        reg = ctx.fresh_reg()
        ctx.emit_inst(
            CallFunction(
                result_reg=reg, func_name=FuncName(func_name), args=tuple(arg_regs)
            ),
            node=node,
        )
        return reg

    target_reg = ctx.lower_expr(func_node) if func_node else ctx.fresh_reg()
    reg = ctx.fresh_reg()
    ctx.emit_inst(
        CallUnknown(result_reg=reg, target_reg=target_reg, args=tuple(arg_regs)),
        node=node,
    )
    return reg


def _extract_js_call_args(ctx: TreeSitterEmitContext, args_node) -> list[str]:
    if args_node is None:
        return []
    return [
        ctx.lower_expr(c)
        for c in args_node.children
        if c.type not in (JSN.OPEN_PAREN, JSN.CLOSE_PAREN, JSN.COMMA) and c.is_named
    ]


def lower_js_store_target(
    ctx: TreeSitterEmitContext, target, val_reg: str, parent_node
) -> None:
    if target.type == JSN.IDENTIFIER:
        ctx.emit_inst(
            StoreVar(name=VarName(ctx.node_text(target)), value_reg=val_reg),
            node=parent_node,
        )
    elif target.type == JSN.MEMBER_EXPRESSION:
        obj_node = target.child_by_field_name(ctx.constants.attr_object_field)
        prop_node = target.child_by_field_name("property")
        if obj_node and prop_node:
            obj_reg = ctx.lower_expr(obj_node)
            ctx.emit_inst(
                StoreField(
                    obj_reg=obj_reg,
                    field_name=FieldName(ctx.node_text(prop_node)),
                    value_reg=val_reg,
                ),
                node=parent_node,
            )
    elif target.type == JSN.SUBSCRIPT_EXPRESSION:
        obj_node = target.child_by_field_name(ctx.constants.attr_object_field)
        idx_node = target.child_by_field_name("index")
        if obj_node and idx_node:
            obj_reg = ctx.lower_expr(obj_node)
            idx_reg = ctx.lower_expr(idx_node)
            ctx.emit_inst(
                StoreIndex(arr_reg=obj_reg, index_reg=idx_reg, value_reg=val_reg),
                node=parent_node,
            )
    else:
        ctx.emit_inst(
            StoreVar(name=VarName(ctx.node_text(target)), value_reg=val_reg),
            node=parent_node,
        )


def lower_assignment_expr(ctx: TreeSitterEmitContext, node) -> Register:
    left = node.child_by_field_name(ctx.constants.assign_left_field)
    right = node.child_by_field_name(ctx.constants.assign_right_field)
    val_reg = ctx.lower_expr(right)
    lower_js_store_target(ctx, left, val_reg, node)
    return val_reg


def lower_js_object_literal(ctx: TreeSitterEmitContext, node) -> Register:
    obj_reg = ctx.fresh_reg()
    ctx.emit_inst(NewObject(result_reg=obj_reg, type_hint=scalar("object")), node=node)
    for child in node.children:
        if child.type == JSN.PAIR:
            key_node = child.child_by_field_name("key")
            val_node = child.child_by_field_name("value")
            if key_node and val_node:
                if key_node.type == JSN.COMPUTED_PROPERTY_NAME:
                    inner_expr = next(
                        (c for c in key_node.children if c.is_named), None
                    )
                    key_reg = (
                        ctx.lower_expr(inner_expr)
                        if inner_expr
                        else lower_const_literal(ctx, key_node)
                    )
                else:
                    key_reg = lower_const_literal(ctx, key_node)
                val_reg = ctx.lower_expr(val_node)
                ctx.emit_inst(
                    StoreIndex(arr_reg=obj_reg, index_reg=key_reg, value_reg=val_reg)
                )
        elif child.type == JSN.SHORTHAND_PROPERTY_IDENTIFIER:
            from interpreter.frontends.common.expressions import lower_identifier

            key_reg = lower_const_literal(ctx, child)
            val_reg = lower_identifier(ctx, child)
            ctx.emit_inst(
                StoreIndex(arr_reg=obj_reg, index_reg=key_reg, value_reg=val_reg)
            )
    return obj_reg


def lower_arrow_function(ctx: TreeSitterEmitContext, node) -> Register:
    params_node = node.child_by_field_name(ctx.constants.func_params_field)
    body_node = node.child_by_field_name(ctx.constants.func_body_field)

    func_name = f"__arrow_{ctx.label_counter}"
    func_label = ctx.fresh_label(f"{constants.FUNC_LABEL_PREFIX}{func_name}")
    end_label = ctx.fresh_label(f"end_{func_name}")

    ctx.emit_inst(Branch(label=end_label))
    ctx.emit_inst(Label_(label=func_label))

    if params_node:
        if params_node.type == JSN.IDENTIFIER:
            lower_js_param(ctx, params_node, 0)
        else:
            lower_js_params(ctx, params_node)

    if body_node:
        if body_node.type == JSN.STATEMENT_BLOCK:
            ctx.lower_block(body_node)
        else:
            # Expression body: implicit return
            val_reg = ctx.lower_expr(body_node)
            ctx.emit_inst(Return_(value_reg=val_reg))

    none_reg = ctx.fresh_reg()
    ctx.emit_inst(Const(result_reg=none_reg, value=ctx.constants.default_return_value))
    ctx.emit_inst(Return_(value_reg=none_reg))
    ctx.emit_inst(Label_(label=end_label))

    func_reg = ctx.fresh_reg()
    ctx.emit_func_ref(func_name, func_label, result_reg=func_reg)
    return func_reg


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
    ctx.emit_inst(DeclVar(name=VarName(result_var), value_reg=true_reg))
    ctx.emit_inst(Branch(label=end_label))

    ctx.emit_inst(Label_(label=false_label))
    false_reg = ctx.lower_expr(false_node)
    ctx.emit_inst(DeclVar(name=VarName(result_var), value_reg=false_reg))
    ctx.emit_inst(Branch(label=end_label))

    ctx.emit_inst(Label_(label=end_label))
    result_reg = ctx.fresh_reg()
    ctx.emit_inst(LoadVar(result_reg=result_reg, name=VarName(result_var)))
    return result_reg


def lower_new_expression(ctx: TreeSitterEmitContext, node) -> Register:
    """Lower `new Foo(args)` -> NEW_OBJECT(class) + CALL_METHOD('constructor', args)."""
    constructor_node = node.child_by_field_name("constructor")
    args_node = node.child_by_field_name(ctx.constants.call_arguments_field)
    class_name = ctx.node_text(constructor_node) if constructor_node else "Object"
    arg_regs = _extract_js_call_args(ctx, args_node) if args_node else []

    obj_reg = ctx.fresh_reg()
    ctx.emit_inst(
        NewObject(result_reg=obj_reg, type_hint=scalar(class_name)), node=node
    )
    ctor_reg = ctx.fresh_reg()
    ctx.emit_inst(
        CallMethod(
            result_reg=ctor_reg,
            obj_reg=obj_reg,
            method_name=FuncName("constructor"),
            args=tuple(arg_regs),
        ),
        node=node,
    )
    return obj_reg


def lower_await_expression(ctx: TreeSitterEmitContext, node) -> Register:
    """Lower `await expr` -> CALL_FUNCTION('await', expr)."""
    children = [c for c in node.children if c.is_named]
    expr_reg = ctx.lower_expr(children[0]) if children else ctx.fresh_reg()
    reg = ctx.fresh_reg()
    ctx.emit_inst(
        CallFunction(result_reg=reg, func_name=FuncName("await"), args=(expr_reg,)),
        node=node,
    )
    return reg


def lower_yield_expression(ctx: TreeSitterEmitContext, node) -> Register:
    """Lower `yield expr` or bare `yield` -> CALL_FUNCTION('yield', expr)."""
    children = [c for c in node.children if c.is_named]
    if children:
        expr_reg = ctx.lower_expr(children[0])
        reg = ctx.fresh_reg()
        ctx.emit_inst(
            CallFunction(result_reg=reg, func_name=FuncName("yield"), args=(expr_reg,)),
            node=node,
        )
        return reg
    # Bare yield
    none_reg = ctx.fresh_reg()
    ctx.emit_inst(Const(result_reg=none_reg, value=ctx.constants.none_literal))
    reg = ctx.fresh_reg()
    ctx.emit_inst(
        CallFunction(result_reg=reg, func_name=FuncName("yield"), args=(none_reg,)),
        node=node,
    )
    return reg


def lower_sequence_expression(ctx: TreeSitterEmitContext, node) -> Register:
    """Lower `(a, b, c)` -> evaluate all, return last register."""
    children = [c for c in node.children if c.is_named]
    if not children:
        return lower_const_literal(ctx, node)
    last_reg = ctx.lower_expr(children[0])
    for child in children[1:]:
        last_reg = ctx.lower_expr(child)
    return last_reg


def lower_spread_element(ctx: TreeSitterEmitContext, node) -> str | SpreadArguments:
    """Lower `...expr` -> CALL_FUNCTION('spread', expr)."""
    from interpreter.frontends.common.expressions import lower_spread_arg

    return lower_spread_arg(ctx, node)


def lower_function_expression(ctx: TreeSitterEmitContext, node) -> Register:
    """Lower anonymous function expression: same as function_declaration but anonymous."""
    name_node = node.child_by_field_name(ctx.constants.func_name_field)
    params_node = node.child_by_field_name(ctx.constants.func_params_field)
    body_node = node.child_by_field_name(ctx.constants.func_body_field)

    func_name = ctx.node_text(name_node) if name_node else f"__anon_{ctx.label_counter}"
    func_label = ctx.fresh_label(f"{constants.FUNC_LABEL_PREFIX}{func_name}")
    end_label = ctx.fresh_label(f"end_{func_name}")

    ctx.emit_inst(Branch(label=end_label))
    ctx.emit_inst(Label_(label=func_label))

    if params_node:
        lower_js_params(ctx, params_node)

    if body_node:
        ctx.lower_block(body_node)

    none_reg = ctx.fresh_reg()
    ctx.emit_inst(Const(result_reg=none_reg, value=ctx.constants.default_return_value))
    ctx.emit_inst(Return_(value_reg=none_reg))
    ctx.emit_inst(Label_(label=end_label))

    func_reg = ctx.fresh_reg()
    ctx.emit_func_ref(func_name, func_label, result_reg=func_reg)
    return func_reg


def lower_template_string(ctx: TreeSitterEmitContext, node) -> Register:
    """Lower template string, descending into template_substitution children."""
    has_substitution = any(c.type == JSN.TEMPLATE_SUBSTITUTION for c in node.children)
    if not has_substitution:
        return lower_const_literal(ctx, node)

    # Build by concatenating literal fragments and substitution expressions
    parts: list[str] = []
    for child in node.children:
        if child.type == JSN.TEMPLATE_SUBSTITUTION:
            parts.append(lower_template_substitution(ctx, child))
        elif child.is_named:
            parts.append(ctx.lower_expr(child))
        elif child.type not in (JSN.BACKTICK,):
            # String fragment
            frag_reg = ctx.fresh_reg()
            ctx.emit_inst(Const(result_reg=frag_reg, value=ctx.node_text(child)))
            parts.append(frag_reg)

    if not parts:
        return lower_const_literal(ctx, node)
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


def lower_template_substitution(ctx: TreeSitterEmitContext, node) -> Register:
    """Lower ${expr} inside a template string."""
    children = [c for c in node.children if c.is_named]
    if children:
        return ctx.lower_expr(children[0])
    return lower_const_literal(ctx, node)


def lower_export_clause(ctx: TreeSitterEmitContext, node) -> Register:
    """Lower `{ a, b }` export clause — lower inner export_specifiers."""
    last_reg = ctx.fresh_reg()
    ctx.emit_inst(Const(result_reg=last_reg, value=ctx.constants.none_literal))
    for child in node.children:
        if child.is_named:
            last_reg = ctx.lower_expr(child)
    return last_reg


def lower_js_field_definition(ctx: TreeSitterEmitContext, node) -> Register:
    """Lower class field: `#privateField = 0` or `name = expr`."""
    property_node = node.child_by_field_name("property")
    value_node = node.child_by_field_name("value")
    field_name = ctx.node_text(property_node) if property_node else ctx.node_text(node)
    if value_node:
        val_reg = ctx.lower_expr(value_node)
    else:
        val_reg = ctx.fresh_reg()
        ctx.emit_inst(Const(result_reg=val_reg, value=ctx.constants.none_literal))
    ctx.emit_inst(DeclVar(name=VarName(field_name), value_reg=val_reg), node=node)
    # Return val_reg so this can be used in both stmt and expr contexts
    return val_reg


# ── JS param handling ────────────────────────────────────────


def lower_js_param(ctx: TreeSitterEmitContext, child, param_index: int) -> None:
    if child.type in (JSN.OPEN_PAREN, JSN.CLOSE_PAREN, JSN.COMMA):
        return
    default_value_node = None
    if child.type == JSN.IDENTIFIER:
        pname = ctx.node_text(child)
    elif child.type == JSN.ASSIGNMENT_PATTERN:
        # name = default_expr — first child is the identifier, last is the value
        pname = ctx.node_text(child.children[0])
        default_value_node = child.children[-1]
    elif child.type in (
        JSN.OBJECT_PATTERN,
        JSN.ARRAY_PATTERN,
    ):
        pname = ctx.node_text(child)
    else:
        from interpreter.frontends.common.declarations import extract_param_name

        pname = extract_param_name(ctx, child)
        if pname is None:
            return
    ctx.emit_inst(
        Symbolic(
            result_reg=ctx.fresh_reg(),
            hint=f"{constants.PARAM_PREFIX}{pname}",
        ),
        node=child,
    )
    ctx.emit_inst(
        DeclVar(name=VarName(pname), value_reg=Register(f"%{ctx.reg_counter - 1}"))
    )
    if default_value_node is not None:
        from interpreter.frontends.common.default_params import (
            emit_default_param_guard,
        )

        emit_default_param_guard(ctx, pname, param_index, default_value_node)


def lower_js_params(ctx: TreeSitterEmitContext, params_node) -> None:
    param_index = 0
    for child in params_node.children:
        if child.type in (JSN.OPEN_PAREN, JSN.CLOSE_PAREN, JSN.COMMA):
            continue
        if child.type == JSN.REST_PATTERN:
            _lower_rest_param(ctx, child, param_index)
        else:
            lower_js_param(ctx, child, param_index)
        param_index += 1


def _lower_rest_param(ctx: TreeSitterEmitContext, child, start_index: int) -> None:
    """Lower ...rest param as slice(arguments, start_index)."""
    from interpreter.frontends.javascript.declarations import _extract_rest_name

    rest_name = _extract_rest_name(child)
    if rest_name is None:
        return
    args_reg = ctx.fresh_reg()
    ctx.emit_inst(LoadVar(result_reg=args_reg, name=VarName("arguments")))
    idx_reg = ctx.fresh_reg()
    ctx.emit_inst(Const(result_reg=idx_reg, value=str(start_index)))
    rest_reg = ctx.fresh_reg()
    ctx.emit_inst(
        CallFunction(
            result_reg=rest_reg,
            func_name=FuncName("slice"),
            args=(args_reg, idx_reg),
        ),
        node=child,
    )
    ctx.emit_inst(DeclVar(name=VarName(rest_name), value_reg=rest_reg))
