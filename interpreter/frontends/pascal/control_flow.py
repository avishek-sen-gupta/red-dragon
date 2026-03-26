"""Pascal-specific control flow lowerers -- pure functions taking (ctx, node)."""

from __future__ import annotations

import logging
from interpreter.frontends.context import TreeSitterEmitContext

from interpreter.constants import DEFAULT_EXCEPTION_TYPE
from interpreter.ir import CodeLabel
from interpreter.frontends.common.exceptions import lower_try_catch
from interpreter.frontends.pascal.pascal_constants import KEYWORD_NOISE
from interpreter.frontends.pascal.node_types import PascalNodeType
from interpreter.operator_kind import resolve_binop
from interpreter.instructions import (
    Const,
    LoadVar,
    DeclVar,
    StoreVar,
    Binop,
    CallFunction,
    LoadIndex,
    Symbolic,
    Label_,
    Branch,
    BranchIf,
    Return_,
    Throw_,
)

logger = logging.getLogger(__name__)


def lower_pascal_root(ctx: TreeSitterEmitContext, node) -> None:
    """Lower the root node -- contains a program node."""
    for child in node.children:
        if child.is_named:
            ctx.lower_stmt(child)


def lower_pascal_program(ctx: TreeSitterEmitContext, node) -> None:
    """Lower the program node -- contains moduleName, declVars, block, etc."""
    for child in node.children:
        if child.type in KEYWORD_NOISE:
            continue
        if child.type == PascalNodeType.MODULE_NAME:
            continue
        if child.is_named:
            ctx.lower_stmt(child)


def lower_pascal_block(ctx: TreeSitterEmitContext, node) -> None:
    """Lower a block -- children between kBegin and kEnd."""
    for child in node.children:
        if child.type in KEYWORD_NOISE:
            continue
        if child.is_named:
            ctx.lower_stmt(child)


def lower_pascal_statement(ctx: TreeSitterEmitContext, node) -> None:
    """Unwrap a statement node and lower its inner content."""
    for child in node.children:
        if child.type in KEYWORD_NOISE:
            continue
        if child.is_named:
            ctx.lower_stmt(child)
            return
    # Fallback: try each named child as expression
    for child in node.children:
        if child.is_named:
            ctx.lower_expr(child)


def lower_pascal_if(ctx: TreeSitterEmitContext, node) -> None:
    """Lower if/ifElse -- contains kIf, condition, kThen, consequence, optional kElse, alternative."""
    named_children = [
        c for c in node.children if c.is_named and c.type not in KEYWORD_NOISE
    ]
    if len(named_children) < 2:
        logger.warning(
            "Pascal if with fewer than 2 named children at %s",
            ctx.source_loc(node),
        )
        return

    cond_node = named_children[0]
    body_node = named_children[1]
    alt_node = named_children[2] if len(named_children) > 2 else None

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
    ctx.lower_stmt(body_node)
    ctx.emit_inst(Branch(label=end_label))

    if alt_node:
        ctx.emit_inst(Label_(label=false_label))
        ctx.lower_stmt(alt_node)
        ctx.emit_inst(Branch(label=end_label))

    ctx.emit_inst(Label_(label=end_label))


def lower_pascal_while(ctx: TreeSitterEmitContext, node) -> None:
    """Lower while -- contains kWhile, condition, kDo, body."""
    named_children = [
        c for c in node.children if c.is_named and c.type not in KEYWORD_NOISE
    ]
    if len(named_children) < 2:
        logger.warning(
            "Pascal while with fewer than 2 named children at %s",
            ctx.source_loc(node),
        )
        return

    cond_node = named_children[0]
    body_node = named_children[1]

    loop_label = ctx.fresh_label("while_cond")
    body_label = ctx.fresh_label("while_body")
    end_label = ctx.fresh_label("while_end")

    ctx.emit_inst(Label_(label=loop_label))
    cond_reg = ctx.lower_expr(cond_node)
    ctx.emit_inst(
        BranchIf(cond_reg=cond_reg, branch_targets=(body_label, end_label)),
        node=node,
    )

    ctx.emit_inst(Label_(label=body_label))
    ctx.lower_stmt(body_node)
    ctx.emit_inst(Branch(label=loop_label))

    ctx.emit_inst(Label_(label=end_label))


