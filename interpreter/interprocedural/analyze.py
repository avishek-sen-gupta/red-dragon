# pyright: standard
"""Interprocedural analysis entry point — thin orchestrator."""

from __future__ import annotations

from interpreter.cfg_types import CFG
from interpreter.interprocedural.call_graph import build_call_graph
from interpreter.interprocedural.propagation import (
    build_whole_program_graph,
    whole_program_fixpoint,
)
from interpreter.interprocedural.types import InterproceduralResult
from interpreter.registry import FunctionRegistry


def analyze_interprocedural(
    cfg: CFG,
    registry: FunctionRegistry,
) -> InterproceduralResult:
    """Build call graph, compute 1-CFA summaries, produce whole-program dependency graph."""
    call_graph = build_call_graph(cfg, registry)
    summaries = whole_program_fixpoint(cfg, call_graph, registry)
    raw_graph, transitive_graph = build_whole_program_graph(summaries, call_graph, cfg)
    return InterproceduralResult(
        call_graph=call_graph,
        summaries=summaries,
        whole_program_graph=transitive_graph,
        raw_program_graph=raw_graph,
    )
