"""Rust-specific expression lowerers -- pure functions taking (ctx, node)."""

from __future__ import annotations

import logging
from interpreter.frontends.context import TreeSitterEmitContext

from interpreter.ir import Opcode
from interpreter import constants
from interpreter.frontends.common.expressions import lower_const_literal
from interpreter.frontends.rust.node_types import RustNodeType

logger = logging.getLogger(__name__)


def lower_call_with_box_option(ctx: TreeSitterEmitContext, node) -> str:
    """Rust-specific call lowering that intercepts Box::new and Some."""
    func_node = node.child_by_field_name(ctx.constants.call_function_field)
    args_node = node.child_by_field_name(ctx.constants.call_arguments_field)

    if func_node and func_node.type == RustNodeType.SCOPED_IDENTIFIER:
        full_name = "::".join(
            ctx.node_text(c)
            for c in func_node.children
            if c.type == RustNodeType.IDENTIFIER
        )
        if full_name == "Box::new":
            return _lower_box_new(ctx, args_node, node)
        if full_name == "String::from":
            return _lower_string_from(ctx, args_node)

    if func_node and func_node.type == RustNodeType.IDENTIFIER:
        name = ctx.node_text(func_node)
        if name == "Some":
            return _lower_some(ctx, args_node, node)

    # Fall through to common call lowering
    from interpreter.frontends.common.expressions import lower_call_impl

    return lower_call_impl(ctx, func_node, args_node, node)


def _lower_box_new(ctx: TreeSitterEmitContext, args_node, call_node) -> str:
    """Lower Box::new(expr) → CALL_FUNCTION 'Box' with the argument."""
    from interpreter.frontends.common.expressions import extract_call_args

    arg_regs = extract_call_args(ctx, args_node)
    reg = ctx.fresh_reg()
    ctx.emit(
        Opcode.CALL_FUNCTION,
        result_reg=reg,
        operands=["Box"] + arg_regs,
        node=call_node,
    )
    return reg


def _lower_string_from(ctx: TreeSitterEmitContext, args_node) -> str:
    """Lower String::from(expr) as pass-through — return the argument directly."""
    from interpreter.frontends.common.expressions import extract_call_args

    arg_regs = extract_call_args(ctx, args_node)
    return arg_regs[0] if arg_regs else ctx.fresh_reg()


def _lower_some(ctx: TreeSitterEmitContext, args_node, call_node) -> str:
    """Lower Some(expr) -> CALL_FUNCTION 'Option' with single arg."""
    from interpreter.frontends.common.expressions import extract_call_args

    arg_regs = extract_call_args(ctx, args_node)
    reg = ctx.fresh_reg()
    ctx.emit(
        Opcode.CALL_FUNCTION,
        result_reg=reg,
        operands=["Option"] + arg_regs,
        node=call_node,
    )
    return reg


def lower_field_expr(ctx: TreeSitterEmitContext, node) -> str:
    """Lower field_expression: value.field -> LOAD_FIELD."""
    value_node = node.child_by_field_name("value")
    field_node = node.child_by_field_name("field")
    if value_node is None or field_node is None:
        return lower_const_literal(ctx, node)
    obj_reg = ctx.lower_expr(value_node)
    field_name = ctx.node_text(field_node)
    reg = ctx.fresh_reg()
    ctx.emit(
        Opcode.LOAD_FIELD,
        result_reg=reg,
        operands=[obj_reg, field_name],
        node=node,
    )
    return reg


def lower_reference_expr(ctx: TreeSitterEmitContext, node) -> str:
    """Lower &expr or &mut expr -> ADDRESS_OF for identifiers, UNOP '&' otherwise."""
    children = [
        c
        for c in node.children
        if c.type
        not in (
            RustNodeType.AMPERSAND,
            RustNodeType.MUT_KEYWORD,
            RustNodeType.MUTABLE_SPECIFIER,
        )
    ]
    inner = children[0] if children else node

    # For simple identifiers, emit ADDRESS_OF for alias tracking
    if inner.type == RustNodeType.IDENTIFIER:
        var_name = ctx.node_text(inner)
        reg = ctx.fresh_reg()
        ctx.emit(
            Opcode.ADDRESS_OF,
            result_reg=reg,
            operands=[var_name],
            node=node,
        )
        return reg

    inner_reg = ctx.lower_expr(inner)
    reg = ctx.fresh_reg()
    ctx.emit(
        Opcode.UNOP,
        result_reg=reg,
        operands=["&", inner_reg],
        node=node,
    )
    return reg


