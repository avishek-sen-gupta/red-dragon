"""Unit tests for call graph construction — TDD: written BEFORE implementation."""

from interpreter.cfg_types import BasicBlock, CFG
from interpreter.ir import IRInstruction, Opcode, CodeLabel
from interpreter.registry import FunctionRegistry
from interpreter.interprocedural.call_graph import (
    build_function_entries,
    build_call_graph,
)
from interpreter.interprocedural.types import (
    FunctionEntry,
    CallSite,
    InstructionLocation,
)


def _make_cfg(blocks: dict[str, BasicBlock], entry: str = "entry") -> CFG:
    return CFG(blocks=blocks, entry=entry)


def _make_registry(
    func_params: dict[str, list[str]] | None = None,
    class_methods: dict[str, dict[str, list[str]]] | None = None,
) -> FunctionRegistry:
    return FunctionRegistry(
        func_params=func_params or {},
        class_methods=class_methods or {},
    )


class TestBuildFunctionEntries:
    def test_creates_entry_for_each_registered_function(self):
        registry = _make_registry(
            func_params={
                "func_foo": ["x", "y"],
                "func_bar": ["a"],
            }
        )
        cfg = _make_cfg(
            blocks={
                "entry": BasicBlock(label=CodeLabel("entry"), instructions=[]),
                "func_foo": BasicBlock(label=CodeLabel("func_foo"), instructions=[]),
                "func_bar": BasicBlock(label=CodeLabel("func_bar"), instructions=[]),
            }
        )

        entries = build_function_entries(cfg, registry)

        assert len(entries) == 2
        assert entries["func_foo"] == FunctionEntry(
            label=CodeLabel("func_foo"), params=("x", "y")
        )
        assert entries["func_bar"] == FunctionEntry(
            label=CodeLabel("func_bar"), params=("a",)
        )

    def test_empty_registry_produces_empty_entries(self):
        registry = _make_registry()
        cfg = _make_cfg(
            blocks={"entry": BasicBlock(label=CodeLabel("entry"), instructions=[])}
        )

        entries = build_function_entries(cfg, registry)

        assert entries == {}


class TestBuildCallGraphDirectCall:
    def test_single_direct_call(self):
        """CALL_FUNCTION 'func_foo' %1 %2 → single callee, arg_operands = ('%1', '%2')."""
        call_inst = IRInstruction(
            opcode=Opcode.CALL_FUNCTION,
            operands=["func_foo", "%1", "%2"],
            result_reg="%3",
        )
        cfg = _make_cfg(
            blocks={
                "func_main": BasicBlock(
                    label=CodeLabel("func_main"), instructions=[call_inst]
                ),
                "func_foo": BasicBlock(label=CodeLabel("func_foo"), instructions=[]),
            }
        )
        registry = _make_registry(func_params={"func_main": [], "func_foo": ["x", "y"]})

        cg = build_call_graph(cfg, registry)

        assert len(cg.call_sites) == 1
        site = next(iter(cg.call_sites))
        assert site.caller == FunctionEntry(label=CodeLabel("func_main"), params=())
        assert site.callees == frozenset(
            {FunctionEntry(label=CodeLabel("func_foo"), params=("x", "y"))}
        )
        assert site.arg_operands == ("%1", "%2")
        assert site.location == InstructionLocation(
            block_label=CodeLabel("func_main"), instruction_index=0
        )


class TestBuildCallGraphMethodCHA:
    def test_method_call_resolves_all_classes_via_cha(self):
        """CALL_METHOD %0 'speak' %1 with Dog.speak and Cat.speak → 2 callees."""
        call_inst = IRInstruction(
            opcode=Opcode.CALL_METHOD,
            operands=["%0", "speak", "%1"],
            result_reg="%2",
        )
        cfg = _make_cfg(
            blocks={
                "func_main": BasicBlock(
                    label=CodeLabel("func_main"), instructions=[call_inst]
                ),
                "func_Dog_speak": BasicBlock(
                    label=CodeLabel("func_Dog_speak"), instructions=[]
                ),
                "func_Cat_speak": BasicBlock(
                    label=CodeLabel("func_Cat_speak"), instructions=[]
                ),
            }
        )
        registry = _make_registry(
            func_params={
                "func_main": [],
                "func_Dog_speak": ["self", "volume"],
                "func_Cat_speak": ["self", "volume"],
            },
            class_methods={
                "Dog": {"speak": ["func_Dog_speak"]},
                "Cat": {"speak": ["func_Cat_speak"]},
            },
        )

        cg = build_call_graph(cfg, registry)

        assert len(cg.call_sites) == 1
        site = next(iter(cg.call_sites))
        assert site.callees == frozenset(
            {
                FunctionEntry(
                    label=CodeLabel("func_Dog_speak"), params=("self", "volume")
                ),
                FunctionEntry(
                    label=CodeLabel("func_Cat_speak"), params=("self", "volume")
                ),
            }
        )
        # arg_operands for CALL_METHOD: skip object register, skip method name
        assert site.arg_operands == ("%1",)


