"""Tests for iterative dataflow analysis — reaching definitions, def-use chains, dependency graphs."""

from __future__ import annotations

from interpreter.cfg import BasicBlock, CFG, build_cfg
from interpreter.dataflow import (
    BlockDataflowFacts,
    DataflowResult,
    Definition,
    DefUseLink,
    Use,
    analyze,
    build_dependency_graph,
    collect_all_definitions,
    compute_gen_kill,
    extract_def_use_chains,
    solve_reaching_definitions,
    _defs_of,
    _uses_of,
    _build_defs_by_variable,
)
from interpreter.frontends.python import PythonFrontend
from interpreter.ir import IRInstruction, Opcode, CodeLabel, NO_LABEL
from interpreter.instructions import InstructionBase
from interpreter.parser import TreeSitterParserFactory
from interpreter import constants
from interpreter.var_name import VarName
from interpreter.register import NO_REGISTER, Register


def _make_inst(
    opcode: Opcode,
    result_reg=NO_REGISTER,
    operands=None,
    label: CodeLabel = NO_LABEL,
    branch_targets: list[CodeLabel] = [],
):
    """Helper to build an IRInstruction concisely."""
    return IRInstruction(
        opcode=opcode,
        result_reg=result_reg,
        operands=operands if operands is not None else [],
        label=label,
        branch_targets=branch_targets,
    )


def _build_simple_cfg(ir_instructions: list[InstructionBase]) -> CFG:
    """Build a CFG from raw IR instructions."""
    return build_cfg(ir_instructions)


def _parse_python_to_cfg(source: str) -> CFG:
    """End-to-end: Python source -> IR -> CFG."""
    frontend = PythonFrontend(TreeSitterParserFactory(), "python")
    ir = frontend.lower(source.encode("utf-8"))
    return build_cfg(ir)


