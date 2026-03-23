"""Python-specific control flow lowerers -- pure functions taking (ctx, node)."""

from __future__ import annotations

from interpreter.frontends.context import TreeSitterEmitContext

from interpreter.ir import Opcode, CodeLabel
from interpreter.frontends.common.exceptions import (
    lower_raise_or_throw,
    lower_try_catch,
)
from interpreter.frontends.python.expressions import (
    _emit_for_increment,
    lower_store_target,
)
from interpreter.frontends.python.node_types import PythonNodeType

_WILDCARD_PATTERN = "_"

# ── if/elif/else ──────────────────────────────────────────────


def lower_python_if(ctx: TreeSitterEmitContext, node) -> None:
    """Lower Python if/elif/else chains by iterating all sibling clauses.

    Python's tree-sitter grammar places elif_clause and else_clause as
    flat siblings under if_statement.  The common lower_if only sees the
    first alternative via child_by_field_name, silently dropping subsequent
    elif/else branches.  This lowerer collects them all.
    """
    cond_node = node.child_by_field_name(ctx.constants.if_condition_field)
    body_node = node.child_by_field_name(ctx.constants.if_consequence_field)

    elif_clauses = [c for c in node.children if c.type == PythonNodeType.ELIF_CLAUSE]
    else_clause = next(
        (c for c in node.children if c.type == PythonNodeType.ELSE_CLAUSE), None
    )
    has_alternative = len(elif_clauses) > 0 or else_clause is not None

    cond_reg = ctx.lower_expr(cond_node)
    true_label = ctx.fresh_label("if_true")
    end_label = ctx.fresh_label("if_end")
    false_label = ctx.fresh_label("if_false") if has_alternative else end_label

    ctx.emit(
        Opcode.BRANCH_IF,
        operands=[cond_reg],
        label=CodeLabel(f"{true_label},{false_label}"),
        node=node,
    )

    ctx.emit(Opcode.LABEL, label=true_label)
    ctx.lower_block(body_node)
    ctx.emit(Opcode.BRANCH, label=end_label)

    if has_alternative:
        ctx.emit(Opcode.LABEL, label=false_label)
        _lower_python_elif_chain(ctx, elif_clauses, else_clause, end_label)

    ctx.emit(Opcode.LABEL, label=end_label)


def _lower_python_elif_chain(
    ctx: TreeSitterEmitContext,
    elif_clauses: list,
    else_clause,
    end_label: str,
) -> None:
    """Lower a chain of elif_clause nodes followed by optional else_clause."""
    remaining_elifs = elif_clauses[1:] if len(elif_clauses) > 1 else []
    has_more = len(remaining_elifs) > 0 or else_clause is not None

    if not elif_clauses:
        # Only else remains
        if else_clause:
            body = else_clause.child_by_field_name("body")
            if body:
                ctx.lower_block(body)
        ctx.emit(Opcode.BRANCH, label=end_label)
        return

    current = elif_clauses[0]
    cond_node = current.child_by_field_name(ctx.constants.if_condition_field)
    body_node = current.child_by_field_name(ctx.constants.if_consequence_field)

    cond_reg = ctx.lower_expr(cond_node)
    true_label = ctx.fresh_label("elif_true")
    false_label = ctx.fresh_label("elif_false") if has_more else end_label

    ctx.emit(
        Opcode.BRANCH_IF,
        operands=[cond_reg],
        label=CodeLabel(f"{true_label},{false_label}"),
        node=current,
    )

    ctx.emit(Opcode.LABEL, label=true_label)
    ctx.lower_block(body_node)
    ctx.emit(Opcode.BRANCH, label=end_label)

    if has_more:
        ctx.emit(Opcode.LABEL, label=false_label)
        _lower_python_elif_chain(ctx, remaining_elifs, else_clause, end_label)


# ── for loop ──────────────────────────────────────────────────


def lower_for(ctx: TreeSitterEmitContext, node) -> None:
    left = node.child_by_field_name(ctx.constants.assign_left_field)
    right = node.child_by_field_name(ctx.constants.assign_right_field)
    body_node = node.child_by_field_name(ctx.constants.for_body_field)

    iter_reg = ctx.lower_expr(right)
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
        label=CodeLabel(f"{body_label},{end_label}"),
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
        if child.type == PythonNodeType.EXCEPT_CLAUSE:
            exc_var = None
            exc_type = None
            # except ExcType as var: ...
            for sub in child.children:
                if sub.type == PythonNodeType.AS_PATTERN:
                    # as_pattern children: type, "as", name
                    parts = [c for c in sub.children if c.is_named]
                    if parts:
                        exc_type = ctx.node_text(parts[0])
                    if len(parts) >= 2:
                        exc_var = ctx.node_text(parts[-1])
                elif sub.type == PythonNodeType.IDENTIFIER and exc_type is None:
                    exc_type = ctx.node_text(sub)
            exc_body = next(
                (c for c in child.children if c.type == PythonNodeType.BLOCK), None
            )
            catch_clauses.append(
                {"body": exc_body, "variable": exc_var, "type": exc_type}
            )
        elif child.type == PythonNodeType.FINALLY_CLAUSE:
            finally_node = next(
                (c for c in child.children if c.type == PythonNodeType.BLOCK), None
            )
        elif child.type == PythonNodeType.ELSE_CLAUSE:
            else_node = child.child_by_field_name("body") or next(
                (c for c in child.children if c.type == PythonNodeType.BLOCK), None
            )
    lower_try_catch(ctx, node, body_node, catch_clauses, finally_node, else_node)