def lower_pascal_for(ctx: TreeSitterEmitContext, node) -> None:
    """Lower for -- contains kFor, assignment(var := start), kTo/kDownto, end, kDo, body."""
    named_children = [
        c for c in node.children if c.is_named and c.type not in KEYWORD_NOISE
    ]

    if len(named_children) >= 3 and named_children[0].type == PascalNodeType.ASSIGNMENT:
        assignment_node = named_children[0]
        assign_children = [
            c
            for c in assignment_node.children
            if c.is_named and c.type not in KEYWORD_NOISE
        ]
        var_node = assign_children[0] if assign_children else None
        start_node = assign_children[1] if len(assign_children) > 1 else None
        end_node = named_children[1]
        body_node = named_children[2]
    elif len(named_children) >= 4:
        var_node = named_children[0]
        start_node = named_children[1]
        end_node = named_children[2]
        body_node = named_children[3]
    else:
        logger.warning(
            "Pascal for-loop: insufficient children (%d), skipping",
            len(named_children),
        )
        return

    # Determine direction: kTo or kDownto
    is_downto = any(c.type == PascalNodeType.K_DOWNTO for c in node.children)

    var_name = ctx.node_text(var_node)
    start_reg = ctx.lower_expr(start_node)
    end_reg = ctx.lower_expr(end_node)

    ctx.emit_inst(DeclVar(name=var_name, value_reg=start_reg))

    loop_label = ctx.fresh_label("for_cond")
    body_label = ctx.fresh_label("for_body")
    end_label = ctx.fresh_label("for_end")

    cmp_op = ">=" if is_downto else "<="

    ctx.emit_inst(Label_(label=loop_label))
    current_reg = ctx.fresh_reg()
    ctx.emit_inst(LoadVar(result_reg=current_reg, name=var_name))
    cond_reg = ctx.fresh_reg()
    ctx.emit_inst(
        Binop(
            result_reg=cond_reg,
            operator=resolve_binop(cmp_op),
            left=current_reg,
            right=end_reg,
        )
    )
    ctx.emit_inst(
        BranchIf(cond_reg=cond_reg, branch_targets=(body_label, end_label)),
        node=node,
    )

    ctx.emit_inst(Label_(label=body_label))
    ctx.lower_stmt(body_node)

    step_op = "-" if is_downto else "+"
    cur_reg = ctx.fresh_reg()
    ctx.emit_inst(LoadVar(result_reg=cur_reg, name=var_name))
    one_reg = ctx.fresh_reg()
    ctx.emit_inst(Const(result_reg=one_reg, value="1"))
    next_reg = ctx.fresh_reg()
    ctx.emit_inst(
        Binop(
            result_reg=next_reg,
            operator=resolve_binop(step_op),
            left=cur_reg,
            right=one_reg,
        )
    )
    ctx.emit_inst(StoreVar(name=var_name, value_reg=next_reg))
    ctx.emit_inst(Branch(label=loop_label))

    ctx.emit_inst(Label_(label=end_label))


def lower_pascal_case(ctx: TreeSitterEmitContext, node) -> None:
    """Lower case statement as if/else chain on caseCase children."""
    named_children = [
        c for c in node.children if c.is_named and c.type not in KEYWORD_NOISE
    ]
    if not named_children:
        return

    # First named child is the selector expression
    selector_node = named_children[0]
    selector_reg = ctx.lower_expr(selector_node)

    case_cases = [c for c in node.children if c.type == PascalNodeType.CASE_CASE]
    else_case = next(
        (c for c in node.children if c.type == PascalNodeType.K_ELSE), None
    )

    end_label = ctx.fresh_label("case_end")

    for case_node in case_cases:
        _lower_pascal_case_branch(ctx, case_node, selector_reg, end_label)

    # Handle else branch: lower remaining statements after kElse
    if else_case:
        logger.debug("Lowering case else branch at %s", ctx.source_loc(node))
        # Children after kElse are the else-body statements
        found_else = False
        for child in node.children:
            if child.type == PascalNodeType.K_ELSE:
                found_else = True
                continue
            if found_else and child.is_named and child.type not in KEYWORD_NOISE:
                ctx.lower_stmt(child)

    ctx.emit_inst(Label_(label=end_label))


