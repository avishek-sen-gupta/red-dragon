# pyright: standard
"""Field reference resolution — subscript parsing and offset computation."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from typing import TYPE_CHECKING

from interpreter.cobol.data_layout import FieldLayout, OccursTable
from interpreter.cobol.field_extent import FieldExtent, Precision
from interpreter.cobol.region_id import RegionId
from interpreter.register import Register

if TYPE_CHECKING:
    from cobol_asg.cobol_expression import ExprNode


@dataclass(frozen=True)
class ResolvedFieldRef:
    """Result of resolving a field reference, possibly with a subscript.

    Attributes:
        fl: The FieldLayout for the base field.
        offset_reg: Register holding the computed byte offset.
            For bare refs, this is a CONST of fl.offset.
            For subscripted refs, this is base + (idx - 1) * element_size.
        extent: Statically-known byte range this reference touches. EXACT when
            the subscript is absent or literal; CLAMPED to the enclosing OCCURS
            extent when computed. Never widens beyond a declared construct.
    """

    fl: FieldLayout
    offset_reg: Register
    extent: FieldExtent


def literal_subscript_value(node: ExprNode) -> int | None:
    """The integer a subscript denotes, or None when it is not a literal.

    This is the whole reason the extent stays bounded: ``resolve_field_ref``
    receives subscripts as structured ``ExprNode``s, so "is this index known?"
    is a question about the tree, not an attempt to reason backwards through
    ``BINOP`` arithmetic on a register. Anything that is not a plain integer
    ``LiteralNode`` — a field ref, a binop, a function call — is treated as
    unknown, which is the conservative (CLAMPED) answer.
    """
    from cobol_asg.cobol_expression import LiteralNode

    if not isinstance(node, LiteralNode):
        return None
    try:
        return int(node.value)
    except ValueError:
        return None


def field_access_extent(
    *,
    name: str,
    fl: FieldLayout,
    region: RegionId,
    subscripts: Sequence[ExprNode],
    tables: Sequence[OccursTable],
    record: tuple[int, int] | None,
    access_len: int,
) -> FieldExtent:
    """The byte range a field reference touches, bounded by declared structure.

    Three cases, and no fourth:

    * No subscripts — EXACT over the field's own ``(offset, byte_length)``.
    * All subscripts literal — EXACT over ``access_len`` at the element offset,
      computed with the same stride arithmetic the register path emits.
    * Any subscript non-literal — CLAMPED to the OCCURS construct owning the
      first unknown dimension: its offset (displaced by the literal outer
      subscripts, which *are* known) and its full ``element_size *
      occurs_count`` span.

    When a computed subscript is written on something that declares no OCCURS
    at all — a malformed program — there is no table to clamp to, and the
    register path falls back to striding by the field's own width, so the
    runtime address genuinely can leave the field. Clamping to the field would
    UNDER-approximate, and an under-sized extent silently misses a real overlap
    in ``may_alias`` — a dropped dependency edge, the very failure this design
    exists to prevent. (Under-approximating is safe for ``must_cover``, which
    refuses to fire on CLAMPED, and unsafe for ``may_alias``; both consume this
    extent.) So the fallback is ``record``, the enclosing level-01 — still a
    declared construct, and nowhere near a region-wide extent.

    There is deliberately no path to a region-wide extent. The widest thing
    this can return is one declared OCCURS table or one declared 01 record.
    ``tables`` is positionally aligned with ``subscripts`` exactly as the
    strides used for the register arithmetic are. ``record`` is consulted only
    in that degenerate branch.
    """
    if not subscripts:
        return FieldExtent(region, fl.offset, fl.byte_length, Precision.EXACT, name)

    # A single subscript strides by the field's own OCCURS if it has one, else
    # by the NEAREST enclosing table — mirror that choice so the extent and the
    # emitted offset arithmetic agree. Multi-dimensional access pairs subscript
    # k with table k, outermost first.
    aligned = list(tables[-1:] if len(subscripts) == 1 else tables[: len(subscripts)])
    values = [literal_subscript_value(node) for node in subscripts]

    if all(value is not None for value in values):
        offset = fl.offset
        for value, table in zip(values, aligned):
            offset += (value - 1) * table.element_size
        if not aligned:
            # No declared OCCURS: the register path strides by the field's own
            # width, so mirror that rather than inventing a different address.
            offset += (values[0] - 1) * fl.byte_length
        return FieldExtent(region, offset, access_len, Precision.EXACT, name)

    if not aligned:
        # Computed subscript on something with no declared OCCURS. The register
        # path strides by the field's own width, so the access can leave the
        # field: clamping to the field would under-approximate and drop a
        # may_alias edge. Clamp to the enclosing 01 record instead — still a
        # declared construct, and still far from the region-wide cliff.
        start, length = record if record is not None else (fl.offset, fl.byte_length)
        return FieldExtent(region, start, length, Precision.CLAMPED, name)

    unknown_dim = next(index for index, value in enumerate(values) if value is None)
    if unknown_dim >= len(aligned):
        # More subscripts than declared dimensions is rejected upstream; if it
        # ever reaches here, clamp to the outermost table rather than widen.
        unknown_dim = 0
    table = aligned[unknown_dim]
    start = table.offset
    for outer in range(unknown_dim):
        start += (values[outer] - 1) * aligned[outer].element_size
    return FieldExtent(region, start, table.total_bytes, Precision.CLAMPED, name)
