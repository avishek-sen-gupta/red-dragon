"""Python-specific control flow lowerers -- pure functions taking (ctx, node)."""

from __future__ import annotations

from typing import TYPE_CHECKING

from interpreter.ir import Opcode
from interpreter.frontends.common.exceptions import (
    lower_raise_or_throw,
    lower_try_catch,
)
from interpreter.frontends.python.expressions import (
    _emit_for_increment,
    lower_store_target,
)

if TYPE_CHECKING:
    from interpreter.frontends.context import TreeSitterEmitContext


_WILDCARD_PATTERN = "_"


# ── for loop ──────────────────────────────────────────────────


def lower_for(ctx: TreeSitterEmitContext, node) -> None:
    left = node.child_by_field_name("left")
    right = node.child_by_field_name("right")
    body_node = node.child_by_field_name("body")

    iter_reg = ctx.lower_expr(right)
    idx_reg = ctx.fresh_reg()
    ctx.emit(Opcode.CONST, result_reg=idx_reg, operands=["0"])
    len_reg = ctx.fresh_reg()
    ctx.emit(Opcode.CALL_FUNCTION, result_reg=len_reg, operands=["len", iter_reg])

    loop_label = ctx.fresh_label("for_cond")
    body_label = ctx.fresh_label("for_body")
    end_label = ctx.fresh_label("for_end")

    ctx.emit(Opcode.LABEL, label=loop_label)
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
    lower_store_target(ctx, left, elem_reg, node)

    update_label = ctx.fresh_label("for_update")
    ctx.push_loop(update_label, end_label)
    ctx.lower_block(body_node)
    ctx.pop_loop()

    ctx.emit(Opcode.LABEL, label=update_label)
    _emit_for_increment(ctx, idx_reg, loop_label)

    ctx.emit(Opcode.LABEL, label=end_label)


# ── raise ─────────────────────────────────────────────────────


def lower_raise(ctx: TreeSitterEmitContext, node) -> None:
    lower_raise_or_throw(ctx, node, keyword="raise")


# ── try/except/else/finally ──────────────────────────────────


def lower_try(ctx: TreeSitterEmitContext, node) -> None:
    body_node = node.child_by_field_name("body")
    catch_clauses: list[dict] = []
    finally_node = None
    else_node = None
    for child in node.children:
        if child.type == "except_clause":
            exc_var = None
            exc_type = None
            # except ExcType as var: ...
            for sub in child.children:
                if sub.type == "as_pattern":
                    # as_pattern children: type, "as", name
                    parts = [c for c in sub.children if c.is_named]
                    if parts:
                        exc_type = ctx.node_text(parts[0])
                    if len(parts) >= 2:
                        exc_var = ctx.node_text(parts[-1])
                elif sub.type == "identifier" and exc_type is None:
                    exc_type = ctx.node_text(sub)
            exc_body = next((c for c in child.children if c.type == "block"), None)
            catch_clauses.append(
                {"body": exc_body, "variable": exc_var, "type": exc_type}
            )
        elif child.type == "finally_clause":
            finally_node = next((c for c in child.children if c.type == "block"), None)
        elif child.type == "else_clause":
            else_node = child.child_by_field_name("body") or next(
                (c for c in child.children if c.type == "block"), None
            )
    lower_try_catch(ctx, node, body_node, catch_clauses, finally_node, else_node)


# ── with statement ────────────────────────────────────────────


