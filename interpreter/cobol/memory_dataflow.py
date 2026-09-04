# pyright: standard
"""Field-level dependency graph over COBOL memory.

The register/variable dataflow in ``interpreter.dataflow`` cannot see COBOL
fields: a field is not a variable but a byte slice of a region buffer, and
``WriteRegion`` reports no ``writes()`` at all. Everything a COBOL program
actually computes therefore vanished from that analysis.

This module puts it back. It does NOT re-implement reaching definitions:
instead it REWRITES each region instruction into an equivalent whose
``writes()``/``reads()`` speak in ``FieldExtent`` terms, and then runs the
existing fixpoint over the rewritten CFG. ``FieldExtent`` satisfies the
``StorageIdentifier`` protocol structurally, so GEN/KILL and use matching
dispatch through ``may_alias``/``must_cover`` exactly as they already do for
registers — group containment, REDEFINES, OCCURS and reference modification
all fall out of byte-range overlap with no rule for any of them.

Registers and extents coexist in one analysis, which is not an accident:
``%4 = LOAD_REGION ws, 10, 5`` defines a REGISTER from an EXTENT, so a chain
crosses between the two worlds at every read and every write.

The governing asymmetry, which every decision here follows:

* ``may_alias`` over-approximates. An edge dropped because two extents were
  wrongly judged disjoint is invisible — no error, just a quietly incomplete
  report. When unsure, keep the edge.
* ``must_cover`` under-approximates. Only an EXACT extent may kill a
  definition; a CLAMPED one (computed subscript) never does.

Accepted imprecision, all asserted in ``tests/unit/cobol/test_memory_dataflow``:

* Context-insensitive PERFORM: all call sites of a paragraph share one CFG
  entry, so definitions live before one call reach reads after another.
  Upgrade path is per-paragraph summaries.
* Field-name projection is flow-insensitive: the graph has one node per
  field, so ``A -> B`` and a later ``C -> A`` make B look dependent on C.
  This is the same property the existing ``dependency_graph`` has, and it is
  inherent in the requested ``dict[str, set[str]]`` shape.
"""

from __future__ import annotations

import logging
from collections.abc import Iterable
from dataclasses import dataclass, field
from typing import Any

from interpreter.cfg import CFG, BasicBlock
from interpreter.cobol.field_extent import FieldExtent
from interpreter.cobol.memory_effects import EffectKind, MemoryEffect
from interpreter.dataflow import (
    BlockDataflowFacts,
    Definition,
    DefUseLink,
    Use,
    _transitive_closure,
    solve_reaching_definitions,
)
from interpreter.instructions import (
    InstructionBase,
    InstructionId,
    LoadRegion,
    WriteRegion,
)
from interpreter.ir import CodeLabel, Opcode, SourceLocation
from interpreter.register import NO_REGISTER, Register
from interpreter.storage_identifier import StorageIdentifier

logger = logging.getLogger(__name__)


@dataclass
class MemoryDataflowResult:
    """Who feeds whom, at three levels of resolution.

    ``extent_graph`` is the precise answer (byte ranges); ``field_graph`` is
    the one a human reads (declared names); ``edge_locations`` says which
    statements produced each named edge, and carries only DIRECT edges — a
    transitive edge was produced by no single statement.
    """

    extent_graph: dict[FieldExtent, set[FieldExtent]]
    field_graph: dict[str, set[str]]
    edge_locations: dict[tuple[str, str], list[SourceLocation]]


@dataclass(frozen=True)
class MemoryAccess(InstructionBase):
    """A region access re-expressed as an access to a ``FieldExtent``.

    Substituted 1:1 for the ``LoadRegion``/``WriteRegion`` it stands for, so
    block structure, indices and control flow are untouched.

    A READ defines its result REGISTER and uses the EXTENT; a WRITE defines
    the EXTENT and uses the value REGISTER. Only the value register is
    reported as a use: the region and offset registers say WHERE the access
    lands, not WHAT it stores, and threading them in would make every field
    depend on the region handle and on every subscript ever computed. Extent
    aliasing already carries the positional information those registers
    encode, at the only resolution the analysis can act on.
    """

    origin: InstructionBase | None = None
    extent: FieldExtent | None = None
    kind: EffectKind = EffectKind.READ
    value_reg: Register = NO_REGISTER

    def writes(self) -> StorageIdentifier | None:
        if self.kind is EffectKind.WRITE:
            return self.extent
        return self.result_reg if self.result_reg.is_present() else None

    def reads(self) -> list[StorageIdentifier]:
        if self.kind is EffectKind.WRITE:
            return [self.value_reg] if self.value_reg.is_present() else []
        return [self.extent] if self.extent is not None else []

    @property
    def opcode(self) -> Opcode:
        assert self.origin is not None
        return self.origin.opcode

    @property
    def operands(self) -> list[Any]:
        assert self.origin is not None
        return self.origin.operands


