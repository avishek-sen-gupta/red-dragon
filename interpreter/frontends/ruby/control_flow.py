"""Ruby-specific control flow lowerers — pure functions taking (ctx, node)."""

from __future__ import annotations

import logging
from interpreter.frontends.context import TreeSitterEmitContext

from interpreter.ir import Opcode
from interpreter import constants
from interpreter.frontends.ruby.node_types import RubyNodeType

logger = logging.getLogger(__name__)


# ── unless (inverted if) ────────────────────────────────────────────


def lower_unless(ctx: TreeSitterEmitContext, node) -> None:
    """Lower unless — inverted if."""
    cond_node = node.child_by_field_name(ctx.constants.if_condition_field)
    body_node = node.child_by_field_name(ctx.constants.if_consequence_field)
    alt_node = node.child_by_field_name(ctx.constants.if_alternative_field)

    cond_reg = ctx.lower_expr(cond_node)
    negated_reg = ctx.fresh_reg()
    ctx.emit(
        Opcode.UNOP,
        result_reg=negated_reg,
        operands=["!", cond_reg],
        node=node,
    )

    true_label = ctx.fresh_label("unless_true")
    false_label = ctx.fresh_label("unless_false")
    end_label = ctx.fresh_label("unless_end")

    if alt_node:
        ctx.emit(
            Opcode.BRANCH_IF,
            operands=[negated_reg],
            label=f"{true_label},{false_label}",
            node=node,
        )
    else:
        ctx.emit(
            Opcode.BRANCH_IF,
            operands=[negated_reg],
            label=f"{true_label},{end_label}",
            node=node,
        )

    ctx.emit(Opcode.LABEL, label=true_label)
    ctx.lower_block(body_node)
    ctx.emit(Opcode.BRANCH, label=end_label)

    if alt_node:
        ctx.emit(Opcode.LABEL, label=false_label)
        _lower_ruby_alternative(ctx, alt_node, end_label)
        ctx.emit(Opcode.BRANCH, label=end_label)

    ctx.emit(Opcode.LABEL, label=end_label)


# ── until (inverted while) ──────────────────────────────────────────


def lower_until(ctx: TreeSitterEmitContext, node) -> None:
    """Lower until — inverted while."""
    cond_node = node.child_by_field_name(ctx.constants.while_condition_field)
    body_node = node.child_by_field_name(ctx.constants.while_body_field)

    loop_label = ctx.fresh_label("until_cond")
    body_label = ctx.fresh_label("until_body")
    end_label = ctx.fresh_label("until_end")

    ctx.emit(Opcode.LABEL, label=loop_label)
    cond_reg = ctx.lower_expr(cond_node)
    negated_reg = ctx.fresh_reg()
    ctx.emit(
        Opcode.UNOP,
        result_reg=negated_reg,
        operands=["!", cond_reg],
        node=node,
    )
    ctx.emit(
        Opcode.BRANCH_IF,
        operands=[negated_reg],
        label=f"{body_label},{end_label}",
        node=node,
    )

    ctx.emit(Opcode.LABEL, label=body_label)
    ctx.push_loop(loop_label, end_label)
    ctx.lower_block(body_node)
    ctx.pop_loop()
    ctx.emit(Opcode.BRANCH, label=loop_label)

    ctx.emit(Opcode.LABEL, label=end_label)


# ── for loop ────────────────────────────────────────────────────────