def lower_deref_expr(ctx: TreeSitterEmitContext, node) -> str:
    """Lower *expr → LOAD_FIELD '__boxed__' (Box unwrap / deref)."""
    children = [c for c in node.children if c.type != RustNodeType.ASTERISK]
    inner = children[0] if children else node
    inner_reg = ctx.lower_expr(inner)
    reg = ctx.fresh_reg()
    ctx.emit(
        Opcode.LOAD_FIELD,
        result_reg=reg,
        operands=[inner_reg, constants.BOXED_FIELD],
        node=node,
    )
    return reg


def lower_unary_or_deref(ctx: TreeSitterEmitContext, node) -> str:
    """Route unary_expression: '*' -> pointer deref, else -> generic unop."""
    from interpreter.frontends.common.expressions import lower_unop

    op_node = next((c for c in node.children if c.type == RustNodeType.ASTERISK), None)
    if op_node is not None:
        return lower_deref_expr(ctx, node)
    return lower_unop(ctx, node)


def lower_if_expr(ctx: TreeSitterEmitContext, node) -> str:
    """Lower Rust if expression (value-producing)."""
    cond_node = node.child_by_field_name(ctx.constants.if_condition_field)

    # if let: detect let_condition and delegate to specialised lowerer
    if cond_node and cond_node.type == RustNodeType.LET_CONDITION:
        return _lower_if_let_expr(ctx, node, cond_node)

    body_node = node.child_by_field_name(ctx.constants.if_consequence_field)
    alt_node = node.child_by_field_name(ctx.constants.if_alternative_field)

    cond_reg = ctx.lower_expr(cond_node)
    true_label = ctx.fresh_label("if_true")
    false_label = ctx.fresh_label("if_false")
    end_label = ctx.fresh_label("if_end")
    result_var = f"__if_result_{ctx.label_counter}"

    if alt_node:
        ctx.emit(
            Opcode.BRANCH_IF,
            operands=[cond_reg],
            label=f"{true_label},{false_label}",
            node=node,
        )
    else:
        ctx.emit(
            Opcode.BRANCH_IF,
            operands=[cond_reg],
            label=f"{true_label},{end_label}",
            node=node,
        )

    ctx.emit(Opcode.LABEL, label=true_label)
    true_reg = lower_block_expr(ctx, body_node)
    ctx.emit(Opcode.DECL_VAR, operands=[result_var, true_reg])
    ctx.emit(Opcode.BRANCH, label=end_label)

    if alt_node:
        ctx.emit(Opcode.LABEL, label=false_label)
        false_reg = ctx.lower_expr(alt_node)
        ctx.emit(Opcode.DECL_VAR, operands=[result_var, false_reg])
        ctx.emit(Opcode.BRANCH, label=end_label)

    ctx.emit(Opcode.LABEL, label=end_label)
    reg = ctx.fresh_reg()
    ctx.emit(Opcode.LOAD_VAR, result_reg=reg, operands=[result_var])
    return reg


def _lower_if_let_expr(ctx: TreeSitterEmitContext, node, let_cond_node) -> str:
    """Lower `if let Pattern = expr { body } else { alt }` as expression."""
    from interpreter.frontends.common.patterns import (
        compile_pattern_bindings,
        compile_pattern_test,
    )
    from interpreter.frontends.rust.patterns import parse_rust_pattern

    pattern_node = let_cond_node.child_by_field_name("pattern")
    value_node = let_cond_node.child_by_field_name("value")
    body_node = node.child_by_field_name(ctx.constants.if_consequence_field)
    alt_node = node.child_by_field_name(ctx.constants.if_alternative_field)

    subject_reg = ctx.lower_expr(value_node)
    pattern = parse_rust_pattern(ctx, pattern_node)
    test_reg = compile_pattern_test(ctx, subject_reg, pattern)

    true_label = ctx.fresh_label("if_let_true")
    false_label = ctx.fresh_label("if_let_false")
    end_label = ctx.fresh_label("if_let_end")
    result_var = f"__if_let_result_{ctx.label_counter}"

    target_label = false_label if alt_node else end_label
    ctx.emit(
        Opcode.BRANCH_IF,
        operands=[test_reg],
        label=f"{true_label},{target_label}",
        node=node,
    )

    ctx.emit(Opcode.LABEL, label=true_label)
    compile_pattern_bindings(ctx, subject_reg, pattern)
    true_reg = lower_block_expr(ctx, body_node)
    ctx.emit(Opcode.DECL_VAR, operands=[result_var, true_reg])
    ctx.emit(Opcode.BRANCH, label=end_label)

    if alt_node:
        ctx.emit(Opcode.LABEL, label=false_label)
        false_reg = ctx.lower_expr(alt_node)
        ctx.emit(Opcode.DECL_VAR, operands=[result_var, false_reg])
        ctx.emit(Opcode.BRANCH, label=end_label)

    ctx.emit(Opcode.LABEL, label=end_label)
    reg = ctx.fresh_reg()
    ctx.emit(Opcode.LOAD_VAR, result_reg=reg, operands=[result_var])
    return reg


