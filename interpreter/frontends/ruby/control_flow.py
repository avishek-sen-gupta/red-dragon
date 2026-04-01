"""Ruby-specific control flow lowerers — pure functions taking (ctx, node)."""

from __future__ import annotations

from typing import Any

import logging
from interpreter.var_name import VarName
from interpreter.frontends.context import TreeSitterEmitContext

from interpreter.ir import NO_LABEL
from interpreter.operator_kind import resolve_binop, resolve_unop
from interpreter.func_name import FuncName
from interpreter.instructions import (
    Binop,
    Branch,
    BranchIf,
    CallFunction,
    Const,
    DeclVar,
    Label_,
    LoadIndex,
    LoadVar,
    StoreVar,
    Symbolic,
    TryPop,
    TryPush,
    Unop,
)
from interpreter import constants
from interpreter.frontends.ruby.node_types import RubyNodeType
from interpreter.register import Register

logger = logging.getLogger(__name__)

# ── unless (inverted if) ────────────────────────────────────────────


def lower_unless(
    ctx: TreeSitterEmitContext, node: Any
) -> None:  # Any: tree-sitter node — untyped at Python boundary
    """Lower unless — inverted if."""
    cond_node = node.child_by_field_name(ctx.constants.if_condition_field)
    body_node = node.child_by_field_name(ctx.constants.if_consequence_field)
    alt_node = node.child_by_field_name(ctx.constants.if_alternative_field)

    cond_reg = ctx.lower_expr(cond_node)
    negated_reg = ctx.fresh_reg()
    ctx.emit_inst(
        Unop(result_reg=negated_reg, operator=resolve_unop("!"), operand=cond_reg),
        node=node,
    )

    true_label = ctx.fresh_label("unless_true")
    false_label = ctx.fresh_label("unless_false")
    end_label = ctx.fresh_label("unless_end")

    if alt_node:
        ctx.emit_inst(
            BranchIf(cond_reg=negated_reg, branch_targets=(true_label, false_label)),
            node=node,
        )
    else:
        ctx.emit_inst(
            BranchIf(cond_reg=negated_reg, branch_targets=(true_label, end_label)),
            node=node,
        )

    ctx.emit_inst(Label_(label=true_label))
    ctx.lower_block(body_node)
    ctx.emit_inst(Branch(label=end_label))

    if alt_node:
        ctx.emit_inst(Label_(label=false_label))
        _lower_ruby_alternative(ctx, alt_node, end_label)
        ctx.emit_inst(Branch(label=end_label))

    ctx.emit_inst(Label_(label=end_label))


# ── until (inverted while) ──────────────────────────────────────────


def lower_until(
    ctx: TreeSitterEmitContext, node: Any
) -> None:  # Any: tree-sitter node — untyped at Python boundary
    """Lower until — inverted while."""
    cond_node = node.child_by_field_name(ctx.constants.while_condition_field)
    body_node = node.child_by_field_name(ctx.constants.while_body_field)

    loop_label = ctx.fresh_label("until_cond")
    body_label = ctx.fresh_label("until_body")
    end_label = ctx.fresh_label("until_end")

    ctx.emit_inst(Label_(label=loop_label))
    cond_reg = ctx.lower_expr(cond_node)
    negated_reg = ctx.fresh_reg()
    ctx.emit_inst(
        Unop(result_reg=negated_reg, operator=resolve_unop("!"), operand=cond_reg),
        node=node,
    )
    ctx.emit_inst(
        BranchIf(cond_reg=negated_reg, branch_targets=(body_label, end_label)),
        node=node,
    )

    ctx.emit_inst(Label_(label=body_label))
    ctx.push_loop(loop_label, end_label)
    ctx.lower_block(body_node)
    ctx.pop_loop()
    ctx.emit_inst(Branch(label=loop_label))

    ctx.emit_inst(Label_(label=end_label))


# ── for loop ────────────────────────────────────────────────────────


