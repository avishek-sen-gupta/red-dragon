"""Scala-specific expression lowerers — pure functions taking (ctx, node)."""

from __future__ import annotations

from interpreter.frontends.context import TreeSitterEmitContext

from interpreter.ir import Opcode, CodeLabel
from interpreter import constants
from interpreter.field_name import FieldName
from interpreter.var_name import VarName
from interpreter.func_name import FuncName
from interpreter.instructions import (
    Const,
    LoadVar,
    DeclVar,
    StoreVar,
    StoreField,
    StoreIndex,
    LoadField,
    CallCtorFunction,
    CallFunction,
    CallMethod,
    NewArray,
    Symbolic,
    Throw_,
    Label_,
    Branch,
    BranchIf,
    Return_,
)
from interpreter.frontends.common.expressions import (
    lower_const_literal,
    lower_interpolated_string_parts,
    lower_call_impl,
    extract_call_args,
)
from interpreter.frontends.common.match_expr import MatchArmSpec, lower_match_as_expr
from interpreter.frontends.scala.node_types import ScalaNodeType as NT
from interpreter.frontends.scala.patterns import parse_scala_pattern
from interpreter.types.type_expr import ScalarType, scalar
from interpreter.register import Register


def lower_scala_call(ctx: TreeSitterEmitContext, node) -> Register:
    """Lower call_expression, unwrapping generic_function to its inner function.

    In Scala, foo[Int](x) parses as call_expression(generic_function(foo, [Int]), (x)).
    We unwrap the generic_function to expose the raw function node (identifier or
    field_expression) so that lower_call_impl can dispatch correctly.

    Note: Scala arr(i) and f(x) are syntactically identical. Array indexing is
    handled at VM level via CALL_FUNCTION on array values (Scala apply semantics).

    ``this(args)`` inside a class context is constructor delegation — lowered
    as CALL_METHOD on this for __init__.
    """
    func_node = node.child_by_field_name(ctx.constants.call_function_field)
    args_node = node.child_by_field_name(ctx.constants.call_arguments_field)

    # this(args) → constructor delegation via CALL_METHOD
    if (
        func_node
        and func_node.type == NT.IDENTIFIER
        and ctx.node_text(func_node) == "this"
    ):
        return _lower_this_call_as_delegation(ctx, args_node, node)

    unwrapped_func = (
        func_node.child_by_field_name("function")
        if func_node and func_node.type == NT.GENERIC_FUNCTION
        else func_node
    )
    return lower_call_impl(ctx, unwrapped_func, args_node, node)


def _lower_this_call_as_delegation(
    ctx: TreeSitterEmitContext, args_node, node
) -> Register:
    """Lower ``this(args)`` as CALL_METHOD on this for __init__."""
    from interpreter.frontends.common.expressions import extract_call_args_unwrap

    arg_regs = extract_call_args_unwrap(ctx, args_node) if args_node else []
    this_reg = ctx.fresh_reg()
    ctx.emit_inst(LoadVar(result_reg=this_reg, name=VarName("this")))
    result_reg = ctx.fresh_reg()
    ctx.emit_inst(
        CallMethod(
            result_reg=result_reg,
            obj_reg=this_reg,
            method_name=FuncName("__init__"),
            args=tuple(arg_regs),
        ),
        node=node,
    )
    return result_reg


def lower_field_expr(ctx: TreeSitterEmitContext, node) -> Register:
    value_node = node.child_by_field_name(ctx.constants.attr_object_field)
    field_node = node.child_by_field_name("field")
    if value_node is None or field_node is None:
        return lower_const_literal(ctx, node)
    obj_reg = ctx.lower_expr(value_node)
    field_name = ctx.node_text(field_node)
    reg = ctx.fresh_reg()
    ctx.emit_inst(
        LoadField(result_reg=reg, obj_reg=obj_reg, field_name=FieldName(field_name)),
        node=node,
    )
    return reg


def lower_assignment_expr(ctx: TreeSitterEmitContext, node) -> Register:
    left = node.child_by_field_name(ctx.constants.assign_left_field)
    right = node.child_by_field_name(ctx.constants.assign_right_field)
    val_reg = ctx.lower_expr(right)
    lower_scala_store_target(ctx, left, val_reg, node)
    return val_reg