def lower_expr_stmt_as_expr(ctx: TreeSitterEmitContext, node) -> str:
    """Unwrap expression_statement to its inner expression."""
    named = [c for c in node.children if c.is_named]
    if named:
        return ctx.lower_expr(named[0])
    reg = ctx.fresh_reg()
    ctx.emit(
        Opcode.CONST,
        result_reg=reg,
        operands=[ctx.constants.none_literal],
    )
    return reg


def lower_else_clause(ctx: TreeSitterEmitContext, node) -> str:
    """Lower else_clause by extracting its inner block or expression."""
    named = [c for c in node.children if c.is_named]
    if named:
        return ctx.lower_expr(named[0])
    reg = ctx.fresh_reg()
    ctx.emit(
        Opcode.CONST,
        result_reg=reg,
        operands=[ctx.constants.none_literal],
    )
    return reg


def lower_return_expr(ctx: TreeSitterEmitContext, node) -> str:
    """Lower Rust return expression (value-producing)."""
    children = [c for c in node.children if c.type != RustNodeType.RETURN_KEYWORD]
    if children:
        val_reg = ctx.lower_expr(children[0])
    else:
        val_reg = ctx.fresh_reg()
        ctx.emit(
            Opcode.CONST,
            result_reg=val_reg,
            operands=[ctx.constants.default_return_value],
        )
    ctx.emit(
        Opcode.RETURN,
        operands=[val_reg],
        node=node,
    )
    return val_reg


def lower_match_expr(ctx: TreeSitterEmitContext, node) -> str:
    """Lower Rust match expression using Pattern ADT."""
    from interpreter.frontends.common.patterns import (
        CapturePattern,
        WildcardPattern,
        compile_pattern_bindings,
        compile_pattern_test,
        _needs_pre_guard_bindings,
    )
    from interpreter.frontends.rust.patterns import parse_rust_pattern

    value_node = node.child_by_field_name("value")
    body_node = node.child_by_field_name("body")
    subject_reg = ctx.lower_expr(value_node) if value_node else ctx.fresh_reg()

    result_var = f"__match_result_{ctx.label_counter}"
    end_label = ctx.fresh_label("match_end")
    arms = (
        [c for c in body_node.children if c.type == RustNodeType.MATCH_ARM]
        if body_node
        else []
    )

    for arm in arms:
        _lower_match_arm(ctx, arm, subject_reg, result_var, end_label)

    ctx.emit(Opcode.LABEL, label=end_label)
    reg = ctx.fresh_reg()
    ctx.emit(Opcode.LOAD_VAR, result_reg=reg, operands=[result_var])
    return reg


