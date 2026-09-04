#!/usr/bin/env python
"""Measure how DENSE the COBOL field-level dependency graph is.

The memory dataflow analysis (``interpreter/cobol/memory_dataflow.py``) is
deliberately context-insensitive across ``PERFORM``: every call site of a
paragraph shares one CFG entry, so definitions made before one call reach
reads after another. That is sound — it only ever adds edges — but COBOL's
idiom is a handful of shared utility paragraphs performed from dozens of
sites over a flat WORKING-STORAGE with no scoping to contain the spill. If
the merge reconnects everything, an impact query ("what does WS-X affect?")
returns most of the program and the analysis is useless in practice even
though it is correct.

This script measures that, printing:

* node count      — declared fields appearing in the graph
* edge count      — DIRECT edges (before transitive closure)
* mean out-degree — edges / nodes
* connected fraction — of the n*(n-1) ordered field pairs, how many are
  connected after transitive closure. THE HEADLINE NUMBER. 1.0 means every
  field affects every other field and an impact query returns the program.
* the ten fields with the highest in-degree, i.e. the ones the most other
  fields flow into.

Two diagnostics accompany the headline, because a high fraction has two
candidate causes and they lead to different fixes:

* ``--decompose`` splits the direct edges into the two kinds
  ``_build_raw_extent_graph`` produces — VALUE edges (a stored value traced
  back to the extents that produced it: the direct ``MOVE A TO B`` flow,
  present with or without any interprocedural merging) and REACHING edges (a
  read matched against the definitions that reach it: the kind the PERFORM
  context merge inflates).
* the flow-SENSITIVE fraction re-runs the same reachability over def-use
  chains at DEFINITION-SITE granularity instead of one node per field. The
  field graph collapses every write to a field into a single node, so some
  connectivity comes from that collapse rather than from context
  insensitivity. If the flow-sensitive fraction is much lower, node collapse
  is the cause; if it is comparably high, the merge is.

Usage:

    export PROLEAP_BRIDGE_JAR=$PWD/proleap-bridge/target/proleap-bridge-0.1.0-shaded.jar
    uv run python scripts/memory_dataflow_density.py PROG.cbl \\
        --copybook-dir path/to/cpy --copybook-ext cpy --decompose

The extension is passed to ProLeap WITHOUT a leading dot.

This is a diagnostic tool, not part of the analysis.
"""

from __future__ import annotations

import argparse
import logging
import sys
import time
from collections import defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from cobol_asg.cobol_parser import make_cobol_parser  # noqa: E402
from interpreter import constants  # noqa: E402
from interpreter.cfg import CFG, build_cfg  # noqa: E402
from interpreter.cobol.cobol_frontend import CobolFrontend  # noqa: E402
from interpreter.cobol.field_extent import FieldExtent  # noqa: E402
from interpreter.cobol.memory_dataflow import (  # noqa: E402
    EffectKind,
    MemoryAccess,
    _extract_def_use_chains,
    _project_to_fields,
    _trace_to_extents,
    _produced_from,
    rewrite_cfg,
)
from interpreter.cobol.memory_effects import CollectingRecorder  # noqa: E402
from interpreter.dataflow import (  # noqa: E402
    DefUseLink,
    _transitive_closure,
    solve_reaching_definitions,
)

FieldGraph = dict[str, set[str]]


class _TruncationWatch(logging.Handler):
    """Notices the solver giving up before the fixpoint settles.

    ``solve_reaching_definitions`` warns and returns whatever it has when it
    hits ``DATAFLOW_MAX_ITERATIONS``. That result is missing edges, so a
    density measured from it is not a density — it is an artefact of the cap.
    The warning must therefore be surfaced, not left in a log nobody reads.
    """

    def __init__(self) -> None:
        super().__init__()
        self.fired = False

    def emit(self, record: logging.LogRecord) -> None:
        if "did not converge" in record.getMessage():
            self.fired = True


def _nodes(graph: FieldGraph) -> set[str]:
    """Every field mentioned, as a target or as a source."""
    return set(graph) | {dep for deps in graph.values() for dep in deps}


def _edge_count(graph: FieldGraph) -> int:
    return sum(len(deps - {target}) for target, deps in graph.items())


def _connected_pairs(closed: FieldGraph) -> int:
    """Ordered (a, b) pairs, a != b, where a flows into b."""
    return sum(len(deps - {target}) for target, deps in closed.items())


def _value_edges(cfg: CFG, chains: list[DefUseLink]) -> FieldGraph:
    """Target field -> fields its STORED VALUE was traced back to.

    Mirrors the second loop of ``_build_raw_extent_graph``. This edge kind
    needs no reaching definition at all, so it is the part of the graph that
    survives however PERFORM is handled.
    """
    produced_from = _produced_from(chains)
    graph: FieldGraph = {}
    for block in cfg.blocks.values():
        for inst in block.instructions:
            if not isinstance(inst, MemoryAccess):
                continue
            if inst.kind is not EffectKind.WRITE or inst.extent is None:
                continue
            sources: set[FieldExtent] = set()
            _trace_to_extents(inst.value_reg, produced_from, sources, set())
            graph.setdefault(inst.extent.field_name, set()).update(
                s.field_name for s in sources if s.field_name != inst.extent.field_name
            )
    return graph