def lower_with(ctx: TreeSitterEmitContext, node) -> None:
    """Lower `with ctx as var: body` into __enter__/__exit__ calls."""
    with_clause = next((c for c in node.children if c.type == "with_clause"), None)
    body_node = node.child_by_field_name("body")

    with_items = (
        [c for c in with_clause.children if c.type == "with_item"]
        if with_clause
        else []
    )

    # Collect enter results for nested exit calls
    enter_info: list[tuple[str, str | None]] = []  # (ctx_reg, var_name or None)

    for item in with_items:
        as_pat = next((c for c in item.children if c.type == "as_pattern"), None)
        if as_pat:
            named = [c for c in as_pat.children if c.is_named]
            ctx_expr = named[0]
            target_node = named[-1] if len(named) >= 2 else None
            # as_pattern_target wraps the identifier
            var_name = (
                ctx.node_text(
                    next(
                        (c for c in target_node.children if c.type == "identifier"),
                        target_node,
                    )
                )
                if target_node
                else None
            )
        else:
            # No 'as' -- the with_item's first named child is the context expr
            ctx_expr = next((c for c in item.children if c.is_named), None)
            var_name = None

        ctx_reg = ctx.lower_expr(ctx_expr)
        enter_reg = ctx.fresh_reg()
        ctx.emit(
            Opcode.CALL_METHOD,
            result_reg=enter_reg,
            operands=[ctx_reg, "__enter__"],
            node=item,
        )
        if var_name:
            ctx.emit(Opcode.STORE_VAR, operands=[var_name, enter_reg])
        enter_info.append((ctx_reg, var_name))

    ctx.lower_block(body_node)

    # Exit in reverse order (LIFO)
    for ctx_reg, _ in reversed(enter_info):
        exit_reg = ctx.fresh_reg()
        ctx.emit(
            Opcode.CALL_METHOD,
            result_reg=exit_reg,
            operands=[ctx_reg, "__exit__"],
            node=node,
        )


# ── decorated definition ─────────────────────────────────────


def lower_decorated_def(ctx: TreeSitterEmitContext, node) -> None:
    """Lower @dec def/class into define, then wrap with decorator calls."""
    decorators = [c for c in node.children if c.type == "decorator"]
    definition = next(
        (
            c
            for c in node.children
            if c.type in ("function_definition", "class_definition")
        ),
        None,
    )

    # Lower the inner definition normally
    ctx.lower_stmt(definition)

    # Extract the defined name
    name_node = definition.child_by_field_name("name")
    func_name = ctx.node_text(name_node)

    # Apply decorators bottom-up (last decorator applied first)
    for dec in reversed(decorators):
        # Decorator expression is the first named child (skip '@')
        dec_expr = next((c for c in dec.children if c.is_named), None)
        if not dec_expr:
            continue

        func_reg = ctx.fresh_reg()
        ctx.emit(Opcode.LOAD_VAR, result_reg=func_reg, operands=[func_name])
        dec_reg = ctx.lower_expr(dec_expr)
        result_reg = ctx.fresh_reg()
        ctx.emit(
            Opcode.CALL_FUNCTION,
            result_reg=result_reg,
            operands=[dec_reg, func_reg],
            node=dec,
        )
        ctx.emit(Opcode.STORE_VAR, operands=[func_name, result_reg])


# ── assert statement ──────────────────────────────────────────


def lower_assert(ctx: TreeSitterEmitContext, node) -> None:
    """Lower assert cond [, msg] as CALL_FUNCTION('assert', cond [, msg])."""
    named_children = [c for c in node.children if c.is_named]
    arg_regs = [ctx.lower_expr(c) for c in named_children]
    ctx.emit(
        Opcode.CALL_FUNCTION,
        result_reg=ctx.fresh_reg(),
        operands=["assert"] + arg_regs,
        node=node,
    )


# ── delete statement ──────────────────────────────────────────


def lower_delete(ctx: TreeSitterEmitContext, node) -> None:
    """Lower del x, y as CALL_FUNCTION('del', target) for each target."""
    for child in node.children:
        if not child.is_named:
            continue
        # expression_list wraps multiple targets
        if child.type == "expression_list":
            for target in child.children:
                if target.is_named:
                    target_reg = ctx.lower_expr(target)
                    ctx.emit(
                        Opcode.CALL_FUNCTION,
                        result_reg=ctx.fresh_reg(),
                        operands=["del", target_reg],
                        node=node,
                    )
        else:
            target_reg = ctx.lower_expr(child)
            ctx.emit(
                Opcode.CALL_FUNCTION,
                result_reg=ctx.fresh_reg(),
                operands=["del", target_reg],
                node=node,
            )