class TestBuildCallGraphUnknown:
    def test_unknown_call_has_empty_callees(self):
        """CALL_UNKNOWN %0 %1 → empty callees."""
        call_inst = IRInstruction(
            opcode=Opcode.CALL_UNKNOWN,
            operands=["%0", "%1"],
            result_reg="%2",
        )
        cfg = _make_cfg(
            blocks={
                "func_main": BasicBlock(
                    label=CodeLabel("func_main"), instructions=[call_inst]
                ),
            }
        )
        registry = _make_registry(func_params={"func_main": []})

        cg = build_call_graph(cfg, registry)

        assert len(cg.call_sites) == 1
        site = next(iter(cg.call_sites))
        assert site.callees == frozenset()
        assert site.arg_operands == ("%0", "%1")


class TestBuildCallGraphNoCalls:
    def test_no_calls_produces_empty_call_sites(self):
        """Program with no CALL_* → CallGraph has functions but empty call_sites."""
        store_inst = IRInstruction(
            opcode=Opcode.STORE_VAR,
            operands=["x", "%1"],
        )
        cfg = _make_cfg(
            blocks={
                "func_main": BasicBlock(
                    label=CodeLabel("func_main"), instructions=[store_inst]
                ),
            }
        )
        registry = _make_registry(func_params={"func_main": []})

        cg = build_call_graph(cfg, registry)

        assert len(cg.functions) == 1
        assert cg.call_sites == frozenset()


class TestBuildCallGraphRecursive:
    def test_recursive_call_has_caller_equal_to_callee(self):
        """func_foo contains CALL_FUNCTION 'func_foo' → caller == callee."""
        call_inst = IRInstruction(
            opcode=Opcode.CALL_FUNCTION,
            operands=["func_foo", "%1"],
            result_reg="%2",
        )
        cfg = _make_cfg(
            blocks={
                "func_foo": BasicBlock(
                    label=CodeLabel("func_foo"), instructions=[call_inst]
                ),
            }
        )
        registry = _make_registry(func_params={"func_foo": ["n"]})

        cg = build_call_graph(cfg, registry)

        assert len(cg.call_sites) == 1
        site = next(iter(cg.call_sites))
        foo_entry = FunctionEntry(label=CodeLabel("func_foo"), params=("n",))
        assert site.caller == foo_entry
        assert site.callees == frozenset({foo_entry})


class TestBuildCallGraphMultipleCalls:
    def test_multiple_calls_in_same_block(self):
        """Two CALL_FUNCTION in same block → 2 CallSites."""
        call1 = IRInstruction(
            opcode=Opcode.CALL_FUNCTION,
            operands=["func_foo"],
            result_reg="%1",
        )
        call2 = IRInstruction(
            opcode=Opcode.CALL_FUNCTION,
            operands=["func_bar", "%1"],
            result_reg="%2",
        )
        cfg = _make_cfg(
            blocks={
                "func_main": BasicBlock(
                    label=CodeLabel("func_main"), instructions=[call1, call2]
                ),
                "func_foo": BasicBlock(label=CodeLabel("func_foo"), instructions=[]),
                "func_bar": BasicBlock(label=CodeLabel("func_bar"), instructions=[]),
            }
        )
        registry = _make_registry(
            func_params={"func_main": [], "func_foo": [], "func_bar": ["x"]}
        )

        cg = build_call_graph(cfg, registry)

        assert len(cg.call_sites) == 2
        locations = {site.location.instruction_index for site in cg.call_sites}
        assert locations == {0, 1}


class TestBuildCallGraphNonExistent:
    def test_call_to_nonexistent_function_has_empty_callees(self):
        """CALL_FUNCTION 'func_nonexistent' → empty callees, no crash."""
        call_inst = IRInstruction(
            opcode=Opcode.CALL_FUNCTION,
            operands=["func_nonexistent", "%1"],
            result_reg="%2",
        )
        cfg = _make_cfg(
            blocks={
                "func_main": BasicBlock(
                    label=CodeLabel("func_main"), instructions=[call_inst]
                ),
            }
        )
        registry = _make_registry(func_params={"func_main": []})

        cg = build_call_graph(cfg, registry)

        assert len(cg.call_sites) == 1
        site = next(iter(cg.call_sites))
        assert site.callees == frozenset()
        assert site.arg_operands == ("%1",)
