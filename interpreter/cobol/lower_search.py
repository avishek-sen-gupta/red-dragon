"""SEARCH statement lowering."""

from __future__ import annotations

import logging

from cobol_asg.cobol_statements import SearchStatement
from cobol_asg.ref_mod import RefModOperand
from interpreter.cobol.condition_lowering import _lower_condition_str
from interpreter.cobol.emit_context import EmitContext
from interpreter.cobol.field_resolution import ResolvedFieldRef
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

_NO_ITEM = RefModOperand(name="")


def _table_occurrence_count(
    table: RefModOperand, materialised: MaterialisedSectionedLayout
) -> int | None:
    """Return the OCCURS count for the SEARCHed table.

    Returns ``None`` when ``table`` resolves in the layout but has no OCCURS
    clause (it names a scalar, not a table). Raises ``KeyError`` when the name
    does not resolve in the layout at all — callers must distinguish the two:
    "not found" and "not a table" are different diagnoses. Modelled on how
    EmitContext.resolve_field_ref reaches the layout: MaterialisedSectionedLayout
    .resolve() does the case-insensitive lookup (see data_layout.py's _ci_get).
    """
    fl, _region_reg = materialised.resolve(table.name, table.qualifiers)
    return fl.occurs_count or None


def _search_index(
    stmt: SearchStatement, materialised: MaterialisedSectionedLayout
) -> RefModOperand:
    """Return the index a SEARCH over its table advances and bounds, or an
    unnamed operand.

    The VARYING operand when it is one of the table's own INDEXED BY names,
    otherwise the table's first INDEXED BY name (ANSI X3.23-1985 VI-6.21.4).
    Index items live in their own region (build_index_layout), which is also
    where the index -> owning table map lives. A table with no INDEXED BY falls
    back to the VARYING operand itself, the only item there is to advance.
    """
    index_layout, _region_reg = materialised.indexes
    if stmt.varying.name and index_layout.is_index_of(stmt.varying.name, stmt.table):
        return stmt.varying
    first_index = index_layout.first_index_for(stmt.table)
    return RefModOperand(name=first_index) if first_index else stmt.varying


def _companion_of(stmt: SearchStatement, search_index: RefModOperand) -> RefModOperand:
    """The VARYING operand when it is not the search index itself: another
    table's index or a data item, incremented in step with the search index."""
    if not search_index.name or stmt.varying.name.upper() == search_index.name.upper():
        return _NO_ITEM
    return stmt.varying


def _store_number(
    ctx: EmitContext,
    stmt: SearchStatement,
    item: RefModOperand,
    value_reg: Register,
    materialised: MaterialisedSectionedLayout,
) -> None:
    ref, region_reg = _resolve(ctx, stmt, item, materialised)
    ctx.emit_encode_and_write(
        region_reg,
        ref.fl,
        ctx.emit_to_string(value_reg, span=stmt.span),
        ref.offset_reg,
        extent=ref.extent,
        span=stmt.span,
    )


def _resolve(
    ctx: EmitContext,
    stmt: SearchStatement,
    item: RefModOperand,
    materialised: MaterialisedSectionedLayout,
) -> tuple[ResolvedFieldRef, Register]:
    return ctx.resolve_field_ref(
        item.name, materialised, item.qualifiers, item.subscripts, span=stmt.span
    )


def _decode(
    ctx: EmitContext,
    stmt: SearchStatement,
    item: RefModOperand,
    materialised: MaterialisedSectionedLayout,
) -> Register:
    ref, region_reg = _resolve(ctx, stmt, item, materialised)
    return ctx.emit_decode_field(
        region_reg, ref.fl, ref.offset_reg, extent=ref.extent, span=stmt.span
    )


def _advance(
    ctx: EmitContext,
    stmt: SearchStatement,
    item: RefModOperand,
    materialised: MaterialisedSectionedLayout,
) -> None:
    incremented = ctx.fresh_reg()
    ctx.emit_inst(
        Binop(
            result_reg=incremented,
            operator=resolve_binop("+"),
            left=_decode(ctx, stmt, item, materialised),
            right=ctx.const_to_reg(1, span=stmt.span),
        ),
        span=stmt.span,
    )
    _store_number(ctx, stmt, item, incremented, materialised)


def _occurrence_bound(
    ctx: EmitContext,
    stmt: SearchStatement,
    occurs: int,
    materialised: MaterialisedSectionedLayout,
) -> Register:
    """The highest occurrence the search may reach: the OCCURS DEPENDING ON
    object's current value for a variable table, else the OCCURS count."""
    depending_on = materialised.resolve(stmt.table.name, stmt.table.qualifiers)[
        0
    ].occurs_depending_on
    if depending_on.name and ctx.has_field(depending_on.name, materialised):
        return _decode(ctx, stmt, depending_on, materialised)
    return ctx.const_to_reg(occurs, span=stmt.span)