class TestReachingDefinitions:
    def test_single_block_linear(self):
        """x=1; y=x+1 → x's def reaches y's use."""
        ir = [
            _make_inst(Opcode.LABEL, label=CodeLabel("entry")),
            _make_inst(Opcode.CONST, result_reg=Register("t0"), operands=["1"]),
            _make_inst(Opcode.STORE_VAR, operands=["x", "t0"]),
            _make_inst(Opcode.LOAD_VAR, result_reg=Register("t1"), operands=["x"]),
            _make_inst(Opcode.CONST, result_reg=Register("t2"), operands=["1"]),
            _make_inst(
                Opcode.BINOP, result_reg=Register("t3"), operands=["+", "t1", "t2"]
            ),
            _make_inst(Opcode.STORE_VAR, operands=["y", "t3"]),
        ]
        cfg = _build_simple_cfg(ir)
        facts = solve_reaching_definitions(cfg)

        entry_label = cfg.entry
        reach_out = facts[entry_label].reach_out

        # x and y should both be defined in reach_out
        defined_vars = {d.variable for d in reach_out}
        assert VarName("x") in defined_vars
        assert VarName("y") in defined_vars

    def test_redefinition_kills(self):
        """x=1; x=2 → only second def of x reaches end."""
        ir = [
            _make_inst(Opcode.LABEL, label=CodeLabel("entry")),
            _make_inst(Opcode.CONST, result_reg=Register("t0"), operands=["1"]),
            _make_inst(Opcode.STORE_VAR, operands=["x", "t0"]),
            _make_inst(Opcode.CONST, result_reg=Register("t1"), operands=["2"]),
            _make_inst(Opcode.STORE_VAR, operands=["x", "t1"]),
        ]
        cfg = _build_simple_cfg(ir)
        facts = solve_reaching_definitions(cfg)

        entry_label = cfg.entry
        x_defs = [d for d in facts[entry_label].reach_out if d.variable == VarName("x")]
        # Only one definition of x should survive (the last one)
        assert len(x_defs) == 1
        assert x_defs[0].instruction.operands == ["x", "t1"]

    def test_branch_merges_definitions(self):
        """if/else both define x → both reach merge point."""
        ir = [
            _make_inst(Opcode.LABEL, label=CodeLabel("entry")),
            _make_inst(Opcode.CONST, result_reg=Register("t_cond"), operands=["true"]),
            _make_inst(
                Opcode.BRANCH_IF,
                operands=["t_cond"],
                branch_targets=[CodeLabel("then"), CodeLabel("else")],
            ),
            # then branch
            _make_inst(Opcode.LABEL, label=CodeLabel("then")),
            _make_inst(Opcode.CONST, result_reg=Register("t0"), operands=["1"]),
            _make_inst(Opcode.STORE_VAR, operands=["x", "t0"]),
            _make_inst(Opcode.BRANCH, label=CodeLabel("merge")),
            # else branch
            _make_inst(Opcode.LABEL, label=CodeLabel("else")),
            _make_inst(Opcode.CONST, result_reg=Register("t1"), operands=["2"]),
            _make_inst(Opcode.STORE_VAR, operands=["x", "t1"]),
            _make_inst(Opcode.BRANCH, label=CodeLabel("merge")),
            # merge point
            _make_inst(Opcode.LABEL, label=CodeLabel("merge")),
            _make_inst(Opcode.LOAD_VAR, result_reg=Register("t2"), operands=["x"]),
        ]
        cfg = _build_simple_cfg(ir)
        facts = solve_reaching_definitions(cfg)

        # At merge's reach_in, both definitions of x should be present
        x_defs_in = [d for d in facts["merge"].reach_in if d.variable == VarName("x")]
        assert len(x_defs_in) == 2

    def test_loop_reaches_header(self):
        """Loop body redefines x → def reaches loop header."""
        ir = [
            _make_inst(Opcode.LABEL, label=CodeLabel("entry")),
            _make_inst(Opcode.CONST, result_reg=Register("t0"), operands=["0"]),
            _make_inst(Opcode.STORE_VAR, operands=["x", "t0"]),
            _make_inst(Opcode.BRANCH, label=CodeLabel("loop_header")),
            # loop header
            _make_inst(Opcode.LABEL, label=CodeLabel("loop_header")),
            _make_inst(Opcode.LOAD_VAR, result_reg=Register("t_cond"), operands=["x"]),
            _make_inst(
                Opcode.BRANCH_IF,
                operands=["t_cond"],
                branch_targets=[CodeLabel("loop_body"), CodeLabel("loop_exit")],
            ),
            # loop body
            _make_inst(Opcode.LABEL, label=CodeLabel("loop_body")),
            _make_inst(Opcode.CONST, result_reg=Register("t1"), operands=["1"]),
            _make_inst(
                Opcode.BINOP, result_reg=Register("t2"), operands=["+", "t_cond", "t1"]
            ),
            _make_inst(Opcode.STORE_VAR, operands=["x", "t2"]),
            _make_inst(Opcode.BRANCH, label=CodeLabel("loop_header")),
            # loop exit
            _make_inst(Opcode.LABEL, label=CodeLabel("loop_exit")),
            _make_inst(Opcode.LOAD_VAR, result_reg=Register("t3"), operands=["x"]),
        ]
        cfg = _build_simple_cfg(ir)
        facts = solve_reaching_definitions(cfg)

        # At loop_header, both the initial x=0 and the body's x=x+1 should reach
        x_defs_in = [
            d for d in facts["loop_header"].reach_in if d.variable == VarName("x")
        ]
        assert len(x_defs_in) == 2

    def test_empty_program(self):
        """Entry label only → no definitions."""
        ir = [_make_inst(Opcode.LABEL, label=CodeLabel("entry"))]
        cfg = _build_simple_cfg(ir)
        facts = solve_reaching_definitions(cfg)

        assert facts[cfg.entry].reach_out == set()
        assert facts[cfg.entry].reach_in == set()


