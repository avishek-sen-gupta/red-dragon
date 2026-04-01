# pyright: standard
"""Iterative Dataflow Analysis on IR — reaching definitions, def-use chains, dependency graphs."""

from __future__ import annotations

import logging
from collections import deque
from dataclasses import dataclass, field
from functools import reduce
from typing import Any

from interpreter import constants
from interpreter.cfg import BasicBlock, CFG
from interpreter.ir import CodeLabel, Opcode, VAR_DEFINITION_OPCODES
from interpreter.instructions import (
    DeclVar,
    InstructionBase,
    StoreVar,
)
from interpreter.register import Register
from interpreter.storage_identifier import StorageIdentifier
from interpreter.var_name import VarName

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class Definition:
    """A single point where a variable or register is defined."""

    variable: StorageIdentifier
    block_label: CodeLabel
    instruction_index: int
    instruction: InstructionBase

    def __hash__(self) -> int:
        return hash((self.variable, self.block_label, self.instruction_index))

    def __eq__(self, other: object) -> bool:
        if not isinstance(other, Definition):
            return NotImplemented
        return (
            self.variable == other.variable
            and self.block_label == other.block_label
            and self.instruction_index == other.instruction_index
        )


@dataclass(frozen=True)
class Use:
    """A single point where a variable or register is used."""

    variable: StorageIdentifier
    block_label: CodeLabel
    instruction_index: int
    instruction: InstructionBase

    def __hash__(self) -> int:
        return hash((self.variable, self.block_label, self.instruction_index))

    def __eq__(self, other: object) -> bool:
        if not isinstance(other, Use):
            return NotImplemented
        return (
            self.variable == other.variable
            and self.block_label == other.block_label
            and self.instruction_index == other.instruction_index
        )


@dataclass(frozen=True)
class DefUseLink:
    """A link from a definition to a use that reads it."""

    definition: Definition
    use: Use


@dataclass
class BlockDataflowFacts:
    """Dataflow facts for a single basic block."""

    gen: set[Definition] = field(default_factory=set)
    kill: set[Definition] = field(default_factory=set)
    reach_in: set[Definition] = field(default_factory=set)
    reach_out: set[Definition] = field(default_factory=set)


@dataclass
class DataflowResult:
    """Complete result of dataflow analysis on a CFG."""

    definitions: list[Definition]
    block_facts: dict[CodeLabel, BlockDataflowFacts]
    def_use_chains: list[DefUseLink]
    dependency_graph: dict[VarName, set[VarName]]
    raw_dependency_graph: dict[VarName, set[VarName]]


def _defs_of(instruction: InstructionBase) -> list[StorageIdentifier]:
    """Return storage locations defined (written) by an instruction."""
    w = instruction.writes()
    return [w] if w is not None else []


def _uses_of(instruction: InstructionBase) -> list[StorageIdentifier]:
    """Return storage locations used (read) by an instruction."""
    return instruction.reads()


def collect_all_definitions(cfg: CFG) -> list[Definition]:
    """Walk all blocks and collect every Definition."""
    return [
        Definition(
            variable=var,
            block_label=label,
            instruction_index=idx,
            instruction=inst,
        )
        for label, block in cfg.blocks.items()
        for idx, inst in enumerate(block.instructions)
        for var in _defs_of(inst)
    ]


def _build_defs_by_variable(
    all_defs: list[Definition],
) -> dict[StorageIdentifier, set[Definition]]:
    """Index definitions by storage identifier (variable or register)."""

    def _acc_def(acc: dict[StorageIdentifier, set[Definition]], d: Definition):
        return {**acc, d.variable: acc.get(d.variable, set()) | {d}}

    return reduce(_acc_def, all_defs, {})


