"""Rust-specific expression lowerers -- pure functions taking (ctx, node)."""

from __future__ import annotations

from typing import Any

import logging
from interpreter.frontends.context import TreeSitterEmitContext

from interpreter.operator_kind import resolve_binop, resolve_unop
from interpreter.var_name import VarName
from interpreter.field_name import FieldName
from interpreter.func_name import FuncName
from interpreter.instructions import (
    AddressOf,
    Binop,
    Branch,
    BranchIf,
    CallFunction,
    Const,
    DeclVar,
    Label_,
    LoadField,
    LoadIndex,
    LoadIndirect,
    LoadVar,
    NewArray,
    NewObject,
    Return_,
    StoreField,
    StoreIndex,
    StoreIndirect,
    StoreVar,
    Symbolic,
    Unop,
)
from interpreter import constants
from interpreter.frontends.common.expressions import lower_const_literal
from interpreter.frontends.rust.node_types import RustNodeType
from interpreter.frontends.common.match_expr import MatchArmSpec, lower_match_as_expr
from interpreter.frontends.common.patterns import (
    Pattern,
    compile_pattern_bindings,
    compile_pattern_test,
)
from interpreter.frontends.rust.patterns import parse_rust_pattern
from interpreter.register import Register
from interpreter.types.type_expr import StructPatternType, scalar

logger = logging.getLogger(__name__)


def lower_call_with_box_option(
    ctx: TreeSitterEmitContext, node: Any
) -> Register:  # Any: tree-sitter node — untyped at Python boundary
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


def _lower_box_new(ctx: TreeSitterEmitContext, args_node, call_node) -> Register:
    """Lower Box::new(expr) → CALL_FUNCTION 'Box' with the argument."""
    from interpreter.frontends.common.expressions import extract_call_args

    arg_regs = extract_call_args(ctx, args_node)
    reg = ctx.fresh_reg()
    ctx.emit_inst(
        CallFunction(result_reg=reg, func_name=FuncName("Box"), args=tuple(arg_regs)),
        node=call_node,
    )
    return reg


def _lower_string_from(ctx: TreeSitterEmitContext, args_node) -> Register:
    """Lower String::from(expr) as pass-through — return the argument directly."""
    from interpreter.frontends.common.expressions import extract_call_args

    arg_regs = extract_call_args(ctx, args_node)
    return arg_regs[0] if arg_regs else ctx.fresh_reg()


def _lower_some(ctx: TreeSitterEmitContext, args_node, call_node) -> Register:
    """Lower Some(expr) -> CALL_FUNCTION 'Option' with single arg."""
    from interpreter.frontends.common.expressions import extract_call_args

    arg_regs = extract_call_args(ctx, args_node)
    reg = ctx.fresh_reg()
    ctx.emit_inst(
        CallFunction(
            result_reg=reg, func_name=FuncName("Option"), args=tuple(arg_regs)
        ),
        node=call_node,
    )
    return reg


def lower_field_expr(
    ctx: TreeSitterEmitContext, node: Any
) -> Register:  # Any: tree-sitter node — untyped at Python boundary
    """Lower field_expression: value.field -> LOAD_FIELD."""
    value_node = node.child_by_field_name("value")
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


def lower_reference_expr(
    ctx: TreeSitterEmitContext, node: Any
) -> Register:  # Any: tree-sitter node — untyped at Python boundary
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
        ctx.emit_inst(AddressOf(result_reg=reg, var_name=VarName(var_name)), node=node)
        return reg

    inner_reg = ctx.lower_expr(inner)
    reg = ctx.fresh_reg()
    ctx.emit_inst(
        Unop(result_reg=reg, operator=resolve_unop("&"), operand=inner_reg), node=node
    )
    return reg


def lower_deref_expr(
    ctx: TreeSitterEmitContext, node: Any
) -> Register:  # Any: tree-sitter node — untyped at Python boundary
    """Lower *expr → LOAD_INDIRECT (unified Box unwrap / reference deref)."""
    children = [c for c in node.children if c.type != RustNodeType.ASTERISK]
    inner = children[0] if children else node
    inner_reg = ctx.lower_expr(inner)
    reg = ctx.fresh_reg()
    ctx.emit_inst(LoadIndirect(result_reg=reg, ptr_reg=inner_reg), node=node)
    return reg


