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
       01  WS-BUF.
           05  WS-B1   PIC X(4).
           05  WS-B2   PIC X(6).
       01  WS-PTR      PIC 9(2).
       LOCAL-STORAGE SECTION.
       01  LS-FLAG     PIC X(3) VALUE 'ABC'.
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
           MOVE 1 TO WS-PTR.
           STRING 'AB' DELIMITED BY SIZE INTO WS-B1 WITH POINTER WS-PTR.
           STOP RUN.
"""


class _Probe:
    """A lowered probe program plus the effects its lowering declared."""

    def __init__(self, src: bytes = _SRC):
        asg = make_cobol_parser().parse(src)
        sectioned = build_sectioned_layout(asg)
        self.recorder = CollectingRecorder()
        self.ctx = EmitContext(dispatch_fn=dispatch_statement, recorder=self.recorder)
        self.materialised = lower_sectioned_data_division(self.ctx, sectioned, "PROBE")
        materialised = self.materialised
        statements = [
            stmt for para in asg.paragraphs for stmt in para.statements
        ] + list(asg.statements)
        assert statements, "probe program produced no statements to lower"
        for stmt in statements:
            self.ctx.lower_statement(stmt, materialised)

    def regions(self, name: str) -> set[RegionId]:
        """Every region any recorded effect attributes to field ``name``."""
        return {
            effect.extent.region
            for effect in self.recorder.effects.values()
            if effect.extent.field_name == name
        }

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
def test_local_storage_value_clause_is_recorded_in_the_local_storage_region(probe):
    """HOLE 2 as it appeared in the wild, and the guard the headline fix lacked.

    ``lower_data_division`` initialises WORKING-STORAGE, LOCAL-STORAGE, FILE,
    INDEXES and SPECIAL-REGISTERS through ONE function, which used to record
    every one of them as WORKING-STORAGE. LS-FLAG's VALUE clause is written by
    that path, so a wrong RegionId at any of those five callers shows up here.

    Hard equality on purpose: an earlier version of this test tolerated the
    empty set and therefore passed while asserting nothing (the field it probed,
    RETURN-CODE, has no VALUE clause, so no effect was ever recorded for it).
    """
    assert probe.regions("LS-FLAG") == {RegionId.LOCAL_STORAGE}


@covers(NotLanguageFeature.INFRASTRUCTURE)
def test_local_storage_and_working_storage_inits_are_kept_apart(probe):
    """Both go through lower_data_division; they must not collapse together."""
    ls_writes = probe.effects("LS-FLAG", EffectKind.WRITE)
    assert ls_writes, "the LOCAL-STORAGE VALUE clause declared no effect"
    for effect in ls_writes:
        assert effect.extent.region is RegionId.LOCAL_STORAGE
        assert not effect.extent.may_alias(
            probe.effects("WS-NAME", EffectKind.WRITE)[0].extent
        )


@covers(NotLanguageFeature.INFRASTRUCTURE)
def test_string_with_pointer_extent_covers_bytes_past_the_target_field(probe):
    """FIX 1: the write runs off the end of WS-B1, so the extent must too.

    ``STRING ... INTO WS-B1 WITH POINTER WS-PTR`` emits a write of
    ``byte_length`` bytes starting ``ptr - 1`` bytes into WS-B1, so it can
    touch WS-B2 — which sits immediately after it inside WS-BUF. An extent
    stopping at WS-B1's own end would be under-sized, and ``may_alias`` would
    silently miss that overlap. Precision alone does not fix this: CLAMPED
    protects ``must_cover`` only.
    """
    b1_ref, _ = probe.ctx.resolve_field_ref("WS-B1", probe.materialised)
    b2_ref, _ = probe.ctx.resolve_field_ref("WS-B2", probe.materialised)
    buf_ref, _ = probe.ctx.resolve_field_ref("WS-BUF", probe.materialised)

    writes = probe.effects("WS-B1", EffectKind.WRITE)
    assert writes, "the STRING WITH POINTER write declared no effect"
    effect = writes[-1]

    assert effect.extent.precision is Precision.CLAMPED
    assert effect.extent.end > b1_ref.extent.end, (
        f"{effect.extent} stops at the target field's own end; the write can "
        "run up to byte_length - 1 bytes past it"
    )
    assert effect.extent.may_alias(
        b2_ref.extent
    ), "the overrun reaches WS-B2, so that alias edge must not be dropped"
    assert (effect.extent.start, effect.extent.length) == (
        buf_ref.extent.start,
        buf_ref.extent.length,
    ), "clamped to the enclosing 01 WS-BUF, per field_extent's stated doctrine"


@covers(NotLanguageFeature.INFRASTRUCTURE)
def test_string_with_pointer_extent_stays_inside_its_own_record(probe):
    """The other cliff: widening must stop at the 01, not reach the region."""
    buf_ref, _ = probe.ctx.resolve_field_ref("WS-BUF", probe.materialised)
    name_ref, _ = probe.ctx.resolve_field_ref("WS-NAME", probe.materialised)
    idx_ref, _ = probe.ctx.resolve_field_ref("WS-IDX", probe.materialised)

    effect = probe.effects("WS-B1", EffectKind.WRITE)[-1]
    assert buf_ref.extent.must_cover(effect.extent)
    assert not effect.extent.may_alias(name_ref.extent)
    assert not effect.extent.may_alias(idx_ref.extent)


# A LINKAGE item handed straight on to a further CALL — the ordinary "pass my
# caller's parameter down the chain" shape. LK-ARG must NOT also exist in WS,
# or resolution would pick WS and prove nothing.
#
# WS-SHADOW is placed to OCCUPY the byte range LK-ARG would be misattributed
# to. LK-ARG is at LINKAGE 5..13; WS-SHADOW spans WORKING-STORAGE 4..15. The
# two overlap on bytes but not on region, so they must never alias — and a
# region hardcoded back to WORKING_STORAGE makes them alias, which is exactly
# the false edge the region distinction exists to prevent. Without WS-SHADOW
# the contrast test would pass under the hardcode by byte-range luck.
_CALL_SRC = b"""\
       IDENTIFICATION DIVISION.
       PROGRAM-ID. CALLPROBE.
       DATA DIVISION.
       WORKING-STORAGE SECTION.
       01  WS-OTHER    PIC X(4).
       01  WS-SHADOW   PIC X(12).
       LINKAGE SECTION.
       01  LK-LEAD     PIC X(5).
       01  LK-ARG      PIC X(9).
       PROCEDURE DIVISION USING LK-LEAD LK-ARG.
       MAIN-PARA.
           MOVE 'ZZZZ' TO WS-OTHER.
           MOVE 'YYYY' TO WS-SHADOW.
           CALL 'SUBPROG' USING LK-ARG.
           STOP RUN.