def compute_gen_kill(
    block: BasicBlock,
    all_defs: list[Definition],
    defs_by_var: dict[StorageIdentifier, set[Definition]],
) -> tuple[set[Definition], set[Definition]]:
    """Compute GEN and KILL sets for a basic block.

    GEN: the last definition of each variable within the block.
    KILL: all definitions (from other blocks) of variables redefined in this block.
    """
    block_defs = [
        Definition(
            variable=var,
            block_label=block.label,
            instruction_index=idx,
            instruction=inst,
        )
        for idx, inst in enumerate(block.instructions)
        for var in _defs_of(inst)
    ]

    # GEN = last definition of each variable in the block (walking forward, last wins)
    gen_map: dict[StorageIdentifier, Definition] = {}
    for d in block_defs:
        gen_map[d.variable] = d
    gen = set(gen_map.values())

    # KILL = all defs of redefined variables across the whole program, minus this block's own defs
    redefined_vars = {d.variable for d in block_defs}
    block_def_set = set(block_defs)
    kill = {
        d
        for var in redefined_vars
        for d in defs_by_var.get(var, set())
        if d not in block_def_set
    }

    return gen, kill


def solve_reaching_definitions(cfg: CFG) -> dict[CodeLabel, BlockDataflowFacts]:
    """Classic worklist-based reaching definitions analysis.

    Returns a mapping of block label -> BlockDataflowFacts with reach_in/reach_out populated.
    """
    all_defs = collect_all_definitions(cfg)
    defs_by_var = _build_defs_by_variable(all_defs)

    facts: dict[CodeLabel, BlockDataflowFacts] = {}
    for label, block in cfg.blocks.items():
        gen, kill = compute_gen_kill(block, all_defs, defs_by_var)
        facts[label] = BlockDataflowFacts(gen=gen, kill=kill)

    worklist: deque[CodeLabel] = deque(cfg.blocks.keys())
    iteration = 0

    while worklist and iteration < constants.DATAFLOW_MAX_ITERATIONS:
        iteration += 1
        label = worklist.popleft()
        block = cfg.blocks[label]
        block_facts = facts[label]

        new_reach_in = reduce(
            set.union,
            [facts[p].reach_out for p in block.predecessors],
            set(),
        )

        new_reach_out = block_facts.gen | (new_reach_in - block_facts.kill)

        if new_reach_out != block_facts.reach_out:
            block_facts.reach_in = new_reach_in
            block_facts.reach_out = new_reach_out
            worklist.extend(s for s in block.successors if s not in worklist)
        else:
            block_facts.reach_in = new_reach_in

    if iteration >= constants.DATAFLOW_MAX_ITERATIONS:
        logger.warning(
            "Reaching definitions did not converge within %d iterations",
            constants.DATAFLOW_MAX_ITERATIONS,
        )

    return facts


def extract_def_use_chains(
    cfg: CFG, block_facts: dict[CodeLabel, BlockDataflowFacts]
) -> list[DefUseLink]:
    """For each use, find which definitions can reach it.

    Checks both local definitions within the same block (most recent before the use)
    and definitions from reach_in.
    """
    chains: list[DefUseLink] = []

    for label, block in cfg.blocks.items():
        reach_in = block_facts[label].reach_in

        # Track local definitions as we walk forward through the block
        local_defs: dict[StorageIdentifier, Definition] = {}

        for idx, inst in enumerate(block.instructions):
            uses = _uses_of(inst)
            for var in uses:
                use = Use(
                    variable=var,
                    block_label=label,
                    instruction_index=idx,
                    instruction=inst,
                )

                if var in local_defs:
                    # Local def shadows incoming defs
                    chains.append(DefUseLink(definition=local_defs[var], use=use))
                else:
                    # Look in reach_in for matching defs
                    matching_defs = [d for d in reach_in if d.variable == var]
                    chains.extend(
                        DefUseLink(definition=d, use=use) for d in matching_defs
                    )

            # Update local defs after processing uses (def happens after use in same instruction)
            for var in _defs_of(inst):
                local_defs[var] = Definition(
                    variable=var,
                    block_label=label,
                    instruction_index=idx,
                    instruction=inst,
                )

    return chains


