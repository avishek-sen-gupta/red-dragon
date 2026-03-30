"""Interprocedural dataflow analysis data types — all frozen, all hashable."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Union

from interpreter.cfg_types import BasicBlock, CFG
from interpreter.dataflow import Definition
from interpreter.field_name import FieldName
from interpreter.ir import IRInstruction, Opcode, CodeLabel, NO_LABEL
from interpreter.instructions import InstructionBase

# ---------------------------------------------------------------------------
# 1. InstructionLocation — hashable reference to an IR instruction
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class InstructionLocation:
    """Hashable coordinate that resolves to an IRInstruction via CFG lookup."""

    block_label: CodeLabel
    instruction_index: int

    def resolve(self, cfg: CFG) -> InstructionBase:
        return cfg.blocks[self.block_label].instructions[self.instruction_index]


NO_INSTRUCTION_LOC = InstructionLocation(block_label=NO_LABEL, instruction_index=-1)


# ---------------------------------------------------------------------------
# 2. FunctionEntry — a resolved function in the program
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class FunctionEntry:
    """A function known to the analysis, identified by its CFG entry label."""

    label: CodeLabel
    params: tuple[str, ...]

    def entry_block(self, cfg: CFG) -> BasicBlock:
        return cfg.blocks[self.label]


# ---------------------------------------------------------------------------
# 3. FlowEndpoints — what flows where
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class VariableEndpoint:
    """A variable at a specific definition point."""

    name: str
    definition: Definition

    def __hash__(self) -> int:
        return hash((self.name, self.definition))

    def __eq__(self, other: object) -> bool:
        if not isinstance(other, VariableEndpoint):
            return NotImplemented
        return self.name == other.name and self.definition == other.definition


@dataclass(frozen=True)
class FieldEndpoint:
    """A field access (STORE_FIELD / LOAD_FIELD) on an object variable."""

    base: VariableEndpoint
    field: FieldName
    location: InstructionLocation

    def __hash__(self) -> int:
        return hash((self.base, self.field, self.location))

    def __eq__(self, other: object) -> bool:
        if not isinstance(other, FieldEndpoint):
            return NotImplemented
        return (
            self.base == other.base
            and self.field == other.field
            and self.location == other.location
        )


@dataclass(frozen=True)
class ReturnEndpoint:
    """A return point from a function."""

    function: FunctionEntry
    location: InstructionLocation


@dataclass(frozen=True)
class DereferenceEndpoint:
    """A pointer dereference (*ptr) — read or write through a pointer variable."""

    base: VariableEndpoint
    location: InstructionLocation

    def __hash__(self) -> int:
        return hash((self.base, self.location))

    def __eq__(self, other: object) -> bool:
        if not isinstance(other, DereferenceEndpoint):
            return NotImplemented
        return self.base == other.base and self.location == other.location


FlowEndpoint = Union[
    VariableEndpoint, FieldEndpoint, ReturnEndpoint, DereferenceEndpoint
]


# ---------------------------------------------------------------------------
# 4. CallSite — a specific call instruction
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class CallSite:
    """A call instruction at a specific location, with resolved callees."""

    caller: FunctionEntry
    location: InstructionLocation
    callees: frozenset[FunctionEntry]
    arg_operands: tuple[str, ...]

    def instruction(self, cfg: CFG) -> InstructionBase:
        return self.location.resolve(cfg)

    def block(self, cfg: CFG) -> BasicBlock:
        return cfg.blocks[self.location.block_label]


# ---------------------------------------------------------------------------
# 5. CallContext — 1-CFA context key
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class CallContext:
    """Context key for 1-CFA: identifies which call site invoked the function."""

    site: CallSite


ROOT_CONTEXT = CallContext(
    site=CallSite(
        caller=FunctionEntry(label=CodeLabel("__root__"), params=()),
        location=NO_INSTRUCTION_LOC,
        callees=frozenset(),
        arg_operands=(),
    )
)


# ---------------------------------------------------------------------------
# 6. FunctionSummary — how data flows through a function
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class FunctionSummary:
    """Summary of data flows through a function at a specific call context."""

    function: FunctionEntry
    context: CallContext
    flows: frozenset[tuple[FlowEndpoint, FlowEndpoint]]


# ---------------------------------------------------------------------------
# 7. SummaryKey — dict key for looking up summaries
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class SummaryKey:
    """Composite key: function + context."""

    function: FunctionEntry
    context: CallContext


# ---------------------------------------------------------------------------
# 8. CallGraph — all functions and call sites
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class CallGraph:
    """The program's call graph: functions and edges (call sites)."""

    functions: frozenset[FunctionEntry]
    call_sites: frozenset[CallSite]


# ---------------------------------------------------------------------------
# 9. InterproceduralResult — the complete analysis output
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class InterproceduralResult:
    """Complete output of interprocedural analysis."""

    call_graph: CallGraph
    summaries: dict[SummaryKey, FunctionSummary]
    whole_program_graph: dict[FlowEndpoint, frozenset[FlowEndpoint]]
    raw_program_graph: dict[FlowEndpoint, frozenset[FlowEndpoint]]


# ---------------------------------------------------------------------------
# 10. NO_DEFINITION sentinel
# ---------------------------------------------------------------------------

_SENTINEL_INSTRUCTION = IRInstruction(opcode=Opcode.CONST, operands=[])

NO_DEFINITION = Definition(
    variable="",
    block_label=NO_LABEL,
    instruction_index=-1,
    instruction=_SENTINEL_INSTRUCTION,
)