def lower_scala_store_target(
    ctx: TreeSitterEmitContext, target, val_reg: str, parent_node
) -> None:
    if target.type == NT.IDENTIFIER:
        ctx.emit_inst(
            StoreVar(name=VarName(ctx.node_text(target)), value_reg=val_reg),
            node=parent_node,
        )
    elif target.type == NT.FIELD_EXPRESSION:
        value_node = target.child_by_field_name(ctx.constants.attr_object_field)
        field_node = target.child_by_field_name("field")
        if value_node and field_node:
            obj_reg = ctx.lower_expr(value_node)
            ctx.emit_inst(
                StoreField(
                    obj_reg=obj_reg,
                    field_name=FieldName(ctx.node_text(field_node)),
                    value_reg=val_reg,
                ),
                node=parent_node,
            )
    elif target.type == NT.CALL_EXPRESSION:
        func_node = target.child_by_field_name(ctx.constants.call_function_field)
        args_node = target.child_by_field_name(ctx.constants.call_arguments_field)
        if func_node and args_node:
            obj_reg = ctx.lower_expr(func_node)
            arg_regs = extract_call_args(ctx, args_node)
            if len(arg_regs) == 1:
                ctx.emit_inst(
                    StoreIndex(
                        arr_reg=obj_reg, index_reg=arg_regs[0], value_reg=val_reg
                    ),
                    node=parent_node,
                )
    else:
        ctx.emit_inst(
            StoreVar(name=VarName(ctx.node_text(target)), value_reg=val_reg),
            node=parent_node,
        )


def lower_if_expr(ctx: TreeSitterEmitContext, node) -> Register:
    """Lower if as a value-producing expression."""
    cond_node = node.child_by_field_name(ctx.constants.if_condition_field)
    body_node = node.child_by_field_name(ctx.constants.if_consequence_field)
    alt_node = node.child_by_field_name(ctx.constants.if_alternative_field)

    cond_reg = ctx.lower_expr(cond_node) if cond_node else ctx.fresh_reg()
    true_label = ctx.fresh_label("if_true")
    false_label = ctx.fresh_label("if_false")
    end_label = ctx.fresh_label("if_end")
    result_var = f"__if_result_{ctx.label_counter}"

    if alt_node:
        ctx.emit_inst(
            BranchIf(cond_reg=cond_reg, branch_targets=(true_label, false_label)),
            node=node,
        )
    else:
        ctx.emit_inst(
            BranchIf(cond_reg=cond_reg, branch_targets=(true_label, end_label)),
            node=node,
        )

    ctx.emit_inst(Label_(label=true_label))
    true_reg = _lower_body_as_expr(ctx, body_node)
    ctx.emit_inst(DeclVar(name=VarName(result_var), value_reg=true_reg))
    ctx.emit_inst(Branch(label=end_label))

    if alt_node:
        ctx.emit_inst(Label_(label=false_label))
        false_reg = _lower_body_as_expr(ctx, alt_node)
        ctx.emit_inst(DeclVar(name=VarName(result_var), value_reg=false_reg))
        ctx.emit_inst(Branch(label=end_label))

    ctx.emit_inst(Label_(label=end_label))
    reg = ctx.fresh_reg()
    ctx.emit_inst(LoadVar(result_reg=reg, name=VarName(result_var)))
    return reg


def _lower_body_as_expr(ctx: TreeSitterEmitContext, body_node) -> Register:
    """Lower a body node as an expression, returning the last expression's reg."""
    if body_node is None:
        reg = ctx.fresh_reg()
        ctx.emit_inst(Const(result_reg=reg, value=ctx.constants.none_literal))
        return reg
    if body_node.type == NT.BLOCK:
        return lower_block_expr(ctx, body_node)
    return ctx.lower_expr(body_node)


def _scala_pattern_of(ctx: TreeSitterEmitContext, clause):
    return parse_scala_pattern(ctx, clause.child_by_field_name("pattern"))