# ── with statement ────────────────────────────────────────────


def lower_with(ctx: TreeSitterEmitContext, node) -> None:
    """Lower `with ctx as var: body` into __enter__/__exit__ calls."""
    with_clause = next(
        (c for c in node.children if c.type == PythonNodeType.WITH_CLAUSE), None
    )
    body_node = node.child_by_field_name("body")

    with_items = (
        [c for c in with_clause.children if c.type == PythonNodeType.WITH_ITEM]
        if with_clause
        else []
    )

    # Collect enter results for nested exit calls
    enter_info: list[tuple[str, str | None]] = []  # (ctx_reg, var_name or None)

    for item in with_items:
        as_pat = next(
            (c for c in item.children if c.type == PythonNodeType.AS_PATTERN), None
        )
        if as_pat:
            named = [c for c in as_pat.children if c.is_named]
            ctx_expr = named[0]
            target_node = named[-1] if len(named) >= 2 else None
            # as_pattern_target wraps the identifier
            var_name = (
                ctx.node_text(
                    next(
                        (
                            c
                            for c in target_node.children
                            if c.type == PythonNodeType.IDENTIFIER
                        ),
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
            ctx.emit(Opcode.DECL_VAR, operands=[var_name, enter_reg])
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
    decorators = [c for c in node.children if c.type == PythonNodeType.DECORATOR]
    definition = next(
        (
            c
            for c in node.children
            if c.type
            in (PythonNodeType.FUNCTION_DEFINITION, PythonNodeType.CLASS_DEFINITION)
        ),
        None,
    )

    # Lower the inner definition normally
    ctx.lower_stmt(definition)

    # Extract the defined name
    name_node = definition.child_by_field_name(ctx.constants.func_name_field)
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
        if child.type == PythonNodeType.EXPRESSION_LIST:
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
    """Lower import module as CALL_FUNCTION('import', module) + DECL_VAR."""
    name_node = node.child_by_field_name(ctx.constants.func_name_field)
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
        Opcode.DECL_VAR,
        operands=[store_name, import_reg],
        node=node,
    )


# ── import from statement ─────────────────────────────────────


def lower_import_from(ctx: TreeSitterEmitContext, node) -> None:
    """Lower from X import Y, Z as CALL_FUNCTION('import', ...) + DECL_VAR per name."""
    module_node = node.child_by_field_name("module_name")
    module_name = ctx.node_text(module_node) if module_node else "unknown"

    # Collect all imported names (dotted_name children after 'import' keyword)
    imported_names = [
        c
        for c in node.children
        if c.is_named and c.type == PythonNodeType.DOTTED_NAME and c != module_node
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
            Opcode.DECL_VAR,
            operands=[imported_name, import_reg],
            node=node,
        )


# ── match statement ───────────────────────────────────────────


def lower_match(ctx: TreeSitterEmitContext, node) -> None:
    """Lower match/case as pattern-driven linear chain."""
    from interpreter.frontends.common.patterns import (
        MatchCase,
        NoBody,
        NoGuard,
        WildcardPattern,
        compile_match,
    )
    from interpreter.frontends.python.patterns import parse_pattern

    subject_node = node.child_by_field_name("subject")
    body_node = node.child_by_field_name("body")
    subject_reg = ctx.lower_expr(subject_node)

    case_clauses = (
        [c for c in body_node.children if c.type == PythonNodeType.CASE_CLAUSE]
        if body_node
        else []
    )

    cases: list[MatchCase] = []
    for case_node in case_clauses:
        pattern_node = next(
            (c for c in case_node.children if c.type == PythonNodeType.CASE_PATTERN),
            None,
        )
        case_body = case_node.child_by_field_name(
            ctx.constants.if_consequence_field
        ) or next(
            (c for c in case_node.children if c.type == PythonNodeType.BLOCK), None
        )

        pattern = (
            parse_pattern(ctx, pattern_node) if pattern_node else WildcardPattern()
        )

        # Extract guard: Python uses "if_clause" inside case_clause
        if_clauses = [c for c in case_node.children if c.type == "if_clause"]
        guard_node: object = (
            next(c for c in if_clauses[0].children if c.is_named)
            if if_clauses
            else NoGuard()
        )

        cases.append(
            MatchCase(
                pattern=pattern,
                guard_node=guard_node,
                body_node=case_body if case_body else NoBody(),
            )
        )

    compile_match(ctx, subject_reg, cases)
