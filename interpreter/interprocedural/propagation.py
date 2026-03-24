"""Interprocedural whole-program propagation with SCC fixpoint.

Computes strongly connected components of the call graph, iterates summaries
to a fixpoint within each SCC, and builds whole-program flow graphs.
"""

from __future__ import annotations

import logging
from collections import defaultdict

from interpreter import constants
from interpreter.cfg_types import CFG
from interpreter.ir import Opcode
from interpreter.instructions import to_typed, LoadVar, DeclVar, StoreVar
from interpreter.interprocedural.summaries import build_summary
from interpreter.interprocedural.types import (
    CallContext,
    CallGraph,
    CallSite,
    FieldEndpoint,
    FlowEndpoint,
    FunctionEntry,
    FunctionSummary,
    InstructionLocation,
    NO_DEFINITION,
    ReturnEndpoint,
    SummaryKey,
    VariableEndpoint,
)
from interpreter.registry import FunctionRegistry

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# 1. SCC computation — Kosaraju's algorithm
# ---------------------------------------------------------------------------


def compute_sccs(call_graph: CallGraph) -> list[frozenset[FunctionEntry]]:
    """Compute SCCs of the call graph in reverse topological order (leaves first).

    Uses Kosaraju's algorithm:
    1. DFS on original graph, record finish order
    2. Transpose graph (reverse edges)
    3. DFS on transpose in reverse finish order → each tree is an SCC
    """
    adjacency = _build_adjacency(call_graph)
    all_functions = list(call_graph.functions)

    # Pass 1: DFS on original graph, record finish order
    finish_order = _dfs_finish_order(all_functions, adjacency)

    # Pass 2: DFS on transposed graph in reverse finish order
    transposed = _transpose_adjacency(all_functions, adjacency)
    sccs_topo = _dfs_collect_sccs(finish_order, transposed)
    # Kosaraju yields topological order (roots first); reverse for leaves first
    sccs_topo.reverse()
    return sccs_topo


def _build_adjacency(
    call_graph: CallGraph,
) -> dict[FunctionEntry, frozenset[FunctionEntry]]:
    """Build caller → callees adjacency map from call sites."""
    adj: dict[FunctionEntry, set[FunctionEntry]] = {
        f: set() for f in call_graph.functions
    }
    for site in call_graph.call_sites:
        if site.caller in adj:
            adj[site.caller].update(site.callees & call_graph.functions)
    return {k: frozenset(v) for k, v in adj.items()}


def _dfs_finish_order(
    functions: list[FunctionEntry],
    adjacency: dict[FunctionEntry, frozenset[FunctionEntry]],
) -> list[FunctionEntry]:
    """DFS on all nodes, return nodes in finish order (first finished first)."""
    visited: set[FunctionEntry] = set()
    finish_order: list[FunctionEntry] = []

    # Use an explicit stack to avoid Python recursion limits
    for start in functions:
        if start in visited:
            continue
        # Stack entries: (node, is_postvisit)
        stack: list[tuple[FunctionEntry, bool]] = [(start, False)]
        while stack:
            node, is_post = stack.pop()
            if is_post:
                finish_order.append(node)
                continue
            if node in visited:
                continue
            visited.add(node)
            stack.append((node, True))
            for neighbour in adjacency.get(node, frozenset()):
                if neighbour not in visited:
                    stack.append((neighbour, False))

    return finish_order


def _transpose_adjacency(
    functions: list[FunctionEntry],
    adjacency: dict[FunctionEntry, frozenset[FunctionEntry]],
) -> dict[FunctionEntry, frozenset[FunctionEntry]]:
    """Reverse all edges in the adjacency map."""
    transposed: dict[FunctionEntry, set[FunctionEntry]] = {f: set() for f in functions}
    for src, dsts in adjacency.items():
        for dst in dsts:
            if dst in transposed:
                transposed[dst].add(src)
    return {k: frozenset(v) for k, v in transposed.items()}


def _dfs_collect_sccs(
    finish_order: list[FunctionEntry],
    transposed: dict[FunctionEntry, frozenset[FunctionEntry]],
) -> list[frozenset[FunctionEntry]]:
    """DFS on transposed graph in reverse finish order. Each DFS tree = one SCC."""
    visited: set[FunctionEntry] = set()
    sccs: list[frozenset[FunctionEntry]] = []

    for start in reversed(finish_order):
        if start in visited:
            continue
        # Collect all reachable nodes from start in transposed graph
        component: set[FunctionEntry] = set()
        stack = [start]
        while stack:
            node = stack.pop()
            if node in visited:
                continue
            visited.add(node)
            component.add(node)
            for neighbour in transposed.get(node, frozenset()):
                if neighbour not in visited:
                    stack.append(neighbour)
        sccs.append(frozenset(component))

    return sccs


