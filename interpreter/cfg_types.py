"""CFG data types (pure data, no business logic)."""

from __future__ import annotations

from dataclasses import dataclass, field

from interpreter.ir import IRInstruction, CodeLabel
from interpreter import constants


@dataclass
class BasicBlock:
    label: CodeLabel
    instructions: list[IRInstruction] = field(default_factory=list)
    successors: list[CodeLabel] = field(default_factory=list)
    predecessors: list[CodeLabel] = field(default_factory=list)


@dataclass
class CFG:
    blocks: dict[CodeLabel, BasicBlock] = field(default_factory=dict)
    entry: CodeLabel = field(
        default_factory=lambda: CodeLabel(constants.CFG_ENTRY_LABEL)
    )

    def __str__(self) -> str:
        lines = []
        for label, block in self.blocks.items():
            preds = (
                ", ".join(str(p) for p in block.predecessors)
                if block.predecessors
                else "(none)"
            )
            succs = (
                ", ".join(str(s) for s in block.successors)
                if block.successors
                else "(none)"
            )
            lines.append(f"[{label}]  preds={preds}  succs={succs}")
            for inst in block.instructions:
                lines.append(f"  {inst}")
            lines.append("")
        return "\n".join(lines)