def _scala_guard_of(ctx: TreeSitterEmitContext, clause):
    guard = next((c for c in clause.children if c.type == NT.GUARD), None)
    if guard is None:
        return None
    return next(c for c in guard.children if c.is_named)


def _scala_body_of(ctx: TreeSitterEmitContext, clause):
    return _lower_body_as_expr(ctx, clause.child_by_field_name("body"))


_SCALA_MATCH_SPEC = MatchArmSpec(
    extract_arms=lambda body: [c for c in body.children if c.type == NT.CASE_CLAUSE],
    pattern_of=_scala_pattern_of,
    guard_of=_scala_guard_of,
    body_of=_scala_body_of,
)


def lower_match_expr(ctx: TreeSitterEmitContext, node) -> Register:
    """Lower Scala match expression using Pattern ADT."""
    value_node = node.child_by_field_name("value")
    body_node = node.child_by_field_name("body")
    subject_reg = ctx.lower_expr(value_node)
    return lower_match_as_expr(ctx, subject_reg, body_node, _SCALA_MATCH_SPEC)


def lower_block_expr(ctx: TreeSitterEmitContext, node) -> Register:
    """Lower a block `{ ... }` as an expression (last expr is value)."""
    children = [
        c
        for c in node.children
        if c.type not in (NT.LBRACE, NT.RBRACE, NT.SEMICOLON)
        and c.type not in ctx.constants.comment_types
        and c.type not in ctx.constants.noise_types
        and c.is_named
    ]
    if not children:
        reg = ctx.fresh_reg()
        ctx.emit_inst(Const(result_reg=reg, value=ctx.constants.none_literal))
        return reg
    for child in children[:-1]:
        ctx.lower_stmt(child)
    return ctx.lower_expr(children[-1])


def lower_loop_as_expr(ctx: TreeSitterEmitContext, node) -> Register:
    """Lower while/for/do-while in expression position (returns unit)."""
    ctx.lower_stmt(node)
    reg = ctx.fresh_reg()
    ctx.emit_inst(Const(result_reg=reg, value=ctx.constants.none_literal))
    return reg


def lower_break_as_expr(ctx: TreeSitterEmitContext, node) -> Register:
    """Lower break in expression position."""
    from interpreter.frontends.common.control_flow import lower_break

    lower_break(ctx, node)
    reg = ctx.fresh_reg()
    ctx.emit_inst(Const(result_reg=reg, value=ctx.constants.none_literal))
    return reg


def lower_continue_as_expr(ctx: TreeSitterEmitContext, node) -> Register:
    """Lower continue in expression position."""
    from interpreter.frontends.common.control_flow import lower_continue

    lower_continue(ctx, node)
    reg = ctx.fresh_reg()
    ctx.emit_inst(Const(result_reg=reg, value=ctx.constants.none_literal))
    return reg


def lower_return_expr(ctx: TreeSitterEmitContext, node) -> Register:
    children = [c for c in node.children if c.type != NT.RETURN]
    if children:
        val_reg = ctx.lower_expr(children[0])
    else:
        val_reg = ctx.fresh_reg()
        ctx.emit_inst(
            Const(result_reg=val_reg, value=ctx.constants.default_return_value)
        )
    ctx.emit_inst(Return_(value_reg=val_reg), node=node)
    return val_reg


def lower_tuple_expr(ctx: TreeSitterEmitContext, node) -> Register:
    elems = [c for c in node.children if c.type not in (NT.LPAREN, NT.RPAREN, NT.COMMA)]
    arr_reg = ctx.fresh_reg()
    size_reg = ctx.fresh_reg()
    ctx.emit_inst(Const(result_reg=size_reg, value=str(len(elems))))
    ctx.emit_inst(
        NewArray(result_reg=arr_reg, type_hint=scalar("tuple"), size_reg=size_reg),
        node=node,
    )
    for i, elem in enumerate(elems):
        val_reg = ctx.lower_expr(elem)
        idx_reg = ctx.fresh_reg()
        ctx.emit_inst(Const(result_reg=idx_reg, value=str(i)))
        ctx.emit_inst(StoreIndex(arr_reg=arr_reg, index_reg=idx_reg, value_reg=val_reg))
    return arr_reg