def lower_ruby_for(
    ctx: TreeSitterEmitContext, node: Any
) -> None:  # Any: tree-sitter node — untyped at Python boundary
    """Lower Ruby for-in loop."""
    pattern_node = node.child_by_field_name("pattern")
    value_node = node.child_by_field_name("value")
    body_node = node.child_by_field_name(ctx.constants.for_body_field)

    # The 'value' field returns the 'in' wrapper node — extract the actual
    # iterable expression from inside it (the named child that isn't 'in').
    if value_node and value_node.type == RubyNodeType.IN:
        iterable_node = next(
            (c for c in value_node.children if c.is_named),
            value_node,
        )
    else:
        iterable_node = value_node
    iter_reg = ctx.lower_expr(iterable_node) if iterable_node else ctx.fresh_reg()
    var_name = ctx.node_text(pattern_node) if pattern_node else "__for_var"

    init_idx = ctx.fresh_reg()
    ctx.emit_inst(Const(result_reg=init_idx, value="0"))
    ctx.emit_inst(DeclVar(name=VarName("__for_idx"), value_reg=init_idx))
    len_reg = ctx.fresh_reg()
    ctx.emit_inst(
        CallFunction(result_reg=len_reg, func_name=FuncName("len"), args=(iter_reg,))
    )

    loop_label = ctx.fresh_label("for_cond")
    body_label = ctx.fresh_label("for_body")
    end_label = ctx.fresh_label("for_end")

    ctx.emit_inst(Label_(label=loop_label))
    idx_reg = ctx.fresh_reg()
    ctx.emit_inst(LoadVar(result_reg=idx_reg, name=VarName("__for_idx")))
    cond_reg = ctx.fresh_reg()
    ctx.emit_inst(
        Binop(
            result_reg=cond_reg,
            operator=resolve_binop("<"),
            left=idx_reg,
            right=len_reg,
        )
    )
    ctx.emit_inst(BranchIf(cond_reg=cond_reg, branch_targets=(body_label, end_label)))

    ctx.emit_inst(Label_(label=body_label))
    elem_reg = ctx.fresh_reg()
    ctx.emit_inst(LoadIndex(result_reg=elem_reg, arr_reg=iter_reg, index_reg=idx_reg))
    ctx.emit_inst(DeclVar(name=VarName(var_name), value_reg=elem_reg))

    update_label = ctx.fresh_label("for_update")
    ctx.push_loop(update_label, end_label)
    if body_node:
        ctx.lower_block(body_node)
    ctx.pop_loop()

    ctx.emit_inst(Label_(label=update_label))
    one_reg = ctx.fresh_reg()
    ctx.emit_inst(Const(result_reg=one_reg, value="1"))
    new_idx = ctx.fresh_reg()
    ctx.emit_inst(
        Binop(
            result_reg=new_idx, operator=resolve_binop("+"), left=idx_reg, right=one_reg
        )
    )
    ctx.emit_inst(StoreVar(name=VarName("__for_idx"), value_reg=new_idx))
    ctx.emit_inst(Branch(label=loop_label))

    ctx.emit_inst(Label_(label=end_label))


# ── case/when ───────────────────────────────────────────────────────


