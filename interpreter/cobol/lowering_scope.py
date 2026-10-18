"""The scope one statement lowers in: where it emits, what its names resolve against, and its source span."""

from __future__ import annotations

from dataclasses import dataclass

from cobol_asg.source_span import SourceSpan
from interpreter.cobol.emit_context import EmitContext
from interpreter.cobol.ir_emitter import IrEmitter
from interpreter.cobol.sectioned_layout import MaterialisedSectionedLayout


@dataclass(frozen=True)
class LoweringScope:
    ctx: EmitContext
    materialised: MaterialisedSectionedLayout
    span: SourceSpan | None

    @property
    def emitter(self) -> IrEmitter:
        return IrEmitter(self.ctx, self.span)