def _build_raw_dependency_graph(
    def_use_chains: list[DefUseLink],
) -> dict[VarName, set[VarName]]:
    """Build a raw variable dependency graph: var -> set of vars it directly depends on.

    Traces through register chains: for each STORE_VAR, find what named variables
    the RHS value ultimately depends on by walking backward through defining instructions.
    Does NOT compute transitive closure.
    """
    # Map: storage identifier -> set of identifiers used by its defining instruction
    produced_from: dict[StorageIdentifier, set[StorageIdentifier]] = reduce(
        lambda acc, link: {
            **acc,
            link.definition.variable: acc.get(link.definition.variable, set())
            | set(_uses_of(link.definition.instruction)),
        },
        def_use_chains,
        {},
    )

    # Collect all variable definitions (DECL_VAR + STORE_VAR)
    store_var_defs: set[tuple[VarName, Register]] = set()
    for link in def_use_chains:
        use_inst_raw: Any = (
            link.use.instruction
        )  # InstructionBase subclasses have opcode/operands  # see red-dragon-4ei7
        if (
            use_inst_raw.opcode in VAR_DEFINITION_OPCODES
            and len(use_inst_raw.operands) >= 2
            and isinstance(link.use.instruction, (DeclVar, StoreVar))
        ):
            t = link.use.instruction
            store_var_defs.add((t.name, t.value_reg))

    # For each STORE_VAR, trace the RHS register backward to named variables
    def _trace_deps(
        var_name: VarName, rhs_reg: Register
    ) -> tuple[VarName, set[VarName]]:
        named_deps: set[VarName] = set()
        _trace_to_named_vars(rhs_reg, produced_from, named_deps, set())
        return (var_name, named_deps)

    traced = [_trace_deps(var_name, rhs_reg) for var_name, rhs_reg in store_var_defs]
    return reduce(
        lambda acc, pair: {**acc, pair[0]: acc.get(pair[0], set()) | pair[1]},
        traced,
        {},
    )


def _transitive_closure(
    raw_graph: dict[VarName, set[VarName]],
) -> dict[VarName, set[VarName]]:
    """Compute transitive closure of a dependency graph."""
    dep_graph = {var: set(deps) for var, deps in raw_graph.items()}
    changed = True
    while changed:
        changed = False
        for var, deps in dep_graph.items():
            transitive = {td for d in deps if d in dep_graph for td in dep_graph[d]}
            new_deps = deps | transitive
            if new_deps != deps:
                dep_graph[var] = new_deps
                changed = True
    return dep_graph


def build_dependency_graph(
    def_use_chains: list[DefUseLink],
) -> dict[VarName, set[VarName]]:
    """Build a variable dependency graph with transitive closure.

    Returns var -> set of all vars it depends on (direct + transitive).
    """
    raw = _build_raw_dependency_graph(def_use_chains)
    return _transitive_closure(raw)


def _trace_to_named_vars(
    identifier: StorageIdentifier,
    produced_from: dict[StorageIdentifier, set[StorageIdentifier]],
    result: set[VarName],
    visited: set[StorageIdentifier],
) -> None:
    """Recursively trace a storage identifier back to named variables.

    VarName identifiers are leaves (added to result directly).
    Register identifiers are intermediates (traced through produced_from).
    """
    if isinstance(identifier, VarName):
        result.add(identifier)
        return
    if identifier in visited:
        return
    visited.add(identifier)

    for source in produced_from.get(identifier, set()):
        _trace_to_named_vars(source, produced_from, result, visited)


def analyze(cfg: CFG) -> DataflowResult:
    """Run complete dataflow analysis: reaching definitions, def-use chains, dependency graph."""
    logger.info("Starting dataflow analysis on CFG with %d blocks", len(cfg.blocks))

    all_defs = collect_all_definitions(cfg)
    logger.info("Collected %d definitions", len(all_defs))

    block_facts = solve_reaching_definitions(cfg)
    logger.info("Reaching definitions solved")

    def_use_chains = extract_def_use_chains(cfg, block_facts)
    logger.info("Extracted %d def-use chains", len(def_use_chains))

    raw_dependency_graph = _build_raw_dependency_graph(def_use_chains)
    logger.info(
        "Built raw dependency graph with %d variables",
        len(raw_dependency_graph),
    )

    dependency_graph = _transitive_closure(raw_dependency_graph)
    logger.info(
        "Built transitive dependency graph with %d variables",
        len(dependency_graph),
    )

    return DataflowResult(
        definitions=all_defs,
        block_facts=block_facts,
        def_use_chains=def_use_chains,
        dependency_graph=dependency_graph,
        raw_dependency_graph=raw_dependency_graph,
    )