def lower_case(
    ctx: TreeSitterEmitContext, node: Any
) -> None:  # Any: tree-sitter node — untyped at Python boundary
    """Lower `case expr; when val; ...; else; ...; end` as if/else chain."""
    value_node = node.child_by_field_name("value")
    val_reg = ctx.lower_expr(value_node) if value_node else ""

    when_clauses = [c for c in node.children if c.type == RubyNodeType.WHEN]
    else_clause = next(
        (c for c in node.children if c.type == RubyNodeType.ELSE),
        None,
    )
    end_label = ctx.fresh_label("case_end")

    for when_node in when_clauses:
        when_label = ctx.fresh_label("when_body")
        next_label = ctx.fresh_label("when_next")

        # Extract pattern(s) and body from when clause
        pattern_node = next(
            (c for c in when_node.children if c.type == RubyNodeType.PATTERN),
            None,
        )
        when_patterns = [
            c
            for c in when_node.children
            if c.is_named
            and c.type
            not in (
                RubyNodeType.WHEN,
                RubyNodeType.THEN,
                RubyNodeType.PATTERN,
                RubyNodeType.BODY_STATEMENT,
            )
        ]
        body_node = when_node.child_by_field_name("body")

        # If there's a pattern node, use it; otherwise use the first named child
        if pattern_node:
            pattern_reg = ctx.lower_expr(pattern_node)
        elif when_patterns:
            pattern_reg = ctx.lower_expr(when_patterns[0])
        else:
            ctx.emit_inst(Branch(label=when_label))
            ctx.emit_inst(Label_(label=when_label))
            if body_node:
                ctx.lower_block(body_node)
            ctx.emit_inst(Branch(label=end_label))
            ctx.emit_inst(Label_(label=next_label))
            continue

        if val_reg:
            cond_reg = ctx.fresh_reg()
            ctx.emit_inst(
                Binop(
                    result_reg=cond_reg,
                    operator=resolve_binop("=="),
                    left=val_reg,
                    right=pattern_reg,
                ),
                node=when_node,
            )
        else:
            cond_reg = pattern_reg

        ctx.emit_inst(
            BranchIf(cond_reg=cond_reg, branch_targets=(when_label, next_label)),
            node=when_node,
        )

        ctx.emit_inst(Label_(label=when_label))
        if body_node:
            ctx.lower_block(body_node)
        ctx.emit_inst(Branch(label=end_label))
        ctx.emit_inst(Label_(label=next_label))

    if else_clause:
        ctx.lower_block(else_clause)

    ctx.emit_inst(Label_(label=end_label))


# ── if with elsif handling ──────────────────────────────────────────


def lower_ruby_if(
    ctx: TreeSitterEmitContext, node: Any
) -> None:  # Any: tree-sitter node — untyped at Python boundary
    """Lower Ruby if statement with elsif support."""
    from interpreter.frontends.common.control_flow import lower_if

    # Ruby uses the same fields as the common lower_if
    cond_node = node.child_by_field_name(ctx.constants.if_condition_field)
    body_node = node.child_by_field_name(ctx.constants.if_consequence_field)
    alt_node = node.child_by_field_name(ctx.constants.if_alternative_field)

    cond_reg = ctx.lower_expr(cond_node)
    true_label = ctx.fresh_label("if_true")
    false_label = ctx.fresh_label("if_false")
    end_label = ctx.fresh_label("if_end")

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
    ctx.lower_block(body_node)
    ctx.emit_inst(Branch(label=end_label))

    if alt_node:
        ctx.emit_inst(Label_(label=false_label))
        _lower_ruby_alternative(ctx, alt_node, end_label)
        ctx.emit_inst(Branch(label=end_label))

    ctx.emit_inst(Label_(label=end_label))


def _lower_ruby_alternative(
    ctx: TreeSitterEmitContext, alt_node, end_label: str
) -> None:
    """Lower an else/elsif alternative block."""
    alt_type = alt_node.type
    if alt_type == RubyNodeType.ELSIF:
        _lower_ruby_elsif(ctx, alt_node, end_label)
    elif alt_type in (RubyNodeType.ELSE, RubyNodeType.ELSE_CLAUSE):
        for child in alt_node.children:
            if (
                child.type not in (RubyNodeType.ELSE, RubyNodeType.COLON)
                and child.is_named
            ):
                ctx.lower_stmt(child)
    else:
        ctx.lower_block(alt_node)


def _lower_ruby_elsif(
    ctx: TreeSitterEmitContext, node: Any, end_label: str
) -> None:  # Any: tree-sitter node — untyped at Python boundary
    """Lower elsif clause."""
    cond_node = node.child_by_field_name(ctx.constants.if_condition_field)
    body_node = node.child_by_field_name(ctx.constants.if_consequence_field)
    alt_node = node.child_by_field_name(ctx.constants.if_alternative_field)

    cond_reg = ctx.lower_expr(cond_node)
    true_label = ctx.fresh_label("elsif_true")
    false_label = ctx.fresh_label("elsif_false") if alt_node else end_label

    ctx.emit_inst(
        BranchIf(cond_reg=cond_reg, branch_targets=(true_label, false_label)), node=node
    )

    ctx.emit_inst(Label_(label=true_label))
    ctx.lower_block(body_node)
    ctx.emit_inst(Branch(label=end_label))

    if alt_node:
        ctx.emit_inst(Label_(label=false_label))
        _lower_ruby_alternative(ctx, alt_node, end_label)
        ctx.emit_inst(Branch(label=end_label))