def lower_unary_or_deref(
    ctx: TreeSitterEmitContext, node: Any
) -> Register:  # Any: tree-sitter node — untyped at Python boundary
    """Route unary_expression: '*' -> pointer deref, else -> generic unop."""
    from interpreter.frontends.common.expressions import lower_unop

    op_node = next((c for c in node.children if c.type == RustNodeType.ASTERISK), None)
    if op_node is not None:
        return lower_deref_expr(ctx, node)
    return lower_unop(ctx, node)


def lower_if_expr(
    ctx: TreeSitterEmitContext, node: Any
) -> Register:  # Any: tree-sitter node — untyped at Python boundary
    """Lower Rust if expression (value-producing)."""
    cond_node = node.child_by_field_name(ctx.constants.if_condition_field)

    # if let: detect let_condition and delegate to specialised lowerer
    if cond_node and cond_node.type == RustNodeType.LET_CONDITION:
        return _lower_if_let_expr(ctx, node, cond_node)

    # if let chain: let A && let B
    if cond_node and cond_node.type == RustNodeType.LET_CHAIN:
        return _lower_if_let_chain_expr(ctx, node, cond_node)

    body_node = node.child_by_field_name(ctx.constants.if_consequence_field)
    alt_node = node.child_by_field_name(ctx.constants.if_alternative_field)

    cond_reg = ctx.lower_expr(cond_node)
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
    true_reg = lower_block_expr(ctx, body_node)
    ctx.emit_inst(DeclVar(name=VarName(result_var), value_reg=true_reg))
    ctx.emit_inst(Branch(label=end_label))

    if alt_node:
        ctx.emit_inst(Label_(label=false_label))
        false_reg = ctx.lower_expr(alt_node)
        ctx.emit_inst(DeclVar(name=VarName(result_var), value_reg=false_reg))
        ctx.emit_inst(Branch(label=end_label))

    ctx.emit_inst(Label_(label=end_label))
    reg = ctx.fresh_reg()
    ctx.emit_inst(LoadVar(result_reg=reg, name=VarName(result_var)))
    return reg


def _lower_if_let_expr(
    ctx: TreeSitterEmitContext, node: Any, let_cond_node
) -> Register:  # Any: tree-sitter node — untyped at Python boundary
    """Lower `if let Pattern = expr { body } else { alt }` as expression."""
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
    ctx.emit_inst(
        BranchIf(cond_reg=test_reg, branch_targets=(true_label, target_label)),
        node=node,
    )

    ctx.emit_inst(Label_(label=true_label))
    compile_pattern_bindings(ctx, subject_reg, pattern)
    true_reg = lower_block_expr(ctx, body_node)
    ctx.emit_inst(DeclVar(name=VarName(result_var), value_reg=true_reg))
    ctx.emit_inst(Branch(label=end_label))

    if alt_node:
        ctx.emit_inst(Label_(label=false_label))
        false_reg = ctx.lower_expr(alt_node)
        ctx.emit_inst(DeclVar(name=VarName(result_var), value_reg=false_reg))
        ctx.emit_inst(Branch(label=end_label))

    ctx.emit_inst(Label_(label=end_label))
    reg = ctx.fresh_reg()
    ctx.emit_inst(LoadVar(result_reg=reg, name=VarName(result_var)))
    return reg