class TestDefUseChains:
    def test_simple_def_use(self):
        """x=1; y=x → link from x's def to y's use of x."""
        ir = [
            _make_inst(Opcode.LABEL, label=CodeLabel("entry")),
            _make_inst(Opcode.CONST, result_reg=Register("t0"), operands=["1"]),
            _make_inst(Opcode.STORE_VAR, operands=["x", "t0"]),
            _make_inst(Opcode.LOAD_VAR, result_reg=Register("t1"), operands=["x"]),
            _make_inst(Opcode.STORE_VAR, operands=["y", "t1"]),
        ]
        cfg = _build_simple_cfg(ir)
        facts = solve_reaching_definitions(cfg)
        chains = extract_def_use_chains(cfg, facts)

        # Should have a chain from x's STORE_VAR to the LOAD_VAR of x
        x_chains = [
            c
            for c in chains
            if c.definition.variable == VarName("x") and c.use.variable == VarName("x")
        ]
        assert len(x_chains) == 1
        assert any(c.use.instruction.opcode == Opcode.LOAD_VAR for c in x_chains)

    def test_use_after_redefinition(self):
        """x=1; x=2; y=x → only second def linked to LOAD_VAR use."""
        ir = [
            _make_inst(Opcode.LABEL, label=CodeLabel("entry")),
            _make_inst(Opcode.CONST, result_reg=Register("t0"), operands=["1"]),
            _make_inst(Opcode.STORE_VAR, operands=["x", "t0"]),
            _make_inst(Opcode.CONST, result_reg=Register("t1"), operands=["2"]),
            _make_inst(Opcode.STORE_VAR, operands=["x", "t1"]),
            _make_inst(Opcode.LOAD_VAR, result_reg=Register("t2"), operands=["x"]),
            _make_inst(Opcode.STORE_VAR, operands=["y", "t2"]),
        ]
        cfg = _build_simple_cfg(ir)
        facts = solve_reaching_definitions(cfg)
        chains = extract_def_use_chains(cfg, facts)

        # The LOAD_VAR of x should only be linked to the second STORE_VAR of x
        load_x_chains = [
            c
            for c in chains
            if c.use.variable == VarName("x")
            and c.use.instruction.opcode == Opcode.LOAD_VAR
        ]
        assert len(load_x_chains) == 1
        assert load_x_chains[0].definition.instruction.operands == ["x", "t1"]

    def test_branch_creates_multiple_chains(self):
        """if/else → use after merge has two possible defs."""
        ir = [
            _make_inst(Opcode.LABEL, label=CodeLabel("entry")),
            _make_inst(Opcode.CONST, result_reg=Register("t_cond"), operands=["true"]),
            _make_inst(
                Opcode.BRANCH_IF,
                operands=["t_cond"],
                branch_targets=[CodeLabel("then"), CodeLabel("else")],
            ),
            _make_inst(Opcode.LABEL, label=CodeLabel("then")),
            _make_inst(Opcode.CONST, result_reg=Register("t0"), operands=["1"]),
            _make_inst(Opcode.STORE_VAR, operands=["x", "t0"]),
            _make_inst(Opcode.BRANCH, label=CodeLabel("merge")),
            _make_inst(Opcode.LABEL, label=CodeLabel("else")),
            _make_inst(Opcode.CONST, result_reg=Register("t1"), operands=["2"]),
            _make_inst(Opcode.STORE_VAR, operands=["x", "t1"]),
            _make_inst(Opcode.BRANCH, label=CodeLabel("merge")),
            _make_inst(Opcode.LABEL, label=CodeLabel("merge")),
            _make_inst(Opcode.LOAD_VAR, result_reg=Register("t2"), operands=["x"]),
        ]
        cfg = _build_simple_cfg(ir)
        facts = solve_reaching_definitions(cfg)
        chains = extract_def_use_chains(cfg, facts)

        # LOAD_VAR of x at merge should have two def chains
        load_x_chains = [
            c
            for c in chains
            if c.use.variable == VarName("x")
            and c.use.instruction.opcode == Opcode.LOAD_VAR
            and c.use.block_label == "merge"
        ]
        assert len(load_x_chains) == 2

    def test_function_params_are_definitions(self):
        """SYMBOLIC param:x → usable as a definition."""
        ir = [
            _make_inst(Opcode.LABEL, label=CodeLabel("entry")),
            _make_inst(
                Opcode.SYMBOLIC, result_reg=Register("t0"), operands=["param:x"]
            ),
            _make_inst(Opcode.STORE_VAR, operands=["x", "t0"]),
            _make_inst(Opcode.LOAD_VAR, result_reg=Register("t1"), operands=["x"]),
        ]
        cfg = _build_simple_cfg(ir)
        facts = solve_reaching_definitions(cfg)
        chains = extract_def_use_chains(cfg, facts)

        # x should be defined and usable
        x_chains = [c for c in chains if c.use.variable == VarName("x")]
        assert len(x_chains) == 1

    def test_decl_var_params_are_definitions(self):
        """SYMBOLIC param:x → DECL_VAR x %0: x is a definition (real frontend pattern)."""
        ir = [
            _make_inst(Opcode.LABEL, label=CodeLabel("entry")),
            _make_inst(
                Opcode.SYMBOLIC, result_reg=Register("t0"), operands=["param:x"]
            ),
            _make_inst(Opcode.DECL_VAR, operands=["x", "t0"]),
            _make_inst(Opcode.LOAD_VAR, result_reg=Register("t1"), operands=["x"]),
        ]
        cfg = _build_simple_cfg(ir)
        facts = solve_reaching_definitions(cfg)
        chains = extract_def_use_chains(cfg, facts)

        x_chains = [c for c in chains if c.use.variable == VarName("x")]
        assert len(x_chains) == 1


