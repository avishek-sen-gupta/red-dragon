# pyright: standard
"""Memory effects — the COBOL lowering's declaration of what each access touches.

emit_context is the only place holding BOTH the source construct (FieldLayout,
structured subscripts, source location) AND the byte layout (offset, length,
region). Neither the ASG nor the IR has both, so the extent is recorded here
rather than reconstructed later from arithmetic on offset registers.

A lowering path that emits a region access without declaring its effect does
not fail loudly — it simply vanishes from the analysis, leaving a quietly
incomplete dependency graph. ``EmitContext._emit_load_region`` and
``_emit_write_region`` are therefore the only construction sites for
``LoadRegion``/``WriteRegion``, enforced by
``tests/unit/cobol/test_region_funnel_invariant.py``.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum, auto
from typing import Protocol

from interpreter.cobol.field_extent import FieldExtent
from interpreter.instructions import InstructionId
from interpreter.ir import SourceLocation


class EffectKind(Enum):
    READ = auto()
    WRITE = auto()


@dataclass(frozen=True)
class MemoryEffect:
    """One region access, as the lowering understands it."""

    kind: EffectKind
    extent: FieldExtent
    source_location: SourceLocation | None = None


class MemoryEffectRecorder(Protocol):
    def record(self, inst_id: InstructionId, effect: MemoryEffect) -> None: ...


class NullRecorder:
    """Default. Analysis off; recording costs nothing."""

    def record(self, inst_id: InstructionId, effect: MemoryEffect) -> None:
        return None


@dataclass
class CollectingRecorder:
    """Builds the sidecar consumed by the memory dataflow analysis."""

    effects: dict[InstructionId, MemoryEffect] = field(default_factory=dict)

    def record(self, inst_id: InstructionId, effect: MemoryEffect) -> None:
        # An id recorded twice means two distinct region accesses are sharing a
        # sidecar key, so one silently inherits the other's extent — a wrong or
        # vanished dependency edge with no error anywhere. That is the one
        # failure mode this whole analysis exists to prevent, so it fails loudly
        # here rather than being discovered in the graph. Ids come from
        # ``EmitContext``'s ``InstructionIdSource``; a collision means the
        # source was not shared across the contexts feeding this recorder.
        assert inst_id not in self.effects, (
            f"memory effect already recorded for instruction id {inst_id}: "
            f"existing={self.effects[inst_id]!r} new={effect!r}. Instruction "
            "ids must be unique across every program lowered into one recorder."
        )
        self.effects[inst_id] = effect
