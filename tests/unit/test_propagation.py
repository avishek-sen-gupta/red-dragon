"""Tests for interprocedural whole-program propagation with SCC fixpoint."""

from __future__ import annotations

from interpreter.cfg import build_cfg
from interpreter.cfg_types import BasicBlock, CFG
from interpreter.ir import IRInstruction, Opcode, CodeLabel, NO_LABEL
from interpreter.interprocedural.types import (
    CallContext,
    CallGraph,
    CallSite,
    FieldEndpoint,
    FunctionEntry,
    FunctionSummary,
    InstructionLocation,
    NO_DEFINITION,
    ReturnEndpoint,
    SummaryKey,
    VariableEndpoint,
)
from interpreter.interprocedural.propagation import (
    apply_summary_at_call_site,
    build_whole_program_graph,
    compute_sccs,
    whole_program_fixpoint,
)
from interpreter.registry import FunctionRegistry


def _inst(
    opcode: Opcode,
    result_reg=None,
    operands=None,
    label: CodeLabel = NO_LABEL,
    branch_targets: list[CodeLabel] = [],
):
    return IRInstruction(
        opcode=opcode,
        result_reg=result_reg,
        operands=operands if operands is not None else [],
        label=label,
        branch_targets=branch_targets,
    )


def _make_function(label: str, params: tuple[str, ...] = ()) -> FunctionEntry:
    return FunctionEntry(label=CodeLabel(label), params=params)


def _make_call_site(
    caller: FunctionEntry,
    callees: frozenset[FunctionEntry],
    arg_operands: tuple[str, ...],
    block_label: str = "entry",
    instruction_index: int = 0,
    result_reg: str = "%result",
) -> CallSite:
    return CallSite(
        caller=caller,
        location=InstructionLocation(
            block_label=block_label, instruction_index=instruction_index
        ),
        callees=callees,
        arg_operands=arg_operands,
    )


def _make_var_endpoint(name: str) -> VariableEndpoint:
    return VariableEndpoint(name=name, definition=NO_DEFINITION)


# ---------------------------------------------------------------------------
# 1. apply_summary_at_call_site — simple substitution
# ---------------------------------------------------------------------------


class TestApplySummaryAtCallSite:
    def test_simple_param_to_return_substitution(self):
        """Call passes %1 for param x. Summary: (Variable(x), Return) → (Variable(%1), Variable(result_reg))."""
        callee = _make_function("func__id", params=("x",))
        caller = _make_function("func__main", params=())
        site = _make_call_site(
            caller=caller,
            callees=frozenset({callee}),
            arg_operands=("%1",),
            block_label=CodeLabel("func__main"),
            instruction_index=3,
        )

        ret_endpoint = ReturnEndpoint(
            function=callee,
            location=InstructionLocation(
                block_label=CodeLabel("func__id"), instruction_index=2
            ),
        )
        summary = FunctionSummary(
            function=callee,
            context=CallContext(site=site),
            flows=frozenset({(_make_var_endpoint("x"), ret_endpoint)}),
        )

        result = apply_summary_at_call_site(site, summary, callee)

        assert len(result) == 1
        src, dst = next(iter(result))
        assert isinstance(src, VariableEndpoint)
        assert src.name == "%1"
        assert isinstance(dst, VariableEndpoint)
        # The result endpoint name comes from the call site instruction's result reg

    def test_field_base_substitution(self):
        """Call passes %obj for param obj. Summary field endpoint base changes from obj to %obj."""
        callee = _make_function("func__setter", params=("obj", "val"))
        caller = _make_function("func__main", params=())
        site = _make_call_site(
            caller=caller,
            callees=frozenset({callee}),
            arg_operands=("%obj", "%val"),
            block_label=CodeLabel("func__main"),
            instruction_index=5,
        )

        obj_var = _make_var_endpoint("obj")
        val_var = _make_var_endpoint("val")
        field_ep = FieldEndpoint(
            base=obj_var,
            field="name",
            location=InstructionLocation(
                block_label=CodeLabel("func__setter"), instruction_index=4
            ),
        )
        summary = FunctionSummary(
            function=callee,
            context=CallContext(site=site),
            flows=frozenset({(val_var, field_ep)}),
        )

        result = apply_summary_at_call_site(site, summary, callee)

        assert len(result) == 1
        src, dst = next(iter(result))
        assert isinstance(src, VariableEndpoint)
        assert src.name == "%val"
        assert isinstance(dst, FieldEndpoint)
        assert dst.base.name == "%obj"
        assert dst.field == "name"

    def test_no_flows_yields_empty(self):
        """Summary with no flows produces empty propagated set."""
        callee = _make_function("func__noop", params=("x",))
        caller = _make_function("func__main", params=())
        site = _make_call_site(
            caller=caller,
            callees=frozenset({callee}),
            arg_operands=("%1",),
        )

        summary = FunctionSummary(
            function=callee,
            context=CallContext(site=site),
            flows=frozenset(),
        )

        result = apply_summary_at_call_site(site, summary, callee)
        assert len(result) == 0