def _lower_match_arm(
    ctx: TreeSitterEmitContext, arm, subject_reg: str, result_var: str, end_label: str
) -> None:
    """Lower a single match arm: test pattern, bind, evaluate body, store result."""
    from interpreter.frontends.common.patterns import (
        CapturePattern,
        WildcardPattern,
        compile_pattern_bindings,
        compile_pattern_test,
        _needs_pre_guard_bindings,
    )
    from interpreter.frontends.rust.patterns import parse_rust_pattern

    match_pattern_node = next(
        c for c in arm.children if c.type == RustNodeType.MATCH_PATTERN
    )

    # Guard lives INSIDE match_pattern (after anonymous 'if' token), NOT a sibling.
    # Named children: [pattern_node] or [pattern_node, guard_expr].
    # Wildcard '_' is anonymous, so named_children may be empty.
    named_children = [c for c in match_pattern_node.children if c.is_named]
    # For wildcard: no named children — pass the match_pattern node itself
    pattern_node = named_children[0] if named_children else match_pattern_node
    guard_node = named_children[1] if len(named_children) > 1 else None

    pattern = parse_rust_pattern(ctx, pattern_node)
    body_expr = _extract_arm_body(arm)

    is_irrefutable = (
        isinstance(pattern, (WildcardPattern, CapturePattern)) and guard_node is None
    )

    if is_irrefutable:
        compile_pattern_bindings(ctx, subject_reg, pattern)
        body_reg = ctx.lower_expr(body_expr)
        ctx.emit(Opcode.DECL_VAR, operands=[result_var, body_reg])
        ctx.emit(Opcode.BRANCH, label=end_label)
        return

    test_reg = compile_pattern_test(ctx, subject_reg, pattern)

    if guard_node:
        # Pre-bind for guard evaluation if pattern introduces variables
        if _needs_pre_guard_bindings(pattern):
            compile_pattern_bindings(ctx, subject_reg, pattern)
        guard_reg = ctx.lower_expr(guard_node)
        final_test = ctx.fresh_reg()
        ctx.emit(
            Opcode.BINOP,
            result_reg=final_test,
            operands=["&&", test_reg, guard_reg],
        )
        test_reg = final_test

    arm_label = ctx.fresh_label("match_arm")
    next_label = ctx.fresh_label("match_next")
    ctx.emit(
        Opcode.BRANCH_IF,
        operands=[test_reg],
        label=f"{arm_label},{next_label}",
    )
    ctx.emit(Opcode.LABEL, label=arm_label)

    # Only emit bindings if not already emitted pre-guard
    if not (guard_node and _needs_pre_guard_bindings(pattern)):
        compile_pattern_bindings(ctx, subject_reg, pattern)

    body_reg = ctx.lower_expr(body_expr)
    ctx.emit(Opcode.DECL_VAR, operands=[result_var, body_reg])
    ctx.emit(Opcode.BRANCH, label=end_label)
    ctx.emit(Opcode.LABEL, label=next_label)


def _extract_arm_body(arm):
    """Extract the body expression node from a match_arm."""
    return [
        c
        for c in arm.children
        if c.type
        not in (
            RustNodeType.MATCH_PATTERN,
            RustNodeType.FAT_ARROW,
            RustNodeType.COMMA,
            RustNodeType.FAT_ARROW_ALIAS,
        )
        and c.is_named
    ][0]


def lower_block_expr(ctx: TreeSitterEmitContext, node) -> str:
    """Lower a block `{ ... }` as an expression (last expr is value)."""
    children = [
        c
        for c in node.children
        if c.type
        not in (
            RustNodeType.OPEN_BRACE,
            RustNodeType.CLOSE_BRACE,
            RustNodeType.SEMICOLON,
        )
        and c.type not in ctx.constants.comment_types
        and c.type not in ctx.constants.noise_types
        and c.is_named
    ]
    if not children:
        reg = ctx.fresh_reg()
        ctx.emit(
            Opcode.CONST,
            result_reg=reg,
            operands=[ctx.constants.none_literal],
        )
        return reg
    for child in children[:-1]:
        ctx.lower_stmt(child)
    return ctx.lower_expr(children[-1])


def lower_closure_expr(ctx: TreeSitterEmitContext, node) -> str:
    """Lower Rust closure expression |params| body."""
    params_node = node.child_by_field_name(ctx.constants.func_params_field)
    body_node = node.child_by_field_name(ctx.constants.func_body_field)

    func_name = f"__closure_{ctx.label_counter}"
    func_label = ctx.fresh_label(f"{constants.FUNC_LABEL_PREFIX}{func_name}")
    end_label = ctx.fresh_label(f"end_{func_name}")

    ctx.emit(Opcode.BRANCH, label=end_label)
    ctx.emit(Opcode.LABEL, label=func_label)

    if params_node:
        _lower_closure_params(ctx, params_node)

    if body_node:
        result_reg = ctx.lower_expr(body_node)
        ctx.emit(Opcode.RETURN, operands=[result_reg])
    else:
        none_reg = ctx.fresh_reg()
        ctx.emit(
            Opcode.CONST,
            result_reg=none_reg,
            operands=[ctx.constants.default_return_value],
        )
        ctx.emit(Opcode.RETURN, operands=[none_reg])

    ctx.emit(Opcode.LABEL, label=end_label)
    reg = ctx.fresh_reg()
    ctx.emit_func_ref(func_name, func_label, result_reg=reg)
    return reg