def _reaching_edges(chains: list[DefUseLink]) -> FieldGraph:
    """Read field -> the fields whose definitions reach that read.

    Mirrors the first loop of ``_build_raw_extent_graph``: the edge kind the
    context-insensitive PERFORM merge inflates, since it is exactly where a
    definition from one call site meets a read from another.
    """
    graph: FieldGraph = {}
    for link in chains:
        used, defined = link.use.variable, link.definition.variable
        if isinstance(used, FieldExtent) and isinstance(defined, FieldExtent):
            if used.field_name != defined.field_name:
                graph.setdefault(used.field_name, set()).add(defined.field_name)
    return graph


def _flow_sensitive_fraction(
    cfg: CFG, chains: list[DefUseLink], fields: list[str]
) -> float:
    """The same impact question asked WITHOUT collapsing a field to one node.

    Nodes are definition SITES — one per (block, instruction index) — so two
    writes to the same field stay distinct and a killed definition genuinely
    stops propagating. An edge ``d -> u`` says the value defined at ``d``
    was read by the instruction at ``u``, so a path is a real chain of
    values. Impact of field X = the fields written by any site reachable
    from a site that READS X.

    Compared against the field-graph fraction, this separates connectivity
    caused by one-node-per-field collapse from connectivity caused by the
    PERFORM context merge.
    """
    if len(fields) < 2:
        return 0.0
    index = {name: i for i, name in enumerate(fields)}

    own: dict[tuple, int] = defaultdict(int)
    seeds: dict[str, set[tuple]] = defaultdict(set)
    for block_label, block in cfg.blocks.items():
        for idx, inst in enumerate(block.instructions):
            site = (block_label, idx)
            written = inst.writes()
            if isinstance(written, FieldExtent) and written.field_name in index:
                own[site] |= 1 << index[written.field_name]
                # Seeded on WRITES as well as reads: "change field X" means
                # change what any statement puts there, and a field whose
                # value is only ever consumed through an ALIASING read (a
                # group written, a child read) is never read under its own
                # name at all. Seeding on reads alone would score such a
                # field as impacting nothing.
                seeds[written.field_name].add(site)
            for read in inst.reads():
                if isinstance(read, FieldExtent) and read.field_name in index:
                    seeds[read.field_name].add(site)

    # Edges carry the field the reaching definition ARRIVED at, so the two
    # edge kinds of the field graph are both represented: a value reaching a
    # write impacts the written field (via ``own`` at the destination), and a
    # definition reaching a READ impacts the read field (via ``extra``).
    # Without the second, a field that is only ever read — very common — could
    # never appear in anyone's impact set and the comparison would be rigged
    # low.
    successors: dict[tuple, list[tuple[tuple, int]]] = defaultdict(list)
    for link in chains:
        src = (link.definition.block_label, link.definition.instruction_index)
        dst = (link.use.block_label, link.use.instruction_index)
        extra = 0
        if isinstance(link.use.variable, FieldExtent):
            name = link.use.variable.field_name
            if name in index:
                extra = 1 << index[name]
        successors[src].append((dst, extra))

    # Fixpoint over a cyclic graph (loops, PERFORM), so iterate.
    reach = dict(own)
    all_sites = (
        set(successors)
        | {d for succs in successors.values() for d, _ in succs}
        | set(own)
    )
    changed = True
    while changed:
        changed = False
        for site in all_sites:
            bits = reach.get(site, 0)
            for succ, extra in successors.get(site, ()):
                bits |= reach.get(succ, 0) | own.get(succ, 0) | extra
            if bits != reach.get(site, 0):
                reach[site] = bits
                changed = True

    connected = 0
    for name in fields:
        bits = 0
        for site in seeds.get(name, ()):
            bits |= reach.get(site, 0)
        bits &= ~(1 << index[name])
        connected += bin(bits).count("1")
    n = len(fields)
    return connected / (n * (n - 1))