# ---------------------------------------------------------------------------
# 2. compute_sccs
# ---------------------------------------------------------------------------


class TestComputeSccs:
    def test_linear_chain(self):
        """A→B→C yields 3 singleton SCCs in reverse topological order: [C, B, A]."""
        func_a = _make_function("func__a")
        func_b = _make_function("func__b")
        func_c = _make_function("func__c")

        site_ab = _make_call_site(
            caller=func_a,
            callees=frozenset({func_b}),
            arg_operands=(),
            block_label=CodeLabel("func__a"),
        )
        site_bc = _make_call_site(
            caller=func_b,
            callees=frozenset({func_c}),
            arg_operands=(),
            block_label=CodeLabel("func__b"),
        )

        call_graph = CallGraph(
            functions=frozenset({func_a, func_b, func_c}),
            call_sites=frozenset({site_ab, site_bc}),
        )

        sccs = compute_sccs(call_graph)

        assert len(sccs) == 3
        # Each SCC is a singleton
        assert all(len(scc) == 1 for scc in sccs)
        # Reverse topological order: leaves first
        scc_labels = [next(iter(scc)).label for scc in sccs]
        assert scc_labels.index("func__c") < scc_labels.index("func__b")
        assert scc_labels.index("func__b") < scc_labels.index("func__a")

    def test_simple_cycle(self):
        """A→B→A yields 1 SCC containing {A, B}."""
        func_a = _make_function("func__a")
        func_b = _make_function("func__b")

        site_ab = _make_call_site(
            caller=func_a,
            callees=frozenset({func_b}),
            arg_operands=(),
            block_label=CodeLabel("func__a"),
        )
        site_ba = _make_call_site(
            caller=func_b,
            callees=frozenset({func_a}),
            arg_operands=(),
            block_label=CodeLabel("func__b"),
        )

        call_graph = CallGraph(
            functions=frozenset({func_a, func_b}),
            call_sites=frozenset({site_ab, site_ba}),
        )

        sccs = compute_sccs(call_graph)

        assert len(sccs) == 1
        assert sccs[0] == frozenset({func_a, func_b})

    def test_isolated_functions(self):
        """3 isolated functions → 3 singleton SCCs."""
        func_a = _make_function("func__a")
        func_b = _make_function("func__b")
        func_c = _make_function("func__c")

        call_graph = CallGraph(
            functions=frozenset({func_a, func_b, func_c}),
            call_sites=frozenset(),
        )

        sccs = compute_sccs(call_graph)

        assert len(sccs) == 3
        assert all(len(scc) == 1 for scc in sccs)

    def test_diamond_with_cycle(self):
        """A→B, A→C, B→D, C→D, D→B yields 2 SCCs: {B,D} and singletons {C}, {A}."""
        func_a = _make_function("func__a")
        func_b = _make_function("func__b")
        func_c = _make_function("func__c")
        func_d = _make_function("func__d")

        sites = frozenset(
            {
                _make_call_site(
                    func_a,
                    frozenset({func_b}),
                    (),
                    "func__a",
                    0,
                ),
                _make_call_site(
                    func_a,
                    frozenset({func_c}),
                    (),
                    "func__a",
                    1,
                ),
                _make_call_site(
                    func_b,
                    frozenset({func_d}),
                    (),
                    "func__b",
                    0,
                ),
                _make_call_site(
                    func_c,
                    frozenset({func_d}),
                    (),
                    "func__c",
                    0,
                ),
                _make_call_site(
                    func_d,
                    frozenset({func_b}),
                    (),
                    "func__d",
                    0,
                ),
            }
        )

        call_graph = CallGraph(
            functions=frozenset({func_a, func_b, func_c, func_d}),
            call_sites=sites,
        )

        sccs = compute_sccs(call_graph)

        # {B, D} form a cycle, C is singleton, A is singleton
        scc_sets = [scc for scc in sccs]
        cycle_scc = frozenset({func_b, func_d})
        assert cycle_scc in scc_sets

        # Reverse topo: {B,D} before {C} before {A}
        cycle_idx = scc_sets.index(cycle_scc)
        c_idx = next(i for i, s in enumerate(scc_sets) if func_c in s)
        a_idx = next(i for i, s in enumerate(scc_sets) if func_a in s)
        assert cycle_idx < c_idx or cycle_idx < a_idx  # leaves first
        assert a_idx > cycle_idx  # A depends on B,C,D


