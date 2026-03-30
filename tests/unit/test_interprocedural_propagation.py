"""Unit tests for interprocedural propagation — ADDRESS_OF tracing and DereferenceEndpoint substitution."""

from __future__ import annotations

from interpreter.cfg_types import BasicBlock, CFG
from interpreter.func_name import FuncName
from interpreter.ir import CodeLabel
from interpreter.register import Register
from interpreter.var_name import VarName
from interpreter.instructions import (
    AddressOf,
    CallFunction,
    Const,
    DeclVar,
    LoadVar,
)
from interpreter.interprocedural.propagation import (
    _trace_reg_to_var,
    _substitute_endpoint,
    apply_summary_at_call_site,
)
from interpreter.interprocedural.types import (
    CallSite,
    DereferenceEndpoint,
    FunctionEntry,
    FunctionSummary,
    InstructionLocation,
    NO_DEFINITION,
    ROOT_CONTEXT,
    VariableEndpoint,
)


def _build_caller_cfg_with_address_of() -> CFG:
    """Build CFG for caller: int x = 10; set_val(&x);

    IR:
      CONST %5, 10
      DECL_VAR x, %5
      ADDRESS_OF %6, x
      CALL_FUNCTION %7, set_val, %6
    """
    instructions = [
        Const(result_reg=Register("%5"), value="10"),
        DeclVar(name=VarName("x"), value_reg=Register("%5")),
        AddressOf(result_reg=Register("%6"), var_name=VarName("x")),
        CallFunction(
            result_reg=Register("%7"),
            func_name=FuncName("set_val"),
            args=(Register("%6"),),
        ),
    ]
    block = BasicBlock(
        label=CodeLabel("func_main_0"),
        instructions=instructions,
        successors=[],
        predecessors=[],
    )
    return CFG(
        blocks={CodeLabel("func_main_0"): block},
        entry=CodeLabel("func_main_0"),
    )


class TestTraceRegToVarAddressOf:
    def test_address_of_traces_to_var_name(self):
        """ADDRESS_OF %6, x -> _trace_reg_to_var('%6') should return 'x'."""
        cfg = _build_caller_cfg_with_address_of()
        result = _trace_reg_to_var("%6", cfg, "func_main_0")
        assert result == "x", f"Expected 'x', got {result!r}"

    def test_load_var_still_works(self):
        """Existing LOAD_VAR tracing should still work."""
        instructions = [
            LoadVar(result_reg=Register("%1"), name=VarName("y")),
        ]
        block = BasicBlock(
            label=CodeLabel("b"),
            instructions=instructions,
            successors=[],
            predecessors=[],
        )
        cfg = CFG(blocks={CodeLabel("b"): block}, entry=CodeLabel("b"))
        result = _trace_reg_to_var("%1", cfg, "b")
        assert result == "y"


class TestSubstituteDereferenceEndpoint:
    def test_deref_endpoint_collapses_to_variable(self):
        """DereferenceEndpoint(p) with p -> &x should collapse to VariableEndpoint(x)."""
        cfg = _build_caller_cfg_with_address_of()
        callee = FunctionEntry(label=CodeLabel("func_set_val_0"), params=("p",))
        caller = FunctionEntry(label=CodeLabel("func_main_0"), params=())
        call_loc = InstructionLocation(
            block_label=CodeLabel("func_main_0"), instruction_index=3
        )
        call_site = CallSite(
            caller=caller,
            location=call_loc,
            callees=frozenset({callee}),
            arg_operands=("%6",),
        )
        deref_ep = DereferenceEndpoint(
            base=VariableEndpoint(name="p", definition=NO_DEFINITION),
            location=InstructionLocation(
                block_label=CodeLabel("func_set_val_0"), instruction_index=4
            ),
        )
        result = _substitute_endpoint(deref_ep, {"p": "%6"}, callee, call_site, cfg)
        assert isinstance(result, VariableEndpoint)
        assert result.name == "x", f"Expected 'x', got {result.name!r}"


class TestApplySummaryWithPointers:
    def test_end_to_end_set_val(self):
        """Summary VariableEndpoint(p) -> DereferenceEndpoint(p) at call site set_val(&x)
        should produce VariableEndpoint(x) -> VariableEndpoint(x)."""
        cfg = _build_caller_cfg_with_address_of()
        callee = FunctionEntry(label=CodeLabel("func_set_val_0"), params=("p",))
        caller = FunctionEntry(label=CodeLabel("func_main_0"), params=())
        call_loc = InstructionLocation(
            block_label=CodeLabel("func_main_0"), instruction_index=3
        )
        call_site = CallSite(
            caller=caller,
            location=call_loc,
            callees=frozenset({callee}),
            arg_operands=("%6",),
        )
        summary = FunctionSummary(
            function=callee,
            context=ROOT_CONTEXT,
            flows=frozenset(
                {
                    (
                        VariableEndpoint(name="p", definition=NO_DEFINITION),
                        DereferenceEndpoint(
                            base=VariableEndpoint(name="p", definition=NO_DEFINITION),
                            location=InstructionLocation(
                                block_label=CodeLabel("func_set_val_0"),
                                instruction_index=4,
                            ),
                        ),
                    ),
                }
            ),
        )
        propagated = apply_summary_at_call_site(call_site, summary, callee, cfg)
        assert len(propagated) == 1
        src, dst = next(iter(propagated))
        assert isinstance(src, VariableEndpoint)
        assert isinstance(dst, VariableEndpoint)
        assert src.name == "x"
        assert dst.name == "x"