def _lower_if_let_chain_expr(
    ctx: TreeSitterEmitContext, node, let_chain_node
) -> Register:
    """Lower `if let A && let B { body } else { alt }` as expression.

    Extracts all let_condition children from the let_chain, tests each
    pattern, ANDs the results, branches, then binds all patterns in
    the true branch.
    """
    let_conditions = [
        c for c in let_chain_node.children if c.type == RustNodeType.LET_CONDITION
    ]

    body_node = node.child_by_field_name(ctx.constants.if_consequence_field)
    alt_node = node.child_by_field_name(ctx.constants.if_alternative_field)

    # Test each let condition and collect (test_reg, pattern, subject_reg)
    arms = [_test_let_condition(ctx, lc) for lc in let_conditions]

    # AND all test registers
    combined = arms[0][0]
    for test_reg, _, _ in arms[1:]:
        and_reg = ctx.fresh_reg()
        ctx.emit_inst(
            Binop(
                result_reg=and_reg,
                operator=resolve_binop("&&"),
                left=combined,
                right=test_reg,
            )
        )
        combined = and_reg

    true_label = ctx.fresh_label("let_chain_true")
    false_label = ctx.fresh_label("let_chain_false")
    end_label = ctx.fresh_label("let_chain_end")
    result_var = f"__let_chain_result_{ctx.label_counter}"

    target_label = false_label if alt_node else end_label
    ctx.emit_inst(
        BranchIf(cond_reg=combined, branch_targets=(true_label, target_label)),
        node=node,
    )

    # True branch: bind all patterns, lower body
    ctx.emit_inst(Label_(label=true_label))
    for _, pattern, subject_reg in arms:
        compile_pattern_bindings(ctx, subject_reg, pattern)
    true_reg = lower_block_expr(ctx, body_node)
    ctx.emit_inst(DeclVar(name=VarName(result_var), value_reg=true_reg))
    ctx.emit_inst(Branch(label=end_label))

    if alt_node:
        ctx.emit_inst(Label_(label=false_label))
        false_reg = ctx.lower_expr(alt_node)
        ctx.emit_inst(DeclVar(name=VarName(result_var), value_reg=false_reg))
        ctx.emit_inst(Branch(label=end_label))

    ctx.emit_inst(Label_(label=end_label))
    reg = ctx.fresh_reg()
    ctx.emit_inst(LoadVar(result_reg=reg, name=VarName(result_var)))
    return reg


def _test_let_condition(
    ctx: TreeSitterEmitContext, let_cond_node: Any
) -> tuple[Any, Any, Any]:  # Any: tree-sitter node — untyped at Python boundary
    """Test a single let_condition, returning (test_reg, pattern, subject_reg)."""
    pattern_node = let_cond_node.child_by_field_name("pattern")
    value_node = let_cond_node.child_by_field_name("value")
    subject_reg = ctx.lower_expr(value_node)
    pattern = parse_rust_pattern(ctx, pattern_node)
    test_reg = compile_pattern_test(ctx, subject_reg, pattern)
    return (test_reg, pattern, subject_reg)


def lower_expr_stmt_as_expr(
    ctx: TreeSitterEmitContext, node: Any
) -> Register:  # Any: tree-sitter node — untyped at Python boundary
    """Unwrap expression_statement to its inner expression."""
    named = [c for c in node.children if c.is_named]
    if named:
        return ctx.lower_expr(named[0])
    reg = ctx.fresh_reg()
    ctx.emit_inst(Const(result_reg=reg, value=ctx.constants.none_literal))
    return reg


def lower_else_clause(
    ctx: TreeSitterEmitContext, node: Any
) -> Register:  # Any: tree-sitter node — untyped at Python boundary
    """Lower else_clause by extracting its inner block or expression."""
    named = [c for c in node.children if c.is_named]
    if named:
        return ctx.lower_expr(named[0])
    reg = ctx.fresh_reg()
    ctx.emit_inst(Const(result_reg=reg, value=ctx.constants.none_literal))
    return reg


def lower_return_expr(
    ctx: TreeSitterEmitContext, node: Any
) -> Register:  # Any: tree-sitter node — untyped at Python boundary
    """Lower Rust return expression (value-producing)."""
    children = [c for c in node.children if c.type != RustNodeType.RETURN_KEYWORD]
    if children:
        val_reg = ctx.lower_expr(children[0])
    else:
        val_reg = ctx.fresh_reg()
        ctx.emit_inst(
            Const(result_reg=val_reg, value=ctx.constants.default_return_value)
        )
    ctx.emit_inst(Return_(value_reg=val_reg), node=node)
    return val_reg


def _rust_pattern_of(ctx: TreeSitterEmitContext, arm) -> Pattern:
    """Extract and parse pattern from a Rust match_arm."""
    match_pattern_node = next(
        c for c in arm.children if c.type == RustNodeType.MATCH_PATTERN
    )
    named_children = [c for c in match_pattern_node.children if c.is_named]
    pattern_node = named_children[0] if named_children else match_pattern_node
    return parse_rust_pattern(ctx, pattern_node)