def lower_lambda_expr(ctx: TreeSitterEmitContext, node) -> Register:
    func_name = f"__lambda_{ctx.label_counter}"
    func_label = ctx.fresh_label(f"{constants.FUNC_LABEL_PREFIX}{func_name}")
    end_label = ctx.fresh_label(f"end_{func_name}")

    ctx.emit_inst(Branch(label=end_label))
    ctx.emit_inst(Label_(label=func_label))

    # Extract lambda parameters: bindings -> binding -> identifier
    bindings_node = next(
        (c for c in node.children if c.type == NT.BINDINGS),
        None,
    )
    if bindings_node:
        for child in bindings_node.children:
            if child.type == NT.BINDING:
                id_node = next(
                    (c for c in child.children if c.type == NT.IDENTIFIER),
                    None,
                )
                if id_node:
                    pname = ctx.node_text(id_node)
                    ctx.emit_inst(
                        Symbolic(
                            result_reg=ctx.fresh_reg(),
                            hint=f"{constants.PARAM_PREFIX}{pname}",
                        ),
                        node=child,
                    )
                    ctx.emit_inst(
                        DeclVar(
                            name=VarName(pname),
                            value_reg=Register(f"%{ctx.reg_counter - 1}"),
                        )
                    )

    # Lambda body: lower all named children except bindings.
    # Scala lambdas implicitly return the last expression.
    named_children = [
        c
        for c in node.children
        if c.is_named
        and c.type != NT.BINDINGS
        and c.type not in ctx.constants.comment_types
    ]
    for child in named_children[:-1]:
        ctx.lower_stmt(child)
    if named_children:
        last_reg = ctx.lower_expr(named_children[-1])
        ctx.emit_inst(Return_(value_reg=last_reg))
    else:
        none_reg = ctx.fresh_reg()
        ctx.emit_inst(
            Const(result_reg=none_reg, value=ctx.constants.default_return_value)
        )
        ctx.emit_inst(Return_(value_reg=none_reg))
    ctx.emit_inst(Label_(label=end_label))

    reg = ctx.fresh_reg()
    ctx.emit_func_ref(func_name, func_label, result_reg=reg)
    return reg


def lower_new_expr(ctx: TreeSitterEmitContext, node) -> Register:
    named_children = [c for c in node.children if c.is_named]
    if named_children:
        type_name = ctx.node_text(named_children[0])
    else:
        type_name = "Object"

    args_node = next(
        (c for c in node.children if c.type == NT.ARGUMENTS),
        None,
    )
    arg_regs = extract_call_args(ctx, args_node) if args_node else []

    reg = ctx.fresh_reg()
    ctx.emit_inst(
        CallCtorFunction(
            result_reg=reg,
            func_name=FuncName(type_name),
            type_hint=scalar(type_name),
            args=tuple(arg_regs),
        ),
        node=node,
    )
    ctx.seed_register_type(reg, ScalarType(type_name))
    return reg


def lower_symbolic_node(ctx: TreeSitterEmitContext, node) -> Register:
    reg = ctx.fresh_reg()
    ctx.emit_inst(
        Symbolic(result_reg=reg, hint=f"{node.type}:{ctx.node_text(node)[:60]}"),
        node=node,
    )
    return reg


def lower_scala_interpolated_string(ctx: TreeSitterEmitContext, node) -> Register:
    """Lower interpolated_string_expression: s"..." / f"..." / raw"..."."""
    interp_string = next(
        (c for c in node.children if c.type == NT.INTERPOLATED_STRING),
        None,
    )
    if interp_string is None:
        return lower_const_literal(ctx, node)
    return lower_scala_interpolated_string_body(ctx, interp_string)


