"""Every resolved field reference carries a statically-known byte extent.

The point of these tests is the ⊤ cliff: a subscripted access whose index is
not a literal must clamp to the *enclosing OCCURS construct*, never to the
whole region. A region-wide extent would make every field alias every other
field, and after transitive closure an impact report would say "changing
anything affects everything".

Every field under test has neighbours on BOTH sides and the neighbours'
extents are asserted too — an extent one byte too long is invisible in
isolation and immediately visible against a neighbour (red-dragon-ilb6,
r9s9, qhtv, bqds all shipped from single-field fixtures).
"""

from __future__ import annotations

from dataclasses import dataclass

import pytest

from cobol_asg.cobol_expression import ExprNode, FieldRefNode, LiteralNode
from cobol_asg.cobol_parser import make_cobol_parser
from interpreter.cobol.emit_context import EmitContext
from interpreter.cobol.field_extent import Precision
from interpreter.cobol.field_resolution import ResolvedFieldRef
from interpreter.cobol.lower_data_division import lower_sectioned_data_division
from interpreter.cobol.region_id import RegionId
from interpreter.cobol.sectioned_layout import (
    MaterialisedSectionedLayout,
    build_sectioned_layout,
)
from interpreter.cobol.statement_dispatch import dispatch_statement
from tests.covers import NotLanguageFeature, covers

_PROBE_SRC = b"""\
       IDENTIFICATION DIVISION.
       PROGRAM-ID. PROBE.
       DATA DIVISION.
       WORKING-STORAGE SECTION.
       01  WS-LEAD     PIC X(7).
       01  WS-REC.
           05  WS-NAME PIC X(20).
           05  WS-TAB.
               10  WS-ENT OCCURS 10 TIMES.
                   15  WS-CODE PIC X(2).
                   15  WS-QTY  PIC 999.
           05  WS-TAIL PIC X(4).
       01  WS-IDX      PIC 9(4).
       01  WS-TRAIL    PIC X(3).
       LINKAGE SECTION.
       01  LK-LEAD     PIC X(5).
       01  LK-MID      PIC X(9).
       01  LK-TRAIL    PIC X(6).
       PROCEDURE DIVISION USING LK-LEAD LK-MID LK-TRAIL.
           MOVE 'HI' TO WS-NAME.
           STOP RUN.
"""


def literal_expr(value: int) -> ExprNode:
    """A subscript the resolver can see through: ``WS-QTY(2)``."""
    return LiteralNode(value=str(value))


def field_expr(name: str) -> ExprNode:
    """A subscript the resolver cannot bound: ``WS-QTY(WS-IDX)``."""
    return FieldRefNode(name=name)


@dataclass
class _Probe:
    """Binds an EmitContext to its materialised layout for terse resolution."""

    ctx: EmitContext
    materialised: MaterialisedSectionedLayout

    def resolve_field_ref(
        self, name: str, subscripts: tuple[ExprNode, ...] = ()
    ) -> tuple[ResolvedFieldRef, object]:
        return self.ctx.resolve_field_ref(
            name, self.materialised, subscripts=subscripts
        )


@pytest.fixture
def probe() -> _Probe:
    parser = make_cobol_parser()
    asg = parser.parse(_PROBE_SRC)
    sectioned = build_sectioned_layout(asg)
    ctx = EmitContext(dispatch_fn=dispatch_statement)
    materialised = lower_sectioned_data_division(ctx, sectioned, "PROBE")
    return _Probe(ctx=ctx, materialised=materialised)


@covers(NotLanguageFeature.INFRASTRUCTURE)
def test_bare_field_gets_an_exact_extent(probe):
    ref, _reg = probe.resolve_field_ref("WS-NAME")
    assert ref.extent.precision is Precision.EXACT
    assert ref.extent.region is RegionId.WORKING_STORAGE
    assert ref.extent.length == 20


@covers(NotLanguageFeature.INFRASTRUCTURE)
def test_neighbours_do_not_overlap(probe):
    """WS-LEAD and WS-TRAIL bracket WS-REC; a width bug shows up as overlap."""
    lead, _ = probe.resolve_field_ref("WS-LEAD")
    name, _ = probe.resolve_field_ref("WS-NAME")
    trail, _ = probe.resolve_field_ref("WS-TRAIL")
    assert not lead.extent.may_alias(name.extent)
    assert not name.extent.may_alias(trail.extent)
    assert lead.extent.end == name.extent.start
    assert lead.extent.length == 7
    assert trail.extent.length == 3


