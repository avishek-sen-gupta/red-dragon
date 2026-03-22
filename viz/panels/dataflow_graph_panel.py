"""Whole-program graph panel — renders interprocedural flow edges with register annotations."""

from __future__ import annotations

import logging
from dataclasses import dataclass, field

from rich.text import Text
from textual.widgets import Static

from interpreter.cfg_types import CFG
from interpreter.interprocedural.call_graph import (
    CALL_OPCODES,
    _build_block_to_function,
)
from interpreter.interprocedural.types import (
    CallGraph,
    FieldEndpoint,
    FlowEndpoint,
    FunctionEntry,
    FunctionSummary,
    InterproceduralResult,
    NO_DEFINITION,
    ReturnEndpoint,
    SummaryKey,
    VariableEndpoint,
)
from interpreter.ir import IRInstruction, Opcode, VAR_DEFINITION_OPCODES
from viz.panels.dataflow_summary_panel import merge_flows_for_function, render_endpoint

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class TopLevelCall:
    """A call instruction in top-level code (not inside any function)."""

    callee_label: str
    arg_operands: tuple[str, ...]
    result_var: str
    block_label: str
    instruction_index: int


@dataclass
class ChainNode:
    """Intermediate tree node for call-chain rendering."""

    label: str
    children: list[ChainNode] = field(default_factory=list)


def trace_reg_to_var(reg: str, cfg: CFG, block_label: str) -> str:
    """Trace a register back to its named variable by scanning the block."""
    block = cfg.blocks[block_label]
    load_match = next(
        (
            str(inst.operands[0])
            for inst in block.instructions
            if inst.opcode == Opcode.LOAD_VAR and inst.result_reg == reg
        ),
        "",
    )
    if load_match:
        return load_match
    store_match = next(
        (
            str(inst.operands[0])
            for inst in block.instructions
            if inst.opcode in VAR_DEFINITION_OPCODES
            and len(inst.operands) >= 2
            and str(inst.operands[1]) == reg
        ),
        "",
    )
    return store_match if store_match else reg


def find_top_level_call_sites(cfg: CFG, call_graph: CallGraph) -> list[TopLevelCall]:
    """Find CALL_FUNCTION/CALL_METHOD instructions in top-level code.

    Scans all blocks NOT owned by any function (using block-to-function mapping).
    These calls are not in call_graph.call_sites because build_call_graph skips
    non-function blocks.
    """
    # Build function-name -> label lookup
    func_by_name: dict[str, str] = {f.label: f.label for f in call_graph.functions}
    func_by_name.update(
        {
            (
                f.label.split("_")[1]
                if f.label.startswith("func_") and "_" in f.label[5:]
                else f.label
            ): f.label
            for f in call_graph.functions
        }
    )

    # Identify top-level blocks: entry block + end_* blocks
    non_func_blocks = {
        label for label in cfg.blocks if label.startswith("end_") or label == "entry"
    }

    return [
        TopLevelCall(
            callee_label=func_by_name.get(
                (
                    str(inst.operands[0])
                    if inst.opcode == Opcode.CALL_FUNCTION
                    else str(inst.operands[1])
                ),
                (
                    str(inst.operands[0])
                    if inst.opcode == Opcode.CALL_FUNCTION
                    else str(inst.operands[1])
                ),
            ),
            arg_operands=(
                tuple(str(op) for op in inst.operands[1:])
                if inst.opcode == Opcode.CALL_FUNCTION
                else tuple(str(op) for op in inst.operands[2:])
            ),
            result_var=(
                trace_reg_to_var(inst.result_reg, cfg, label) if inst.result_reg else ""
            ),
            block_label=label,
            instruction_index=idx,
        )
        for label in non_func_blocks
        for idx, inst in enumerate(cfg.blocks[label].instructions)
        if inst.opcode in (Opcode.CALL_FUNCTION, Opcode.CALL_METHOD)
    ]


def _build_param_map(site, callee: FunctionEntry, cfg: CFG) -> dict[str, str]:
    """Map callee formal params to caller actual arg names."""
    block_label = site.location.block_label
    return {
        formal: trace_reg_to_var(actual_reg, cfg, block_label)
        for formal, actual_reg in zip(callee.params, site.arg_operands)
    }


def _param_inner_calls(
    param: str,
    inner_sites: list,
    cfg: CFG,
) -> list[tuple]:
    """Find inner call sites where this param flows as an argument."""
    return [
        (site, arg_op)
        for site in inner_sites
        for arg_op in site.arg_operands
        if trace_reg_to_var(arg_op, cfg, site.location.block_label) == param
    ]


