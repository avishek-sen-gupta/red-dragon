"""What the ORDINARY lowering path actually records for a region access.

``test_resolved_extent`` proves ``ResolvedFieldRef.extent`` is computed
correctly. That is worth nothing if the lowering then throws it away at the
point of use, which is precisely what happened: seventy-odd call sites passed
``fl`` and ``offset_reg`` to the emit helpers and let them rebuild an extent
from the FieldLayout alone.

Two silent holes came out of that, and these tests exist to keep them shut:

* A subscripted access rebuilt from ``fl`` alone names the FIRST element
  (``WS-QTY(1)``, 3 bytes) rather than the OCCURS construct a computed index
  can reach (50 bytes). The recorded extent then UNDER-approximates by a
  factor of ten, ``may_alias`` misses real overlaps, and dependency edges are
  dropped without any error.
* A region defaulted to WORKING_STORAGE is wrong for five of the six regions.
  Cross-region extents NEVER alias, so a wrong region does not blur a field's
  aliasing — it deletes it outright.

So these tests drive real statements through ``lower_statement`` and assert on
what the recorder saw. Nothing here hand-builds a ``ResolvedFieldRef``: if the
threading regresses anywhere on that path, these fail.
"""

from __future__ import annotations

import pytest

from cobol_asg.cobol_parser import make_cobol_parser
from interpreter.cobol.emit_context import EmitContext
from interpreter.cobol.field_extent import Precision
from interpreter.cobol.lower_data_division import lower_sectioned_data_division
from interpreter.cobol.memory_effects import CollectingRecorder, EffectKind
from interpreter.cobol.region_id import RegionId
from interpreter.cobol.sectioned_layout import build_sectioned_layout
from interpreter.cobol.statement_dispatch import dispatch_statement
from interpreter.instructions import LoadRegion, WriteRegion
from tests.covers import NotLanguageFeature, covers

# WS-REC starts at 7 (after WS-LEAD X(7)); WS-NAME is 20, so the OCCURS
# construct WS-ENT starts at 27 and spans 10 x 5 = 50 bytes. WS-CODE is the
# first 2 bytes of an entry and WS-QTY the last 3, so a first-element rebuild
# of WS-QTY would say (29, 3) instead of (27, 50).
_SRC = b"""\
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
       LINKAGE SECTION.
       01  LK-LEAD     PIC X(5).
       01  LK-MID      PIC X(9).
       PROCEDURE DIVISION USING LK-LEAD LK-MID.
       MAIN-PARA.
           MOVE 1 TO WS-IDX.
           MOVE 7 TO WS-QTY(WS-IDX).
           MOVE WS-QTY(WS-IDX) TO WS-IDX.
           MOVE 'HELLO' TO LK-MID.
           MOVE LK-MID TO WS-NAME.
           STOP RUN.
"""


class _Probe:
    """A lowered probe program plus the effects its lowering declared."""

    def __init__(self):
        asg = make_cobol_parser().parse(_SRC)
        sectioned = build_sectioned_layout(asg)
        self.recorder = CollectingRecorder()
        self.ctx = EmitContext(dispatch_fn=dispatch_statement, recorder=self.recorder)
        materialised = lower_sectioned_data_division(self.ctx, sectioned, "PROBE")
        statements = [
            stmt for para in asg.paragraphs for stmt in para.statements
        ] + list(asg.statements)
        assert statements, "probe program produced no statements to lower"
        for stmt in statements:
            self.ctx.lower_statement(stmt, materialised)

    def effects(self, name: str, kind: EffectKind):
        """Every recorded effect of ``kind`` naming field ``name``."""
        wanted = LoadRegion if kind is EffectKind.READ else WriteRegion
        out = []
        for inst in self.ctx.instructions:
            effect = self.recorder.effects.get(inst.id)
            if effect is None:
                continue
            assert isinstance(
                inst, (LoadRegion, WriteRegion)
            ), f"effect recorded against a non-region instruction {inst!r}"
            if isinstance(inst, wanted) and effect.extent.field_name == name:
                out.append(effect)
        return out


@pytest.fixture
def probe() -> _Probe:
    return _Probe()


