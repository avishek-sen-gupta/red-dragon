"""Tests for interprocedural dataflow data types — TDD: written before implementation."""

from __future__ import annotations

from interpreter.cfg import BasicBlock, CFG
from interpreter.field_name import FieldName
from interpreter.dataflow import Definition
from interpreter.ir import IRInstruction, Opcode, CodeLabel, NO_LABEL
from interpreter.register import NO_REGISTER, Register
from interpreter.var_name import VarName
from interpreter.interprocedural.types import (
    CallContext,
    CallGraph,
    CallSite,
    FieldEndpoint,
    FlowEndpoint,
    FunctionEntry,
    FunctionSummary,
    InstructionLocation,
    InterproceduralResult,
    NO_DEFINITION,
    NO_INSTRUCTION_LOC,
    ROOT_CONTEXT,
    ReturnEndpoint,
    SummaryKey,
    VariableEndpoint,
)


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


def _make_cfg() -> CFG:
    """Build a simple two-block CFG for testing resolve methods."""
    inst0 = _make_inst(Opcode.CONST, result_reg=Register("%0"), operands=["42"])
    inst1 = _make_inst(Opcode.STORE_VAR, operands=["x", "%0"])
    inst2 = _make_inst(Opcode.LOAD_VAR, result_reg=Register("%1"), operands=["x"])
    inst3 = _make_inst(Opcode.RETURN, operands=["%1"])
    entry_block = BasicBlock(label=CodeLabel("entry"), instructions=[inst0, inst1])
    exit_block = BasicBlock(label=CodeLabel("exit"), instructions=[inst2, inst3])
    return CFG(blocks={"entry": entry_block, "exit": exit_block}, entry="entry")


class TestInstructionLocation:
    def test_construction_and_equality(self):
        loc1 = InstructionLocation(block_label=CodeLabel("entry"), instruction_index=0)
        loc2 = InstructionLocation(block_label=CodeLabel("entry"), instruction_index=0)
        assert loc1 == loc2

    def test_inequality(self):
        loc1 = InstructionLocation(block_label=CodeLabel("entry"), instruction_index=0)
        loc2 = InstructionLocation(block_label=CodeLabel("entry"), instruction_index=1)
        assert loc1 != loc2

    def test_hashable_in_set(self):
        loc1 = InstructionLocation(block_label=CodeLabel("entry"), instruction_index=0)
        loc2 = InstructionLocation(block_label=CodeLabel("entry"), instruction_index=0)
        loc3 = InstructionLocation(block_label=CodeLabel("exit"), instruction_index=0)
        s = {loc1, loc2, loc3}
        assert len(s) == 2

    def test_hashable_as_dict_key(self):
        loc = InstructionLocation(block_label=CodeLabel("entry"), instruction_index=0)
        d = {loc: "value"}
        assert d[loc] == "value"

    def test_resolve_returns_correct_instruction(self):
        cfg = _make_cfg()
        loc = InstructionLocation(block_label=CodeLabel("entry"), instruction_index=1)
        inst = loc.resolve(cfg)
        assert inst.opcode == Opcode.STORE_VAR
        assert inst.operands == ["x", "%0"]

    def test_resolve_different_block(self):
        cfg = _make_cfg()
        loc = InstructionLocation(block_label=CodeLabel("exit"), instruction_index=1)
        inst = loc.resolve(cfg)
        assert inst.opcode == Opcode.RETURN


class TestNoInstructionLocSentinel:
    def test_sentinel_exists(self):
        assert NO_INSTRUCTION_LOC.block_label == ""
        assert NO_INSTRUCTION_LOC.instruction_index == -1

    def test_sentinel_is_hashable(self):
        s = {NO_INSTRUCTION_LOC}
        assert NO_INSTRUCTION_LOC in s