def lower_search(
    ctx: EmitContext,
    stmt: SearchStatement,
    materialised: MaterialisedSectionedLayout,
) -> None:
    """SEARCH table VARYING index WHEN cond ... AT END ..."""
    span = stmt.span
    loop_label = ctx.fresh_label("search_loop")
    end_label = ctx.fresh_label("search_end")
    at_end_label = ctx.fresh_label("search_at_end")
    increment_label = ctx.fresh_label("search_incr")

    candidate = _search_index(stmt, materialised)
    advance = (
        candidate
        if candidate.name and ctx.has_field(candidate.name, materialised)
        else _NO_ITEM
    )
    if not advance.name:
        logger.warning(
            "SEARCH over %r has no index to advance — the loop cannot progress "
            "(VARYING operand: %s)",
            stmt.table.name,
            repr(stmt.varying.name) if stmt.varying.name else "none given",
        )
    companion = _companion_of(stmt, advance)

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
            stmt.table.name,
        )
    else:
        if occurs is None:
            logger.warning(
                "SEARCH table %r is not a table (no OCCURS clause) — falling "
                "back to the runaway guard; the loop bound is not the table's "
                "own length",
                stmt.table.name,
            )
    bound_limit = occurs if occurs is not None else _RUNAWAY_GUARD
    bound_index = advance if occurs is not None else _NO_ITEM

    if not bound_index.name:
        counter_var = ctx.fresh_name("__search_ctr")
        zero_reg = ctx.const_to_reg(0, span=span)
        ctx.emit_inst(
            StoreVar(name=VarName(counter_var), value_reg=Register(str(zero_reg))),
            span=span,
        )
        max_reg = ctx.const_to_reg(bound_limit, span=span)
    else:
        max_reg = _occurrence_bound(ctx, stmt, bound_limit, materialised)

    if stmt.search_all and advance.name:
        _store_number(ctx, stmt, advance, ctx.const_to_reg(1, span=span), materialised)

    ctx.emit_inst(Label_(label=loop_label), span=span)

    if bound_index.name:
        bound_ref, bound_rr = _resolve(ctx, stmt, bound_index, materialised)
        current_reg = ctx.emit_decode_field(
            bound_rr,
            bound_ref.fl,
            bound_ref.offset_reg,
            extent=bound_ref.extent,
            span=span,
        )
        bound_operator = ">"
    else:
        current_reg = ctx.fresh_reg()
        ctx.emit_inst(
            LoadVar(result_reg=current_reg, name=VarName(counter_var)), span=span
        )
        bound_operator = ">="
    bound_cond = ctx.fresh_reg()
    ctx.emit_inst(
        Binop(
            result_reg=bound_cond,
            operator=resolve_binop(bound_operator),
            left=Register(str(current_reg)),
            right=Register(str(max_reg)),
        ),
        span=span,
    )
    body_label = ctx.fresh_label("search_body")
    ctx.emit_inst(
        BranchIf(
            cond_reg=Register(str(bound_cond)),
            branch_targets=(at_end_label, body_label),
        ),
        span=span,
    )

    ctx.emit_inst(Label_(label=body_label), span=span)
    for when in stmt.whens:
        if not when.condition:
            continue
        if isinstance(when.condition, dict):
            cond_reg = ctx.lower_condition(when.condition, materialised, span=span)
        else:
            cond_reg = _lower_condition_str(
                ctx, when.condition, materialised, ctx._condition_index, span=span
            )
        when_true = ctx.fresh_label("search_when_true")
        when_next = ctx.fresh_label("search_when_next")
        ctx.emit_inst(
            BranchIf(
                cond_reg=Register(str(cond_reg)),
                branch_targets=(when_true, when_next),
            ),
            span=span,
        )
        ctx.emit_inst(Label_(label=when_true), span=span)
        for child in when.children:
            ctx.lower_statement(child, materialised)
        ctx.emit_inst(Branch(label=end_label), span=span)
        ctx.emit_inst(Label_(label=when_next), span=span)

    ctx.emit_inst(Branch(label=increment_label), span=span)
    ctx.emit_inst(Label_(label=increment_label), span=span)

    if advance.name:
        _advance(ctx, stmt, advance, materialised)
    if companion.name and ctx.has_field(companion.name, materialised):
        _advance(ctx, stmt, companion, materialised)

    if not bound_index.name:
        ctr_reg2 = ctx.fresh_reg()
        ctx.emit_inst(
            LoadVar(result_reg=ctr_reg2, name=VarName(counter_var)), span=span
        )
        one_ctr = ctx.const_to_reg(1, span=span)
        inc_ctr = ctx.fresh_reg()
        ctx.emit_inst(
            Binop(
                result_reg=inc_ctr,
                operator=resolve_binop("+"),
                left=ctr_reg2,
                right=Register(str(one_ctr)),
            ),
            span=span,
        )
        ctx.emit_inst(StoreVar(name=VarName(counter_var), value_reg=inc_ctr), span=span)
    ctx.emit_inst(Branch(label=loop_label), span=span)

    ctx.emit_inst(Label_(label=at_end_label), span=span)
    for child in stmt.at_end:
        ctx.lower_statement(child, materialised)

    ctx.emit_inst(Label_(label=end_label), span=span)