# ---------------------------------------------------------------------------
# 2. Argument substitution at call sites
# ---------------------------------------------------------------------------


def _trace_reg_to_var(reg: str, cfg: CFG, block_label: str) -> str:
    """Trace a register back to its named variable by scanning the block for LOAD_VAR/STORE_VAR.

    If the register was produced by LOAD_VAR x → %reg, return "x".
    If the register is the result_reg of a CALL_*, scan for STORE_VAR/DECL_VAR that consumes it.
    Falls back to the register name itself if no named variable found.
    """
    block = cfg.blocks.get(block_label)
    if block is None:
        return reg
    # Scan for LOAD_VAR that produces this register
    for inst in block.instructions:
        if inst.opcode == Opcode.LOAD_VAR and inst.result_reg == reg:
            t = to_typed(inst)
            assert isinstance(t, LoadVar)
            return str(t.name)
    # Scan for DECL_VAR/STORE_VAR that consumes this register
    for inst in block.instructions:
        if (
            inst.opcode in (Opcode.DECL_VAR, Opcode.STORE_VAR)
            and len(inst.operands) >= 2
        ):
            t = to_typed(inst)
            assert isinstance(t, (DeclVar, StoreVar))
            if str(t.value_reg) == reg:
                return str(t.name)
    return reg


def _substitute_endpoint(
    endpoint: FlowEndpoint,
    param_to_actual: dict[str, str],
    callee: FunctionEntry,
    call_site: CallSite,
    cfg: CFG,
) -> FlowEndpoint:
    """Substitute formal parameter names with actual argument names (traced to variables)."""
    if isinstance(endpoint, VariableEndpoint):
        raw_reg = param_to_actual.get(endpoint.name, endpoint.name)
        traced_name = _trace_reg_to_var(raw_reg, cfg, call_site.location.block_label)
        return VariableEndpoint(name=traced_name, definition=NO_DEFINITION)

    if isinstance(endpoint, FieldEndpoint):
        new_base = _substitute_endpoint(
            endpoint.base, param_to_actual, callee, call_site, cfg
        )
        assert isinstance(new_base, VariableEndpoint)
        return FieldEndpoint(
            base=new_base,
            field=endpoint.field,
            location=endpoint.location,
        )

    if isinstance(endpoint, ReturnEndpoint):
        # Return endpoint maps to the variable that receives the call result
        result_reg = _call_site_result_reg(call_site, cfg)
        traced_name = _trace_reg_to_var(result_reg, cfg, call_site.location.block_label)
        return VariableEndpoint(name=traced_name, definition=NO_DEFINITION)

    # Exhaustive — all FlowEndpoint variants handled
    raise TypeError(f"Unknown endpoint type: {type(endpoint)}")


def _call_site_result_reg(
    call_site: CallSite, cfg: CFG = CFG(blocks={}, entry="")
) -> str:
    """Get the result register for a call site from the actual instruction."""
    block = cfg.blocks.get(call_site.location.block_label)
    if block is not None and call_site.location.instruction_index < len(
        block.instructions
    ):
        inst = block.instructions[call_site.location.instruction_index]
        if inst.result_reg.is_present():
            return str(inst.result_reg)
    loc = call_site.location
    return f"%call_{loc.block_label}_{loc.instruction_index}"


def apply_summary_at_call_site(
    call_site: CallSite,
    summary: FunctionSummary,
    callee: FunctionEntry,
    cfg: CFG = CFG(blocks={}, entry=""),
) -> frozenset[tuple[FlowEndpoint, FlowEndpoint]]:
    """Substitute formal params with actual args in a summary's flows.

    Given a call site where caller passes arg_operands mapping to callee params,
    rewrite each flow endpoint to use the caller's named variables (traced from registers).
    """
    params = callee.params
    actuals = call_site.arg_operands

    # Build param name → actual register mapping
    param_to_actual = dict(zip(params, actuals))

    return frozenset(
        (
            _substitute_endpoint(src, param_to_actual, callee, call_site, cfg),
            _substitute_endpoint(dst, param_to_actual, callee, call_site, cfg),
        )
        for src, dst in summary.flows
    )


# ---------------------------------------------------------------------------
# 3. Whole-program fixpoint
# ---------------------------------------------------------------------------