class TestDependencyGraph:
    def test_direct_dependency(self):
        """y = x + 1 → y depends on x."""
        ir = [
            _make_inst(Opcode.LABEL, label=CodeLabel("entry")),
            _make_inst(Opcode.CONST, result_reg=Register("t0"), operands=["10"]),
            _make_inst(Opcode.STORE_VAR, operands=["x", "t0"]),
            _make_inst(Opcode.LOAD_VAR, result_reg=Register("t1"), operands=["x"]),
            _make_inst(Opcode.CONST, result_reg=Register("t2"), operands=["1"]),
            _make_inst(
                Opcode.BINOP, result_reg=Register("t3"), operands=["+", "t1", "t2"]
            ),
            _make_inst(Opcode.STORE_VAR, operands=["y", "t3"]),
        ]
        cfg = _build_simple_cfg(ir)
        result = analyze(cfg)

        assert VarName("y") in result.dependency_graph
        assert VarName("x") in result.dependency_graph[VarName("y")]

    def test_decl_var_dependency(self):
        """DECL_VAR x t0; y = x + 1 → y depends on x (DECL_VAR is a variable definition)."""
        ir = [
            _make_inst(Opcode.LABEL, label=CodeLabel("entry")),
            _make_inst(Opcode.CONST, result_reg=Register("t0"), operands=["10"]),
            _make_inst(Opcode.DECL_VAR, operands=["x", "t0"]),
            _make_inst(Opcode.LOAD_VAR, result_reg=Register("t1"), operands=["x"]),
            _make_inst(Opcode.CONST, result_reg=Register("t2"), operands=["1"]),
            _make_inst(
                Opcode.BINOP, result_reg=Register("t3"), operands=["+", "t1", "t2"]
            ),
            _make_inst(Opcode.STORE_VAR, operands=["y", "t3"]),
        ]
        cfg = _build_simple_cfg(ir)
        result = analyze(cfg)

        assert VarName("y") in result.dependency_graph
        assert VarName("x") in result.dependency_graph[VarName("y")]

    def test_direct_dependency_in_raw_graph(self):
        """y = x + 1 → raw graph has y depending on x."""
        ir = [
            _make_inst(Opcode.LABEL, label=CodeLabel("entry")),
            _make_inst(Opcode.CONST, result_reg=Register("t0"), operands=["10"]),
            _make_inst(Opcode.STORE_VAR, operands=["x", "t0"]),
            _make_inst(Opcode.LOAD_VAR, result_reg=Register("t1"), operands=["x"]),
            _make_inst(Opcode.CONST, result_reg=Register("t2"), operands=["1"]),
            _make_inst(
                Opcode.BINOP, result_reg=Register("t3"), operands=["+", "t1", "t2"]
            ),
            _make_inst(Opcode.STORE_VAR, operands=["y", "t3"]),
        ]
        cfg = _build_simple_cfg(ir)
        result = analyze(cfg)

        assert VarName("y") in result.raw_dependency_graph
        assert VarName("x") in result.raw_dependency_graph[VarName("y")]

    def test_transitive_dependency(self):
        """y=x+1; z=y*2 → z depends on y and transitively on x."""
        ir = [
            _make_inst(Opcode.LABEL, label=CodeLabel("entry")),
            _make_inst(Opcode.CONST, result_reg=Register("t0"), operands=["10"]),
            _make_inst(Opcode.STORE_VAR, operands=["x", "t0"]),
            _make_inst(Opcode.LOAD_VAR, result_reg=Register("t1"), operands=["x"]),
            _make_inst(Opcode.CONST, result_reg=Register("t2"), operands=["1"]),
            _make_inst(
                Opcode.BINOP, result_reg=Register("t3"), operands=["+", "t1", "t2"]
            ),
            _make_inst(Opcode.STORE_VAR, operands=["y", "t3"]),
            _make_inst(Opcode.LOAD_VAR, result_reg=Register("t4"), operands=["y"]),
            _make_inst(Opcode.CONST, result_reg=Register("t5"), operands=["2"]),
            _make_inst(
                Opcode.BINOP, result_reg=Register("t6"), operands=["*", "t4", "t5"]
            ),
            _make_inst(Opcode.STORE_VAR, operands=["z", "t6"]),
        ]
        cfg = _build_simple_cfg(ir)
        result = analyze(cfg)

        assert VarName("z") in result.dependency_graph
        assert VarName("y") in result.dependency_graph[VarName("z")]
        assert VarName("x") in result.dependency_graph[VarName("z")]

    def test_raw_graph_excludes_transitive_deps(self):
        """y=x+1; z=y*2 → raw graph has z depending on y but NOT x."""
        ir = [
            _make_inst(Opcode.LABEL, label=CodeLabel("entry")),
            _make_inst(Opcode.CONST, result_reg=Register("t0"), operands=["10"]),
            _make_inst(Opcode.STORE_VAR, operands=["x", "t0"]),
            _make_inst(Opcode.LOAD_VAR, result_reg=Register("t1"), operands=["x"]),
            _make_inst(Opcode.CONST, result_reg=Register("t2"), operands=["1"]),
            _make_inst(
                Opcode.BINOP, result_reg=Register("t3"), operands=["+", "t1", "t2"]
            ),
            _make_inst(Opcode.STORE_VAR, operands=["y", "t3"]),
            _make_inst(Opcode.LOAD_VAR, result_reg=Register("t4"), operands=["y"]),
            _make_inst(Opcode.CONST, result_reg=Register("t5"), operands=["2"]),
            _make_inst(
                Opcode.BINOP, result_reg=Register("t6"), operands=["*", "t4", "t5"]
            ),
            _make_inst(Opcode.STORE_VAR, operands=["z", "t6"]),
        ]
        cfg = _build_simple_cfg(ir)
        result = analyze(cfg)

        assert VarName("z") in result.raw_dependency_graph
        assert VarName("y") in result.raw_dependency_graph[VarName("z")]
        assert VarName("x") not in result.raw_dependency_graph[VarName("z")]

    def test_raw_graph_preserves_all_direct_deps_in_multi_operand_expression(self):
        """a=1; b=2; c=a+b; d=c+b → raw graph has d depending on both c and b."""
        ir = [
            _make_inst(Opcode.LABEL, label=CodeLabel("entry")),
            _make_inst(Opcode.CONST, result_reg=Register("t0"), operands=["1"]),
            _make_inst(Opcode.STORE_VAR, operands=["a", "t0"]),
            _make_inst(Opcode.CONST, result_reg=Register("t1"), operands=["2"]),
            _make_inst(Opcode.STORE_VAR, operands=["b", "t1"]),
            _make_inst(Opcode.LOAD_VAR, result_reg=Register("t2"), operands=["a"]),
            _make_inst(Opcode.LOAD_VAR, result_reg=Register("t3"), operands=["b"]),
            _make_inst(
                Opcode.BINOP, result_reg=Register("t4"), operands=["+", "t2", "t3"]
            ),
            _make_inst(Opcode.STORE_VAR, operands=["c", "t4"]),
            _make_inst(Opcode.LOAD_VAR, result_reg=Register("t5"), operands=["c"]),
            _make_inst(Opcode.LOAD_VAR, result_reg=Register("t6"), operands=["b"]),
            _make_inst(
                Opcode.BINOP, result_reg=Register("t7"), operands=["+", "t5", "t6"]
            ),
            _make_inst(Opcode.STORE_VAR, operands=["d", "t7"]),
        ]
        cfg = _build_simple_cfg(ir)
        result = analyze(cfg)

        # Raw: d directly depends on c and b (both operands of d = c + b)
        assert result.raw_dependency_graph[VarName("d")] == {VarName("c"), VarName("b")}
        # Transitive: d depends on a, b, c (b directly, a through c)
        assert result.dependency_graph[VarName("d")] == {
            VarName("a"),
            VarName("b"),
            VarName("c"),
        }

    def test_no_self_dependency_without_loop(self):
        """x=1 → x does not depend on itself."""
        ir = [
            _make_inst(Opcode.LABEL, label=CodeLabel("entry")),
            _make_inst(Opcode.CONST, result_reg=Register("t0"), operands=["1"]),
            _make_inst(Opcode.STORE_VAR, operands=["x", "t0"]),
        ]
        cfg = _build_simple_cfg(ir)
        result = analyze(cfg)

        # x must appear in definitions (proves analysis processed it)
        defined_vars = {d.variable for d in result.definitions}
        assert VarName("x") in defined_vars, "x should appear in definitions"
        # x = 1 has no self-dependency
        assert VarName("x") not in result.dependency_graph.get(
            VarName("x"), set()
        ), "x = 1 should not self-depend"

    def test_loop_creates_self_dependency(self):
        """while: x = x + 1 → x depends on x."""
        ir = [
            _make_inst(Opcode.LABEL, label=CodeLabel("entry")),
            _make_inst(Opcode.CONST, result_reg=Register("t0"), operands=["0"]),
            _make_inst(Opcode.STORE_VAR, operands=["x", "t0"]),
            _make_inst(Opcode.BRANCH, label=CodeLabel("loop_header")),
            _make_inst(Opcode.LABEL, label=CodeLabel("loop_header")),
            _make_inst(Opcode.LOAD_VAR, result_reg=Register("t_cond"), operands=["x"]),
            _make_inst(
                Opcode.BRANCH_IF,
                operands=["t_cond"],
                branch_targets=[CodeLabel("loop_body"), CodeLabel("loop_exit")],
            ),
            _make_inst(Opcode.LABEL, label=CodeLabel("loop_body")),
            _make_inst(Opcode.LOAD_VAR, result_reg=Register("t1"), operands=["x"]),
            _make_inst(Opcode.CONST, result_reg=Register("t2"), operands=["1"]),
            _make_inst(
                Opcode.BINOP, result_reg=Register("t3"), operands=["+", "t1", "t2"]
            ),
            _make_inst(Opcode.STORE_VAR, operands=["x", "t3"]),
            _make_inst(Opcode.BRANCH, label=CodeLabel("loop_header")),
            _make_inst(Opcode.LABEL, label=CodeLabel("loop_exit")),
            _make_inst(Opcode.LOAD_VAR, result_reg=Register("t4"), operands=["x"]),
        ]
        cfg = _build_simple_cfg(ir)
        result = analyze(cfg)

        assert VarName("x") in result.dependency_graph
        assert VarName("x") in result.dependency_graph[VarName("x")]