def _lower_pascal_case_branch(
    ctx: TreeSitterEmitContext, case_node, selector_reg: str, end_label: str
) -> None:
    """Lower a single caseCase -- extract caseLabel values, BINOP == + BRANCH_IF."""
    labels = [c for c in case_node.children if c.type == PascalNodeType.CASE_LABEL]
    body_children = [
        c
        for c in case_node.children
        if c.is_named
        and c.type not in KEYWORD_NOISE
        and c.type != PascalNodeType.CASE_LABEL
    ]

    true_label = ctx.fresh_label("case_match")
    next_label = ctx.fresh_label("case_next")

    # Build OR of all label comparisons
    if labels:
        label_values = [
            c
            for lbl in labels
            for c in lbl.children
            if c.is_named and c.type not in KEYWORD_NOISE
        ]
        if label_values:
            cmp_reg = ctx.fresh_reg()
            first_val_reg = ctx.lower_expr(label_values[0])
            ctx.emit_inst(
                Binop(
                    result_reg=cmp_reg,
                    operator=resolve_binop("=="),
                    left=selector_reg,
                    right=first_val_reg,
                ),
                node=case_node,
            )
            for extra_val in label_values[1:]:
                extra_reg = ctx.lower_expr(extra_val)
                extra_cmp = ctx.fresh_reg()
                ctx.emit_inst(
                    Binop(
                        result_reg=extra_cmp,
                        operator=resolve_binop("=="),
                        left=selector_reg,
                        right=extra_reg,
                    )
                )
                or_reg = ctx.fresh_reg()
                ctx.emit_inst(
                    Binop(
                        result_reg=or_reg,
                        operator=resolve_binop("or"),
                        left=cmp_reg,
                        right=extra_cmp,
                    )
                )
                cmp_reg = or_reg

            ctx.emit_inst(
                BranchIf(cond_reg=cmp_reg, branch_targets=(true_label, next_label)),
                node=case_node,
            )

    ctx.emit_inst(Label_(label=true_label))
    for child in body_children:
        ctx.lower_stmt(child)
    ctx.emit_inst(Branch(label=end_label))
    ctx.emit_inst(Label_(label=next_label))


def lower_pascal_repeat(ctx: TreeSitterEmitContext, node) -> None:
    """Lower repeat ... until condition (execute body first, then check)."""
    named_children = [
        c for c in node.children if c.is_named and c.type not in KEYWORD_NOISE
    ]
    if len(named_children) < 2:
        logger.warning(
            "Pascal repeat with fewer than 2 named children at %s",
            ctx.source_loc(node),
        )
        return

    # Last named child is the condition, everything before is body
    cond_node = named_children[-1]
    body_nodes = named_children[:-1]

    body_label = ctx.fresh_label("repeat_body")
    end_label = ctx.fresh_label("repeat_end")

    ctx.emit_inst(Label_(label=body_label))
    for child in body_nodes:
        ctx.lower_stmt(child)

    cond_reg = ctx.lower_expr(cond_node)
    # repeat-until: loop continues while condition is FALSE
    ctx.emit_inst(
        BranchIf(cond_reg=cond_reg, branch_targets=(end_label, body_label)),
        node=node,
    )
    ctx.emit_inst(Label_(label=end_label))


def lower_pascal_try(ctx: TreeSitterEmitContext, node) -> None:
    """Lower try/except/finally using common lower_try_catch."""
    body_node, catch_clauses, finally_node = _extract_pascal_try_parts(ctx, node)
    lower_try_catch(ctx, node, body_node, catch_clauses, finally_node)