def _lower_closure_params(ctx: TreeSitterEmitContext, params_node) -> None:
    """Lower closure parameters (|a, b| style)."""
    from interpreter.frontends.rust.declarations import lower_rust_param

    for child in params_node.children:
        if child.type in (
            RustNodeType.PIPE,
            RustNodeType.COMMA,
            RustNodeType.COLON,
        ):
            continue
        if child.type == RustNodeType.IDENTIFIER:
            pname = ctx.node_text(child)
            ctx.emit(
                Opcode.SYMBOLIC,
                result_reg=ctx.fresh_reg(),
                operands=[f"{constants.PARAM_PREFIX}{pname}"],
                node=child,
            )
            ctx.emit(
                Opcode.DECL_VAR,
                operands=[pname, f"%{ctx.reg_counter - 1}"],
            )
        elif child.type == RustNodeType.PARAMETER:
            lower_rust_param(ctx, child)


def lower_struct_instantiation(ctx: TreeSitterEmitContext, node) -> str:
    """Lower struct_expression: Point { x: 1, y: 2 }."""
    name_node = node.child_by_field_name(ctx.constants.class_name_field)
    body_node = node.child_by_field_name(ctx.constants.class_body_field)
    struct_name = ctx.node_text(name_node) if name_node else "Struct"

    obj_reg = ctx.fresh_reg()
    ctx.emit(
        Opcode.NEW_OBJECT,
        result_reg=obj_reg,
        operands=[struct_name],
        node=node,
    )

    if body_node:
        for child in body_node.children:
            if child.type == RustNodeType.FIELD_INITIALIZER:
                field_name_node = child.child_by_field_name("field")
                field_val_node = child.child_by_field_name("value")
                if field_name_node and field_val_node:
                    val_reg = ctx.lower_expr(field_val_node)
                    ctx.emit(
                        Opcode.STORE_FIELD,
                        operands=[
                            obj_reg,
                            ctx.node_text(field_name_node),
                            val_reg,
                        ],
                    )
                elif field_name_node:
                    # Shorthand: `Point { x, y }` means `Point { x: x, y: y }`
                    from interpreter.frontends.common.expressions import (
                        lower_identifier,
                    )

                    val_reg = lower_identifier(ctx, field_name_node)
                    ctx.emit(
                        Opcode.STORE_FIELD,
                        operands=[
                            obj_reg,
                            ctx.node_text(field_name_node),
                            val_reg,
                        ],
                    )
    return obj_reg


def lower_macro_invocation(ctx: TreeSitterEmitContext, node) -> str:
    """Lower macro_invocation: println!(...) -> CALL_FUNCTION."""
    macro_name = ctx.node_text(node).split("!")[0] + "!"
    reg = ctx.fresh_reg()
    ctx.emit(
        Opcode.CALL_FUNCTION,
        result_reg=reg,
        operands=[macro_name],
        node=node,
    )
    return reg


def lower_index_expr(ctx: TreeSitterEmitContext, node) -> str:
    """Lower index_expression: arr[idx] -> LOAD_INDEX, arr[1..3] -> slice."""
    children = [c for c in node.children if c.is_named]
    if len(children) < 2:
        return lower_const_literal(ctx, node)
    obj_reg = ctx.lower_expr(children[0])
    if children[1].type == RustNodeType.RANGE_EXPRESSION:
        return _lower_range_slice(ctx, children[1], obj_reg)
    idx_reg = ctx.lower_expr(children[1])
    reg = ctx.fresh_reg()
    ctx.emit(
        Opcode.LOAD_INDEX,
        result_reg=reg,
        operands=[obj_reg, idx_reg],
        node=node,
    )
    return reg


def _lower_range_slice(
    ctx: TreeSitterEmitContext, range_node, collection_reg: str
) -> str:
    """Lower arr[start..end] as CALL_FUNCTION('slice', collection, start, end).

    Rust's `..` is exclusive (like Python's slice), `..=` is inclusive.
    """
    named = [c for c in range_node.children if c.is_named]
    start_reg = (
        ctx.lower_expr(named[0]) if len(named) > 0 else _make_rust_const(ctx, "0")
    )
    end_reg = (
        ctx.lower_expr(named[1])
        if len(named) > 1
        else _make_rust_const(ctx, ctx.constants.none_literal)
    )
    # ..= is inclusive → need end+1
    is_inclusive = any(c.type == "..=" for c in range_node.children)
    if is_inclusive and len(named) > 1:
        one_reg = _make_rust_const(ctx, "1")
        adjusted = ctx.fresh_reg()
        ctx.emit(
            Opcode.BINOP,
            result_reg=adjusted,
            operands=["+", end_reg, one_reg],
            node=range_node,
        )
        end_reg = adjusted
    none_reg = _make_rust_const(ctx, ctx.constants.none_literal)
    reg = ctx.fresh_reg()
    ctx.emit(
        Opcode.CALL_FUNCTION,
        result_reg=reg,
        operands=["slice", collection_reg, start_reg, end_reg, none_reg],
        node=range_node,
    )
    return reg


