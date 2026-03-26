"""Tests for InstructionBase.map_registers() and map_labels()."""

from interpreter.instructions import (
    Binop,
    Branch,
    BranchIf,
    CallFunction,
    Const,
    DeclVar,
    Label_,
    Return_,
    SetContinuation,
    StoreField,
    TryPush,
    WriteRegion,
)
from interpreter.operator_kind import BinopKind
from interpreter.ir import CodeLabel, NO_LABEL, SpreadArguments
from interpreter.register import Register
from interpreter.var_name import VarName


def _inc(reg: Register) -> Register:
    """Test helper: increment register number by 100."""
    return reg.rebase(100)


def _ns(label: CodeLabel) -> CodeLabel:
    """Test helper: namespace a label."""
    return label.namespace("mod")


class TestMapRegisters:
    def test_binop(self):
        inst = Binop(
            result_reg=Register("%r0"),
            operator=BinopKind.ADD,
            left=Register("%r1"),
            right=Register("%r2"),
        )
        mapped = inst.map_registers(_inc)
        assert mapped.result_reg == Register("%r100")
        assert mapped.left == Register("%r101")
        assert mapped.right == Register("%r102")
        assert mapped.operator == "+"  # not a register — unchanged

    def test_decl_var(self):
        inst = DeclVar(name=VarName("x"), value_reg=Register("%r0"))
        mapped = inst.map_registers(_inc)
        assert mapped.value_reg == Register("%r100")
        assert mapped.name == VarName("x")  # not a register — unchanged

    def test_call_function_with_spread(self):
        inst = CallFunction(
            result_reg=Register("%r0"),
            func_name="f",
            args=(
                Register("%r1"),
                SpreadArguments(register=Register("%r2")),
                Register("%r3"),
            ),
        )
        mapped = inst.map_registers(_inc)
        assert mapped.result_reg == Register("%r100")
        assert mapped.args[0] == Register("%r101")
        assert isinstance(mapped.args[1], SpreadArguments)
        assert mapped.args[1].register == Register("%r102")
        assert mapped.args[2] == Register("%r103")

    def test_return_with_value(self):
        inst = Return_(value_reg=Register("%r5"))
        mapped = inst.map_registers(_inc)
        assert mapped.value_reg == Register("%r105")

    def test_return_void(self):
        inst = Return_(value_reg=None)
        mapped = inst.map_registers(_inc)
        assert mapped.value_reg is None

    def test_no_register_unchanged(self):
        inst = Label_(label=CodeLabel("entry"))
        mapped = inst.map_registers(_inc)
        assert mapped.label == CodeLabel("entry")  # labels not affected

    def test_const_value_not_touched(self):
        inst = Const(result_reg=Register("%r0"), value="42")
        mapped = inst.map_registers(_inc)
        assert mapped.result_reg == Register("%r100")
        assert mapped.value == "42"  # str field — not a register

    def test_store_field(self):
        inst = StoreField(
            obj_reg=Register("%r0"), field_name="x", value_reg=Register("%r1")
        )
        mapped = inst.map_registers(_inc)
        assert mapped.obj_reg == Register("%r100")
        assert mapped.value_reg == Register("%r101")
        assert mapped.field_name == "x"

    def test_write_region(self):
        inst = WriteRegion(
            region_reg=Register("%r0"),
            offset_reg=Register("%r1"),
            length=8,
            value_reg=Register("%r2"),
        )
        mapped = inst.map_registers(_inc)
        assert mapped.region_reg == Register("%r100")
        assert mapped.offset_reg == Register("%r101")
        assert mapped.value_reg == Register("%r102")
        assert mapped.length == 8  # int field — unchanged


class TestMapLabels:
    def test_label(self):
        inst = Label_(label=CodeLabel("entry"))
        mapped = inst.map_labels(_ns)
        assert mapped.label == CodeLabel("mod.entry")

    def test_branch(self):
        inst = Branch(label=CodeLabel("L_end"))
        mapped = inst.map_labels(_ns)
        assert mapped.label == CodeLabel("mod.L_end")

    def test_branch_if(self):
        inst = BranchIf(
            cond_reg=Register("%r0"),
            branch_targets=(CodeLabel("L_true"), CodeLabel("L_false")),
        )
        mapped = inst.map_labels(_ns)
        assert mapped.branch_targets == (
            CodeLabel("mod.L_true"),
            CodeLabel("mod.L_false"),
        )
        assert mapped.cond_reg == Register("%r0")  # registers unchanged

    def test_try_push(self):
        inst = TryPush(
            catch_labels=(CodeLabel("catch_0"),),
            finally_label=CodeLabel("finally_0"),
            end_label=CodeLabel("end_try"),
        )
        mapped = inst.map_labels(_ns)
        assert mapped.catch_labels == (CodeLabel("mod.catch_0"),)
        assert mapped.finally_label == CodeLabel("mod.finally_0")
        assert mapped.end_label == CodeLabel("mod.end_try")

    def test_set_continuation(self):
        inst = SetContinuation(name="__cont", target_label=CodeLabel("L_resume"))
        mapped = inst.map_labels(_ns)
        assert mapped.target_label == CodeLabel("mod.L_resume")
        assert mapped.name == "__cont"  # str field — unchanged

    def test_no_label_unchanged(self):
        inst = Const(result_reg=Register("%r0"), value="42")
        mapped = inst.map_labels(_ns)
        assert mapped.label == NO_LABEL  # NO_LABEL.namespace() returns self

    def test_binop_no_labels(self):
        inst = Binop(
            result_reg=Register("%r0"),
            operator=BinopKind.ADD,
            left=Register("%r1"),
            right=Register("%r2"),
        )
        mapped = inst.map_labels(_ns)
        assert mapped.result_reg == Register("%r0")  # registers unchanged