@covers(NotLanguageFeature.INFRASTRUCTURE)
def test_group_extent_brackets_its_own_neighbours(probe):
    """WS-NAME and WS-TAIL bracket WS-TAB inside WS-REC."""
    name, _ = probe.resolve_field_ref("WS-NAME")
    tab, _ = probe.resolve_field_ref("WS-TAB")
    tail, _ = probe.resolve_field_ref("WS-TAIL")
    assert tab.extent.length == 50
    assert name.extent.end == tab.extent.start
    assert tab.extent.end == tail.extent.start
    assert tail.extent.length == 4
    assert not name.extent.may_alias(tail.extent)


@covers(NotLanguageFeature.INFRASTRUCTURE)
def test_literal_subscript_gives_an_exact_element_extent(probe):
    ref, _reg = probe.resolve_field_ref("WS-QTY", subscripts=(literal_expr(2),))
    assert ref.extent.precision is Precision.EXACT
    assert ref.extent.length == 3


@covers(NotLanguageFeature.INFRASTRUCTURE)
def test_literal_subscript_elements_tile_the_table_without_overlap(probe):
    """WS-CODE(2) | WS-QTY(2) | WS-CODE(3) must abut, not overlap."""
    code2, _ = probe.resolve_field_ref("WS-CODE", subscripts=(literal_expr(2),))
    qty2, _ = probe.resolve_field_ref("WS-QTY", subscripts=(literal_expr(2),))
    code3, _ = probe.resolve_field_ref("WS-CODE", subscripts=(literal_expr(3),))
    assert code2.extent.length == 2
    assert code2.extent.end == qty2.extent.start
    assert qty2.extent.end == code3.extent.start
    assert not code2.extent.may_alias(qty2.extent)
    assert not qty2.extent.may_alias(code3.extent)


@covers(NotLanguageFeature.INFRASTRUCTURE)
def test_computed_subscript_clamps_to_the_table(probe):
    """An unbounded offset must clamp to the OCCURS extent, never the region."""
    ref, _reg = probe.resolve_field_ref("WS-QTY", subscripts=(field_expr("WS-IDX"),))
    assert ref.extent.precision is Precision.CLAMPED
    assert ref.extent.length == 50, "clamped to WS-TAB (10 entries x 5 bytes)"


@covers(NotLanguageFeature.INFRASTRUCTURE)
def test_clamped_extent_never_spans_the_whole_region(probe):
    """The cliff: a clamped extent must stay inside its own table."""
    tab, _ = probe.resolve_field_ref("WS-TAB")
    ref, _reg = probe.resolve_field_ref("WS-QTY", subscripts=(field_expr("WS-IDX"),))
    assert tab.extent.must_cover(ref.extent)


@covers(NotLanguageFeature.INFRASTRUCTURE)
def test_clamped_extent_misses_the_tables_neighbours(probe):
    """A computed subscript must not be made to alias WS-NAME or WS-TAIL."""
    name, _ = probe.resolve_field_ref("WS-NAME")
    tail, _ = probe.resolve_field_ref("WS-TAIL")
    trail, _ = probe.resolve_field_ref("WS-TRAIL")
    ref, _reg = probe.resolve_field_ref("WS-QTY", subscripts=(field_expr("WS-IDX"),))
    assert not ref.extent.may_alias(name.extent)
    assert not ref.extent.may_alias(tail.extent)
    assert not ref.extent.may_alias(trail.extent)


@covers(NotLanguageFeature.INFRASTRUCTURE)
def test_linkage_field_reports_the_linkage_region(probe):
    """A non-WORKING-STORAGE field must not be hardcoded to WORKING_STORAGE."""
    lead, _ = probe.resolve_field_ref("LK-LEAD")
    mid, _ = probe.resolve_field_ref("LK-MID")
    trail, _ = probe.resolve_field_ref("LK-TRAIL")
    assert mid.extent.region is RegionId.LINKAGE
    assert mid.extent.length == 9
    assert lead.extent.end == mid.extent.start
    assert mid.extent.end == trail.extent.start
    assert not lead.extent.may_alias(mid.extent)
    assert not mid.extent.may_alias(trail.extent)


@covers(NotLanguageFeature.INFRASTRUCTURE)
def test_extents_in_different_regions_never_alias(probe):
    """Same byte offset, different region buffer — no overlap."""
    ws_lead, _ = probe.resolve_field_ref("WS-LEAD")
    lk_lead, _ = probe.resolve_field_ref("LK-LEAD")
    assert ws_lead.extent.start == lk_lead.extent.start == 0
    assert not ws_lead.extent.may_alias(lk_lead.extent)
