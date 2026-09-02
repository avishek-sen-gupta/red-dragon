"""SEARCH statement lowering."""

from __future__ import annotations

import logging

from cobol_asg.cobol_statements import SearchStatement
from interpreter.cobol.condition_lowering import _lower_condition_str
from interpreter.cobol.emit_context import EmitContext
from interpreter.cobol.sectioned_layout import MaterialisedSectionedLayout
from interpreter.instructions import (
    Binop,
    Branch,
    BranchIf,
    Label_,
    LoadVar,
    StoreVar,
)
from interpreter.operator_kind import resolve_binop
from interpreter.register import Register
from interpreter.var_name import VarName

logger = logging.getLogger(__name__)

# Only a runaway guard, never the intended terminating condition — reached only
# on a path that already logs loudly that the bound is not the table's own
# length. It counts ITERATIONS PERFORMED rather than comparing the index value,
# so it cannot express "past the last occurrence"; that is exactly why it is
# confined to the case where the table has no known occurrence count. Sized to
# be unreachable by any real table (corpus max OCCURS is 357; only 45 clauses
# exceed 256) while staying cheap on the diagnostic path: 4096 is more than an
# order of magnitude above the largest real table.
_RUNAWAY_GUARD = 4096


def _table_occurrence_count(
    table: str, materialised: MaterialisedSectionedLayout
) -> int | None:
    """Return the OCCURS count for the SEARCHed table.

    Returns ``None`` when ``table`` resolves in the layout but has no OCCURS
    clause (it names a scalar, not a table). Raises ``KeyError`` when the name
    does not resolve in the layout at all — callers must distinguish the two:
    "not found" and "not a table" are different diagnoses. Modelled on how
    EmitContext.resolve_field_ref reaches the layout: MaterialisedSectionedLayout
    .resolve() does the case-insensitive lookup (see data_layout.py's _ci_get).
    """
    fl, _region_reg = materialised.resolve(table)
    return fl.occurs_count or None


def _implicit_index_for(
    table: str, materialised: MaterialisedSectionedLayout
) -> str | None:
    """Return the index a Format 1 SEARCH over ``table`` implicitly advances.

    Index items live in their own region (build_index_layout), which is also
    where the index -> owning table map lives. first_index_for() matches both
    names case-insensitively and preserves declaration order, so the table's
    first INDEXED BY name wins — which is the one the standard says a SEARCH
    without VARYING uses.
    """
    index_layout, _region_reg = materialised.indexes
    return index_layout.first_index_for(table)