def lower_ruby_elsif_stmt(
    ctx: TreeSitterEmitContext, node: Any
) -> None:  # Any: tree-sitter node — untyped at Python boundary
    """Handle elsif appearing as a top-level statement (fallback)."""
    end_label = ctx.fresh_label("elsif_end")
    _lower_ruby_elsif(ctx, node, end_label)
    ctx.emit_inst(Label_(label=end_label))


# ── if_modifier (body if condition) ─────────────────────────────────


def lower_ruby_if_modifier(
    ctx: TreeSitterEmitContext, node: Any
) -> None:  # Any: tree-sitter node — untyped at Python boundary
    """Lower `body if condition` — modifier-form if."""
    named = [c for c in node.children if c.is_named]
    if len(named) < 2:
        logger.warning(
            "if_modifier with fewer than 2 children: %s", ctx.node_text(node)[:40]
        )
        return
    body_node = named[0]
    cond_node = named[1]

    cond_reg = ctx.lower_expr(cond_node)
    true_label = ctx.fresh_label("ifmod_true")
    end_label = ctx.fresh_label("ifmod_end")

    ctx.emit_inst(
        BranchIf(cond_reg=cond_reg, branch_targets=(true_label, end_label)), node=node
    )
    ctx.emit_inst(Label_(label=true_label))
    ctx.lower_stmt(body_node)
    ctx.emit_inst(Branch(label=end_label))
    ctx.emit_inst(Label_(label=end_label))


# ── unless_modifier (body unless condition) ─────────────────────────


def lower_ruby_unless_modifier(
    ctx: TreeSitterEmitContext, node: Any
) -> None:  # Any: tree-sitter node — untyped at Python boundary
    """Lower `body unless condition` — inverted modifier-form if."""
    named = [c for c in node.children if c.is_named]
    if len(named) < 2:
        logger.warning(
            "unless_modifier with fewer than 2 children: %s",
            ctx.node_text(node)[:40],
        )
        return
    body_node = named[0]
    cond_node = named[1]

    cond_reg = ctx.lower_expr(cond_node)
    negated_reg = ctx.fresh_reg()
    ctx.emit_inst(
        Unop(result_reg=negated_reg, operator=resolve_unop("!"), operand=cond_reg),
        node=node,
    )
    true_label = ctx.fresh_label("unlessmod_true")
    end_label = ctx.fresh_label("unlessmod_end")

    ctx.emit_inst(
        BranchIf(cond_reg=negated_reg, branch_targets=(true_label, end_label)),
        node=node,
    )
    ctx.emit_inst(Label_(label=true_label))
    ctx.lower_stmt(body_node)
    ctx.emit_inst(Branch(label=end_label))
    ctx.emit_inst(Label_(label=end_label))


# ── while_modifier (body while condition) ───────────────────────────


def lower_ruby_while_modifier(
    ctx: TreeSitterEmitContext, node: Any
) -> None:  # Any: tree-sitter node — untyped at Python boundary
    """Lower `body while condition` — modifier-form while loop."""
    named = [c for c in node.children if c.is_named]
    if len(named) < 2:
        logger.warning(
            "while_modifier with fewer than 2 children: %s",
            ctx.node_text(node)[:40],
        )
        return
    body_node = named[0]
    cond_node = named[1]

    loop_label = ctx.fresh_label("whilemod_cond")
    body_label = ctx.fresh_label("whilemod_body")
    end_label = ctx.fresh_label("whilemod_end")

    ctx.emit_inst(Label_(label=loop_label))
    cond_reg = ctx.lower_expr(cond_node)
    ctx.emit_inst(
        BranchIf(cond_reg=cond_reg, branch_targets=(body_label, end_label)), node=node
    )

    ctx.emit_inst(Label_(label=body_label))
    ctx.push_loop(loop_label, end_label)
    ctx.lower_stmt(body_node)
    ctx.pop_loop()
    ctx.emit_inst(Branch(label=loop_label))

    ctx.emit_inst(Label_(label=end_label))


# ── until_modifier (body until condition) ───────────────────────────