def _make_rust_const(ctx: TreeSitterEmitContext, value: str) -> str:
    """Emit a CONST and return the register."""
    reg = ctx.fresh_reg()
    ctx.emit(Opcode.CONST, result_reg=reg, operands=[value])
    return reg


def lower_tuple_expr(ctx: TreeSitterEmitContext, node) -> str:
    """Lower tuple_expression: (a, b, c) -> NEW_ARRAY."""
    elems = [
        c
        for c in node.children
        if c.type
        not in (RustNodeType.OPEN_PAREN, RustNodeType.CLOSE_PAREN, RustNodeType.COMMA)
    ]
    arr_reg = ctx.fresh_reg()
    size_reg = ctx.fresh_reg()
    ctx.emit(Opcode.CONST, result_reg=size_reg, operands=[str(len(elems))])
    ctx.emit(
        Opcode.NEW_ARRAY,
        result_reg=arr_reg,
        operands=["tuple", size_reg],
        node=node,
    )
    for i, elem in enumerate(elems):
        val_reg = ctx.lower_expr(elem)
        idx_reg = ctx.fresh_reg()
        ctx.emit(Opcode.CONST, result_reg=idx_reg, operands=[str(i)])
        ctx.emit(Opcode.STORE_INDEX, operands=[arr_reg, idx_reg, val_reg])
    return arr_reg


def lower_try_expr(ctx: TreeSitterEmitContext, node) -> str:
    """Lower `expr?` as CALL_FUNCTION("try_unwrap", inner)."""
    inner = next(
        (
            c
            for c in node.children
            if c.type != RustNodeType.QUESTION_MARK and c.is_named
        ),
        None,
    )
    inner_reg = ctx.lower_expr(inner) if inner else ctx.fresh_reg()
    reg = ctx.fresh_reg()
    ctx.emit(
        Opcode.CALL_FUNCTION,
        result_reg=reg,
        operands=["try_unwrap", inner_reg],
        node=node,
    )
    return reg


def lower_await_expr(ctx: TreeSitterEmitContext, node) -> str:
    """Lower `expr.await` as CALL_FUNCTION("await", inner)."""
    inner = next(
        (
            c
            for c in node.children
            if c.type not in (RustNodeType.DOT, RustNodeType.AWAIT_KEYWORD)
            and c.is_named
        ),
        None,
    )
    inner_reg = ctx.lower_expr(inner) if inner else ctx.fresh_reg()
    reg = ctx.fresh_reg()
    ctx.emit(
        Opcode.CALL_FUNCTION,
        result_reg=reg,
        operands=["await", inner_reg],
        node=node,
    )
    return reg


def lower_type_cast_expr(ctx: TreeSitterEmitContext, node) -> str:
    """Lower `expr as Type` as CALL_FUNCTION('as', expr, type_name)."""
    named_children = [c for c in node.children if c.is_named]
    if not named_children:
        return lower_const_literal(ctx, node)
    expr_reg = ctx.lower_expr(named_children[0])
    type_name = ctx.node_text(named_children[-1])
    reg = ctx.fresh_reg()
    ctx.emit(
        Opcode.CALL_FUNCTION,
        result_reg=reg,
        operands=["as", expr_reg, type_name],
        node=node,
    )
    return reg


def lower_scoped_identifier(ctx: TreeSitterEmitContext, node) -> str:
    """Lower `HashMap::new`, `Shape::Circle` as LOAD_VAR with qualified name."""
    full_name = "::".join(
        ctx.node_text(c) for c in node.children if c.type == RustNodeType.IDENTIFIER
    )
    reg = ctx.fresh_reg()
    ctx.emit(
        Opcode.LOAD_VAR,
        result_reg=reg,
        operands=[full_name],
        node=node,
    )
    return reg


