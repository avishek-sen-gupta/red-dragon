"""Iterative Dataflow Analysis on IR — reaching definitions, def-use chains, dependency graphs."""

from __future__ import annotations

import logging
from collections import deque
from dataclasses import dataclass, field
from functools import reduce

from . import constants
from .cfg import BasicBlock, CFG
from .ir import IRInstruction, Opcode

logger = logging.getLogger(__name__)

# Opcodes that produce a value in result_reg
_VALUE_PRODUCERS: frozenset[Opcode] = frozenset(
    {
        Opcode.CONST,
        Opcode.LOAD_VAR,
        Opcode.LOAD_FIELD,
        Opcode.LOAD_INDEX,
        Opcode.NEW_OBJECT,
        Opcode.NEW_ARRAY,
        Opcode.BINOP,
        Opcode.UNOP,
        Opcode.CALL_FUNCTION,
        Opcode.CALL_METHOD,
        Opcode.CALL_UNKNOWN,
    }
)

# Opcodes that define a named variable (not just a register)
_VAR_DEFINERS: frozenset[Opcode] = frozenset({Opcode.STORE_VAR})


@dataclass(frozen=True)
class Definition:
    """A single point where a variable or register is defined."""

    variable: str
    block_label: str
    instruction_index: int
    instruction: IRInstruction

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

    variable: str
    block_label: str
    instruction_index: int
    instruction: IRInstruction

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
    block_facts: dict[str, BlockDataflowFacts]
    def_use_chains: list[DefUseLink]
    dependency_graph: dict[str, set[str]]


def _defs_of(instruction: IRInstruction) -> list[str]:
    """Return variable/register names defined by an instruction."""
    if instruction.opcode == Opcode.STORE_VAR and len(instruction.operands) >= 1:
        return [instruction.operands[0]]
    if instruction.opcode in _VALUE_PRODUCERS and instruction.result_reg is not None:
        return [instruction.result_reg]
    if instruction.opcode == Opcode.SYMBOLIC and instruction.result_reg is not None:
        return [instruction.result_reg]
    return []


def _uses_of(instruction: IRInstruction) -> list[str]:
    """Return variable/register names used by an instruction."""
    op = instruction.opcode
    operands = instruction.operands

    if op == Opcode.CONST:
        return []
    if op == Opcode.LOAD_VAR and len(operands) >= 1:
        return [operands[0]]
    if op == Opcode.STORE_VAR and len(operands) >= 2:
        return [operands[1]]
    if op == Opcode.LOAD_FIELD and len(operands) >= 1:
        return [operands[0]]
    if op == Opcode.STORE_FIELD and len(operands) >= 3:
        return [operands[0], operands[2]]
    if op == Opcode.LOAD_INDEX and len(operands) >= 2:
        return [operands[0], operands[1]]
    if op == Opcode.STORE_INDEX and len(operands) >= 3:
        return [operands[0], operands[1], operands[2]]
    if op == Opcode.BINOP and len(operands) >= 3:
        return [operands[1], operands[2]]
    if op == Opcode.UNOP and len(operands) >= 2:
        return [operands[1]]
    if op in (Opcode.CALL_FUNCTION, Opcode.CALL_METHOD, Opcode.CALL_UNKNOWN):
        return list(operands[1:]) if len(operands) > 1 else []
    if op == Opcode.BRANCH_IF and len(operands) >= 1:
        return [operands[0]]
    if op == Opcode.RETURN and len(operands) >= 1:
        return [operands[0]]
    if op == Opcode.THROW and len(operands) >= 1:
        return [operands[0]]
    return []


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
) -> dict[str, set[Definition]]:
    """Index definitions by variable name."""
    result: dict[str, set[Definition]] = {}
    for d in all_defs:
        result.setdefault(d.variable, set()).add(d)
    return result