def _rust_guard_of(
    ctx: TreeSitterEmitContext, arm: Any
) -> Any | None:  # Any: tree-sitter node — untyped at Python boundary
    """Extract guard expression from a Rust match_arm (inside match_pattern)."""
    match_pattern_node = next(
        c for c in arm.children if c.type == RustNodeType.MATCH_PATTERN
    )
    named_children = [c for c in match_pattern_node.children if c.is_named]
    return named_children[1] if len(named_children) > 1 else None


def _rust_body_of(ctx: TreeSitterEmitContext, arm) -> Register:
    """Lower a Rust match_arm body as expression."""
    body_expr = _extract_arm_body(arm)
    return ctx.lower_expr(body_expr)


_RUST_MATCH_SPEC = MatchArmSpec(
    extract_arms=lambda body: [
        c for c in body.children if c.type == RustNodeType.MATCH_ARM
    ],
    pattern_of=_rust_pattern_of,
    guard_of=_rust_guard_of,
    body_of=_rust_body_of,
)


def lower_match_expr(
    ctx: TreeSitterEmitContext, node: Any
) -> Register:  # Any: tree-sitter node — untyped at Python boundary
    """Lower Rust match expression using unified framework."""
    value_node = node.child_by_field_name("value")
    body_node = node.child_by_field_name("body")
    subject_reg = ctx.lower_expr(value_node)
    return lower_match_as_expr(ctx, subject_reg, body_node, _RUST_MATCH_SPEC)


def _extract_arm_body(
    arm: Any,
) -> Any:  # Any: tree-sitter node — untyped at Python boundary
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


def lower_block_expr(
    ctx: TreeSitterEmitContext, node: Any
) -> Register:  # Any: tree-sitter node — untyped at Python boundary
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
        ctx.emit_inst(Const(result_reg=reg, value=ctx.constants.none_literal))
        return reg
    for child in children[:-1]:
        ctx.lower_stmt(child)
    return ctx.lower_expr(children[-1])


def lower_closure_expr(
    ctx: TreeSitterEmitContext, node: Any
) -> Register:  # Any: tree-sitter node — untyped at Python boundary
    """Lower Rust closure expression |params| body."""
    params_node = node.child_by_field_name(ctx.constants.func_params_field)
    body_node = node.child_by_field_name(ctx.constants.func_body_field)

    func_name = f"__closure_{ctx.label_counter}"
    func_label = ctx.fresh_label(f"{constants.FUNC_LABEL_PREFIX}{func_name}")
    end_label = ctx.fresh_label(f"end_{func_name}")

    ctx.emit_inst(Branch(label=end_label))
    ctx.emit_inst(Label_(label=func_label))

    if params_node:
        _lower_closure_params(ctx, params_node)

    if body_node:
        result_reg = ctx.lower_expr(body_node)
        ctx.emit_inst(Return_(value_reg=result_reg))
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
            ctx.emit_inst(
                Symbolic(
                    result_reg=ctx.fresh_reg(), hint=f"{constants.PARAM_PREFIX}{pname}"
                ),
                node=child,
            )
            ctx.emit_inst(
                DeclVar(
                    name=VarName(pname), value_reg=Register(f"%{ctx.reg_counter - 1}")
                )
            )
        elif child.type == RustNodeType.PARAMETER:
            lower_rust_param(ctx, child)


def lower_struct_instantiation(
    ctx: TreeSitterEmitContext, node: Any
) -> Register:  # Any: tree-sitter node — untyped at Python boundary
    """Lower struct_expression: Point { x: 1, y: 2 }."""
    name_node = node.child_by_field_name(ctx.constants.class_name_field)
    body_node = node.child_by_field_name(ctx.constants.class_body_field)
    struct_name = ctx.node_text(name_node) if name_node else "Struct"

    obj_reg = ctx.fresh_reg()
    ctx.emit_inst(
        NewObject(result_reg=obj_reg, type_hint=scalar(struct_name)), node=node
    )

    if body_node:
        for child in body_node.children:
            if child.type == RustNodeType.FIELD_INITIALIZER:
                field_name_node = child.child_by_field_name("field")
                field_val_node = child.child_by_field_name("value")
                if field_name_node and field_val_node:
                    val_reg = ctx.lower_expr(field_val_node)
                    ctx.emit_inst(
                        StoreField(
                            obj_reg=obj_reg,
                            field_name=FieldName(ctx.node_text(field_name_node)),
                            value_reg=val_reg,
                        )
                    )
                elif field_name_node:
                    # Shorthand: `Point { x, y }` means `Point { x: x, y: y }`
                    from interpreter.frontends.common.expressions import (
                        lower_identifier,
                    )

                    val_reg = lower_identifier(ctx, field_name_node)
                    ctx.emit_inst(
                        StoreField(
                            obj_reg=obj_reg,
                            field_name=FieldName(ctx.node_text(field_name_node)),
                            value_reg=val_reg,
                        )
                    )
    return obj_reg


