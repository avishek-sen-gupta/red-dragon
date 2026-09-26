# pyright: standard
"""Iterative Dataflow Analysis on IR — reaching definitions, def-use chains, dependency graphs."""

from __future__ import annotations

import logging
from collections import deque
from collections.abc import Hashable
from dataclasses import dataclass, field
from functools import reduce
from typing import Any, TypeVar

from interpreter import constants
from interpreter.cfg import CFG, BasicBlock
from interpreter.instructions import (
    DeclVar,
    InstructionBase,
    StoreVar,
)
from interpreter.ir import VAR_DEFINITION_OPCODES, CodeLabel
from interpreter.register import Register
from cobol_memory.storage_identifier import StorageIdentifier
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
) -> dict[Hashable, set[Definition]]:
    """Index definitions by alias bucket (coarse key shared by aliasing locations)."""

    def _acc_def(acc: dict[Hashable, set[Definition]], d: Definition):
        key = d.variable.alias_key()
        return {**acc, key: acc.get(key, set()) | {d}}

    return reduce(_acc_def, all_defs, {})


def compute_gen_kill(
    block: BasicBlock,
    all_defs: list[Definition],
    defs_by_var: dict[Hashable, set[Definition]],
) -> tuple[set[Definition], set[Definition]]:
    """Compute GEN and KILL sets for a basic block.

    GEN: the writes that survive to the block exit, per the alias relation.
    KILL: definitions elsewhere that this block's writes definitely overwrite.
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

    # GEN = the writes that survive to the block exit. A later write removes
    # an earlier one only if it definitely overwrites all of it (must_cover);
    # a write that merely MIGHT overlap coexists with what was there.
    gen_list: list[Definition] = []
    for d in block_defs:
        gen_list = [
            prior for prior in gen_list if not d.variable.must_cover(prior.variable)
        ]
        gen_list.append(d)
    gen = set(gen_list)

    # KILL = definitions elsewhere that this block's writes definitely
    # overwrite. Only a must-cover write kills; a may-overlap write cannot.
    block_def_set = set(block_defs)
    kill = {
        other
        for d in block_defs
        for other in defs_by_var.get(d.variable.alias_key(), set())
        if other not in block_def_set and d.variable.must_cover(other.variable)
    }

    return gen, kill


def solve_reaching_definitions(cfg: CFG) -> dict[CodeLabel, BlockDataflowFacts]:
    """Classic worklist-based reaching definitions analysis.

    Returns a mapping of block label -> BlockDataflowFacts with reach_in/reach_out populated.

    The result may be TRUNCATED: see ``solve_reaching_definitions_checked``,
    which returns the same facts plus whether the fixpoint was actually
    reached. This signature is kept unchanged because it is shared by all 16
    frontends.
    """
    facts, _converged = solve_reaching_definitions_checked(cfg)
    return facts


def solve_reaching_definitions_checked(
    cfg: CFG,
) -> tuple[dict[CodeLabel, BlockDataflowFacts], bool]:
    """As ``solve_reaching_definitions``, but says whether it converged.

    ``DATAFLOW_MAX_ITERATIONS`` counts worklist POPS, not sweeps, so a large
    program exhausts it and the solve stops mid-flight. What comes back then is
    not a smaller answer, it is a WRONG one: definitions that had not yet
    propagated are simply absent, so edges are missing with nothing but a log
    line to say so. A caller that cannot distinguish a complete result from a
    truncated one will report the truncated one as fact.

    ``converged`` is ``False`` exactly when the worklist was still non-empty at
    the cap. Callers that must not publish a partial answer check it; the
    cap itself is red-dragon-aso9's business, not this function's.
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

    # A non-empty worklist is the truncation itself, and is what the caller
    # needs to know. The warning above is deliberately left on its original,
    # slightly coarser predicate: a solve whose LAST allowed pop settled the
    # fixpoint hits the cap without having lost anything.
    return facts, not worklist


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
                    matching_defs = [d for d in reach_in if d.variable.may_alias(var)]
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


_Node = TypeVar("_Node", bound=Hashable)


def _transitive_closure(
    raw_graph: dict[_Node, set[_Node]],
) -> dict[_Node, set[_Node]]:
    """Compute transitive closure of a dependency graph.

    Node-generic: the register/variable analysis closes over ``VarName``, the
    COBOL memory analysis over ``FieldExtent`` and then over field-name
    strings. The algorithm never inspects a node, only hashes it.
    """
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
