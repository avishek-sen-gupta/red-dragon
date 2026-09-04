"""No region access may be emitted without declaring its memory effect.

The silent failure mode this guards: a lowering path that emits a write
without an effect simply vanishes from the analysis, producing a quietly
incomplete dependency graph rather than a visible error. That is exactly the
shape of the ``WriteRegion.writes() -> None`` bug this work exists to fix.
"""

import re
from pathlib import Path

from interpreter.cobol.field_extent import FieldExtent, Precision
from interpreter.cobol.memory_effects import CollectingRecorder, EffectKind
from interpreter.cobol.region_id import RegionId
from interpreter.instructions import LoadRegion, WriteRegion
from interpreter.register import Register
from tests.covers import NotLanguageFeature, covers

REPO_ROOT = Path(__file__).resolve().parents[3]

CONSTRUCTION = re.compile(r"\b(LoadRegion|WriteRegion)\(")

# emit_context.py owns the funnel helpers; instructions.py owns the classes
# themselves and the flat-operand factory that builds them.
ALLOWED = {"interpreter/cobol/emit_context.py", "interpreter/instructions.py"}


def _construction_sites() -> set[str]:
    return {
        path.relative_to(REPO_ROOT).as_posix()
        for path in (REPO_ROOT / "interpreter").rglob("*.py")
        if CONSTRUCTION.search(path.read_text())
    }


@covers(NotLanguageFeature.INFRASTRUCTURE)
def test_region_instructions_are_constructed_only_in_the_funnel():
    offenders = sorted(_construction_sites() - ALLOWED)
    assert offenders == [], (
        f"LoadRegion/WriteRegion constructed outside the funnel: {offenders}. "
        "Use EmitContext._emit_load_region / _emit_write_region so the memory "
        "effect is declared alongside the instruction."
    )


@covers(NotLanguageFeature.INFRASTRUCTURE)
def test_the_funnel_itself_still_constructs_them():
    """Guards against the invariant passing vacuously."""
    src = (REPO_ROOT / "interpreter/cobol/emit_context.py").read_text()
    assert "LoadRegion(" in src and "WriteRegion(" in src


def _ctx():
    from interpreter.cobol.emit_context import EmitContext

    recorder = CollectingRecorder()
    return EmitContext(dispatch_fn=lambda *_: None, recorder=recorder), recorder


def _extent(name="WS-A"):
    return FieldExtent(
        region=RegionId.WORKING_STORAGE,
        start=3,
        length=4,
        precision=Precision.EXACT,
        field_name=name,
    )


@covers(NotLanguageFeature.INFRASTRUCTURE)
def test_load_funnel_emits_the_instruction_and_records_a_read():
    ctx, recorder = _ctx()
    extent = _extent()
    ctx._emit_load_region(
        result_reg=Register("%0"),
        region_reg=Register("%1"),
        offset_reg=Register("%2"),
        length=4,
        extent=extent,
    )
    (inst,) = ctx.instructions
    assert isinstance(inst, LoadRegion)
    assert inst.length == 4
    assert recorder.effects[inst.id].kind is EffectKind.READ
    assert recorder.effects[inst.id].extent is extent


@covers(NotLanguageFeature.INFRASTRUCTURE)
def test_write_funnel_emits_the_instruction_and_records_a_write():
    ctx, recorder = _ctx()
    extent = _extent()
    ctx._emit_write_region(
        region_reg=Register("%1"),
        offset_reg=Register("%2"),
        value_reg=Register("%3"),
        length=4,
        extent=extent,
    )
    (inst,) = ctx.instructions
    assert isinstance(inst, WriteRegion)
    assert inst.length == 4
    assert recorder.effects[inst.id].kind is EffectKind.WRITE
    assert recorder.effects[inst.id].extent is extent


@covers(NotLanguageFeature.INFRASTRUCTURE)
def test_recording_is_off_by_default_and_still_emits_the_instruction():
    """The default recorder discards, and emitting does not depend on one."""
    from interpreter.cobol.emit_context import EmitContext
    from interpreter.cobol.memory_effects import NullRecorder

    ctx = EmitContext(dispatch_fn=lambda *_: None)
    assert isinstance(ctx._recorder, NullRecorder)
    ctx._emit_write_region(
        region_reg=Register("%1"),
        offset_reg=Register("%2"),
        value_reg=Register("%3"),
        length=4,
        extent=_extent(),
    )
    assert len(ctx.instructions) == 1
