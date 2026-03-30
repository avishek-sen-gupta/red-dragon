"""Unit tests for interprocedural summary extraction — pointer dereference flows."""

from __future__ import annotations

from interpreter.cfg_types import BasicBlock, CFG
from interpreter.constants import PARAM_PREFIX
from interpreter.ir import CodeLabel
from interpreter.register import Register
from interpreter.var_name import VarName
from interpreter.instructions import (
    Const,
    DeclVar,
    LoadVar,
    Return_,
    StoreIndirect,
    Symbolic,
)
from interpreter.interprocedural.summaries import build_summary
from interpreter.interprocedural.types import (
    CallContext,
    DereferenceEndpoint,
    FunctionEntry,
    ROOT_CONTEXT,
    VariableEndpoint,
)


def _build_set_val_cfg() -> tuple[CFG, FunctionEntry]:
    """Build CFG for: void set_val(int *p) { *p = 99; }

    IR:
      SYMBOLIC %0 param:p
      DECL_VAR p, %0
      CONST %1, 99
      LOAD_VAR %2, p
      STORE_INDIRECT %2, %1   # *p = 99
      CONST %3, 0
      RETURN %3
    """
    instructions = [
        Symbolic(result_reg=Register("%0"), hint=f"{PARAM_PREFIX}p"),
        DeclVar(name=VarName("p"), value_reg=Register("%0")),
        Const(result_reg=Register("%1"), value="99"),
        LoadVar(result_reg=Register("%2"), name=VarName("p")),
        StoreIndirect(ptr_reg=Register("%2"), value_reg=Register("%1")),
        Const(result_reg=Register("%3"), value="0"),
        Return_(value_reg=Register("%3")),
    ]
    block = BasicBlock(
        label=CodeLabel("func_set_val_0"),
        instructions=instructions,
        successors=[],
        predecessors=[],
    )
    cfg = CFG(
        blocks={CodeLabel("func_set_val_0"): block},
        entry=CodeLabel("func_set_val_0"),
    )
    entry = FunctionEntry(label=CodeLabel("func_set_val_0"), params=("p",))
    return cfg, entry


class TestStoreIndirectSummary:
    def test_set_val_produces_deref_write_flow(self):
        """*p = 99 should produce VariableEndpoint(p) -> DereferenceEndpoint(p)."""
        cfg, entry = _build_set_val_cfg()
        summary = build_summary(cfg, entry, ROOT_CONTEXT)
        assert len(summary.flows) > 0, "Expected at least one flow for *p = 99"

    def test_set_val_flow_source_is_param_p(self):
        cfg, entry = _build_set_val_cfg()
        summary = build_summary(cfg, entry, ROOT_CONTEXT)
        sources = {src for src, _ in summary.flows}
        source_names = {s.name for s in sources if isinstance(s, VariableEndpoint)}
        assert (
            "p" in source_names
        ), f"Expected param 'p' as flow source, got {source_names}"

    def test_set_val_flow_destination_is_deref_endpoint(self):
        cfg, entry = _build_set_val_cfg()
        summary = build_summary(cfg, entry, ROOT_CONTEXT)
        destinations = {dst for _, dst in summary.flows}
        deref_dsts = [d for d in destinations if isinstance(d, DereferenceEndpoint)]
        assert (
            len(deref_dsts) > 0
        ), f"Expected DereferenceEndpoint destination, got {destinations}"

    def test_set_val_deref_endpoint_base_is_param_p(self):
        cfg, entry = _build_set_val_cfg()
        summary = build_summary(cfg, entry, ROOT_CONTEXT)
        deref_dsts = [
            dst for _, dst in summary.flows if isinstance(dst, DereferenceEndpoint)
        ]
        assert len(deref_dsts) > 0
        assert deref_dsts[0].base.name == "p"
