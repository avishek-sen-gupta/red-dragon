# pyright: standard
"""Trace data types for step-by-step execution replay."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING

from interpreter.run_types import ExecutionStats

if TYPE_CHECKING:
    from interpreter.instructions import InstructionBase
    from interpreter.vm.vm_types import StateUpdate, VMState


@dataclass(frozen=True)
class TraceStep:
    """A single step in the execution trace.

    Captures the instruction executed, the state update produced,
    and a deep-copied snapshot of the VMState after the update was applied.
    """

    step_index: int
    block_label: str
    instruction_index: int
    instruction: InstructionBase
    update: StateUpdate
    vm_state: VMState  # deep-copied VMState after applying update
    used_llm: bool


@dataclass(frozen=True)
class ExecutionTrace:
    """Complete trace of an execution run.

    Contains the initial VMState (before any instruction) and a list of
    TraceStep snapshots for each instruction that was actually executed.
    """

    steps: list[TraceStep] = field(default_factory=list)
    stats: ExecutionStats = field(default_factory=ExecutionStats)
    initial_state: VMState | None = None  # VMState before any instruction