def lower_macro_invocation(
    ctx: TreeSitterEmitContext, node: Any
) -> Register:  # Any: tree-sitter node — untyped at Python boundary
    """Lower macro_invocation: vec![...] -> NEW_ARRAY; others -> CALL_FUNCTION."""
    macro_name = ctx.node_text(node).split("!")[0] + "!"
    if macro_name == "vec!":
        return _lower_vec_macro(ctx, node)
    reg = ctx.fresh_reg()
    ctx.emit_inst(
        CallFunction(result_reg=reg, func_name=FuncName(macro_name), args=()), node=node
    )
    return reg


def _lower_vec_macro(
    ctx: TreeSitterEmitContext, node: Any
) -> Register:  # Any: tree-sitter node — untyped at Python boundary
    """Lower vec![e1, e2, ...] -> NEW_ARRAY + STORE_INDEX per element."""
    token_tree = next(c for c in node.children if c.type == "token_tree")
    elems = [c for c in token_tree.children if c.is_named]
    arr_reg = ctx.fresh_reg()
    size_reg = ctx.fresh_reg()
    ctx.emit_inst(Const(result_reg=size_reg, value=str(len(elems))))
    ctx.emit_inst(
        NewArray(result_reg=arr_reg, type_hint=scalar("list"), size_reg=size_reg),
        node=node,
    )
    for i, elem in enumerate(elems):
        val_reg = ctx.lower_expr(elem)
        idx_reg = ctx.fresh_reg()
        ctx.emit_inst(Const(result_reg=idx_reg, value=str(i)))
        ctx.emit_inst(StoreIndex(arr_reg=arr_reg, index_reg=idx_reg, value_reg=val_reg))
    return arr_reg


def lower_index_expr(
    ctx: TreeSitterEmitContext, node: Any
) -> Register:  # Any: tree-sitter node — untyped at Python boundary
    """Lower index_expression: arr[idx] -> LOAD_INDEX, arr[1..3] -> slice."""
    children = [c for c in node.children if c.is_named]
    if len(children) < 2:
        return lower_const_literal(ctx, node)
    obj_reg = ctx.lower_expr(children[0])
    if children[1].type == RustNodeType.RANGE_EXPRESSION:
        return _lower_range_slice(ctx, children[1], obj_reg)
    idx_reg = ctx.lower_expr(children[1])
    reg = ctx.fresh_reg()
    ctx.emit_inst(
        LoadIndex(result_reg=reg, arr_reg=obj_reg, index_reg=idx_reg), node=node
    )
    return reg


def _lower_range_slice(
    ctx: TreeSitterEmitContext, range_node, collection_reg: str
) -> Register:
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
        ctx.emit_inst(
            Binop(
                result_reg=adjusted,
                operator=resolve_binop("+"),
                left=end_reg,
                right=one_reg,
            ),
            node=range_node,
        )
        end_reg = adjusted
    none_reg = _make_rust_const(ctx, ctx.constants.none_literal)
    reg = ctx.fresh_reg()
    ctx.emit_inst(
        CallFunction(
            result_reg=reg,
            func_name=FuncName("slice"),
            args=(
                collection_reg,
                start_reg,
                end_reg,
                none_reg,
            ),
        ),
        node=range_node,
    )
    return reg


def _make_rust_const(ctx: TreeSitterEmitContext, value: str) -> Register:
    """Emit a CONST and return the register."""
    reg = ctx.fresh_reg()
    ctx.emit_inst(Const(result_reg=reg, value=value))
    return reg


def lower_tuple_expr(
    ctx: TreeSitterEmitContext, node: Any
) -> Register:  # Any: tree-sitter node — untyped at Python boundary
    """Lower tuple_expression: (a, b, c) -> NEW_ARRAY."""
    elems = [
        c
        for c in node.children
        if c.type
        not in (RustNodeType.OPEN_PAREN, RustNodeType.CLOSE_PAREN, RustNodeType.COMMA)
    ]
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