class TestFunctionEntry:
    def test_construction_and_equality(self):
        fe1 = FunctionEntry(label=CodeLabel("func_a"), params=("x", "y"))
        fe2 = FunctionEntry(label=CodeLabel("func_a"), params=("x", "y"))
        assert fe1 == fe2

    def test_hashable_in_set(self):
        fe1 = FunctionEntry(label=CodeLabel("func_a"), params=("x",))
        fe2 = FunctionEntry(label=CodeLabel("func_b"), params=("y",))
        s = {fe1, fe2}
        assert len(s) == 2

    def test_entry_block_returns_correct_block(self):
        cfg = _make_cfg()
        fe = FunctionEntry(label=CodeLabel("entry"), params=())
        block = fe.entry_block(cfg)
        assert block.label == "entry"
        assert len(block.instructions) == 2

    def test_hashable_as_dict_key(self):
        fe = FunctionEntry(label=CodeLabel("func_a"), params=("x",))
        d = {fe: 42}
        assert d[fe] == 42


class TestFlowEndpoints:
    def test_variable_endpoint_construction(self):
        defn = NO_DEFINITION
        ve = VariableEndpoint(name="x", definition=defn)
        assert ve.name == "x"
        assert ve.definition is defn

    def test_variable_endpoint_hashable(self):
        ve1 = VariableEndpoint(name="x", definition=NO_DEFINITION)
        ve2 = VariableEndpoint(name="x", definition=NO_DEFINITION)
        assert ve1 == ve2
        s = {ve1, ve2}
        assert len(s) == 1

    def test_variable_endpoint_with_real_definition(self):
        inst = _make_inst(Opcode.STORE_VAR, operands=["x", "%0"])
        defn = Definition(
            variable=VarName("x"),
            block_label=CodeLabel("entry"),
            instruction_index=2,
            instruction=inst,
        )
        ve = VariableEndpoint(name="x", definition=defn)
        assert ve.definition.variable == VarName("x")
        # Hashable even with real Definition (Definition has custom __hash__)
        s = {ve}
        assert ve in s

    def test_field_endpoint_construction(self):
        base = VariableEndpoint(name="obj", definition=NO_DEFINITION)
        loc = InstructionLocation(block_label=CodeLabel("entry"), instruction_index=0)
        fe = FieldEndpoint(base=base, field=FieldName("name"), location=loc)
        assert fe.base.name == "obj"
        assert fe.field == FieldName("name")

    def test_field_endpoint_hashable(self):
        base = VariableEndpoint(name="obj", definition=NO_DEFINITION)
        loc = InstructionLocation(block_label=CodeLabel("entry"), instruction_index=0)
        fe1 = FieldEndpoint(base=base, field=FieldName("name"), location=loc)
        fe2 = FieldEndpoint(base=base, field=FieldName("name"), location=loc)
        s = {fe1, fe2}
        assert len(s) == 1

    def test_return_endpoint_construction(self):
        func = FunctionEntry(label=CodeLabel("func_a"), params=("x",))
        loc = InstructionLocation(block_label=CodeLabel("exit"), instruction_index=1)
        re = ReturnEndpoint(function=func, location=loc)
        assert re.function.label == "func_a"

    def test_return_endpoint_hashable(self):
        func = FunctionEntry(label=CodeLabel("func_a"), params=("x",))
        loc = InstructionLocation(block_label=CodeLabel("exit"), instruction_index=1)
        re1 = ReturnEndpoint(function=func, location=loc)
        re2 = ReturnEndpoint(function=func, location=loc)
        s = {re1, re2}
        assert len(s) == 1

    def test_flow_endpoint_isinstance_checks(self):
        """FlowEndpoint union: all three types are valid."""
        ve: FlowEndpoint = VariableEndpoint(name="x", definition=NO_DEFINITION)
        fe: FlowEndpoint = FieldEndpoint(
            base=VariableEndpoint(name="obj", definition=NO_DEFINITION),
            field=FieldName("f"),
            location=InstructionLocation(
                block_label=CodeLabel("b"), instruction_index=0
            ),
        )
        re: FlowEndpoint = ReturnEndpoint(
            function=FunctionEntry(label=CodeLabel("fn"), params=()),
            location=InstructionLocation(
                block_label=CodeLabel("b"), instruction_index=1
            ),
        )
        assert isinstance(ve, VariableEndpoint)
        assert isinstance(fe, FieldEndpoint)
        assert isinstance(re, ReturnEndpoint)
        # They are all FlowEndpoint per the union type
        assert isinstance(ve, VariableEndpoint | FieldEndpoint | ReturnEndpoint)
        assert isinstance(fe, VariableEndpoint | FieldEndpoint | ReturnEndpoint)
        assert isinstance(re, VariableEndpoint | FieldEndpoint | ReturnEndpoint)