def lower_ruby_for(ctx: TreeSitterEmitContext, node) -> None:
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
    ctx.emit(Opcode.CONST, result_reg=init_idx, operands=["0"])
    ctx.emit(Opcode.DECL_VAR, operands=["__for_idx", init_idx])
    len_reg = ctx.fresh_reg()
    ctx.emit(Opcode.CALL_FUNCTION, result_reg=len_reg, operands=["len", iter_reg])

    loop_label = ctx.fresh_label("for_cond")
    body_label = ctx.fresh_label("for_body")
    end_label = ctx.fresh_label("for_end")

    ctx.emit(Opcode.LABEL, label=loop_label)
    idx_reg = ctx.fresh_reg()
    ctx.emit(Opcode.LOAD_VAR, result_reg=idx_reg, operands=["__for_idx"])
    cond_reg = ctx.fresh_reg()
    ctx.emit(Opcode.BINOP, result_reg=cond_reg, operands=["<", idx_reg, len_reg])
    ctx.emit(
        Opcode.BRANCH_IF,
        operands=[cond_reg],
        label=f"{body_label},{end_label}",
    )

    ctx.emit(Opcode.LABEL, label=body_label)
    elem_reg = ctx.fresh_reg()
    ctx.emit(Opcode.LOAD_INDEX, result_reg=elem_reg, operands=[iter_reg, idx_reg])
    ctx.emit(Opcode.DECL_VAR, operands=[var_name, elem_reg])

    update_label = ctx.fresh_label("for_update")
    ctx.push_loop(update_label, end_label)
    if body_node:
        ctx.lower_block(body_node)
    ctx.pop_loop()

    ctx.emit(Opcode.LABEL, label=update_label)
    one_reg = ctx.fresh_reg()
    ctx.emit(Opcode.CONST, result_reg=one_reg, operands=["1"])
    new_idx = ctx.fresh_reg()
    ctx.emit(Opcode.BINOP, result_reg=new_idx, operands=["+", idx_reg, one_reg])
    ctx.emit(Opcode.STORE_VAR, operands=["__for_idx", new_idx])
    ctx.emit(Opcode.BRANCH, label=loop_label)

    ctx.emit(Opcode.LABEL, label=end_label)


# ── case/when ───────────────────────────────────────────────────────


def lower_case(ctx: TreeSitterEmitContext, node) -> None:
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
            ctx.emit(Opcode.BRANCH, label=when_label)
            ctx.emit(Opcode.LABEL, label=when_label)
            if body_node:
                ctx.lower_block(body_node)
            ctx.emit(Opcode.BRANCH, label=end_label)
            ctx.emit(Opcode.LABEL, label=next_label)
            continue

        if val_reg:
            cond_reg = ctx.fresh_reg()
            ctx.emit(
                Opcode.BINOP,
                result_reg=cond_reg,
                operands=["==", val_reg, pattern_reg],
                node=when_node,
            )
        else:
            cond_reg = pattern_reg

        ctx.emit(
            Opcode.BRANCH_IF,
            operands=[cond_reg],
            label=f"{when_label},{next_label}",
            node=when_node,
        )

        ctx.emit(Opcode.LABEL, label=when_label)
        if body_node:
            ctx.lower_block(body_node)
        ctx.emit(Opcode.BRANCH, label=end_label)
        ctx.emit(Opcode.LABEL, label=next_label)

    if else_clause:
        ctx.lower_block(else_clause)

    ctx.emit(Opcode.LABEL, label=end_label)


# ── if with elsif handling ──────────────────────────────────────────


def lower_ruby_if(ctx: TreeSitterEmitContext, node) -> None:
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
    ctx.lower_block(body_node)
    ctx.emit(Opcode.BRANCH, label=end_label)

    if alt_node:
        ctx.emit(Opcode.LABEL, label=false_label)
        _lower_ruby_alternative(ctx, alt_node, end_label)
        ctx.emit(Opcode.BRANCH, label=end_label)

    ctx.emit(Opcode.LABEL, label=end_label)


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


def _lower_ruby_elsif(ctx: TreeSitterEmitContext, node, end_label: str) -> None:
    """Lower elsif clause."""
    cond_node = node.child_by_field_name(ctx.constants.if_condition_field)
    body_node = node.child_by_field_name(ctx.constants.if_consequence_field)
    alt_node = node.child_by_field_name(ctx.constants.if_alternative_field)

    cond_reg = ctx.lower_expr(cond_node)
    true_label = ctx.fresh_label("elsif_true")
    false_label = ctx.fresh_label("elsif_false") if alt_node else end_label

    ctx.emit(
        Opcode.BRANCH_IF,
        operands=[cond_reg],
        label=f"{true_label},{false_label}",
        node=node,
    )

    ctx.emit(Opcode.LABEL, label=true_label)
    ctx.lower_block(body_node)
    ctx.emit(Opcode.BRANCH, label=end_label)

    if alt_node:
        ctx.emit(Opcode.LABEL, label=false_label)
        _lower_ruby_alternative(ctx, alt_node, end_label)
        ctx.emit(Opcode.BRANCH, label=end_label)