"""


@pytest.fixture
def call_probe() -> _Probe:
    return _Probe(_CALL_SRC)


def _caller_side(effects):
    """The caller-side half of a CALL's marshalling, by byte range.

    Each USING argument produces TWO recorded effects per direction under the
    SAME field name: one against the argument's slot in its own section (what
    this module is about) and one against its slot in the freshly allocated
    marshalling buffer, which ``_params_extent`` deliberately names as a
    LINKAGE extent at a cumulative offset from zero. LK-ARG sits at LINKAGE
    offset 5, so the caller-side extent is the one starting there; the buffer
    slot for the sole argument starts at 0.
    """
    return [e for e in effects if e.extent.start == 5]


@covers(NotLanguageFeature.INFRASTRUCTURE)
def test_call_using_a_linkage_item_records_the_linkage_region(call_probe):
    """CALL marshalling must name the argument's OWN section, not WORKING-STORAGE.

    The lowering used to marshal every USING argument out of the caller's WS
    region regardless of where it was declared (red-dragon-8krz), and the
    recorded extent hardcoded ``RegionId.WORKING_STORAGE`` to stay faithful to
    that. Once the lowering was fixed to read from the resolved owning region,
    a leftover hardcode would make the analysis describe WS bytes while the
    instruction touches LINKAGE bytes — and because cross-region pairs never
    alias, every alias edge for a non-WS ``CALL USING`` argument would vanish
    with no error anywhere.

    LK-ARG is at offset 5 in LINKAGE, 9 bytes long. Hard equality on the region
    set: a stray WORKING_STORAGE entry fails here even if a LINKAGE one is also
    present.
    """
    assert call_probe.regions("LK-ARG") == {RegionId.LINKAGE}

    (read,) = _caller_side(call_probe.effects("LK-ARG", EffectKind.READ))
    assert read.extent.region is RegionId.LINKAGE
    assert (read.extent.start, read.extent.length) == (5, 9)

    # BY REFERENCE is the default, so the copy-back write is emitted too.
    (write,) = _caller_side(call_probe.effects("LK-ARG", EffectKind.WRITE))
    assert write.extent.region is RegionId.LINKAGE
    assert (write.extent.start, write.extent.length) == (5, 9)


@covers(NotLanguageFeature.INFRASTRUCTURE)
def test_the_call_argument_extent_cannot_alias_working_storage(call_probe):
    """The concrete cost of a hardcoded region, stated as a false alias edge.

    LK-ARG occupies LINKAGE 5..13; WS-SHADOW occupies WORKING-STORAGE 4..15.
    They overlap on bytes and differ only in region, so the region is the ONLY
    thing keeping them apart. Record the CALL's read as WORKING-STORAGE and the
    analysis invents a dependency between a subprogram argument and an
    unrelated WS field.
    """
    (call_read,) = _caller_side(call_probe.effects("LK-ARG", EffectKind.READ))
    (shadow_write,) = call_probe.effects("WS-SHADOW", EffectKind.WRITE)
    assert shadow_write.extent.region is RegionId.WORKING_STORAGE
    assert (
        shadow_write.extent.start < call_read.extent.end
        and call_read.extent.start < shadow_write.extent.end
    ), "WS-SHADOW must overlap LK-ARG's byte range for this test to bite"
    assert not call_read.extent.may_alias(shadow_write.extent)