def build_call_chain(
    func_entry: FunctionEntry,
    call_graph: CallGraph,
    summaries: dict[SummaryKey, FunctionSummary],
    cfg: CFG,
    visited: set[str],
) -> list[ChainNode]:
    """Recursively build a call-chain tree for a function.

    Shows per-param flows: to return (leaf), to field writes (leaf),
    or through inner call sites (recursive subtree).
    """
    if func_entry.label in visited:
        return [ChainNode(label="[recursive — see above]")]
    visited = visited | {func_entry.label}

    flows = merge_flows_for_function(func_entry, summaries)
    inner_sites = [s for s in call_graph.call_sites if s.caller == func_entry]

    def _nodes_for_param(param: str) -> list[ChainNode]:
        inner_calls = _param_inner_calls(param, inner_sites, cfg)
        call_nodes = [
            ChainNode(
                label=f"{param} → {callee.label}({', '.join(f'{p}={v}' for p, v in _build_param_map(site, callee, cfg).items())})",
                children=build_call_chain(callee, call_graph, summaries, cfg, visited),
            )
            for site, arg_op in inner_calls
            for callee in site.callees
        ]
        return_nodes = [
            ChainNode(label=f"{param} → return({func_entry.label})")
            for src, dst in flows
            if isinstance(src, VariableEndpoint)
            and src.name == param
            and isinstance(dst, ReturnEndpoint)
        ]
        field_nodes = [
            ChainNode(label=f"{param} → Field({dst.base.name}.{dst.field})")
            for src, dst in flows
            if isinstance(src, VariableEndpoint)
            and src.name == param
            and isinstance(dst, FieldEndpoint)
        ]
        return call_nodes + return_nodes + field_nodes

    return [node for param in func_entry.params for node in _nodes_for_param(param)]


def annotate_endpoint(ep: FlowEndpoint, cfg: CFG | None) -> str:
    """Render a FlowEndpoint with register annotation for VariableEndpoints.

    Reuses render_endpoint from the summary panel for non-register cases.
    """
    if isinstance(ep, VariableEndpoint):
        name = ep.name
        if name.startswith("%") and ep.definition != NO_DEFINITION:
            opcode = ep.definition.instruction.opcode
            if opcode in (Opcode.CALL_FUNCTION, Opcode.CALL_METHOD):
                callee_name = str(ep.definition.instruction.operands[0])
                return f"{name} (call result: {callee_name})"
        return name
    return render_endpoint(ep)


def render_graph_lines(
    graph: dict[FlowEndpoint, frozenset[FlowEndpoint]],
    cfg: CFG | None,
) -> list[str]:
    """Render graph edges as human-readable lines grouped by source."""
    lines: list[str] = []
    sorted_sources = sorted(graph.keys(), key=lambda ep: annotate_endpoint(ep, cfg))
    for src in sorted_sources:
        src_str = annotate_endpoint(src, cfg)
        dsts = sorted(graph[src], key=lambda ep: annotate_endpoint(ep, cfg))
        for dst in dsts:
            dst_str = annotate_endpoint(dst, cfg)
            lines.append(f"{src_str} → {dst_str}")
    return lines


class DataflowGraphPanel(Static):
    """Displays the whole-program flow graph with annotated edges."""

    def __init__(
        self,
        result: InterproceduralResult | None = None,
        cfg: CFG | None = None,
        **kwargs,
    ) -> None:
        super().__init__(**kwargs)
        self._result = result
        self._cfg = cfg

    def on_mount(self) -> None:
        self._render_graph()

    def _render_graph(self) -> None:
        if self._result is None:
            self.update("[dim]No dataflow analysis available[/dim]")
            return

        graph = self._result.whole_program_graph
        edge_count = sum(len(dsts) for dsts in graph.values())
        lines = render_graph_lines(graph, self._cfg)

        text = Text()
        text.append(
            f"WHOLE-PROGRAM GRAPH ({edge_count} edges)\n\n",
            style="bold magenta",
        )

        for line in lines:
            arrow_idx = line.index("→")
            src_part = line[:arrow_idx]
            dst_part = line[arrow_idx + 1 :].strip()
            text.append(src_part, style="cyan")
            text.append("→ ", style="dim")
            text.append(f"{dst_part}\n", style="yellow")

        self.update(text)