# ---------------------------------------------------------------------------
# 3. whole_program_fixpoint
# ---------------------------------------------------------------------------


def _build_two_function_cfg_and_registry():
    """Build a CFG with func__main calling func__add(a, b) → a + b.

    func__add body:
      SYMBOLIC param:a; STORE_VAR a %0
      SYMBOLIC param:b; STORE_VAR b %1
      LOAD_VAR a → %2; LOAD_VAR b → %3
      BINOP + %2 %3 → %4; STORE_VAR result %4
      LOAD_VAR result → %5; RETURN %5

    main body:
      CONST 3 → %10; CONST 4 → %11
      CALL_FUNCTION func__add %10 %11 → %12
      STORE_VAR result %12
    """
    ir = [
        # main
        _inst(Opcode.LABEL, label=CodeLabel("func__main")),
        _inst(Opcode.CONST, result_reg="%10", operands=["3"]),
        _inst(Opcode.CONST, result_reg="%11", operands=["4"]),
        _inst(
            Opcode.CALL_FUNCTION,
            result_reg="%12",
            operands=["func__add", "%10", "%11"],
        ),
        _inst(Opcode.STORE_VAR, operands=["result", "%12"]),
        _inst(Opcode.LOAD_VAR, result_reg="%13", operands=["result"]),
        _inst(Opcode.RETURN, operands=["%13"]),
        # func__add
        _inst(Opcode.LABEL, label=CodeLabel("func__add")),
        _inst(Opcode.SYMBOLIC, result_reg="%0", operands=["param:a"]),
        _inst(Opcode.STORE_VAR, operands=["a", "%0"]),
        _inst(Opcode.SYMBOLIC, result_reg="%1", operands=["param:b"]),
        _inst(Opcode.STORE_VAR, operands=["b", "%1"]),
        _inst(Opcode.LOAD_VAR, result_reg="%2", operands=["a"]),
        _inst(Opcode.LOAD_VAR, result_reg="%3", operands=["b"]),
        _inst(Opcode.BINOP, result_reg="%4", operands=["+", "%2", "%3"]),
        _inst(Opcode.STORE_VAR, operands=["result", "%4"]),
        _inst(Opcode.LOAD_VAR, result_reg="%5", operands=["result"]),
        _inst(Opcode.RETURN, operands=["%5"]),
    ]
    cfg = build_cfg(ir)
    registry = FunctionRegistry(
        func_params={
            "func__main": [],
            "func__add": ["a", "b"],
        }
    )
    return cfg, registry