def lower_range_expr(ctx: TreeSitterEmitContext, node) -> str:
    """Lower `0..10` or `0..=10` as CALL_FUNCTION("range", start, end)."""
    named = [c for c in node.children if c.is_named]
    start_reg = ctx.lower_expr(named[0]) if len(named) > 0 else ctx.fresh_reg()
    end_reg = ctx.lower_expr(named[1]) if len(named) > 1 else ctx.fresh_reg()
    reg = ctx.fresh_reg()
    ctx.emit(
        Opcode.CALL_FUNCTION,
        result_reg=reg,
        operands=["range", start_reg, end_reg],
        node=node,
    )
    return reg


def lower_loop_as_expr(ctx: TreeSitterEmitContext, node) -> str:
    """Lower while/loop/for in expression position (returns unit)."""
    ctx.lower_stmt(node)
    reg = ctx.fresh_reg()
    ctx.emit(
        Opcode.CONST,
        result_reg=reg,
        operands=[ctx.constants.none_literal],
    )
    return reg


def lower_continue_as_expr(ctx: TreeSitterEmitContext, node) -> str:
    """Lower continue in expression position."""
    from interpreter.frontends.common.control_flow import lower_continue

    lower_continue(ctx, node)
    reg = ctx.fresh_reg()
    ctx.emit(
        Opcode.CONST,
        result_reg=reg,
        operands=[ctx.constants.none_literal],
    )
    return reg


def lower_break_as_expr(ctx: TreeSitterEmitContext, node) -> str:
    """Lower break in expression position."""
    from interpreter.frontends.common.control_flow import lower_break

    lower_break(ctx, node)
    reg = ctx.fresh_reg()
    ctx.emit(
        Opcode.CONST,
        result_reg=reg,
        operands=[ctx.constants.none_literal],
    )
    return reg


def lower_assignment_expr(ctx: TreeSitterEmitContext, node) -> str:
    """Lower assignment_expression: left = right (value-producing)."""
    left = node.child_by_field_name(ctx.constants.assign_left_field)
    right = node.child_by_field_name(ctx.constants.assign_right_field)
    val_reg = ctx.lower_expr(right)
    lower_rust_store_target(ctx, left, val_reg, node)
    return val_reg


def lower_compound_assignment_expr(ctx: TreeSitterEmitContext, node) -> str:
    """Lower compound_assignment_expr: left += right."""
    left = node.child_by_field_name(ctx.constants.assign_left_field)
    right = node.child_by_field_name(ctx.constants.assign_right_field)
    op_node = node.child_by_field_name("operator")
    op_text = ctx.node_text(op_node).rstrip("=") if op_node else "+"
    lhs_reg = ctx.lower_expr(left)
    rhs_reg = ctx.lower_expr(right)
    result = ctx.fresh_reg()
    ctx.emit(
        Opcode.BINOP,
        result_reg=result,
        operands=[op_text, lhs_reg, rhs_reg],
        node=node,
    )
    lower_rust_store_target(ctx, left, result, node)
    return result


def lower_tuple_struct_pattern(ctx: TreeSitterEmitContext, node) -> str:
    """Lower tuple_struct_pattern like Some(x) or Message::Write(text)."""
    type_node = next(
        (
            c
            for c in node.children
            if c.type
            in (
                RustNodeType.IDENTIFIER,
                RustNodeType.SCOPED_IDENTIFIER,
                RustNodeType.TYPE_IDENTIFIER,
            )
        ),
        None,
    )
    variant_name = ctx.node_text(type_node) if type_node else ctx.node_text(node)
    variant_reg = ctx.fresh_reg()
    ctx.emit(
        Opcode.CONST,
        result_reg=variant_reg,
        operands=[variant_name],
        node=node,
    )
    # Extract inner bindings (identifiers inside parentheses)
    inner_ids = [
        c
        for c in node.children
        if c.is_named
        and c.type
        not in (
            RustNodeType.IDENTIFIER,
            RustNodeType.SCOPED_IDENTIFIER,
            RustNodeType.TYPE_IDENTIFIER,
        )
    ]
    for i, child in enumerate(inner_ids):
        child_reg = ctx.lower_expr(child)
        idx_reg = ctx.fresh_reg()
        ctx.emit(Opcode.CONST, result_reg=idx_reg, operands=[str(i)])
        ctx.emit(
            Opcode.STORE_INDEX,
            operands=[variant_reg, idx_reg, child_reg],
        )
    return variant_reg