def lower_ruby_elsif_stmt(ctx: TreeSitterEmitContext, node) -> None:
    """Handle elsif appearing as a top-level statement (fallback)."""
    end_label = ctx.fresh_label("elsif_end")
    _lower_ruby_elsif(ctx, node, end_label)
    ctx.emit(Opcode.LABEL, label=end_label)


# ── if_modifier (body if condition) ─────────────────────────────────


def lower_ruby_if_modifier(ctx: TreeSitterEmitContext, node) -> None:
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

    ctx.emit(
        Opcode.BRANCH_IF,
        operands=[cond_reg],
        label=f"{true_label},{end_label}",
        node=node,
    )
    ctx.emit(Opcode.LABEL, label=true_label)
    ctx.lower_stmt(body_node)
    ctx.emit(Opcode.BRANCH, label=end_label)
    ctx.emit(Opcode.LABEL, label=end_label)


# ── unless_modifier (body unless condition) ─────────────────────────


def lower_ruby_unless_modifier(ctx: TreeSitterEmitContext, node) -> None:
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
    ctx.emit(
        Opcode.UNOP,
        result_reg=negated_reg,
        operands=["!", cond_reg],
        node=node,
    )
    true_label = ctx.fresh_label("unlessmod_true")
    end_label = ctx.fresh_label("unlessmod_end")

    ctx.emit(
        Opcode.BRANCH_IF,
        operands=[negated_reg],
        label=f"{true_label},{end_label}",
        node=node,
    )
    ctx.emit(Opcode.LABEL, label=true_label)
    ctx.lower_stmt(body_node)
    ctx.emit(Opcode.BRANCH, label=end_label)
    ctx.emit(Opcode.LABEL, label=end_label)


# ── while_modifier (body while condition) ───────────────────────────


def lower_ruby_while_modifier(ctx: TreeSitterEmitContext, node) -> None:
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

    ctx.emit(Opcode.LABEL, label=loop_label)
    cond_reg = ctx.lower_expr(cond_node)
    ctx.emit(
        Opcode.BRANCH_IF,
        operands=[cond_reg],
        label=f"{body_label},{end_label}",
        node=node,
    )

    ctx.emit(Opcode.LABEL, label=body_label)
    ctx.push_loop(loop_label, end_label)
    ctx.lower_stmt(body_node)
    ctx.pop_loop()
    ctx.emit(Opcode.BRANCH, label=loop_label)

    ctx.emit(Opcode.LABEL, label=end_label)


# ── until_modifier (body until condition) ───────────────────────────


def lower_ruby_until_modifier(ctx: TreeSitterEmitContext, node) -> None:
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

    ctx.emit(Opcode.LABEL, label=loop_label)
    cond_reg = ctx.lower_expr(cond_node)
    negated_reg = ctx.fresh_reg()
    ctx.emit(
        Opcode.UNOP,
        result_reg=negated_reg,
        operands=["!", cond_reg],
        node=node,
    )
    ctx.emit(
        Opcode.BRANCH_IF,
        operands=[negated_reg],
        label=f"{body_label},{end_label}",
        node=node,
    )

    ctx.emit(Opcode.LABEL, label=body_label)
    ctx.push_loop(loop_label, end_label)
    ctx.lower_stmt(body_node)
    ctx.pop_loop()
    ctx.emit(Opcode.BRANCH, label=loop_label)

    ctx.emit(Opcode.LABEL, label=end_label)


# ── begin/rescue/else/ensure ────────────────────────────────────────