def _report(title: str, graph: FieldGraph) -> None:
    nodes = _nodes(graph)
    edges = _edge_count(graph)
    print(f"  {title:<24} nodes={len(nodes):<6} edges={edges}")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("source", type=Path, help="COBOL source file")
    parser.add_argument(
        "--copybook-dir", type=Path, action="append", default=[], dest="copybook_dirs"
    )
    parser.add_argument(
        "--copybook-ext", action="append", default=[], dest="copybook_exts"
    )
    parser.add_argument("--top", type=int, default=10)
    parser.add_argument(
        "--max-iterations",
        type=int,
        default=None,
        help=(
            "override DATAFLOW_MAX_ITERATIONS. The default 1000 counts WORKLIST "
            "POPS, not sweeps, and a real program exhausts it long before the "
            "fixpoint settles; a truncated solve silently UNDER-reports edges, "
            "so a density figure taken from one is not a density figure. The "
            "script says whether the solve converged."
        ),
    )
    parser.add_argument(
        "--decompose",
        action="store_true",
        help="split direct edges into VALUE and REACHING kinds",
    )
    args = parser.parse_args()

    if args.max_iterations is not None:
        constants.DATAFLOW_MAX_ITERATIONS = args.max_iterations

    truncated = _TruncationWatch()
    logging.getLogger("interpreter.dataflow").addHandler(truncated)
    logging.getLogger("interpreter.dataflow").setLevel(logging.WARNING)

    started = time.monotonic()
    recorder = CollectingRecorder()
    frontend = CobolFrontend(
        make_cobol_parser(
            copybook_dirs=list(args.copybook_dirs),
            copybook_exts=list(args.copybook_exts),
        ),
        recorder=recorder,
    )
    ir = frontend.lower(args.source.read_bytes())
    parsed_at = time.monotonic()

    cfg = build_cfg(ir)
    rewritten = rewrite_cfg(cfg, recorder.effects)
    chains = _extract_def_use_chains(rewritten, solve_reaching_definitions(rewritten))
    solved_at = time.monotonic()

    value = _value_edges(rewritten, chains)
    reaching = _reaching_edges(chains)
    direct: FieldGraph = {}
    for part in (value, reaching):
        for target, deps in part.items():
            direct.setdefault(target, set()).update(deps)
    closed = _transitive_closure(direct)
    closed_at = time.monotonic()

    nodes = sorted(_nodes(direct))
    n = len(nodes)
    edges = _edge_count(direct)
    pairs = n * (n - 1)
    connected = _connected_pairs(closed)

    print(f"program              {args.source.name}")
    print(
        "solver converged     "
        + (
            "NO — truncated at the iteration cap, edges are MISSING"
            if truncated.fired
            else "yes"
        )
    )
    print(f"IR instructions      {len(ir)}")
    print(f"recorded effects     {len(recorder.effects)}")
    print(
        f"declared fields hit  {len({e.extent.field_name for e in recorder.effects.values()})}"
    )
    print()
    print(f"nodes (fields)       {n}")
    print(f"edges (direct)       {edges}")
    print(f"mean out-degree      {edges / n if n else 0:.2f}")
    print(f"connected pairs      {connected} / {pairs}")
    print(
        "CONNECTED FRACTION   "
        f"{connected / pairs if pairs else 0:.4f}"
        "   (after transitive closure)"
    )
    print()

    fs = _flow_sensitive_fraction(rewritten, chains, nodes)
    print(f"flow-sensitive frac  {fs:.4f}   (def-site nodes, no field collapse)")
    print()

    if args.decompose:
        print("edge decomposition (direct):")
        _report("VALUE edges", value)
        _report("REACHING edges", reaching)
        value_only = _transitive_closure(value)
        vp = _connected_pairs(value_only)
        vn = len(_nodes(value))
        print(
            f"  VALUE-only closure     fraction="
            f"{vp / (vn * (vn - 1)) if vn > 1 else 0:.4f} over {vn} nodes"
        )
        print()

    in_degree = {name: len(direct.get(name, set()) - {name}) for name in nodes}
    out_degree = defaultdict(int)
    for target, deps in direct.items():
        for dep in deps - {target}:
            out_degree[dep] += 1
    # The connected fraction averages over pairs, but an impact query is
    # asked about ONE field: "I change WS-X, what breaks?" The answer is the
    # forward closure of that field, so its DISTRIBUTION decides usability. A
    # graph can have a low mean and still be useless if the fields anyone
    # actually asks about are the ones that reach everything.
    impact: dict[str, set[str]] = defaultdict(set)
    for target, deps in closed.items():
        for dep in deps - {target}:
            impact[dep].add(target)
    sizes = sorted((len(impact.get(name, ())) for name in nodes), reverse=True)
    median = sizes[len(sizes) // 2] if sizes else 0
    print("impact-set size (fields reached FROM a field, after closure):")
    print(
        f"  max {sizes[0] if sizes else 0}  median {median}  "
        f"mean {sum(sizes) / n if n else 0:.1f}  of {n} fields"
    )
    print(f"top {args.top} fields by IMPACT (how many fields they reach):")
    for name in sorted(nodes, key=lambda f: (-len(impact.get(f, ())), f))[: args.top]:
        print(f"  {len(impact.get(name, ())):>5} reached   {name}")
    print()

    print(f"top {args.top} fields by IN-degree (how many fields flow INTO them):")
    for name in sorted(nodes, key=lambda f: (-in_degree[f], f))[: args.top]:
        print(
            f"  {in_degree[name]:>5} in  {out_degree[name]:>5} out  "
            f"{len(closed.get(name, set())):>5} closed-in  {name}"
        )
    print()
    print(
        f"timing  parse+lower {parsed_at - started:.1f}s  "
        f"solve {solved_at - parsed_at:.1f}s  "
        f"graph+closure {closed_at - solved_at:.1f}s"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