class TestIntegration:
    def test_analyze_returns_well_formed_result(self):
        """Multi-block program produces correct structure and content."""
        ir = [
            _make_inst(Opcode.LABEL, label=CodeLabel("entry")),
            _make_inst(Opcode.CONST, result_reg=Register("t0"), operands=["1"]),
            _make_inst(Opcode.STORE_VAR, operands=["x", "t0"]),
            _make_inst(Opcode.CONST, result_reg=Register("t_cond"), operands=["true"]),
            _make_inst(
                Opcode.BRANCH_IF,
                operands=["t_cond"],
                branch_targets=[CodeLabel("then"), CodeLabel("else")],
            ),
            _make_inst(Opcode.LABEL, label=CodeLabel("then")),
            _make_inst(Opcode.CONST, result_reg=Register("t1"), operands=["2"]),
            _make_inst(Opcode.STORE_VAR, operands=["y", "t1"]),
            _make_inst(Opcode.BRANCH, label=CodeLabel("merge")),
            _make_inst(Opcode.LABEL, label=CodeLabel("else")),
            _make_inst(Opcode.CONST, result_reg=Register("t2"), operands=["3"]),
            _make_inst(Opcode.STORE_VAR, operands=["y", "t2"]),
            _make_inst(Opcode.BRANCH, label=CodeLabel("merge")),
            _make_inst(Opcode.LABEL, label=CodeLabel("merge")),
            _make_inst(Opcode.LOAD_VAR, result_reg=Register("t3"), operands=["y"]),
            _make_inst(Opcode.RETURN, operands=["t3"]),
        ]
        cfg = _build_simple_cfg(ir)
        result = analyze(cfg)

        assert isinstance(result, DataflowResult)
        assert len(result.block_facts) == len(cfg.blocks)
        # x is defined in entry, y is defined in both then and else
        x_defs = [d for d in result.definitions if d.variable == VarName("x")]
        y_defs = [d for d in result.definitions if d.variable == VarName("y")]
        assert len(x_defs) == 1
        assert len(y_defs) == 2
        # y is used in the merge block's LOAD_VAR
        y_uses = [
            c for c in result.def_use_chains if c.definition.variable == VarName("y")
        ]
        assert len(y_uses) >= 1

    def test_python_frontend_to_dataflow(self):
        """End-to-end: Python source → IR → CFG → dataflow with dependency verification."""
        source = "x = 10\ny = x + 1\nz = y * 2"
        cfg = _parse_python_to_cfg(source)
        result = analyze(cfg)

        assert isinstance(result, DataflowResult)
        # z depends on y, y depends on x
        assert VarName("y") in result.dependency_graph
        assert VarName("x") in result.dependency_graph[VarName("y")]
        assert VarName("z") in result.dependency_graph
        assert VarName("y") in result.dependency_graph[VarName("z")]

    def test_analysis_converges_for_loop_program(self):
        """Reaching definitions analysis converges and covers all blocks on a loop program."""
        ir = [
            _make_inst(Opcode.LABEL, label=CodeLabel("entry")),
            _make_inst(Opcode.CONST, result_reg=Register("t0"), operands=["0"]),
            _make_inst(Opcode.STORE_VAR, operands=["x", "t0"]),
            _make_inst(Opcode.BRANCH, label=CodeLabel("loop")),
            _make_inst(Opcode.LABEL, label=CodeLabel("loop")),
            _make_inst(Opcode.LOAD_VAR, result_reg=Register("t1"), operands=["x"]),
            _make_inst(Opcode.CONST, result_reg=Register("t2"), operands=["1"]),
            _make_inst(
                Opcode.BINOP, result_reg=Register("t3"), operands=["+", "t1", "t2"]
            ),
            _make_inst(Opcode.STORE_VAR, operands=["x", "t3"]),
            _make_inst(
                Opcode.BRANCH_IF,
                operands=["t3"],
                branch_targets=[CodeLabel("loop"), CodeLabel("exit")],
            ),
            _make_inst(Opcode.LABEL, label=CodeLabel("exit")),
            _make_inst(Opcode.RETURN, operands=["t3"]),
        ]
        cfg = _build_simple_cfg(ir)

        # Should converge without hitting the limit
        facts = solve_reaching_definitions(cfg)
        assert all(label in facts for label in cfg.blocks)