def lower_scala_interpolated_string_body(ctx: TreeSitterEmitContext, node) -> Register:
    """Lower interpolated_string, extracting literal gaps and interpolation children."""
    interpolations = [c for c in node.children if c.type == NT.INTERPOLATION]
    if not interpolations:
        return lower_const_literal(ctx, node)

    parts: list[str] = []
    content_start = node.start_byte + 1  # skip opening "
    content_end = node.end_byte - 1  # skip closing "

    for child in node.children:
        if child.type == NT.DOUBLE_QUOTE:
            continue
        if child.type == NT.INTERPOLATION:
            # Emit literal gap before this interpolation
            gap_text = ctx.source[content_start : child.start_byte].decode("utf-8")
            if gap_text:
                frag_reg = ctx.fresh_reg()
                ctx.emit_inst(Const(result_reg=frag_reg, value=gap_text), node=node)
                parts.append(frag_reg)
            # Lower the interpolation expression
            named = [c for c in child.children if c.is_named]
            if named:
                parts.append(ctx.lower_expr(named[0]))
            content_start = child.end_byte

    # Trailing literal after last interpolation
    trailing = ctx.source[content_start:content_end].decode("utf-8")
    if trailing:
        frag_reg = ctx.fresh_reg()
        ctx.emit_inst(Const(result_reg=frag_reg, value=trailing), node=node)
        parts.append(frag_reg)

    return lower_interpolated_string_parts(ctx, parts, node)


def lower_try_expr(ctx: TreeSitterEmitContext, node) -> Register:
    """Lower try_expression in expression context (returns a register)."""
    from interpreter.frontends.scala.control_flow import lower_try_stmt

    lower_try_stmt(ctx, node)
    reg = ctx.fresh_reg()
    ctx.emit_inst(Const(result_reg=reg, value=ctx.constants.none_literal))
    return reg


def lower_throw_expr(ctx: TreeSitterEmitContext, node) -> Register:
    """Lower throw_expression: throw expr -> lower expr, emit THROW, return reg."""
    children = [c for c in node.children if c.type != NT.THROW and c.is_named]
    if children:
        val_reg = ctx.lower_expr(children[0])
    else:
        val_reg = ctx.fresh_reg()
        ctx.emit_inst(
            Const(result_reg=val_reg, value=ctx.constants.default_return_value)
        )
    ctx.emit_inst(Throw_(value_reg=val_reg), node=node)
    return val_reg


def lower_generic_function(ctx: TreeSitterEmitContext, node) -> Register:
    """Lower generic_function: foo[Int] -> delegate to the inner function expression.

    The generic_function node has field 'function' (the base expression) and
    field 'type_arguments' (the type params, which we strip). When used as a
    callee in call_expression, the call_expression handler manages the call;
    here we just resolve the function reference by lowering the inner expression.
    """
    func_node = node.child_by_field_name("function")
    return ctx.lower_expr(func_node)


def lower_postfix_expression(ctx: TreeSitterEmitContext, node) -> Register:
    """Lower postfix_expression: 'list sorted' -> CALL_METHOD(sorted) on list with 0 args.

    The node has two named children: child[0] is the receiver, child[1] is the method name.
    """
    named_children = [c for c in node.children if c.is_named]
    receiver_node = named_children[0]
    method_node = named_children[1]
    obj_reg = ctx.lower_expr(receiver_node)
    method_name = ctx.node_text(method_node)
    reg = ctx.fresh_reg()
    ctx.emit_inst(
        CallMethod(
            result_reg=reg, obj_reg=obj_reg, method_name=FuncName(method_name), args=()
        ),
        node=node,
    )
    return reg


def lower_stable_type_identifier(ctx: TreeSitterEmitContext, node) -> Register:
    """Lower stable_type_identifier: pkg.MyClass -> LOAD_VAR(pkg), LOAD_FIELD(MyClass).

    The node has named children: identifier(s) separated by '.', ending with type_identifier.
    Lower as a chain of LOAD_FIELD operations on the base identifier.
    """
    named_children = [c for c in node.children if c.is_named]
    result = ctx.lower_expr(named_children[0])
    for child in named_children[1:]:
        field_name = ctx.node_text(child)
        reg = ctx.fresh_reg()
        ctx.emit_inst(
            LoadField(result_reg=reg, obj_reg=result, field_name=FieldName(field_name)),
            node=node,
        )
        result = reg
    return result
