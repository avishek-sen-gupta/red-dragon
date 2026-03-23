"""Scala-specific control flow lowerers — pure functions taking (ctx, node)."""

from __future__ import annotations

from interpreter.frontends.context import TreeSitterEmitContext

from interpreter.ir import Opcode, CodeLabel
from interpreter.frontends.common.exceptions import lower_try_catch
from interpreter.frontends.scala.expressions import lower_if_expr, lower_match_expr
from interpreter.frontends.scala.node_types import ScalaNodeType as NT


def lower_if_stmt(ctx: TreeSitterEmitContext, node) -> None:
    """Lower if as a statement (discard result)."""
    lower_if_expr(ctx, node)


def lower_while(ctx: TreeSitterEmitContext, node) -> None:
    cond_node = node.child_by_field_name(ctx.constants.while_condition_field)
    body_node = node.child_by_field_name(ctx.constants.while_body_field)

    loop_label = ctx.fresh_label("while_cond")
    body_label = ctx.fresh_label("while_body")
    end_label = ctx.fresh_label("while_end")

    ctx.emit(Opcode.LABEL, label=loop_label)
    cond_reg = ctx.lower_expr(cond_node) if cond_node else ctx.fresh_reg()
    ctx.emit(
        Opcode.BRANCH_IF,
        operands=[cond_reg],
        label=CodeLabel(f"{body_label},{end_label}"),
        node=node,
    )

    ctx.emit(Opcode.LABEL, label=body_label)
    if body_node:
        ctx.lower_block(body_node)
    ctx.emit(Opcode.BRANCH, label=loop_label)

    ctx.emit(Opcode.LABEL, label=end_label)


def lower_match_stmt(ctx: TreeSitterEmitContext, node) -> None:
    """Lower match as a statement (discard result)."""
    lower_match_expr(ctx, node)


def lower_for_expr(ctx: TreeSitterEmitContext, node) -> None:
    """Lower for-comprehension: for (generators) body / for (generators) yield body."""
    enumerators_node = next(
        (c for c in node.children if c.type == NT.ENUMERATORS), None
    )
    # Body is the last named child (after the enumerators and yield keyword)
    named_children = [c for c in node.children if c.is_named]
    body_node = named_children[-1] if named_children else None
    # Don't use enumerators_node as body
    if body_node is enumerators_node:
        body_node = None

    generators = (
        [c for c in enumerators_node.children if c.type == NT.ENUMERATOR]
        if enumerators_node
        else []
    )
    guards = (
        [c for c in enumerators_node.children if c.type == NT.GUARD]
        if enumerators_node
        else []
    )

    loop_label = ctx.fresh_label("for_comp_loop")
    end_label = ctx.fresh_label("for_comp_end")

    # Lower each generator: extract binding + iterable from children
    for gen in generators:
        gen_children = [c for c in gen.children if c.is_named]
        # First named child is the binding, last is the iterable
        binding_node = gen_children[0] if gen_children else None
        iterable_node = gen_children[-1] if len(gen_children) > 1 else None
        var_name = ctx.node_text(binding_node) if binding_node else "__for_var"
        iter_reg = ctx.lower_expr(iterable_node) if iterable_node else ctx.fresh_reg()
        iter_fn_reg = ctx.fresh_reg()
        ctx.emit(
            Opcode.CALL_FUNCTION,
            result_reg=iter_fn_reg,
            operands=["iter", iter_reg],
            node=gen,
        )

    ctx.emit(Opcode.LABEL, label=loop_label)
    ctx.enter_block_scope()

    for gen in generators:
        gen_children = [c for c in gen.children if c.is_named]
        binding_node = gen_children[0] if gen_children else None
        raw_name = ctx.node_text(binding_node) if binding_node else "__for_var"
        var_name = ctx.declare_block_var(raw_name)
        next_reg = ctx.fresh_reg()
        ctx.emit(
            Opcode.CALL_FUNCTION,
            result_reg=next_reg,
            operands=["next"],
            node=gen,
        )
        ctx.emit(
            Opcode.DECL_VAR,
            operands=[var_name, next_reg],
            node=gen,
        )

    # Lower guards as BRANCH_IF
    for guard in guards:
        guard_children = [c for c in guard.children if c.is_named]
        if guard_children:
            guard_reg = ctx.lower_expr(guard_children[0])
            continue_label = ctx.fresh_label("for_guard_ok")
            ctx.emit(
                Opcode.BRANCH_IF,
                operands=[guard_reg],
                label=CodeLabel(f"{continue_label},{loop_label}"),
            )
            ctx.emit(Opcode.LABEL, label=continue_label)

    if body_node:
        ctx.lower_stmt(body_node)

    ctx.exit_block_scope()
    ctx.emit(Opcode.BRANCH, label=loop_label)
    ctx.emit(Opcode.LABEL, label=end_label)