@covers(NotLanguageFeature.INFRASTRUCTURE)
def test_every_region_instruction_carries_a_recorded_effect(probe):
    """The funnel is only worth anything if nothing slips through it."""
    missing = [
        inst
        for inst in probe.ctx.instructions
        if isinstance(inst, (LoadRegion, WriteRegion))
        and inst.id not in probe.recorder.effects
    ]
    assert missing == [], f"{len(missing)} region access(es) declared no effect"


@covers(NotLanguageFeature.INFRASTRUCTURE)
def test_a_region_access_was_actually_emitted(probe):
    """Guards the rest of this module against passing vacuously."""
    region_insts = [
        i for i in probe.ctx.instructions if isinstance(i, (LoadRegion, WriteRegion))
    ]
    assert len(region_insts) > 5


@covers(NotLanguageFeature.INFRASTRUCTURE)
def test_computed_subscript_write_records_the_table_wide_clamped_extent(probe):
    """HOLE 1: `MOVE 7 TO WS-QTY(WS-IDX)` may land on any of the ten entries."""
    (effect,) = probe.effects("WS-QTY", EffectKind.WRITE)
    assert effect.extent.precision is Precision.CLAMPED
    assert (effect.extent.start, effect.extent.length) == (27, 50), (
        "the write must be recorded against the whole OCCURS construct WS-ENT; "
        f"got {effect.extent}, which is the first-element extent a rebuild "
        "from the FieldLayout alone would produce"
    )


@covers(NotLanguageFeature.INFRASTRUCTURE)
def test_computed_subscript_read_records_the_table_wide_clamped_extent(probe):
    """The same hole on the read side: `MOVE WS-QTY(WS-IDX) TO WS-IDX`."""
    reads = probe.effects("WS-QTY", EffectKind.READ)
    assert reads, "the read of WS-QTY(WS-IDX) declared no effect at all"
    for effect in reads:
        assert effect.extent.precision is Precision.CLAMPED
        assert (effect.extent.start, effect.extent.length) == (27, 50)


@covers(NotLanguageFeature.INFRASTRUCTURE)
def test_the_clamped_extent_reaches_entries_the_first_element_would_miss(probe):
    """The concrete cost of HOLE 1, stated as a lost alias edge.

    WS-QTY(10) lives at bytes 72..74. A first-element extent (29..31) does not
    reach it, so a dependency between the computed write and a literal read of
    the last entry would simply be absent.
    """
    (write,) = probe.effects("WS-QTY", EffectKind.WRITE)
    last_entry_start = 27 + 9 * 5 + 2
    assert write.extent.start <= last_entry_start < write.extent.end


@covers(NotLanguageFeature.INFRASTRUCTURE)
def test_linkage_write_is_recorded_in_the_linkage_region(probe):
    """HOLE 2: a defaulted WORKING_STORAGE region silently unlinks the field."""
    (effect,) = probe.effects("LK-MID", EffectKind.WRITE)
    assert effect.extent.region is RegionId.LINKAGE
    assert (effect.extent.start, effect.extent.length) == (5, 9)


@covers(NotLanguageFeature.INFRASTRUCTURE)
def test_linkage_read_is_recorded_in_the_linkage_region(probe):
    (effect,) = probe.effects("LK-MID", EffectKind.READ)
    assert effect.extent.region is RegionId.LINKAGE


@covers(NotLanguageFeature.INFRASTRUCTURE)
def test_a_linkage_extent_never_aliases_a_working_storage_one(probe):
    """Why the region matters: these two must not be confusable."""
    (lk,) = probe.effects("LK-MID", EffectKind.WRITE)
    (ws,) = probe.effects("WS-NAME", EffectKind.WRITE)
    assert ws.extent.region is RegionId.WORKING_STORAGE
    assert not lk.extent.may_alias(ws.extent)
    assert not ws.extent.may_alias(lk.extent)


@covers(NotLanguageFeature.INFRASTRUCTURE)
def test_working_storage_value_initialisation_is_not_mislabelled(probe):
    """SPECIAL-REGISTERS are initialised by the same lower_data_division call
    that initialises WORKING-STORAGE; they must not share a region."""
    regions = {
        effect.extent.region
        for effect in probe.recorder.effects.values()
        if effect.extent.field_name.upper() == "RETURN-CODE"
    }
    assert regions in ({RegionId.SPECIAL_REGISTERS}, set())
