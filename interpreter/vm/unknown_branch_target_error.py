"""An instruction transferred control to a label that names no block in the CFG."""

from __future__ import annotations

from interpreter.ir import CodeLabel


class UnknownBranchTargetError(LookupError):
    def __init__(self, source: CodeLabel, target: CodeLabel) -> None:
        super().__init__(f"branch from {source} to unknown label {target}")
        self.source = source
        self.target = target