def _substitute(
    inst: InstructionBase, effects: dict[InstructionId, MemoryEffect]
) -> InstructionBase:
    """Replace a recorded region access with its extent-level equivalent."""
    effect = effects.get(inst.id)
    if effect is None:
        return inst
    if isinstance(inst, LoadRegion):
        return MemoryAccess(
            source_location=inst.source_location,
            result_reg=inst.result_reg,
            id=inst.id,
            origin=inst,
            extent=effect.extent,
            kind=EffectKind.READ,
        )
    if isinstance(inst, WriteRegion):
        return MemoryAccess(
            source_location=inst.source_location,
            id=inst.id,
            origin=inst,
            extent=effect.extent,
            kind=EffectKind.WRITE,
            value_reg=inst.value_reg,
        )
    # An effect recorded against something that is not a region access means
    # the funnel has been bypassed; the analysis cannot interpret it.
    raise AssertionError(
        f"memory effect recorded against a non-region instruction: {inst!r}"
    )


def rewrite_cfg(cfg: CFG, effects: dict[InstructionId, MemoryEffect]) -> CFG:
    """Copy the CFG, substituting region accesses for extent accesses.

    Block-by-block, carrying the label, successors, predecessors and entry
    across verbatim. It must NOT round-trip through ``build_cfg``: that
    partitions a flat instruction stream and strips each block's leading
    ``Label_``, so re-flattening ``block.instructions`` yields a stream with
    no labels at all. Every block is then renamed ``__block_N``, the
    ``if target in cfg.blocks`` guard on edge wiring never fires, and the
    result has ZERO edges — ``reach_in`` empty everywhere, the analysis
    silently degenerated to intra-block, and every cross-block aliasing edge
    gone without a word. Guarded by
    ``test_the_rewritten_cfg_keeps_every_control_flow_edge``.

    The substitution is per-instruction and changes no control flow, so
    control flow should not be re-derived here at all.
    """
    rewritten = CFG(entry=cfg.entry)
    for label, block in cfg.blocks.items():
        rewritten.blocks[label] = BasicBlock(
            label=block.label,
            instructions=[_substitute(inst, effects) for inst in block.instructions],
            successors=list(block.successors),
            predecessors=list(block.predecessors),
        )
    return rewritten


def _extract_def_use_chains(
    cfg: CFG, block_facts: dict[CodeLabel, BlockDataflowFacts]
) -> list[DefUseLink]:
    """Match each use against the definitions that can reach it.

    Deliberately NOT ``interpreter.dataflow.extract_def_use_chains``. That one
    shadows by dict identity: if the block has already defined exactly this
    location, the incoming definitions are skipped entirely. For a register
    that is right, because a register write replaces the whole register. For
    an extent it drops edges: writing three bytes of a hundred-byte record
    does not hide what flowed into the other ninety-seven.

    So local definitions are kept as a forward-simulated list (a new write
    removes only the priors it ``must_cover``), and ``reach_in`` is consulted
    unless some local write ``must_cover``s the use outright.
    """
    chains: list[DefUseLink] = []

    for label, block in cfg.blocks.items():
        reach_in = block_facts[label].reach_in
        local: list[Definition] = []

        for idx, inst in enumerate(block.instructions):
            for var in inst.reads():
                use = Use(
                    variable=var,
                    block_label=label,
                    instruction_index=idx,
                    instruction=inst,
                )
                chains.extend(
                    DefUseLink(definition=d, use=use)
                    for d in local
                    if d.variable.may_alias(var)
                )
                if not any(d.variable.must_cover(var) for d in local):
                    chains.extend(
                        DefUseLink(definition=d, use=use)
                        for d in reach_in
                        if d.variable.may_alias(var)
                    )

            written = inst.writes()
            if written is not None:
                local = [p for p in local if not written.must_cover(p.variable)]
                local.append(
                    Definition(
                        variable=written,
                        block_label=label,
                        instruction_index=idx,
                        instruction=inst,
                    )
                )

    return chains


def _produced_from(
    chains: Iterable[DefUseLink],
) -> dict[StorageIdentifier, set[StorageIdentifier]]:
    """location -> the locations its defining instructions read."""
    produced: dict[StorageIdentifier, set[StorageIdentifier]] = {}
    for link in chains:
        key = link.definition.variable
        produced.setdefault(key, set()).update(link.definition.instruction.reads())
    return produced


def _trace_to_extents(
    identifier: StorageIdentifier,
    produced_from: dict[StorageIdentifier, set[StorageIdentifier]],
    result: set[FieldExtent],
    visited: set[StorageIdentifier],
) -> None:
    """Walk a value backwards until it lands in memory.

    ``FieldExtent`` is the leaf — this is the extension hazard 3 names: a
    register chain must terminate at an extent as well as at a name, or
    ``%4 = LOAD_REGION ws, 10, 5`` never bridges back to the field at those
    bytes and the whole graph is empty.

    ``VarName`` is NOT a leaf here, unlike in the register analysis. COBOL
    has no user-level variables: every declared field is an extent, so a name
    reaching this point is a lowering temporary and the value continues
    through it.
    """
    if isinstance(identifier, FieldExtent):
        result.add(identifier)
        return
    if identifier in visited:
        return
    visited.add(identifier)
    for source in produced_from.get(identifier, set()):
        _trace_to_extents(source, produced_from, result, visited)