def compute_gen_kill(
    block: BasicBlock,
    all_defs: list[Definition],
    defs_by_var: dict[str, set[Definition]],
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
    gen_map: dict[str, Definition] = {}
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


def solve_reaching_definitions(cfg: CFG) -> dict[str, BlockDataflowFacts]:
    """Classic worklist-based reaching definitions analysis.

    Returns a mapping of block label -> BlockDataflowFacts with reach_in/reach_out populated.
    """
    all_defs = collect_all_definitions(cfg)
    defs_by_var = _build_defs_by_variable(all_defs)

    facts: dict[str, BlockDataflowFacts] = {}
    for label, block in cfg.blocks.items():
        gen, kill = compute_gen_kill(block, all_defs, defs_by_var)
        facts[label] = BlockDataflowFacts(gen=gen, kill=kill)

    worklist: deque[str] = deque(cfg.blocks.keys())
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
    cfg: CFG, block_facts: dict[str, BlockDataflowFacts]
) -> list[DefUseLink]:
    """For each use, find which definitions can reach it.

    Checks both local definitions within the same block (most recent before the use)
    and definitions from reach_in.
    """
    chains: list[DefUseLink] = []

    for label, block in cfg.blocks.items():
        reach_in = block_facts[label].reach_in

        # Track local definitions as we walk forward through the block
        local_defs: dict[str, Definition] = {}

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


def build_dependency_graph(
    def_use_chains: list[DefUseLink],
) -> dict[str, set[str]]:
    """Build a variable dependency graph: var -> set of vars it depends on.

    Traces through register chains: for each STORE_VAR, find what named variables
    the RHS value ultimately depends on by walking backward through defining instructions.
    """
    # Build map: register/variable -> uses of the instruction that defines it
    # i.e., what does the instruction that produces this register consume?
    defined_by_uses: dict[str, set[str]] = {}
    for link in def_use_chains:
        defn = link.definition
        defined_by_uses.setdefault(defn.variable, set())
        # The instruction that defines defn.variable uses link.use.variable... no.
        # Actually: link = (definition -> use), meaning the definition feeds INTO the use.
        # We need the reverse: for each defined variable, what does its defining instruction use?

    # Correct approach: for each definition, gather what its instruction uses
    all_def_instructions: dict[str, list[IRInstruction]] = {}
    for link in def_use_chains:
        all_def_instructions.setdefault(link.definition.variable, []).append(
            link.definition.instruction
        )

    # Map: variable -> set of variables/registers used by its defining instruction
    produced_from: dict[str, set[str]] = {}
    for link in def_use_chains:
        defn = link.definition
        uses = _uses_of(defn.instruction)
        produced_from.setdefault(defn.variable, set()).update(uses)

    # For each STORE_VAR, trace the RHS register backward to named variables
    dep_graph: dict[str, set[str]] = {}

    # Collect all STORE_VAR definitions
    store_var_defs: set[tuple[str, str]] = set()
    for link in def_use_chains:
        use_inst = link.use.instruction
        if use_inst.opcode == Opcode.STORE_VAR and len(use_inst.operands) >= 2:
            var_name = use_inst.operands[0]
            rhs_reg = use_inst.operands[1]
            store_var_defs.add((var_name, rhs_reg))

    for var_name, rhs_reg in store_var_defs:
        named_deps: set[str] = set()
        _trace_to_named_vars(rhs_reg, produced_from, named_deps, set())
        dep_graph.setdefault(var_name, set()).update(named_deps)

    # Compute transitive closure
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


def _is_temporary_register(name: str) -> bool:
    """Check if a name is a temporary register (t0, t1, t_cond, %0, %1, etc.)."""
    if name.startswith("%"):
        return True
    if not name.startswith("t"):
        return False
    rest = name[1:]
    return rest.isdigit() or rest.startswith("_")


def _trace_to_named_vars(
    reg: str,
    produced_from: dict[str, set[str]],
    result: set[str],
    visited: set[str],
) -> None:
    """Recursively trace a register back to named variables via the produced_from map."""
    if reg in visited:
        return
    visited.add(reg)

    if not _is_temporary_register(reg):
        result.add(reg)
        return

    for source in produced_from.get(reg, set()):
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

    dependency_graph = build_dependency_graph(def_use_chains)
    logger.info(
        "Built dependency graph with %d variables",
        len(dependency_graph),
    )

    return DataflowResult(
        definitions=all_defs,
        block_facts=block_facts,
        def_use_chains=def_use_chains,
        dependency_graph=dependency_graph,
    )