def lower_ruby_until_modifier(
    ctx: TreeSitterEmitContext, node: Any
) -> None:  # Any: tree-sitter node — untyped at Python boundary
    """Lower `body until condition` — inverted modifier-form while loop."""
    named = [c for c in node.children if c.is_named]
    if len(named) < 2:
        logger.warning(
            "until_modifier with fewer than 2 children: %s",
            ctx.node_text(node)[:40],
        )
        return
    body_node = named[0]
    cond_node = named[1]

    loop_label = ctx.fresh_label("untilmod_cond")
    body_label = ctx.fresh_label("untilmod_body")
    end_label = ctx.fresh_label("untilmod_end")

    ctx.emit_inst(Label_(label=loop_label))
    cond_reg = ctx.lower_expr(cond_node)
    negated_reg = ctx.fresh_reg()
    ctx.emit_inst(
        Unop(result_reg=negated_reg, operator=resolve_unop("!"), operand=cond_reg),
        node=node,
    )
    ctx.emit_inst(
        BranchIf(cond_reg=negated_reg, branch_targets=(body_label, end_label)),
        node=node,
    )

    ctx.emit_inst(Label_(label=body_label))
    ctx.push_loop(loop_label, end_label)
    ctx.lower_stmt(body_node)
    ctx.pop_loop()
    ctx.emit_inst(Branch(label=loop_label))

    ctx.emit_inst(Label_(label=end_label))


# ── begin/rescue/else/ensure ────────────────────────────────────────


def lower_begin(
    ctx: TreeSitterEmitContext, node: Any
) -> None:  # Any: tree-sitter node — untyped at Python boundary
    """Lower begin...rescue...else...ensure...end."""
    container = node
    body_stmt = next(
        (c for c in node.children if c.type == RubyNodeType.BODY_STATEMENT),
        None,
    )
    if body_stmt is not None:
        container = body_stmt

    body_children = []
    catch_clauses = []
    finally_node = None
    else_node = None

    for child in container.children:
        if child.type == RubyNodeType.RESCUE:
            exc_var = None
            exc_type = None
            exceptions_node = next(
                (c for c in child.children if c.type == RubyNodeType.EXCEPTIONS),
                None,
            )
            if exceptions_node:
                exc_type = ctx.node_text(exceptions_node)
            var_node = next(
                (
                    c
                    for c in child.children
                    if c.type == RubyNodeType.EXCEPTION_VARIABLE
                ),
                None,
            )
            if var_node:
                # exception_variable contains => and identifier
                id_node = next(
                    (c for c in var_node.children if c.type == RubyNodeType.IDENTIFIER),
                    None,
                )
                exc_var = ctx.node_text(id_node) if id_node else None
            rescue_body = child.child_by_field_name("body") or next(
                (c for c in child.children if c.type == RubyNodeType.THEN),
                None,
            )
            catch_clauses.append(
                {"body": rescue_body, "variable": exc_var, "type": exc_type}
            )
        elif child.type == RubyNodeType.ENSURE:
            # ensure children: "ensure" keyword + body statements
            finally_node = child
        elif child.type == RubyNodeType.ELSE:
            else_node = child
        else:
            body_children.append(child)

    _lower_try_catch_ruby(
        ctx, node, body_children, catch_clauses, finally_node, else_node
    )