class TestCallSite:
    def test_construction_and_equality(self):
        caller = FunctionEntry(label=CodeLabel("main"), params=())
        callee = FunctionEntry(label=CodeLabel("helper"), params=("a",))
        loc = InstructionLocation(block_label=CodeLabel("entry"), instruction_index=0)
        cs1 = CallSite(
            caller=caller,
            location=loc,
            callees=frozenset({callee}),
            arg_operands=("%0",),
        )
        cs2 = CallSite(
            caller=caller,
            location=loc,
            callees=frozenset({callee}),
            arg_operands=("%0",),
        )
        assert cs1 == cs2

    def test_hashable(self):
        caller = FunctionEntry(label=CodeLabel("main"), params=())
        loc = InstructionLocation(block_label=CodeLabel("entry"), instruction_index=0)
        cs = CallSite(
            caller=caller,
            location=loc,
            callees=frozenset(),
            arg_operands=(),
        )
        s = {cs}
        assert cs in s

    def test_instruction_resolves(self):
        cfg = _make_cfg()
        caller = FunctionEntry(label=CodeLabel("entry"), params=())
        loc = InstructionLocation(block_label=CodeLabel("entry"), instruction_index=0)
        cs = CallSite(
            caller=caller,
            location=loc,
            callees=frozenset(),
            arg_operands=(),
        )
        inst = cs.instruction(cfg)
        assert inst.opcode == Opcode.CONST

    def test_block_resolves(self):
        cfg = _make_cfg()
        caller = FunctionEntry(label=CodeLabel("entry"), params=())
        loc = InstructionLocation(block_label=CodeLabel("exit"), instruction_index=0)
        cs = CallSite(
            caller=caller,
            location=loc,
            callees=frozenset(),
            arg_operands=(),
        )
        block = cs.block(cfg)
        assert block.label == "exit"


class TestCallContext:
    def test_construction_and_equality(self):
        caller = FunctionEntry(label=CodeLabel("main"), params=())
        loc = InstructionLocation(block_label=CodeLabel("entry"), instruction_index=0)
        site = CallSite(
            caller=caller,
            location=loc,
            callees=frozenset(),
            arg_operands=(),
        )
        ctx1 = CallContext(site=site)
        ctx2 = CallContext(site=site)
        assert ctx1 == ctx2

    def test_hashable(self):
        ctx = ROOT_CONTEXT
        s = {ctx}
        assert ctx in s

    def test_root_context_is_distinct(self):
        caller = FunctionEntry(label=CodeLabel("main"), params=())
        loc = InstructionLocation(block_label=CodeLabel("entry"), instruction_index=0)
        site = CallSite(
            caller=caller,
            location=loc,
            callees=frozenset(),
            arg_operands=(),
        )
        ctx = CallContext(site=site)
        assert ctx != ROOT_CONTEXT


class TestFunctionSummary:
    def test_construction(self):
        func = FunctionEntry(label=CodeLabel("f"), params=("x",))
        ctx = ROOT_CONTEXT
        src = VariableEndpoint(name="x", definition=NO_DEFINITION)
        sink = ReturnEndpoint(
            function=func,
            location=InstructionLocation(
                block_label=CodeLabel("f"), instruction_index=2
            ),
        )
        summary = FunctionSummary(
            function=func,
            context=ctx,
            flows=frozenset({(src, sink)}),
        )
        assert summary.function.label == "f"
        assert len(summary.flows) == 1

    def test_flows_is_frozenset(self):
        func = FunctionEntry(label=CodeLabel("f"), params=())
        summary = FunctionSummary(
            function=func,
            context=ROOT_CONTEXT,
            flows=frozenset(),
        )
        assert isinstance(summary.flows, frozenset)

    def test_hashable(self):
        func = FunctionEntry(label=CodeLabel("f"), params=())
        summary = FunctionSummary(
            function=func,
            context=ROOT_CONTEXT,
            flows=frozenset(),
        )
        s = {summary}
        assert summary in s