def lower_try_expr(
    ctx: TreeSitterEmitContext, node: Any
) -> Register:  # Any: tree-sitter node — untyped at Python boundary
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
    ctx.emit_inst(
        CallFunction(
            result_reg=reg, func_name=FuncName("try_unwrap"), args=(inner_reg,)
        ),
        node=node,
    )
    return reg


def lower_await_expr(
    ctx: TreeSitterEmitContext, node: Any
) -> Register:  # Any: tree-sitter node — untyped at Python boundary
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
    ctx.emit_inst(
        CallFunction(result_reg=reg, func_name=FuncName("await"), args=(inner_reg,)),
        node=node,
    )
    return reg


def lower_type_cast_expr(
    ctx: TreeSitterEmitContext, node: Any
) -> Register:  # Any: tree-sitter node — untyped at Python boundary
    """Lower `expr as Type` as CALL_FUNCTION('as', expr, type_name)."""
    named_children = [c for c in node.children if c.is_named]
    if not named_children:
        return lower_const_literal(ctx, node)
    expr_reg = ctx.lower_expr(named_children[0])
    type_name = ctx.node_text(named_children[-1])
    reg = ctx.fresh_reg()
    ctx.emit_inst(
        CallFunction(
            result_reg=reg,
            func_name=FuncName("as"),
            args=(
                expr_reg,
                type_name,
            ),
        ),
        node=node,
    )
    return reg


def lower_scoped_identifier(
    ctx: TreeSitterEmitContext, node: Any
) -> Register:  # Any: tree-sitter node — untyped at Python boundary
    """Lower `HashMap::new`, `Shape::Circle` as LOAD_VAR with qualified name."""
    full_name = "::".join(
        ctx.node_text(c) for c in node.children if c.type == RustNodeType.IDENTIFIER
    )
    reg = ctx.fresh_reg()
    ctx.emit_inst(LoadVar(result_reg=reg, name=VarName(full_name)), node=node)
    return reg


def lower_range_expr(
    ctx: TreeSitterEmitContext, node: Any
) -> Register:  # Any: tree-sitter node — untyped at Python boundary
    """Lower `0..10` or `0..=10` as CALL_FUNCTION("range", start, end)."""
    named = [c for c in node.children if c.is_named]
    start_reg = ctx.lower_expr(named[0]) if len(named) > 0 else ctx.fresh_reg()
    end_reg = ctx.lower_expr(named[1]) if len(named) > 1 else ctx.fresh_reg()
    reg = ctx.fresh_reg()
    ctx.emit_inst(
        CallFunction(
            result_reg=reg,
            func_name=FuncName("range"),
            args=(
                start_reg,
                end_reg,
            ),
        ),
        node=node,
    )
    return reg


def lower_loop_as_expr(
    ctx: TreeSitterEmitContext, node: Any
) -> Register:  # Any: tree-sitter node — untyped at Python boundary
    """Lower while/loop/for in expression position (returns unit)."""
    ctx.lower_stmt(node)
    reg = ctx.fresh_reg()
    ctx.emit_inst(Const(result_reg=reg, value=ctx.constants.none_literal))
    return reg


def lower_continue_as_expr(
    ctx: TreeSitterEmitContext, node: Any
) -> Register:  # Any: tree-sitter node — untyped at Python boundary
    """Lower continue in expression position."""
    from interpreter.frontends.common.control_flow import lower_continue

    lower_continue(ctx, node)
    reg = ctx.fresh_reg()
    ctx.emit_inst(Const(result_reg=reg, value=ctx.constants.none_literal))
    return reg


def lower_break_as_expr(
    ctx: TreeSitterEmitContext, node: Any
) -> Register:  # Any: tree-sitter node — untyped at Python boundary
    """Lower break in expression position."""
    from interpreter.frontends.common.control_flow import lower_break

    lower_break(ctx, node)
    reg = ctx.fresh_reg()
    ctx.emit_inst(Const(result_reg=reg, value=ctx.constants.none_literal))
    return reg