# ── import statement ──────────────────────────────────────────


def lower_import(ctx: TreeSitterEmitContext, node) -> None:
    """Lower import module as CALL_FUNCTION('import', module) + STORE_VAR."""
    name_node = node.child_by_field_name("name")
    module_name = ctx.node_text(name_node) if name_node else "unknown"
    import_reg = ctx.fresh_reg()
    ctx.emit(
        Opcode.CALL_FUNCTION,
        result_reg=import_reg,
        operands=["import", module_name],
        node=node,
    )
    # Store using the top-level module name (e.g., 'os' for 'os.path')
    store_name = module_name.split(".")[0]
    ctx.emit(
        Opcode.STORE_VAR,
        operands=[store_name, import_reg],
        node=node,
    )


# ── import from statement ─────────────────────────────────────


def lower_import_from(ctx: TreeSitterEmitContext, node) -> None:
    """Lower from X import Y, Z as CALL_FUNCTION('import', ...) + STORE_VAR per name."""
    module_node = node.child_by_field_name("module_name")
    module_name = ctx.node_text(module_node) if module_node else "unknown"

    # Collect all imported names (dotted_name children after 'import' keyword)
    imported_names = [
        c
        for c in node.children
        if c.is_named and c.type == "dotted_name" and c != module_node
    ]

    for name_node in imported_names:
        imported_name = ctx.node_text(name_node)
        import_reg = ctx.fresh_reg()
        ctx.emit(
            Opcode.CALL_FUNCTION,
            result_reg=import_reg,
            operands=["import", f"from {module_name} import {imported_name}"],
            node=node,
        )
        ctx.emit(
            Opcode.STORE_VAR,
            operands=[imported_name, import_reg],
            node=node,
        )


# ── match statement ───────────────────────────────────────────


def lower_match(ctx: TreeSitterEmitContext, node) -> None:
    """Lower match/case as if/elif/else chain."""
    subject_node = node.child_by_field_name("subject")
    body_node = node.child_by_field_name("body")

    subject_reg = ctx.lower_expr(subject_node)

    case_clauses = (
        [c for c in body_node.children if c.type == "case_clause"] if body_node else []
    )

    end_label = ctx.fresh_label("match_end")

    for case_node in case_clauses:
        pattern_node = next(
            (c for c in case_node.children if c.type == "case_pattern"), None
        )
        case_body = case_node.child_by_field_name("consequence") or next(
            (c for c in case_node.children if c.type == "block"), None
        )

        # Extract the inner pattern value from case_pattern
        inner_pattern = (
            next((c for c in pattern_node.children if c.is_named), None)
            if pattern_node
            else None
        )

        is_wildcard = (
            inner_pattern is not None
            and ctx.node_text(inner_pattern) == _WILDCARD_PATTERN
        )

        if is_wildcard:
            # Default case: unconditionally lower the body
            if case_body:
                ctx.lower_block(case_body)
            ctx.emit(Opcode.BRANCH, label=end_label)
        else:
            pattern_reg = (
                ctx.lower_expr(inner_pattern) if inner_pattern else subject_reg
            )
            cmp_reg = ctx.fresh_reg()
            ctx.emit(
                Opcode.BINOP,
                result_reg=cmp_reg,
                operands=["==", subject_reg, pattern_reg],
                node=case_node,
            )
            case_true_label = ctx.fresh_label("case_true")
            case_next_label = ctx.fresh_label("case_next")
            ctx.emit(
                Opcode.BRANCH_IF,
                operands=[cmp_reg],
                label=f"{case_true_label},{case_next_label}",
            )
            ctx.emit(Opcode.LABEL, label=case_true_label)
            if case_body:
                ctx.lower_block(case_body)
            ctx.emit(Opcode.BRANCH, label=end_label)
            ctx.emit(Opcode.LABEL, label=case_next_label)

    ctx.emit(Opcode.LABEL, label=end_label)