class TestRegionOpcodeDataflow:
    def test_alloc_region_tracked_as_definition(self):
        """ALLOC_REGION result_reg appears in collected definitions."""
        ir = [
            _make_inst(Opcode.LABEL, label=CodeLabel("entry")),
            _make_inst(
                Opcode.ALLOC_REGION, result_reg=Register("%r0"), operands=[1024]
            ),
        ]
        cfg = _build_simple_cfg(ir)
        defs = collect_all_definitions(cfg)

        defined_vars = {d.variable for d in defs}
        assert Register("%r0") in defined_vars

    def test_load_region_tracked_as_definition(self):
        """LOAD_REGION result_reg appears in collected definitions."""
        ir = [
            _make_inst(Opcode.LABEL, label=CodeLabel("entry")),
            _make_inst(
                Opcode.ALLOC_REGION, result_reg=Register("%r0"), operands=[1024]
            ),
            _make_inst(
                Opcode.LOAD_REGION,
                result_reg=Register("%r1"),
                operands=["%r0", "%off", 4],
            ),
        ]
        cfg = _build_simple_cfg(ir)
        defs = collect_all_definitions(cfg)

        defined_vars = {d.variable for d in defs}
        assert Register("%r1") in defined_vars

    def test_write_region_uses_tracked(self):
        """WRITE_REGION's region_reg, offset_reg, and value_reg tracked as uses."""
        inst = _make_inst(Opcode.WRITE_REGION, operands=["%r0", "%off", 4, "%val"])
        uses = _uses_of(inst)

        assert Register("%r0") in uses
        assert Register("%off") in uses
        assert Register("%val") in uses
        assert 4 not in uses

    def test_load_region_uses_tracked(self):
        """LOAD_REGION's region_reg and offset_reg tracked as uses."""
        inst = _make_inst(
            Opcode.LOAD_REGION,
            result_reg=Register("%r1"),
            operands=["%r0", "%off", 4],
        )
        uses = _uses_of(inst)

        assert Register("%r0") in uses
        assert Register("%off") in uses
        assert 4 not in uses

    def test_cobol_style_def_use_chain(self):
        """Mini COBOL-like program produces correct def-use chains through region ops."""
        ir = [
            _make_inst(Opcode.LABEL, label=CodeLabel("entry")),
            # Allocate a region
            _make_inst(Opcode.ALLOC_REGION, result_reg=Register("%r0"), operands=[256]),
            # Write a value into the region
            _make_inst(Opcode.CONST, result_reg=Register("%off"), operands=["0"]),
            _make_inst(Opcode.CONST, result_reg=Register("%val"), operands=["42"]),
            _make_inst(Opcode.WRITE_REGION, operands=["%r0", "%off", 4, "%val"]),
            # Load from the region
            _make_inst(
                Opcode.LOAD_REGION,
                result_reg=Register("%loaded"),
                operands=["%r0", "%off", 4],
            ),
            # Store into a named variable
            _make_inst(Opcode.STORE_VAR, operands=["result", "%loaded"]),
        ]
        cfg = _build_simple_cfg(ir)
        result = analyze(cfg)

        # %r0 should be defined (ALLOC_REGION)
        defined_vars = {d.variable for d in result.definitions}
        assert Register("%r0") in defined_vars
        assert Register("%loaded") in defined_vars

        # WRITE_REGION should have def-use chain from %r0
        write_region_uses = [
            c
            for c in result.def_use_chains
            if c.use.instruction.opcode == Opcode.WRITE_REGION
            and c.use.variable == Register("%r0")
        ]
        assert len(write_region_uses) == 1

        # LOAD_REGION should have def-use chain from %r0
        load_region_uses = [
            c
            for c in result.def_use_chains
            if c.use.instruction.opcode == Opcode.LOAD_REGION
            and c.use.variable == Register("%r0")
        ]
        assert len(load_region_uses) == 1

        # STORE_VAR of 'result' should use %loaded from LOAD_REGION
        store_result_uses = [
            c
            for c in result.def_use_chains
            if c.use.instruction.opcode == Opcode.STORE_VAR
            and c.use.variable == Register("%loaded")
        ]
        assert len(store_result_uses) == 1