def _extract_pascal_try_parts(ctx: TreeSitterEmitContext, node):
    """Extract body, catch clauses, and finally from a Pascal try node."""
    body_node = None
    catch_clauses: list[dict] = []
    finally_node = None
    in_except = False
    in_finally = False

    for child in node.children:
        if child.type == PascalNodeType.K_EXCEPT:
            in_except = True
            in_finally = False
            continue
        if child.type == PascalNodeType.K_FINALLY:
            in_finally = True
            in_except = False
            continue
        if child.type in (
            PascalNodeType.K_TRY,
            PascalNodeType.K_END,
            PascalNodeType.SEMICOLON,
        ):
            continue

        if not in_except and not in_finally and child.type == PascalNodeType.STATEMENTS:
            body_node = child
        elif in_except and child.type == PascalNodeType.EXCEPTION_HANDLER:
            id_node = next(
                (c for c in child.children if c.type == PascalNodeType.IDENTIFIER), None
            )
            type_node = next(
                (c for c in child.children if c.type == PascalNodeType.TYPEREF), None
            )
            # The handler body is everything after kDo
            body_children = [
                c
                for c in child.children
                if c.is_named
                and c.type not in (PascalNodeType.IDENTIFIER, PascalNodeType.TYPEREF)
                and c.type not in KEYWORD_NOISE
            ]
            # Use the first non-identifier/non-typeref named child as body
            handler_body = body_children[0] if body_children else None
            catch_clauses.append(
                {
                    "body": handler_body,
                    "variable": ctx.node_text(id_node) if id_node else None,
                    "type": (
                        ctx.node_text(type_node)
                        if type_node
                        else DEFAULT_EXCEPTION_TYPE
                    ),
                }
            )
        elif in_except and child.type == PascalNodeType.STATEMENTS:
            # Bare except block without "on E: Exception do" wrapper
            catch_clauses.append(
                {
                    "body": child,
                    "variable": None,
                    "type": DEFAULT_EXCEPTION_TYPE,
                }
            )
        elif in_finally and child.type == PascalNodeType.STATEMENTS:
            finally_node = child

    return body_node, catch_clauses, finally_node


def lower_pascal_exception_handler(ctx: TreeSitterEmitContext, node) -> None:
    """Lower `on E: Exception do statement` -- extract variable, lower body."""
    from interpreter import constants

    id_node = next(
        (c for c in node.children if c.type == PascalNodeType.IDENTIFIER), None
    )
    if id_node:
        var_name = ctx.node_text(id_node)
        reg = ctx.fresh_reg()
        ctx.emit_inst(
            Symbolic(result_reg=reg, hint=f"{constants.PARAM_PREFIX}{var_name}"),
            node=id_node,
        )
        ctx.emit_inst(DeclVar(name=var_name, value_reg=f"%{ctx.reg_counter - 1}"))
    # Lower body statements
    named_children = [
        c for c in node.children if c.is_named and c.type not in KEYWORD_NOISE
    ]
    for child in named_children:
        if child.type != PascalNodeType.IDENTIFIER:
            ctx.lower_stmt(child)


def lower_pascal_raise(ctx: TreeSitterEmitContext, node) -> None:
    """Lower `raise Exception.Create('oops');` as THROW."""
    named_children = [
        c for c in node.children if c.is_named and c.type not in KEYWORD_NOISE
    ]
    if named_children:
        val_reg = ctx.lower_expr(named_children[0])
    else:
        val_reg = ctx.fresh_reg()
        ctx.emit_inst(
            Const(result_reg=val_reg, value=ctx.constants.default_return_value)
        )
    ctx.emit_inst(Throw_(value_reg=val_reg), node=node)


def lower_pascal_with(ctx: TreeSitterEmitContext, node) -> None:
    """Lower `with P do statement` -- lower object then body."""
    named_children = [
        c for c in node.children if c.is_named and c.type not in KEYWORD_NOISE
    ]
    if len(named_children) >= 2:
        ctx.lower_expr(named_children[0])
        ctx.lower_stmt(named_children[-1])
    elif named_children:
        ctx.lower_stmt(named_children[0])


