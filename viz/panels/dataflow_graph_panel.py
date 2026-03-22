"""Whole-program graph panel — renders interprocedural flow edges with register annotations."""

from __future__ import annotations

import logging

from rich.text import Text
from textual.widgets import Static

from interpreter.cfg_types import CFG
from interpreter.interprocedural.types import (
    FlowEndpoint,
    InterproceduralResult,
    NO_DEFINITION,
    VariableEndpoint,
)
from interpreter.ir import Opcode
from viz.panels.dataflow_summary_panel import render_endpoint

logger = logging.getLogger(__name__)


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