def _lower_try_catch_ruby(
    ctx: TreeSitterEmitContext,
    node,
    body_children,
    catch_clauses,
    finally_node,
    else_node,
) -> None:
    """Ruby-specific try/catch lowering (body is a list of children, not a single node)."""
    try_body_label = ctx.fresh_label("try_body")
    catch_labels = [ctx.fresh_label(f"catch_{i}") for i in range(len(catch_clauses))]
    finally_label = ctx.fresh_label("try_finally") if finally_node else NO_LABEL
    else_label = ctx.fresh_label("try_else") if else_node else NO_LABEL
    end_label = ctx.fresh_label("try_end")

    exit_target = finally_label if finally_label.is_present() else end_label

    # push exception handler
    ctx.emit_inst(
        TryPush(
            catch_labels=tuple(catch_labels),
            finally_label=finally_label,
            end_label=end_label,
        )
    )

    # try body
    ctx.emit_inst(Label_(label=try_body_label))
    for child in body_children:
        if (
            child.is_named
            and child.type not in ctx.constants.comment_types
            and child.type not in ctx.constants.noise_types
        ):
            ctx.lower_stmt(child)
    # pop exception handler (normal exit)
    ctx.emit_inst(TryPop())
    if else_label.is_present():
        ctx.emit_inst(Branch(label=else_label))
    else:
        ctx.emit_inst(Branch(label=exit_target))

    # catch clauses
    for i, clause in enumerate(catch_clauses):
        ctx.emit_inst(Label_(label=catch_labels[i]))
        exc_type = clause.get("type", "StandardError") or "StandardError"
        exc_reg = ctx.fresh_reg()
        ctx.emit_inst(
            Symbolic(
                result_reg=exc_reg,
                hint=f"{constants.CAUGHT_EXCEPTION_PREFIX}:{exc_type}",
            ),
            node=node,
        )
        exc_var = clause.get("variable")
        if exc_var:
            ctx.emit_inst(DeclVar(name=VarName(exc_var), value_reg=exc_reg), node=node)
        catch_body = clause.get("body")
        if catch_body:
            ctx.lower_block(catch_body)
        ctx.emit_inst(Branch(label=exit_target))

    # else clause
    if else_node:
        ctx.emit_inst(Label_(label=else_label))
        ctx.lower_block(else_node)
        ctx.emit_inst(Branch(label=finally_label or end_label))

    # finally (ensure)
    if finally_node:
        ctx.emit_inst(Label_(label=finally_label))
        ctx.lower_block(finally_node)

    ctx.emit_inst(Label_(label=end_label))


# ── case/in pattern matching ─────────────────────────────────────────


def _extract_case_match_arms(node) -> list:
    """Collect in_clause children, appending else as a synthetic wildcard arm."""
    from interpreter.frontends.common.patterns import WildcardPattern

    arms = [c for c in node.children if c.type == RubyNodeType.IN_CLAUSE]
    else_node = next(
        (c for c in node.children if c.type == RubyNodeType.ELSE),
        None,
    )
    if else_node:
        arms.append(("__else__", else_node))
    return arms


def _case_match_pattern_of(ctx: TreeSitterEmitContext, arm) -> "Pattern":
    """Extract and parse the pattern from an in_clause or synthetic else arm."""
    from interpreter.frontends.common.patterns import WildcardPattern
    from interpreter.frontends.ruby.patterns import parse_ruby_pattern

    if isinstance(arm, tuple) and arm[0] == "__else__":
        return WildcardPattern()
    pattern_node = arm.child_by_field_name("pattern")
    return parse_ruby_pattern(ctx, pattern_node)


def _case_match_guard_of(
    ctx: TreeSitterEmitContext, arm: Any
) -> None:  # Any: tree-sitter node — untyped at Python boundary
    """Ruby case/in guards are out of scope — always None."""
    return None


def _case_match_body_of(ctx: TreeSitterEmitContext, arm) -> str:
    """Lower the body of an in_clause or synthetic else arm as an expression."""
    if isinstance(arm, tuple) and arm[0] == "__else__":
        else_node = arm[1]
        body_children = [c for c in else_node.children if c.is_named]
        # Lower the last named child as the expression result
        return ctx.lower_expr(body_children[-1]) if body_children else ctx.fresh_reg()

    body_node = arm.child_by_field_name("body")
    # body is a `then` node; its named children (excluding `then` keyword) are body exprs
    body_exprs = [c for c in body_node.children if c.is_named]
    # Lower all but the last as statements, return the last as expression
    for expr in body_exprs[:-1]:
        ctx.lower_stmt(expr)
    return ctx.lower_expr(body_exprs[-1]) if body_exprs else ctx.fresh_reg()


_RUBY_CASE_MATCH_SPEC = None  # lazy init to avoid circular imports


def _get_case_match_spec() -> Any:
    global _RUBY_CASE_MATCH_SPEC
    if _RUBY_CASE_MATCH_SPEC is None:
        from interpreter.frontends.common.match_expr import MatchArmSpec

        _RUBY_CASE_MATCH_SPEC = MatchArmSpec(
            extract_arms=_extract_case_match_arms,
            pattern_of=_case_match_pattern_of,
            guard_of=_case_match_guard_of,
            body_of=_case_match_body_of,
        )
    return _RUBY_CASE_MATCH_SPEC