def lower_pascal_inherited_stmt(ctx: TreeSitterEmitContext, node) -> None:
    """Lower `inherited Create` as statement."""
    from interpreter.frontends.pascal.expressions import lower_pascal_inherited_expr

    lower_pascal_inherited_expr(ctx, node)


def lower_pascal_foreach(ctx: TreeSitterEmitContext, node) -> None:
    """Lower for-in loop: for var in collection do body."""
    foreach_noise = KEYWORD_NOISE | frozenset({"kIn"})
    named_children = [
        c for c in node.children if c.is_named and c.type not in foreach_noise
    ]
    var_node = named_children[0]
    collection_node = named_children[1]
    body_node = named_children[2] if len(named_children) > 2 else named_children[-1]

    var_name = ctx.node_text(var_node)
    coll_reg = ctx.lower_expr(collection_node)

    idx_var = f"__foreach_idx_{var_name}"
    zero_reg = ctx.fresh_reg()
    ctx.emit_inst(Const(result_reg=zero_reg, value="0"))
    ctx.emit_inst(DeclVar(name=idx_var, value_reg=zero_reg))

    len_reg = ctx.fresh_reg()
    ctx.emit_inst(
        CallFunction(result_reg=len_reg, func_name="len", args=(coll_reg,)),
        node=node,
    )

    loop_label = ctx.fresh_label("foreach_cond")
    body_label = ctx.fresh_label("foreach_body")
    end_label = ctx.fresh_label("foreach_end")

    ctx.emit_inst(Label_(label=loop_label))
    cur_idx_reg = ctx.fresh_reg()
    ctx.emit_inst(LoadVar(result_reg=cur_idx_reg, name=idx_var))
    cond_reg = ctx.fresh_reg()
    ctx.emit_inst(
        Binop(
            result_reg=cond_reg,
            operator=resolve_binop("<"),
            left=cur_idx_reg,
            right=len_reg,
        )
    )
    ctx.emit_inst(
        BranchIf(cond_reg=cond_reg, branch_targets=(body_label, end_label)),
        node=node,
    )

    ctx.emit_inst(Label_(label=body_label))
    elem_reg = ctx.fresh_reg()
    ctx.emit_inst(
        LoadIndex(result_reg=elem_reg, arr_reg=coll_reg, index_reg=cur_idx_reg)
    )
    ctx.emit_inst(DeclVar(name=var_name, value_reg=elem_reg))
    ctx.lower_stmt(body_node)

    cur2_reg = ctx.fresh_reg()
    ctx.emit_inst(LoadVar(result_reg=cur2_reg, name=idx_var))
    one_reg = ctx.fresh_reg()
    ctx.emit_inst(Const(result_reg=one_reg, value="1"))
    next_reg = ctx.fresh_reg()
    ctx.emit_inst(
        Binop(
            result_reg=next_reg,
            operator=resolve_binop("+"),
            left=cur2_reg,
            right=one_reg,
        )
    )
    ctx.emit_inst(StoreVar(name=idx_var, value_reg=next_reg))
    ctx.emit_inst(Branch(label=loop_label))

    ctx.emit_inst(Label_(label=end_label))


def lower_pascal_goto(ctx: TreeSitterEmitContext, node) -> None:
    """Lower goto label -- emit BRANCH to the label."""
    id_node = next(
        (c for c in node.children if c.type == PascalNodeType.IDENTIFIER), None
    )
    label_name = ctx.node_text(id_node) if id_node else "unknown"
    ctx.emit_inst(Branch(label=CodeLabel(label_name)), node=node)


def lower_pascal_label(ctx: TreeSitterEmitContext, node) -> None:
    """Lower label: statement -- emit LABEL."""
    id_node = next(
        (c for c in node.children if c.type == PascalNodeType.IDENTIFIER), None
    )
    label_name = ctx.node_text(id_node) if id_node else "unknown"
    ctx.emit_inst(Label_(label=CodeLabel(label_name)))


def lower_pascal_noop(ctx: TreeSitterEmitContext, node) -> None:
    """No-op handler -- skips nodes that produce no IR."""
    logger.debug("Skipping %s at %s (no-op)", node.type, ctx.source_loc(node))