@dataclass
class _RawGraph:
    edges: dict[FieldExtent, set[FieldExtent]] = field(default_factory=dict)
    locations: dict[tuple[FieldExtent, FieldExtent], list[SourceLocation]] = field(
        default_factory=dict
    )

    def add(
        self, target: FieldExtent, source: FieldExtent, where: SourceLocation | None
    ) -> None:
        self.edges.setdefault(target, set()).add(source)
        if where is not None:
            self.locations.setdefault((source, target), []).append(where)


def _build_raw_extent_graph(cfg: CFG, chains: list[DefUseLink]) -> _RawGraph:
    """Two edge kinds, and both are needed.

    * VALUE edges: a write's extent depends on every extent its stored value
      was traced back to. This is the direct ``MOVE A TO B`` flow.
    * REACHING edges: a read's extent depends on the definitions that reach
      it. This is what makes containment work in both directions —
      ``MOVE X TO WS-REC`` then ``MOVE WS-NAME TO Y`` links only because the
      read of the child is matched against the definition of the group.
    """
    raw = _RawGraph()
    produced_from = _produced_from(chains)

    for link in chains:
        definition, use = link.definition, link.use

        if isinstance(use.variable, FieldExtent) and isinstance(
            definition.variable, FieldExtent
        ):
            raw.add(use.variable, definition.variable, use.instruction.source_location)

    # Walk the CFG rather than the chains: a write whose value register has
    # no reaching definition produces no chain, and skipping it would drop
    # the very edge the write exists to create.
    for block in cfg.blocks.values():
        for inst in block.instructions:
            if not isinstance(inst, MemoryAccess):
                continue
            if inst.kind is not EffectKind.WRITE or inst.extent is None:
                continue
            sources: set[FieldExtent] = set()
            _trace_to_extents(inst.value_reg, produced_from, sources, set())
            for source in sources:
                raw.add(inst.extent, source, inst.source_location)

    return raw


def _project_to_fields(
    extent_graph: dict[FieldExtent, set[FieldExtent]],
) -> dict[str, set[str]]:
    """Collapse extents onto the names a reader recognises.

    An extent projects to its OWN field name and no other. Projecting onto
    every overlapping field as well was considered and rejected: it would
    make any mention of a group an edge to each of its children, which is
    precisely the mush ``test_two_unrelated_records_stay_unconnected``
    guards. Overlap is already accounted for on the reaching-definition edge,
    where it is flow-sensitive; doing it a second time here would only
    restate it without the flow.
    """
    graph: dict[str, set[str]] = {}
    for target, sources in extent_graph.items():
        graph.setdefault(target.field_name, set()).update(
            s.field_name for s in sources if s.field_name != target.field_name
        )
    return graph


def build_def_use_chains(
    cfg: CFG, effects: dict[InstructionId, MemoryEffect]
) -> list[DefUseLink]:
    """Extent-level def-use chains — the flow-SENSITIVE layer of the result.

    Exposed separately because the graphs are not: they have one node per
    extent, so two writes to the same field collapse and the KILL that
    separated them stops being observable there. A caller (or a test) that
    needs to know which particular write a read saw asks here.
    """
    rewritten_cfg = rewrite_cfg(cfg, effects)
    return _extract_def_use_chains(
        rewritten_cfg, solve_reaching_definitions(rewritten_cfg)
    )


def analyze_memory_dataflow(
    cfg: CFG, effects: dict[InstructionId, MemoryEffect]
) -> MemoryDataflowResult:
    """Build the field-level dependency graph for one COBOL CFG.

    ``effects`` is the sidecar from a ``CollectingRecorder`` attached to the
    frontend. An empty sidecar yields an empty graph rather than an error:
    the analysis is opt-in, and running it against a lowering that recorded
    nothing is a caller mistake the caller can see.
    """
    rewritten_cfg = rewrite_cfg(cfg, effects)
    block_facts = solve_reaching_definitions(rewritten_cfg)
    chains = _extract_def_use_chains(rewritten_cfg, block_facts)
    logger.info("memory dataflow: %d def-use links over extents", len(chains))

    raw = _build_raw_extent_graph(rewritten_cfg, chains)
    extent_graph = _transitive_closure(raw.edges)

    # Close again after projection: two distinct extents can share a field
    # name (an EXACT and a CLAMPED access to the same OCCURS element), and
    # merging them can create a path the extent-level closure could not see.
    field_graph = _transitive_closure(_project_to_fields(raw.edges))

    edge_locations: dict[tuple[str, str], list[SourceLocation]] = {}
    for (source, target), locations in raw.locations.items():
        if source.field_name == target.field_name:
            continue
        edge_locations.setdefault((source.field_name, target.field_name), []).extend(
            locations
        )

    logger.info(
        "memory dataflow: %d extents, %d fields",
        len(extent_graph),
        len(field_graph),
    )
    return MemoryDataflowResult(
        extent_graph=extent_graph,
        field_graph=field_graph,
        edge_locations=edge_locations,
    )