class TestSummaryKey:
    def test_construction_and_equality(self):
        func = FunctionEntry(label=CodeLabel("f"), params=())
        key1 = SummaryKey(function=func, context=ROOT_CONTEXT)
        key2 = SummaryKey(function=func, context=ROOT_CONTEXT)
        assert key1 == key2

    def test_usable_as_dict_key(self):
        func = FunctionEntry(label=CodeLabel("f"), params=())
        key = SummaryKey(function=func, context=ROOT_CONTEXT)
        d = {key: "summary"}
        assert d[key] == "summary"

    def test_different_contexts_produce_different_keys(self):
        func = FunctionEntry(label=CodeLabel("f"), params=())
        caller = FunctionEntry(label=CodeLabel("main"), params=())
        loc = InstructionLocation(block_label=CodeLabel("entry"), instruction_index=0)
        site = CallSite(
            caller=caller,
            location=loc,
            callees=frozenset({func}),
            arg_operands=(),
        )
        ctx = CallContext(site=site)
        key1 = SummaryKey(function=func, context=ROOT_CONTEXT)
        key2 = SummaryKey(function=func, context=ctx)
        assert key1 != key2
        assert len({key1, key2}) == 2


class TestCallGraph:
    def test_construction(self):
        f1 = FunctionEntry(label=CodeLabel("f1"), params=())
        f2 = FunctionEntry(label=CodeLabel("f2"), params=("x",))
        loc = InstructionLocation(block_label=CodeLabel("f1"), instruction_index=0)
        site = CallSite(
            caller=f1,
            location=loc,
            callees=frozenset({f2}),
            arg_operands=("%0",),
        )
        cg = CallGraph(
            functions=frozenset({f1, f2}),
            call_sites=frozenset({site}),
        )
        assert len(cg.functions) == 2
        assert len(cg.call_sites) == 1

    def test_hashable(self):
        cg = CallGraph(functions=frozenset(), call_sites=frozenset())
        s = {cg}
        assert cg in s


class TestInterproceduralResult:
    def test_construction(self):
        cg = CallGraph(functions=frozenset(), call_sites=frozenset())
        result = InterproceduralResult(
            call_graph=cg,
            summaries={},
            whole_program_graph={},
            raw_program_graph={},
        )
        assert result.call_graph is cg
        assert result.summaries == {}
        assert result.whole_program_graph == {}
        assert result.raw_program_graph == {}

    def test_with_populated_summaries(self):
        func = FunctionEntry(label=CodeLabel("f"), params=("x",))
        cg = CallGraph(functions=frozenset({func}), call_sites=frozenset())
        key = SummaryKey(function=func, context=ROOT_CONTEXT)
        summary = FunctionSummary(
            function=func, context=ROOT_CONTEXT, flows=frozenset()
        )
        src = VariableEndpoint(name="x", definition=NO_DEFINITION)
        sink = VariableEndpoint(name="y", definition=NO_DEFINITION)
        result = InterproceduralResult(
            call_graph=cg,
            summaries={key: summary},
            whole_program_graph={src: frozenset({sink})},
            raw_program_graph={src: frozenset({sink})},
        )
        assert key in result.summaries
        assert sink in result.whole_program_graph[src]


class TestNoDefinitionSentinel:
    def test_sentinel_is_definition(self):
        assert isinstance(NO_DEFINITION, Definition)

    def test_sentinel_is_hashable(self):
        s = {NO_DEFINITION}
        assert NO_DEFINITION in s

    def test_sentinel_has_dummy_values(self):
        assert NO_DEFINITION.variable == ""
        assert NO_DEFINITION.block_label == ""
        assert NO_DEFINITION.instruction_index == -1