def lower_do_while(ctx: TreeSitterEmitContext, node) -> None:
    """Lower do { body } while (condition)."""
    body_node = node.child_by_field_name(ctx.constants.while_body_field)
    cond_node = node.child_by_field_name(ctx.constants.while_condition_field)

    body_label = ctx.fresh_label("do_body")
    end_label = ctx.fresh_label("do_end")

    ctx.emit(Opcode.LABEL, label=body_label)
    if body_node:
        ctx.lower_block(body_node)

    if cond_node:
        cond_reg = ctx.lower_expr(cond_node)
        ctx.emit(
            Opcode.BRANCH_IF,
            operands=[cond_reg],
            label=CodeLabel(f"{body_label},{end_label}"),
            node=node,
        )
    else:
        ctx.emit(Opcode.BRANCH, label=body_label)

    ctx.emit(Opcode.LABEL, label=end_label)


def _extract_try_parts(ctx: TreeSitterEmitContext, node):
    """Extract body, catch clauses, and finally from a try_expression."""
    body_node = node.child_by_field_name("body")
    catch_clauses: list[dict] = []
    finally_node = None
    for child in node.children:
        if child.type == NT.CATCH_CLAUSE:
            # Scala catch clause has a case_block child (not a named "body" field)
            catch_body_node = next(
                (c for c in child.children if c.type == NT.CASE_BLOCK), None
            )
            if catch_body_node:
                # Each case_clause in the catch body is a separate handler
                cases = [
                    c for c in catch_body_node.children if c.type == NT.CASE_CLAUSE
                ]
                if cases:
                    for case in cases:
                        pattern = case.child_by_field_name("pattern")
                        case_body = case.child_by_field_name("body")
                        exc_var = None
                        exc_type = None
                        if pattern:
                            # typed_pattern: identifier : Type
                            id_node = next(
                                (
                                    c
                                    for c in pattern.children
                                    if c.type == NT.IDENTIFIER
                                ),
                                None,
                            )
                            exc_var = ctx.node_text(id_node) if id_node else None
                            type_node = next(
                                (
                                    c
                                    for c in pattern.children
                                    if c.type == NT.TYPE_IDENTIFIER
                                ),
                                None,
                            )
                            exc_type = (
                                ctx.node_text(type_node)
                                if type_node
                                else ctx.node_text(pattern)
                            )
                        catch_clauses.append(
                            {
                                "body": case_body,
                                "variable": exc_var,
                                "type": exc_type,
                            }
                        )
                else:
                    # Catch body without case clauses: lower entire body
                    catch_clauses.append(
                        {"body": catch_body_node, "variable": None, "type": None}
                    )
        elif child.type == NT.FINALLY_CLAUSE:
            finally_node = child.child_by_field_name("body") or next(
                (c for c in child.children if c.type == NT.BLOCK), None
            )
    return body_node, catch_clauses, finally_node


def lower_try_stmt(ctx: TreeSitterEmitContext, node) -> None:
    body_node, catch_clauses, finally_node = _extract_try_parts(ctx, node)
    lower_try_catch(ctx, node, body_node, catch_clauses, finally_node)