def lower_search(
    ctx: EmitContext,
    stmt: SearchStatement,
    materialised: MaterialisedSectionedLayout,
) -> None:
    """SEARCH table VARYING index WHEN cond ... AT END ..."""
    loop_label = ctx.fresh_label("search_loop")
    end_label = ctx.fresh_label("search_end")
    at_end_label = ctx.fresh_label("search_at_end")
    increment_label = ctx.fresh_label("search_incr")

    # Format 1 SEARCH names only the table and advances its FIRST INDEXED BY
    # index. That form is the common one; the explicit VARYING operand is not.
    # Until index items were allocated there was nothing to advance, so the loop
    # re-tested occurrence 1 until the bound.
    implicit_name = _implicit_index_for(stmt.table, materialised)
    advance_name = stmt.varying or implicit_name
    if not (advance_name and ctx.has_field(advance_name, materialised)):
        logger.warning(
            "SEARCH over %r has no index to advance — the loop cannot progress "
            "(VARYING operand: %s; table's implicit INDEXED BY index: %s)",
            stmt.table,
            repr(stmt.varying) if stmt.varying else "none given",
            repr(implicit_name) if implicit_name else "none declared",
        )
        advance_name = None

    # Real SEARCH terminates when the INDEX VALUE passes the table's occurrence
    # count, and only then runs AT END. The old hard-coded 256 was wrong in both
    # directions: a shorter table was subscripted past its end into adjacent
    # storage (a WHEN could match whatever followed it), and a longer one had its
    # occurrences beyond 256 silently unreachable with AT END reporting
    # not-found. The corpus has 45 OCCURS clauses above 256.
    #
    # Counting iterations instead reintroduces the overrun for any SEARCH entered
    # with the index already past 1 — n iterations from occurrence k reads through
    # occurrence n + k - 1 — so the comparison must be against the advancing
    # operand itself. The iteration counter survives only as the runaway guard for
    # a table whose occurrence count is unknown, and to terminate the degraded
    # loop that has no index to advance at all.
    try:
        occurs = _table_occurrence_count(stmt.table, materialised)
    except KeyError:
        occurs = None
        logger.warning(
            "SEARCH table %r not found in layout — falling back to the runaway "
            "guard; the loop bound is not the table's own length",
            stmt.table,
        )
    else:
        if occurs is None:
            logger.warning(
                "SEARCH table %r is not a table (no OCCURS clause) — falling "
                "back to the runaway guard; the loop bound is not the table's "
                "own length",
                stmt.table,
            )
    bound_limit = occurs if occurs is not None else _RUNAWAY_GUARD
    bound_index_name = advance_name if occurs is not None else None

    if bound_index_name is None:
        counter_var = ctx.fresh_name("__search_ctr")
        zero_reg = ctx.const_to_reg(0)
        ctx.emit_inst(
            StoreVar(name=VarName(counter_var), value_reg=Register(str(zero_reg)))
        )

    max_reg = ctx.const_to_reg(bound_limit)

    ctx.emit_inst(Label_(label=loop_label))

    if bound_index_name is not None:
        bound_ref, bound_rr = ctx.resolve_field_ref(bound_index_name, materialised)
        current_reg = ctx.emit_decode_field(
            bound_rr, bound_ref.fl, bound_ref.offset_reg
        )
        bound_operator = ">"
    else:
        current_reg = ctx.fresh_reg()
        ctx.emit_inst(LoadVar(result_reg=current_reg, name=VarName(counter_var)))
        bound_operator = ">="
    bound_cond = ctx.fresh_reg()
    ctx.emit_inst(
        Binop(
            result_reg=bound_cond,
            operator=resolve_binop(bound_operator),
            left=Register(str(current_reg)),
            right=Register(str(max_reg)),
        )
    )
    body_label = ctx.fresh_label("search_body")
    ctx.emit_inst(
        BranchIf(
            cond_reg=Register(str(bound_cond)),
            branch_targets=(at_end_label, body_label),
        )
    )

    ctx.emit_inst(Label_(label=body_label))
    for when in stmt.whens:
        if not when.condition:
            continue
        if isinstance(when.condition, dict):
            cond_reg = ctx.lower_condition(when.condition, materialised)
        else:
            cond_reg = _lower_condition_str(
                ctx, when.condition, materialised, ctx._condition_index
            )
        when_true = ctx.fresh_label("search_when_true")
        when_next = ctx.fresh_label("search_when_next")
        ctx.emit_inst(
            BranchIf(
                cond_reg=Register(str(cond_reg)),
                branch_targets=(when_true, when_next),
            )
        )
        ctx.emit_inst(Label_(label=when_true))
        for child in when.children:
            ctx.lower_statement(child, materialised)
        ctx.emit_inst(Branch(label=end_label))
        ctx.emit_inst(Label_(label=when_next))

    ctx.emit_inst(Branch(label=increment_label))
    ctx.emit_inst(Label_(label=increment_label))

    if advance_name is not None:
        advance_ref, advance_rr = ctx.resolve_field_ref(advance_name, materialised)
        decoded_reg = ctx.emit_decode_field(
            advance_rr, advance_ref.fl, advance_ref.offset_reg
        )
        one_reg = ctx.const_to_reg(1)
        inc_reg = ctx.fresh_reg()
        ctx.emit_inst(
            Binop(
                result_reg=inc_reg,
                operator=resolve_binop("+"),
                left=Register(str(decoded_reg)),
                right=Register(str(one_reg)),
            )
        )
        str_reg = ctx.emit_to_string(inc_reg)
        ctx.emit_encode_and_write(
            advance_rr, advance_ref.fl, str_reg, advance_ref.offset_reg
        )

    if bound_index_name is None:
        ctr_reg2 = ctx.fresh_reg()
        ctx.emit_inst(LoadVar(result_reg=ctr_reg2, name=VarName(counter_var)))
        one_ctr = ctx.const_to_reg(1)
        inc_ctr = ctx.fresh_reg()
        ctx.emit_inst(
            Binop(
                result_reg=inc_ctr,
                operator=resolve_binop("+"),
                left=ctr_reg2,
                right=Register(str(one_ctr)),
            )
        )
        ctx.emit_inst(StoreVar(name=VarName(counter_var), value_reg=inc_ctr))
    ctx.emit_inst(Branch(label=loop_label))

    ctx.emit_inst(Label_(label=at_end_label))
    for child in stmt.at_end:
        ctx.lower_statement(child, materialised)

    ctx.emit_inst(Label_(label=end_label))
