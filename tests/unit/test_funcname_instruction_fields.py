"""Test that CallFunction/CallMethod/CallCtorFunction use FuncName-typed fields."""

from interpreter.func_name import FuncName, NO_FUNC_NAME
from interpreter.instructions import CallFunction, CallMethod, CallCtorFunction


class TestCallFunctionFuncNameField:
    def test_default_is_no_func_name(self):
        inst = CallFunction()
        assert inst.func_name == NO_FUNC_NAME
        assert isinstance(inst.func_name, FuncName)

    def test_func_name_is_func_name_type(self):
        inst = CallFunction(func_name=FuncName("add"))
        assert inst.func_name == FuncName("add")
        assert isinstance(inst.func_name, FuncName)

    def test_operands_returns_str(self):
        inst = CallFunction(func_name=FuncName("add"))
        assert inst.operands == ["add"]
        assert isinstance(inst.operands[0], str)


class TestCallMethodFuncNameField:
    def test_default_is_no_func_name(self):
        inst = CallMethod()
        assert inst.method_name == NO_FUNC_NAME
        assert isinstance(inst.method_name, FuncName)

    def test_method_name_is_func_name_type(self):
        inst = CallMethod(method_name=FuncName("get"))
        assert inst.method_name == FuncName("get")

    def test_operands_returns_str(self):
        inst = CallMethod(method_name=FuncName("get"))
        assert inst.operands[1] == "get"
        assert isinstance(inst.operands[1], str)


class TestCallCtorFunctionFuncNameField:
    def test_default_is_no_func_name(self):
        inst = CallCtorFunction()
        assert inst.func_name == NO_FUNC_NAME
        assert isinstance(inst.func_name, FuncName)

    def test_func_name_is_func_name_type(self):
        inst = CallCtorFunction(func_name=FuncName("MyClass"))
        assert inst.func_name == FuncName("MyClass")

    def test_operands_returns_str(self):
        inst = CallCtorFunction(func_name=FuncName("MyClass"))
        assert inst.operands == ["MyClass"]
        assert isinstance(inst.operands[0], str)