class TestEdgeCases:
    def test_symbolic_instruction_does_not_crash_analysis(self):
        """SYMBOLIC instruction doesn't crash analysis."""
        ir = [
            _make_inst(Opcode.LABEL, label=CodeLabel("entry")),
            _make_inst(
                Opcode.SYMBOLIC, result_reg=Register("t0"), operands=["unknown_value"]
            ),
            _make_inst(Opcode.STORE_VAR, operands=["x", "t0"]),
            _make_inst(Opcode.LOAD_VAR, result_reg=Register("t1"), operands=["x"]),
            _make_inst(Opcode.RETURN, operands=["t1"]),
        ]
        cfg = _build_simple_cfg(ir)
        result = analyze(cfg)

        assert isinstance(result, DataflowResult)
        x_defs = [d for d in result.definitions if d.variable == VarName("x")]
        assert len(x_defs) == 1


class TestAddressOfDataflow:
    """ADDRESS_OF x should read x, creating def-use chains and dependency edges."""

    def test_address_of_reads_the_variable(self):
        """ADDRESS_OF x uses x — creates a def-use chain from STORE_VAR x."""
        ir = [
            _make_inst(Opcode.LABEL, label=CodeLabel("entry")),
            _make_inst(Opcode.CONST, result_reg=Register("%0"), operands=["42"]),
            _make_inst(Opcode.STORE_VAR, operands=["x", "%0"]),
            _make_inst(Opcode.ADDRESS_OF, result_reg=Register("%1"), operands=["x"]),
        ]
        cfg = _build_simple_cfg(ir)
        result = analyze(cfg)

        # ADDRESS_OF x should use x — a def-use chain must exist
        x_to_addr = [
            c
            for c in result.def_use_chains
            if c.definition.variable == VarName("x")
            and c.use.variable == VarName("x")
            and c.use.instruction.opcode == Opcode.ADDRESS_OF
        ]
        assert len(x_to_addr) == 1

    def test_address_of_creates_dependency(self):
        """ptr = &x → dependency_graph[ptr] includes x."""
        ir = [
            _make_inst(Opcode.LABEL, label=CodeLabel("entry")),
            _make_inst(Opcode.CONST, result_reg=Register("%0"), operands=["42"]),
            _make_inst(Opcode.STORE_VAR, operands=["x", "%0"]),
            _make_inst(Opcode.ADDRESS_OF, result_reg=Register("%1"), operands=["x"]),
            _make_inst(Opcode.STORE_VAR, operands=["ptr", "%1"]),
        ]
        cfg = _build_simple_cfg(ir)
        result = analyze(cfg)

        assert VarName("x") in result.dependency_graph.get(VarName("ptr"), set())

    def test_address_of_undefined_variable_has_no_incoming_chain(self):
        """ADDRESS_OF x with no prior STORE_VAR x has no def-use chain for x."""
        ir = [
            _make_inst(Opcode.LABEL, label=CodeLabel("entry")),
            _make_inst(Opcode.ADDRESS_OF, result_reg=Register("%0"), operands=["x"]),
        ]
        cfg = _build_simple_cfg(ir)
        result = analyze(cfg)

        # %0 should be defined (ADDRESS_OF writes to result_reg)
        addr_defs = [d for d in result.definitions if d.variable == Register("%0")]
        assert len(addr_defs) == 1
        # No def-use chain for x (nothing defines x before ADDRESS_OF)
        x_chains = [c for c in result.def_use_chains if c.use.variable == VarName("x")]
        assert len(x_chains) == 0

    def test_c_pointer_program_dependency(self):
        """End-to-end: C program 'int x = 10; int *p = &x;' — p depends on x."""
        from interpreter.frontend import get_frontend
        from interpreter.cfg import build_cfg

        fe = get_frontend("c")
        ir = fe.lower(b"int x = 10;\nint *p = &x;\n")
        cfg = build_cfg(ir)
        result = analyze(cfg)

        assert VarName("x") in result.dependency_graph.get(VarName("p"), set())