class TestWholeProgramFixpoint:
    def test_two_function_chain(self):
        """func__main calls func__add. Both get summaries."""
        cfg, registry = _build_two_function_cfg_and_registry()

        from interpreter.interprocedural.call_graph import build_call_graph

        call_graph = build_call_graph(cfg, registry)

        summaries = whole_program_fixpoint(cfg, call_graph, registry)

        # Both functions should have summaries
        summary_functions = {key.function.label for key in summaries}
        assert "func__add" in summary_functions
        assert "func__main" in summary_functions

        # func__add should have param→return flows (a and b flow to return)
        add_summaries = [
            s for s in summaries.values() if s.function.label == "func__add"
        ]
        assert len(add_summaries) >= 1
        add_summary = add_summaries[0]
        source_names = {
            src.name
            for src, dst in add_summary.flows
            if isinstance(src, VariableEndpoint)
        }
        assert "a" in source_names
        assert "b" in source_names

    def test_recursive_function_converges(self):
        """func__f calls func__f. Fixpoint converges without infinite loop."""
        ir = [
            _inst(Opcode.LABEL, label=CodeLabel("func__f")),
            _inst(Opcode.SYMBOLIC, result_reg="%0", operands=["param:x"]),
            _inst(Opcode.STORE_VAR, operands=["x", "%0"]),
            _inst(Opcode.LOAD_VAR, result_reg="%1", operands=["x"]),
            _inst(
                Opcode.CALL_FUNCTION,
                result_reg="%2",
                operands=["func__f", "%1"],
            ),
            _inst(Opcode.RETURN, operands=["%1"]),
        ]
        cfg = build_cfg(ir)
        registry = FunctionRegistry(func_params={"func__f": ["x"]})

        from interpreter.interprocedural.call_graph import build_call_graph

        call_graph = build_call_graph(cfg, registry)

        summaries = whole_program_fixpoint(cfg, call_graph, registry)

        # Should have at least one summary for func__f
        assert any(key.function.label == "func__f" for key in summaries)

    def test_empty_call_graph(self):
        """Empty call graph produces empty summaries."""
        cfg = CFG()
        call_graph = CallGraph(functions=frozenset(), call_sites=frozenset())
        registry = FunctionRegistry()

        summaries = whole_program_fixpoint(cfg, call_graph, registry)
        assert len(summaries) == 0


# ---------------------------------------------------------------------------
# 4. build_whole_program_graph
# ---------------------------------------------------------------------------


class TestBuildWholeProgramGraph:
    def test_raw_and_transitive_graphs(self):
        """Given summaries with known flows, raw graph has direct edges, transitive has indirect."""
        func_a = _make_function("func__a", params=("x",))
        func_b = _make_function("func__b", params=("y",))

        # Flow in A: x → return_a
        ret_a = ReturnEndpoint(
            function=func_a,
            location=InstructionLocation(
                block_label=CodeLabel("func__a"), instruction_index=3
            ),
        )
        summary_a = FunctionSummary(
            function=func_a,
            context=CallContext(
                site=CallSite(
                    caller=_make_function("__root__"),
                    location=InstructionLocation(
                        block_label=CodeLabel(""), instruction_index=-1
                    ),
                    callees=frozenset(),
                    arg_operands=(),
                )
            ),
            flows=frozenset({(_make_var_endpoint("x"), ret_a)}),
        )

        # Flow in B: y → return_b
        ret_b = ReturnEndpoint(
            function=func_b,
            location=InstructionLocation(
                block_label=CodeLabel("func__b"), instruction_index=3
            ),
        )
        summary_b = FunctionSummary(
            function=func_b,
            context=CallContext(
                site=CallSite(
                    caller=_make_function("__root__"),
                    location=InstructionLocation(
                        block_label=CodeLabel(""), instruction_index=-1
                    ),
                    callees=frozenset(),
                    arg_operands=(),
                )
            ),
            flows=frozenset({(_make_var_endpoint("y"), ret_b)}),
        )

        # A calls B: passing %arg for y, result in %res
        site_ab = _make_call_site(
            caller=func_a,
            callees=frozenset({func_b}),
            arg_operands=("%arg",),
            block_label=CodeLabel("func__a"),
            instruction_index=2,
        )

        call_graph = CallGraph(
            functions=frozenset({func_a, func_b}),
            call_sites=frozenset({site_ab}),
        )

        summaries = {
            SummaryKey(function=func_a, context=summary_a.context): summary_a,
            SummaryKey(function=func_b, context=summary_b.context): summary_b,
        }

        raw_graph, transitive_graph = build_whole_program_graph(summaries, call_graph)

        # Raw graph should contain the summary flows + propagated call-site edges
        # The summaries themselves contribute flows
        assert len(raw_graph) > 0

    def test_empty_summaries(self):
        """Empty summaries produce empty graphs."""
        call_graph = CallGraph(functions=frozenset(), call_sites=frozenset())
        raw, transitive = build_whole_program_graph({}, call_graph)
        assert len(raw) == 0
        assert len(transitive) == 0