def lower_begin(ctx: TreeSitterEmitContext, node) -> None:
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
    finally_label = ctx.fresh_label("try_finally") if finally_node else ""
    else_label = ctx.fresh_label("try_else") if else_node else ""
    end_label = ctx.fresh_label("try_end")

    exit_target = finally_label or end_label

    # push exception handler
    ctx.emit(
        Opcode.TRY_PUSH,
        operands=[
            ",".join(catch_labels),
            finally_label or "",
            end_label,
        ],
    )

    # try body
    ctx.emit(Opcode.LABEL, label=try_body_label)
    for child in body_children:
        if (
            child.is_named
            and child.type not in ctx.constants.comment_types
            and child.type not in ctx.constants.noise_types
        ):
            ctx.lower_stmt(child)
    # pop exception handler (normal exit)
    ctx.emit(Opcode.TRY_POP)
    if else_label:
        ctx.emit(Opcode.BRANCH, label=else_label)
    else:
        ctx.emit(Opcode.BRANCH, label=exit_target)

    # catch clauses
    for i, clause in enumerate(catch_clauses):
        ctx.emit(Opcode.LABEL, label=catch_labels[i])
        exc_type = clause.get("type", "StandardError") or "StandardError"
        exc_reg = ctx.fresh_reg()
        ctx.emit(
            Opcode.SYMBOLIC,
            result_reg=exc_reg,
            operands=[f"{constants.CAUGHT_EXCEPTION_PREFIX}:{exc_type}"],
            node=node,
        )
        exc_var = clause.get("variable")
        if exc_var:
            ctx.emit(
                Opcode.DECL_VAR,
                operands=[exc_var, exc_reg],
                node=node,
            )
        catch_body = clause.get("body")
        if catch_body:
            ctx.lower_block(catch_body)
        ctx.emit(Opcode.BRANCH, label=exit_target)

    # else clause
    if else_node:
        ctx.emit(Opcode.LABEL, label=else_label)
        ctx.lower_block(else_node)
        ctx.emit(Opcode.BRANCH, label=finally_label or end_label)

    # finally (ensure)
    if finally_node:
        ctx.emit(Opcode.LABEL, label=finally_label)
        ctx.lower_block(finally_node)

    ctx.emit(Opcode.LABEL, label=end_label)


# ── in clause (case/in pattern matching) ────────────────────────────


def lower_ruby_in_clause(ctx: TreeSitterEmitContext, node) -> None:
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


def lower_ruby_retry(ctx: TreeSitterEmitContext, node) -> None:
    """Lower `retry` as CALL_FUNCTION('retry')."""
    reg = ctx.fresh_reg()
    ctx.emit(
        Opcode.CALL_FUNCTION,
        result_reg=reg,
        operands=["retry"],
        node=node,
    )


# ── rescue_modifier (expr rescue fallback) ────────────────────────


def lower_ruby_rescue_modifier_expr(ctx: TreeSitterEmitContext, node) -> str:
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

    ctx.emit(Opcode.TRY_PUSH, operands=[catch_label, "", end_label])
    body_reg = ctx.lower_expr(body_node)
    ctx.emit(Opcode.DECL_VAR, operands=[result_var, body_reg], node=node)
    ctx.emit(Opcode.TRY_POP)
    ctx.emit(Opcode.BRANCH, label=end_label)

    ctx.emit(Opcode.LABEL, label=catch_label)
    fallback_reg = ctx.lower_expr(fallback_node)
    ctx.emit(Opcode.DECL_VAR, operands=[result_var, fallback_reg], node=node)
    ctx.emit(Opcode.BRANCH, label=end_label)

    ctx.emit(Opcode.LABEL, label=end_label)
    reg = ctx.fresh_reg()
    ctx.emit(Opcode.LOAD_VAR, result_reg=reg, operands=[result_var])
    return reg


def lower_ruby_rescue_modifier(ctx: TreeSitterEmitContext, node) -> None:
    """Lower ``expr rescue fallback`` at statement level."""
    lower_ruby_rescue_modifier_expr(ctx, node)