def lower_case_match(
    ctx: TreeSitterEmitContext, node: Any
) -> Register:  # Any: tree-sitter node — untyped at Python boundary
    """Lower Ruby case/in using unified match framework."""
    from interpreter.frontends.common.match_expr import lower_match_as_expr

    subject_node = node.child_by_field_name("value")
    subject_reg = ctx.lower_expr(subject_node)
    return lower_match_as_expr(ctx, subject_reg, node, _get_case_match_spec())


def lower_case_match_stmt(
    ctx: TreeSitterEmitContext, node: Any
) -> None:  # Any: tree-sitter node — untyped at Python boundary
    """Lower Ruby case/in at statement level."""
    lower_case_match(ctx, node)


# ── in clause (case/in pattern matching) ────────────────────────────


def lower_ruby_in_clause(
    ctx: TreeSitterEmitContext, node: Any
) -> None:  # Any: tree-sitter node — untyped at Python boundary
    """Lower `in pattern then body` clause — treated as a when-like arm."""
    named_children = [
        c
        for c in node.children
        if c.is_named and c.type not in (RubyNodeType.THEN, RubyNodeType.IN)
    ]
    for child in named_children:
        if child.type == RubyNodeType.BODY_STATEMENT:
            ctx.lower_block(child)
        else:
            ctx.lower_expr(child)


# ── retry ───────────────────────────────────────────────────────────


def lower_ruby_retry(
    ctx: TreeSitterEmitContext, node: Any
) -> None:  # Any: tree-sitter node — untyped at Python boundary
    """Lower `retry` as CALL_FUNCTION('retry')."""
    reg = ctx.fresh_reg()
    ctx.emit_inst(
        CallFunction(result_reg=reg, func_name=FuncName("retry"), args=()), node=node
    )


# ── rescue_modifier (expr rescue fallback) ────────────────────────


def lower_ruby_rescue_modifier_expr(
    ctx: TreeSitterEmitContext, node: Any
) -> Register:  # Any: tree-sitter node — untyped at Python boundary
    """Lower ``expr rescue fallback`` as an expression — inline exception handling.

    Wraps the body expression in TRY_PUSH / TRY_POP; on exception,
    evaluates the fallback expression instead.  Returns the result register.
    """
    named = [c for c in node.children if c.is_named]
    if len(named) < 2:
        logger.warning(
            "rescue_modifier with fewer than 2 children: %s",
            ctx.node_text(node)[:40],
        )
        return ctx.fresh_reg()
    body_node = named[0]
    fallback_node = named[1]

    result_var = f"__rescue_result_{ctx.label_counter}"
    catch_label = ctx.fresh_label("rescue_catch")
    end_label = ctx.fresh_label("rescue_end")

    ctx.emit_inst(
        TryPush(
            catch_labels=(catch_label,), finally_label=NO_LABEL, end_label=end_label
        )
    )
    body_reg = ctx.lower_expr(body_node)
    ctx.emit_inst(DeclVar(name=VarName(result_var), value_reg=body_reg), node=node)
    ctx.emit_inst(TryPop())
    ctx.emit_inst(Branch(label=end_label))

    ctx.emit_inst(Label_(label=catch_label))
    fallback_reg = ctx.lower_expr(fallback_node)
    ctx.emit_inst(DeclVar(name=VarName(result_var), value_reg=fallback_reg), node=node)
    ctx.emit_inst(Branch(label=end_label))

    ctx.emit_inst(Label_(label=end_label))
    reg = ctx.fresh_reg()
    ctx.emit_inst(LoadVar(result_reg=reg, name=VarName(result_var)))
    return reg


def lower_ruby_rescue_modifier(
    ctx: TreeSitterEmitContext, node: Any
) -> None:  # Any: tree-sitter node — untyped at Python boundary
    """Lower ``expr rescue fallback`` at statement level."""
    lower_ruby_rescue_modifier_expr(ctx, node)
