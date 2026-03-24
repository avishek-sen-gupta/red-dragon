"""Test that typed instructions expose the same interface as IRInstruction."""

from interpreter.instructions import *
from interpreter.ir import CodeLabel, NO_LABEL, Opcode
from interpreter.register import Register, NO_REGISTER


class TestOpcodeProperty:
    def test_every_typed_class_has_opcode(self):
        cases = [
            (Const(value="42"), Opcode.CONST),
            (LoadVar(name="x"), Opcode.LOAD_VAR),
            (DeclVar(name="x", value_reg="%0"), Opcode.DECL_VAR),
            (StoreVar(name="x", value_reg="%0"), Opcode.STORE_VAR),
            (Symbolic(hint="p"), Opcode.SYMBOLIC),
            (Binop(operator="+", left="%0", right="%1"), Opcode.BINOP),
            (Unop(operator="!", operand="%0"), Opcode.UNOP),
            (CallFunction(func_name="f"), Opcode.CALL_FUNCTION),
            (CallMethod(obj_reg="%0", method_name="m"), Opcode.CALL_METHOD),
            (CallUnknown(target_reg="%0"), Opcode.CALL_UNKNOWN),
            (LoadField(obj_reg="%0", field_name="x"), Opcode.LOAD_FIELD),
            (
                StoreField(obj_reg="%0", field_name="x", value_reg="%1"),
                Opcode.STORE_FIELD,
            ),
            (
                LoadFieldIndirect(obj_reg="%0", name_reg="%1"),
                Opcode.LOAD_FIELD_INDIRECT,
            ),
            (LoadIndex(arr_reg="%0", index_reg="%1"), Opcode.LOAD_INDEX),
            (
                StoreIndex(arr_reg="%0", index_reg="%1", value_reg="%2"),
                Opcode.STORE_INDEX,
            ),
            (LoadIndirect(ptr_reg="%0"), Opcode.LOAD_INDIRECT),
            (StoreIndirect(ptr_reg="%0", value_reg="%1"), Opcode.STORE_INDIRECT),
            (AddressOf(var_name="x"), Opcode.ADDRESS_OF),
            (NewObject(type_hint="Foo"), Opcode.NEW_OBJECT),
            (NewArray(type_hint="list", size_reg="%0"), Opcode.NEW_ARRAY),
            (Label_(label=CodeLabel("entry")), Opcode.LABEL),
            (Branch(label=CodeLabel("L1")), Opcode.BRANCH),
            (BranchIf(cond_reg="%0"), Opcode.BRANCH_IF),
            (Return_(value_reg="%0"), Opcode.RETURN),
            (Throw_(value_reg="%0"), Opcode.THROW),
            (TryPush(catch_labels=(CodeLabel("c"),)), Opcode.TRY_PUSH),
            (TryPop(), Opcode.TRY_POP),
            (AllocRegion(size_reg="%0"), Opcode.ALLOC_REGION),
            (LoadRegion(region_reg="%0", offset_reg="%1"), Opcode.LOAD_REGION),
            (
                WriteRegion(region_reg="%0", offset_reg="%1", length=4, value_reg="%2"),
                Opcode.WRITE_REGION,
            ),
            (
                SetContinuation(name="c", target_label=CodeLabel("L")),
                Opcode.SET_CONTINUATION,
            ),
            (ResumeContinuation(name="c"), Opcode.RESUME_CONTINUATION),
        ]
        for inst, expected_opcode in cases:
            assert inst.opcode == expected_opcode, f"{type(inst).__name__}.opcode"


class TestResultRegDefault:
    """Types without result_reg should return NO_REGISTER."""

    def test_no_result_types(self):
        for inst in [
            DeclVar(name="x", value_reg="%0"),
            StoreVar(name="x", value_reg="%0"),
            StoreField(obj_reg="%0", field_name="x", value_reg="%1"),
            StoreIndex(arr_reg="%0", index_reg="%1", value_reg="%2"),
            StoreIndirect(ptr_reg="%0", value_reg="%1"),
            Label_(label=CodeLabel("entry")),
            Branch(label=CodeLabel("L1")),
            BranchIf(cond_reg="%0"),
            Return_(value_reg="%0"),
            Throw_(value_reg="%0"),
            TryPush(),
            TryPop(),
            WriteRegion(region_reg="%0", offset_reg="%1", length=4, value_reg="%2"),
            SetContinuation(name="c", target_label=CodeLabel("L")),
            ResumeContinuation(name="c"),
        ]:
            assert (
                inst.result_reg == NO_REGISTER
            ), f"{type(inst).__name__} should have NO_REGISTER"


class TestLabelDefault:
    """Types without label should return NO_LABEL."""

    def test_no_label_types(self):
        for inst in [
            Const(value="42"),
            Binop(operator="+"),
            CallFunction(func_name="f"),
            StoreVar(name="x", value_reg="%0"),
        ]:
            assert inst.label == NO_LABEL, f"{type(inst).__name__} should have NO_LABEL"


class TestBranchTargetsDefault:
    """Types without branch_targets should return empty tuple."""

    def test_no_branch_targets(self):
        for inst in [
            Const(value="42"),
            Binop(operator="+"),
            Return_(),
            Label_(label=CodeLabel("entry")),
        ]:
            assert (
                inst.branch_targets == ()
            ), f"{type(inst).__name__} should have empty branch_targets"


class TestOperandsProperty:
    """Each typed instruction should expose operands matching the flat IR layout."""

    def test_const(self):
        assert Const(value="42").operands == ["42"]

    def test_binop(self):
        assert Binop(operator="+", left="%0", right="%1").operands == ["+", "%0", "%1"]

    def test_call_function_no_args(self):
        assert CallFunction(func_name="f").operands == ["f"]

    def test_call_function_with_args(self):
        assert CallFunction(func_name="f", args=("%0", "%1")).operands == [
            "f",
            "%0",
            "%1",
        ]

    def test_branch_if(self):
        assert BranchIf(cond_reg="%0").operands == ["%0"]

    def test_return_void(self):
        assert Return_().operands == []

    def test_return_value(self):
        assert Return_(value_reg="%0").operands == ["%0"]

    def test_try_push(self):
        ops = TryPush(
            catch_labels=(CodeLabel("c"),),
            finally_label=CodeLabel("f"),
            end_label=CodeLabel("e"),
        ).operands
        assert len(ops) == 3
        assert ops[0] == [CodeLabel("c")]

    def test_write_region(self):
        assert WriteRegion(
            region_reg="%0", offset_reg="%1", length=4, value_reg="%2"
        ).operands == ["%0", "%1", 4, "%2"]
