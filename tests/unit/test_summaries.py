"""Tests for interprocedural function summary extraction."""

from __future__ import annotations

from interpreter.cfg import build_cfg
from interpreter.cfg_types import BasicBlock, CFG
from interpreter.dataflow import Definition
from interpreter.ir import IRInstruction, Opcode
from interpreter import constants
from interpreter.interprocedural.types import (
    CallContext,
    CallSite,
    FieldEndpoint,
    FunctionEntry,
    FunctionSummary,
    InstructionLocation,
    NO_DEFINITION,
    ReturnEndpoint,
    VariableEndpoint,
)
from interpreter.interprocedural.summaries import (
    build_summary,
    extract_sub_cfg,
)


def _inst(opcode: Opcode, result_reg=None, operands=None, label=None):
    return IRInstruction(
        opcode=opcode,
        result_reg=result_reg,
        operands=operands if operands is not None else [],
        label=label,
    )


def _make_context() -> CallContext:
    """Build a root context for testing."""
    return CallContext(
        site=CallSite(
            caller=FunctionEntry(label="__root__", params=()),
            location=InstructionLocation(block_label="", instruction_index=-1),
            callees=frozenset(),
            arg_operands=(),
        )
    )


class TestExtractSubCfg:
    def test_extracts_only_function_blocks(self):
        """A program with main + func__foo: extract_sub_cfg returns only foo's blocks."""
        ir = [
            _inst(Opcode.LABEL, label="entry"),
            _inst(Opcode.CONST, result_reg="%0", operands=["42"]),
            _inst(Opcode.RETURN, operands=["%0"]),
            _inst(Opcode.LABEL, label="func__foo"),
            _inst(Opcode.SYMBOLIC, result_reg="%1", operands=["param:x"]),
            _inst(Opcode.STORE_VAR, operands=["x", "%1"]),
            _inst(Opcode.LOAD_VAR, result_reg="%2", operands=["x"]),
            _inst(Opcode.RETURN, operands=["%2"]),
        ]
        full_cfg = build_cfg(ir)
        entry = FunctionEntry(label="func__foo", params=("x",))

        sub = extract_sub_cfg(full_cfg, entry)

        assert "func__foo" in sub.blocks
        assert "entry" not in sub.blocks
        assert sub.entry == "func__foo"

    def test_extracts_function_with_branches(self):
        """Function with internal branching blocks — all prefixed blocks included."""
        ir = [
            _inst(Opcode.LABEL, label="entry"),
            _inst(Opcode.CONST, result_reg="%0", operands=["0"]),
            _inst(Opcode.RETURN, operands=["%0"]),
            _inst(Opcode.LABEL, label="func__bar"),
            _inst(Opcode.SYMBOLIC, result_reg="%1", operands=["param:x"]),
            _inst(Opcode.STORE_VAR, operands=["x", "%1"]),
            _inst(Opcode.LOAD_VAR, result_reg="%2", operands=["x"]),
            _inst(
                Opcode.BRANCH_IF,
                operands=["%2"],
                label="func__bar_if_true_1, func__bar_if_false_1",
            ),
            _inst(Opcode.LABEL, label="func__bar_if_true_1"),
            _inst(Opcode.CONST, result_reg="%3", operands=["1"]),
            _inst(Opcode.RETURN, operands=["%3"]),
            _inst(Opcode.LABEL, label="func__bar_if_false_1"),
            _inst(Opcode.CONST, result_reg="%4", operands=["0"]),
            _inst(Opcode.RETURN, operands=["%4"]),
        ]
        full_cfg = build_cfg(ir)
        entry = FunctionEntry(label="func__bar", params=("x",))

        sub = extract_sub_cfg(full_cfg, entry)

        assert "func__bar" in sub.blocks
        assert "func__bar_if_true_1" in sub.blocks
        assert "func__bar_if_false_1" in sub.blocks
        assert "entry" not in sub.blocks


