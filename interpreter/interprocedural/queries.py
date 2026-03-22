"""Query interface for interprocedural dataflow analysis results."""

from __future__ import annotations

from collections import deque

from interpreter.interprocedural.types import FlowEndpoint, InterproceduralResult


def impact_of(
    result: InterproceduralResult, target: FlowEndpoint
) -> frozenset[FlowEndpoint]:
    """Forward transitive closure from target. O(1) lookup on pre-computed graph."""
    return result.whole_program_graph.get(target, frozenset())


def taint_reaches(
    result: InterproceduralResult, source: FlowEndpoint, sink: FlowEndpoint
) -> bool:
    """Does source flow to sink (transitively)?"""
    return sink in result.whole_program_graph.get(source, frozenset())


def taint_path(
    result: InterproceduralResult, source: FlowEndpoint, sink: FlowEndpoint
) -> tuple[FlowEndpoint, ...]:
    """Witness path from source to sink via BFS on raw graph.

    Returns tuple of FlowEndpoints on the path (including source and sink).
    Returns empty tuple if no path exists.
    """
    if source == sink:
        return (source,)

    predecessors: dict[FlowEndpoint, FlowEndpoint] = {}
    queue: deque[FlowEndpoint] = deque([source])
    visited: set[FlowEndpoint] = {source}

    while queue:
        current = queue.popleft()
        for neighbour in result.raw_program_graph.get(current, frozenset()):
            if neighbour in visited:
                continue
            predecessors[neighbour] = current
            if neighbour == sink:
                return _reconstruct_path(predecessors, source, sink)
            visited.add(neighbour)
            queue.append(neighbour)

    return ()


def _reconstruct_path(
    predecessors: dict[FlowEndpoint, FlowEndpoint],
    source: FlowEndpoint,
    sink: FlowEndpoint,
) -> tuple[FlowEndpoint, ...]:
    path: list[FlowEndpoint] = []
    current = sink
    while current != source:
        path.append(current)
        current = predecessors[current]
    path.append(source)
    path.reverse()
    return tuple(path)


def backward_slice(
    result: InterproceduralResult, target: FlowEndpoint
) -> frozenset[FlowEndpoint]:
    """All endpoints that contribute to target's value (reverse graph walk)."""
    reverse_graph = _build_reverse_graph(result.raw_program_graph)
    return _reachable_from(reverse_graph, target) - {target}


def forward_slice(
    result: InterproceduralResult, target: FlowEndpoint
) -> frozenset[FlowEndpoint]:
    """All endpoints affected by target's value (uses pre-computed transitive graph)."""
    return result.whole_program_graph.get(target, frozenset())


def _build_reverse_graph(
    graph: dict[FlowEndpoint, frozenset[FlowEndpoint]],
) -> dict[FlowEndpoint, frozenset[FlowEndpoint]]:
    reverse: dict[FlowEndpoint, set[FlowEndpoint]] = {}
    for source, targets in graph.items():
        for target in targets:
            reverse.setdefault(target, set()).add(source)
    return {k: frozenset(v) for k, v in reverse.items()}


def _reachable_from(
    graph: dict[FlowEndpoint, frozenset[FlowEndpoint]],
    start: FlowEndpoint,
) -> frozenset[FlowEndpoint]:
    visited: set[FlowEndpoint] = set()
    queue: deque[FlowEndpoint] = deque([start])
    while queue:
        current = queue.popleft()
        if current in visited:
            continue
        visited.add(current)
        for neighbour in graph.get(current, frozenset()):
            if neighbour not in visited:
                queue.append(neighbour)
    return frozenset(visited)