def _build_callee_to_sites(
    call_graph: CallGraph,
) -> dict[FunctionEntry, list[CallSite]]:
    """Map each callee to the call sites that invoke it."""
    result: dict[FunctionEntry, list[CallSite]] = defaultdict(list)
    for site in call_graph.call_sites:
        for callee in site.callees:
            result[callee].append(site)
    return dict(result)


def whole_program_fixpoint(
    cfg: CFG,
    call_graph: CallGraph,
    registry: FunctionRegistry,
) -> dict[SummaryKey, FunctionSummary]:
    """Compute all function summaries with 1-CFA context sensitivity.

    Processes SCCs in reverse topological order. Within each SCC, iterates
    until all summaries stabilize (or DATAFLOW_MAX_ITERATIONS is reached).
    """
    sccs = compute_sccs(call_graph)
    callee_to_sites = _build_callee_to_sites(call_graph)
    summaries: dict[SummaryKey, FunctionSummary] = {}

    for scc in sccs:
        logger.info("Processing SCC: %s", {f.label for f in scc})
        _fixpoint_scc(cfg, scc, callee_to_sites, summaries)

    return summaries


def _fixpoint_scc(
    cfg: CFG,
    scc: frozenset[FunctionEntry],
    callee_to_sites: dict[FunctionEntry, list[CallSite]],
    summaries: dict[SummaryKey, FunctionSummary],
) -> None:
    """Iterate summary computation for an SCC until stable."""
    for iteration in range(constants.DATAFLOW_MAX_ITERATIONS):
        changed = False

        for func in scc:
            sites = callee_to_sites.get(func, [])

            # If no call sites invoke this function, compute with ROOT context
            contexts = (
                [CallContext(site=site) for site in sites]
                if sites
                else [_root_context()]
            )

            for ctx in contexts:
                key = SummaryKey(function=func, context=ctx)
                new_summary = build_summary(cfg, func, ctx)

                old_summary = summaries.get(key)
                if old_summary is None or old_summary.flows != new_summary.flows:
                    summaries[key] = new_summary
                    changed = True

        if not changed:
            logger.info("SCC stabilized after %d iterations", iteration + 1)
            return

    logger.warning(
        "SCC did not stabilize after %d iterations",
        constants.DATAFLOW_MAX_ITERATIONS,
    )


def _root_context() -> CallContext:
    """Build the ROOT call context for functions with no known callers."""
    from interpreter.interprocedural.types import ROOT_CONTEXT

    return ROOT_CONTEXT


# ---------------------------------------------------------------------------
# 4. Whole-program graph construction
# ---------------------------------------------------------------------------


def build_whole_program_graph(
    summaries: dict[SummaryKey, FunctionSummary],
    call_graph: CallGraph,
    cfg: CFG = CFG(blocks={}, entry=""),
) -> tuple[
    dict[FlowEndpoint, frozenset[FlowEndpoint]],
    dict[FlowEndpoint, frozenset[FlowEndpoint]],
]:
    """Build raw and transitive whole-program flow graphs.

    Raw graph: direct edges from summaries + propagated call-site edges.
    Transitive graph: transitive closure of the raw graph.
    """
    raw_edges: dict[FlowEndpoint, set[FlowEndpoint]] = defaultdict(set)

    # Add all summary flows directly
    for summary in summaries.values():
        for src, dst in summary.flows:
            raw_edges[src].add(dst)

    # Add propagated edges at each call site
    for site in call_graph.call_sites:
        for callee in site.callees:
            callee_summaries = [s for s in summaries.values() if s.function == callee]
            for summary in callee_summaries:
                propagated = apply_summary_at_call_site(site, summary, callee, cfg)
                for src, dst in propagated:
                    raw_edges[src].add(dst)

    raw_graph = {k: frozenset(v) for k, v in raw_edges.items()}
    transitive_graph = _transitive_closure(raw_graph)

    return raw_graph, transitive_graph


def _transitive_closure(
    graph: dict[FlowEndpoint, frozenset[FlowEndpoint]],
) -> dict[FlowEndpoint, frozenset[FlowEndpoint]]:
    """Compute transitive closure of a directed graph via BFS from each node."""
    result: dict[FlowEndpoint, frozenset[FlowEndpoint]] = {}

    for start in graph:
        reachable: set[FlowEndpoint] = set()
        stack = list(graph.get(start, frozenset()))
        while stack:
            node = stack.pop()
            if node in reachable:
                continue
            reachable.add(node)
            stack.extend(graph.get(node, frozenset()))
        result[start] = frozenset(reachable)

    return result