class TestBuildSummary:
    def test_passthrough_param_to_return(self):
        """SYMBOLIC param:x; STORE_VAR x; LOAD_VAR x; RETURN → (Variable(x), Return)."""
        ir = [
            _inst(Opcode.LABEL, label="func__id"),
            _inst(Opcode.SYMBOLIC, result_reg="%0", operands=["param:x"]),
            _inst(Opcode.STORE_VAR, operands=["x", "%0"]),
            _inst(Opcode.LOAD_VAR, result_reg="%1", operands=["x"]),
            _inst(Opcode.RETURN, operands=["%1"]),
        ]
        cfg = build_cfg(ir)
        entry = FunctionEntry(label="func__id", params=("x",))
        ctx = _make_context()

        summary = build_summary(cfg, entry, ctx)

        # There should be exactly one flow: x → return
        assert len(summary.flows) == 1
        src, dst = next(iter(summary.flows))
        assert isinstance(src, VariableEndpoint)
        assert src.name == "x"
        assert isinstance(dst, ReturnEndpoint)
        assert dst.function == entry

    def test_passthrough_param_to_return_with_decl_var(self):
        """SYMBOLIC param:x; DECL_VAR x; LOAD_VAR x; RETURN → (Variable(x), Return).

        Real frontends emit DECL_VAR (not STORE_VAR) for parameter declarations.
        """
        ir = [
            _inst(Opcode.LABEL, label="func__id"),
            _inst(Opcode.SYMBOLIC, result_reg="%0", operands=["param:x"]),
            _inst(Opcode.DECL_VAR, operands=["x", "%0"]),
            _inst(Opcode.LOAD_VAR, result_reg="%1", operands=["x"]),
            _inst(Opcode.RETURN, operands=["%1"]),
        ]
        cfg = build_cfg(ir)
        entry = FunctionEntry(label="func__id", params=("x",))
        ctx = _make_context()

        summary = build_summary(cfg, entry, ctx)

        assert len(summary.flows) == 1
        src, dst = next(iter(summary.flows))
        assert isinstance(src, VariableEndpoint)
        assert src.name == "x"
        assert isinstance(dst, ReturnEndpoint)
        assert dst.function == entry

    def test_param_through_computation_to_return(self):
        """SYMBOLIC param:x; DECL_VAR x; LOAD_VAR x; BINOP + x 1; RETURN → x flows to return.

        Tests the case where the return operand is from a computation (BINOP), not
        a direct LOAD_VAR. The register trace must walk backward through BINOP to
        find the LOAD_VAR source.
        """
        ir = [
            _inst(Opcode.LABEL, label="func__inc"),
            _inst(Opcode.SYMBOLIC, result_reg="%0", operands=["param:x"]),
            _inst(Opcode.DECL_VAR, operands=["x", "%0"]),
            _inst(Opcode.LOAD_VAR, result_reg="%1", operands=["x"]),
            _inst(Opcode.CONST, result_reg="%2", operands=["1"]),
            _inst(Opcode.BINOP, result_reg="%3", operands=["+", "%1", "%2"]),
            _inst(Opcode.RETURN, operands=["%3"]),
        ]
        cfg = build_cfg(ir)
        entry = FunctionEntry(label="func__inc", params=("x",))
        ctx = _make_context()

        summary = build_summary(cfg, entry, ctx)

        assert len(summary.flows) == 1
        src, dst = next(iter(summary.flows))
        assert isinstance(src, VariableEndpoint)
        assert src.name == "x"
        assert isinstance(dst, ReturnEndpoint)

    def test_two_params_to_return(self):
        """a + b → return: both params flow to return."""
        ir = [
            _inst(Opcode.LABEL, label="func__add"),
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
        entry = FunctionEntry(label="func__add", params=("a", "b"))
        ctx = _make_context()

        summary = build_summary(cfg, entry, ctx)

        source_names = {
            src.name for src, dst in summary.flows if isinstance(src, VariableEndpoint)
        }
        assert "a" in source_names
        assert "b" in source_names

        return_flows = [
            (src, dst) for src, dst in summary.flows if isinstance(dst, ReturnEndpoint)
        ]
        assert len(return_flows) == 2

    def test_param_to_field_write(self):
        """STORE_FIELD obj "name" val → (Variable(val), FieldEndpoint(obj, "name"))."""
        ir = [
            _inst(Opcode.LABEL, label="func__setter"),
            _inst(Opcode.SYMBOLIC, result_reg="%0", operands=["param:obj"]),
            _inst(Opcode.STORE_VAR, operands=["obj", "%0"]),
            _inst(Opcode.SYMBOLIC, result_reg="%1", operands=["param:val"]),
            _inst(Opcode.STORE_VAR, operands=["val", "%1"]),
            _inst(Opcode.LOAD_VAR, result_reg="%2", operands=["val"]),
            _inst(Opcode.LOAD_VAR, result_reg="%3", operands=["obj"]),
            _inst(Opcode.STORE_FIELD, operands=["%3", "name", "%2"]),
        ]
        cfg = build_cfg(ir)
        entry = FunctionEntry(label="func__setter", params=("obj", "val"))
        ctx = _make_context()

        summary = build_summary(cfg, entry, ctx)

        field_flows = [
            (src, dst) for src, dst in summary.flows if isinstance(dst, FieldEndpoint)
        ]
        assert len(field_flows) >= 1
        src, dst = field_flows[0]
        assert isinstance(src, VariableEndpoint)
        assert src.name == "val"
        assert dst.field == "name"
        assert dst.base.name == "obj"

    def test_field_read_to_return(self):
        """LOAD_FIELD obj "name" → return: (FieldEndpoint(obj, "name"), Return)."""
        ir = [
            _inst(Opcode.LABEL, label="func__getter"),
            _inst(Opcode.SYMBOLIC, result_reg="%0", operands=["param:obj"]),
            _inst(Opcode.STORE_VAR, operands=["obj", "%0"]),
            _inst(Opcode.LOAD_VAR, result_reg="%1", operands=["obj"]),
            _inst(Opcode.LOAD_FIELD, result_reg="%2", operands=["%1", "name"]),
            _inst(Opcode.STORE_VAR, operands=["__field_name", "%2"]),
            _inst(Opcode.LOAD_VAR, result_reg="%3", operands=["__field_name"]),
            _inst(Opcode.RETURN, operands=["%3"]),
        ]
        cfg = build_cfg(ir)
        entry = FunctionEntry(label="func__getter", params=("obj",))
        ctx = _make_context()

        summary = build_summary(cfg, entry, ctx)

        field_source_flows = [
            (src, dst) for src, dst in summary.flows if isinstance(src, FieldEndpoint)
        ]
        assert len(field_source_flows) >= 1
        src, dst = field_source_flows[0]
        assert src.field == "name"
        assert src.base.name == "obj"
        assert isinstance(dst, ReturnEndpoint)

    def test_constant_return_yields_no_param_flows(self):
        """CONST 42; RETURN → no param-connected flows."""
        ir = [
            _inst(Opcode.LABEL, label="func__const"),
            _inst(Opcode.CONST, result_reg="%0", operands=["42"]),
            _inst(Opcode.RETURN, operands=["%0"]),
        ]
        cfg = build_cfg(ir)
        entry = FunctionEntry(label="func__const", params=())
        ctx = _make_context()

        summary = build_summary(cfg, entry, ctx)

        assert len(summary.flows) == 0

    def test_summary_is_frozen(self):
        """FunctionSummary should be immutable (frozen dataclass)."""
        ir = [
            _inst(Opcode.LABEL, label="func__id"),
            _inst(Opcode.SYMBOLIC, result_reg="%0", operands=["param:x"]),
            _inst(Opcode.STORE_VAR, operands=["x", "%0"]),
            _inst(Opcode.LOAD_VAR, result_reg="%1", operands=["x"]),
            _inst(Opcode.RETURN, operands=["%1"]),
        ]
        cfg = build_cfg(ir)
        entry = FunctionEntry(label="func__id", params=("x",))
        ctx = _make_context()

        summary = build_summary(cfg, entry, ctx)

        assert isinstance(summary, FunctionSummary)
        assert summary.function == entry
        assert summary.context == ctx
