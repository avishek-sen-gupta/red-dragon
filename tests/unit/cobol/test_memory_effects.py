"""Memory effects — what the lowering tells the analysis about each access."""

import pytest

from interpreter.cobol.field_extent import FieldExtent, Precision
from interpreter.cobol.memory_effects import (
    CollectingRecorder,
    EffectKind,
    MemoryEffect,
    NullRecorder,
)
from interpreter.cobol.region_id import RegionId
from interpreter.instructions import InstructionId
from tests.covers import NotLanguageFeature, covers


@pytest.fixture
def sample_extent():
    return FieldExtent(
        region=RegionId.WORKING_STORAGE,
        start=0,
        length=4,
        precision=Precision.EXACT,
        field_name="WS-A",
    )


@covers(NotLanguageFeature.INFRASTRUCTURE)
def test_null_recorder_discards_and_costs_nothing(sample_extent):
    NullRecorder().record(
        InstructionId(1), MemoryEffect(kind=EffectKind.READ, extent=sample_extent)
    )


@covers(NotLanguageFeature.INFRASTRUCTURE)
def test_collecting_recorder_keys_effects_by_instruction_id(sample_extent):
    rec = CollectingRecorder()
    effect = MemoryEffect(kind=EffectKind.WRITE, extent=sample_extent)
    rec.record(InstructionId(7), effect)
    assert rec.effects[InstructionId(7)] is effect


@covers(NotLanguageFeature.INFRASTRUCTURE)
def test_effect_carries_kind_extent_and_optional_source_location(sample_extent):
    effect = MemoryEffect(kind=EffectKind.READ, extent=sample_extent)
    assert effect.kind is EffectKind.READ
    assert effect.extent is sample_extent
    assert effect.source_location is None