def lower_generic_function(ctx: TreeSitterEmitContext, node) -> str:
    """Lower a.parse::<i32>() -- strip type params, lower as identifier."""
    named_children = [c for c in node.children if c.is_named]
    if named_children:
        return ctx.lower_expr(named_children[0])
    return lower_const_literal(ctx, node)


def lower_let_condition(ctx: TreeSitterEmitContext, node) -> str:
    """Lower `let Pattern = expr` — returns boolean test register."""
    from interpreter.frontends.common.patterns import compile_pattern_test
    from interpreter.frontends.rust.patterns import parse_rust_pattern

    pattern_node = node.child_by_field_name("pattern")
    value_node = node.child_by_field_name("value")
    subject_reg = ctx.lower_expr(value_node) if value_node else ctx.fresh_reg()
    pattern = parse_rust_pattern(ctx, pattern_node)
    return compile_pattern_test(ctx, subject_reg, pattern)


def lower_struct_pattern_expr(ctx: TreeSitterEmitContext, node) -> str:
    """Lower struct_pattern like Message::Move { x, y } as pattern value."""
    type_node = next(
        (
            c
            for c in node.children
            if c.type
            in (RustNodeType.TYPE_IDENTIFIER, RustNodeType.SCOPED_TYPE_IDENTIFIER)
        ),
        None,
    )
    type_name = ctx.node_text(type_node) if type_node else ctx.node_text(node)
    obj_reg = ctx.fresh_reg()
    ctx.emit(
        Opcode.NEW_OBJECT,
        result_reg=obj_reg,
        operands=[f"struct_pattern:{type_name}"],
        node=node,
    )
    # Extract field bindings
    field_patterns = [c for c in node.children if c.type == RustNodeType.FIELD_PATTERN]
    for fp in field_patterns:
        name_node = next(
            (
                ch
                for ch in fp.children
                if ch.type
                in (
                    RustNodeType.FIELD_IDENTIFIER,
                    RustNodeType.SHORTHAND_FIELD_IDENTIFIER,
                )
            ),
            None,
        )
        if name_node:
            field_name = ctx.node_text(name_node)
            key_reg = ctx.fresh_reg()
            ctx.emit(Opcode.CONST, result_reg=key_reg, operands=[field_name])
            val_reg = ctx.fresh_reg()
            ctx.emit(Opcode.CONST, result_reg=val_reg, operands=[field_name])
            ctx.emit(Opcode.STORE_INDEX, operands=[obj_reg, key_reg, val_reg])
    return obj_reg


# ── Rust-specific store target ────────────────────────────────────────


def lower_rust_store_target(
    ctx: TreeSitterEmitContext, target, val_reg: str, parent_node
) -> None:
    """Rust-specific store target handling field_expression and index_expression."""
    if target.type == RustNodeType.IDENTIFIER:
        ctx.emit(
            Opcode.STORE_VAR,
            operands=[ctx.node_text(target), val_reg],
            node=parent_node,
        )
    elif target.type == RustNodeType.FIELD_EXPRESSION:
        value_node = target.child_by_field_name("value")
        field_node = target.child_by_field_name("field")
        if value_node and field_node:
            obj_reg = ctx.lower_expr(value_node)
            ctx.emit(
                Opcode.STORE_FIELD,
                operands=[obj_reg, ctx.node_text(field_node), val_reg],
                node=parent_node,
            )
    elif target.type == RustNodeType.INDEX_EXPRESSION:
        children = [c for c in target.children if c.is_named]
        if len(children) >= 2:
            obj_reg = ctx.lower_expr(children[0])
            idx_reg = ctx.lower_expr(children[1])
            ctx.emit(
                Opcode.STORE_INDEX,
                operands=[obj_reg, idx_reg, val_reg],
                node=parent_node,
            )
    elif target.type in (
        RustNodeType.DEREFERENCE_EXPRESSION,
        RustNodeType.UNARY_EXPRESSION,
    ):
        inner_children = [c for c in target.children if c.type != RustNodeType.ASTERISK]
        # Filter out the '*' operator text node for unary_expression
        inner_children = [c for c in inner_children if c.is_named]
        if inner_children:
            inner_reg = ctx.lower_expr(inner_children[0])
            ctx.emit(
                Opcode.STORE_INDIRECT,
                operands=[inner_reg, val_reg],
                node=parent_node,
            )
    else:
        ctx.emit(
            Opcode.STORE_VAR,
            operands=[ctx.node_text(target), val_reg],
            node=parent_node,
        )