def lower_assignment_expr(
    ctx: TreeSitterEmitContext, node: Any
) -> Register:  # Any: tree-sitter node — untyped at Python boundary
    """Lower assignment_expression: left = right (value-producing)."""
    left = node.child_by_field_name(ctx.constants.assign_left_field)
    right = node.child_by_field_name(ctx.constants.assign_right_field)
    val_reg = ctx.lower_expr(right)
    lower_rust_store_target(ctx, left, val_reg, node)
    return val_reg


def lower_compound_assignment_expr(
    ctx: TreeSitterEmitContext, node: Any
) -> Register:  # Any: tree-sitter node — untyped at Python boundary
    """Lower compound_assignment_expr: left += right."""
    left = node.child_by_field_name(ctx.constants.assign_left_field)
    right = node.child_by_field_name(ctx.constants.assign_right_field)
    op_node = node.child_by_field_name("operator")
    op_text = ctx.node_text(op_node).rstrip("=") if op_node else "+"
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
    lower_rust_store_target(ctx, left, result, node)
    return result


def lower_tuple_struct_pattern(
    ctx: TreeSitterEmitContext, node: Any
) -> Register:  # Any: tree-sitter node — untyped at Python boundary
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
    ctx.emit_inst(Const(result_reg=variant_reg, value=variant_name), node=node)
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
        ctx.emit_inst(Const(result_reg=idx_reg, value=str(i)))
        ctx.emit_inst(
            StoreIndex(arr_reg=variant_reg, index_reg=idx_reg, value_reg=child_reg)
        )
    return variant_reg


def lower_generic_function(
    ctx: TreeSitterEmitContext, node: Any
) -> Register:  # Any: tree-sitter node — untyped at Python boundary
    """Lower a.parse::<i32>() -- strip type params, lower as identifier."""
    named_children = [c for c in node.children if c.is_named]
    if named_children:
        return ctx.lower_expr(named_children[0])
    return lower_const_literal(ctx, node)


def lower_let_condition(
    ctx: TreeSitterEmitContext, node: Any
) -> Register:  # Any: tree-sitter node — untyped at Python boundary
    """Lower `let Pattern = expr` — returns boolean test register."""
    pattern_node = node.child_by_field_name("pattern")
    value_node = node.child_by_field_name("value")
    subject_reg = ctx.lower_expr(value_node)
    pattern = parse_rust_pattern(ctx, pattern_node)
    return compile_pattern_test(ctx, subject_reg, pattern)


def lower_struct_pattern_expr(
    ctx: TreeSitterEmitContext, node: Any
) -> Register:  # Any: tree-sitter node — untyped at Python boundary
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
    ctx.emit_inst(
        NewObject(result_reg=obj_reg, type_hint=StructPatternType(type_name)),
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
            ctx.emit_inst(Const(result_reg=key_reg, value=field_name))
            val_reg = ctx.fresh_reg()
            ctx.emit_inst(Const(result_reg=val_reg, value=field_name))
            ctx.emit_inst(
                StoreIndex(arr_reg=obj_reg, index_reg=key_reg, value_reg=val_reg)
            )
    return obj_reg


# ── Rust-specific store target ────────────────────────────────────────


def lower_rust_store_target(
    ctx: TreeSitterEmitContext, target, val_reg: str, parent_node
) -> None:
    """Rust-specific store target handling field_expression and index_expression."""
    if target.type == RustNodeType.IDENTIFIER:
        ctx.emit_inst(
            StoreVar(name=VarName(ctx.node_text(target)), value_reg=val_reg),
            node=parent_node,
        )
    elif target.type == RustNodeType.FIELD_EXPRESSION:
        value_node = target.child_by_field_name("value")
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
    elif target.type == RustNodeType.INDEX_EXPRESSION:
        children = [c for c in target.children if c.is_named]
        if len(children) >= 2:
            obj_reg = ctx.lower_expr(children[0])
            idx_reg = ctx.lower_expr(children[1])
            ctx.emit_inst(
                StoreIndex(arr_reg=obj_reg, index_reg=idx_reg, value_reg=val_reg),
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
            ctx.emit_inst(
                StoreIndirect(ptr_reg=inner_reg, value_reg=val_reg), node=parent_node
            )
    else:
        ctx.emit_inst(
            StoreVar(name=VarName(ctx.node_text(target)), value_reg=val_reg),
            node=parent_node,
        )
