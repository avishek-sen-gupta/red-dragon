"""Dataflow summary panel — call graph + per-function flow summaries as a collapsible tree."""

from __future__ import annotations

import logging

from textual.message import Message
from textual.widgets import Tree

from interpreter.interprocedural.types import (
    CallGraph,
    CallSite,
    FieldEndpoint,
    FlowEndpoint,
    FunctionEntry,
    FunctionSummary,
    InterproceduralResult,
    ReturnEndpoint,
    SummaryKey,
    VariableEndpoint,
)

logger = logging.getLogger(__name__)


class FunctionSelected(Message):
    """Posted when a function node is selected in the tree."""

    def __init__(self, label: str) -> None:
        super().__init__()
        self.label = label


def render_endpoint(ep: FlowEndpoint) -> str:
    """Render a FlowEndpoint as a human-readable string."""
    if isinstance(ep, VariableEndpoint):
        return ep.name
    if isinstance(ep, ReturnEndpoint):
        return f"Return({ep.function.label})"
    if isinstance(ep, FieldEndpoint):
        return f"Field({ep.base.name}.{ep.field})"
    return str(ep)


def build_function_callers(func: FunctionEntry, call_graph: CallGraph) -> set[str]:
    """Find labels of all functions that call this function."""
    return {site.caller.label for site in call_graph.call_sites if func in site.callees}


def build_function_callees(func: FunctionEntry, call_graph: CallGraph) -> set[str]:
    """Find labels of all functions called by this function."""
    return {
        callee.label
        for site in call_graph.call_sites
        if site.caller == func
        for callee in site.callees
    }


def merge_flows_for_function(
    func: FunctionEntry,
    summaries: dict[SummaryKey, FunctionSummary],
) -> set[tuple[FlowEndpoint, FlowEndpoint]]:
    """Merge flows across all call contexts for a function."""
    merged: set[tuple[FlowEndpoint, FlowEndpoint]] = set()
    for key, summary in summaries.items():
        if key.function == func:
            merged.update(summary.flows)
    return merged


class DataflowSummaryPanel(Tree):
    """Displays call graph and per-function summaries as a collapsible tree."""

    def __init__(self, result: InterproceduralResult | None = None, **kwargs) -> None:
        super().__init__("Dataflow", **kwargs)
        self._result = result

    def on_mount(self) -> None:
        if self._result is None:
            self.root.add_leaf("[dim]No dataflow analysis available[/dim]")
            return
        self._populate_tree()
        self.root.expand()

    def _populate_tree(self) -> None:
        result = self._result
        call_graph = result.call_graph
        sorted_functions = sorted(call_graph.functions, key=lambda f: f.label)

        for func in sorted_functions:
            params_str = ", ".join(func.params) if func.params else "(none)"
            func_node = self.root.add(
                f"{func.label} (params: {params_str})",
                data=func,
            )

            callers = build_function_callers(func, call_graph)
            callers_str = (
                ", ".join(sorted(str(c) for c in callers)) if callers else "(none)"
            )
            func_node.add_leaf(f"callers: {callers_str}")

            callees = build_function_callees(func, call_graph)
            callees_str = (
                ", ".join(sorted(str(c) for c in callees)) if callees else "(none)"
            )
            func_node.add_leaf(f"callees: {callees_str}")

            flows = merge_flows_for_function(func, result.summaries)
            flows_node = func_node.add(f"Flows ({len(flows)})")
            for src, dst in sorted(flows, key=lambda f: render_endpoint(f[0])):
                flows_node.add_leaf(
                    f"{render_endpoint(src)} \u2192 {render_endpoint(dst)}"
                )

    def on_tree_node_selected(self, event: Tree.NodeSelected) -> None:
        """When a function node is clicked, post FunctionSelected message."""
        node = event.node
        if node.data is not None and isinstance(node.data, FunctionEntry):
            self.post_message(FunctionSelected(node.data.label))
