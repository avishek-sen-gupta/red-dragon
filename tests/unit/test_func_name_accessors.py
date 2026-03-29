"""Tests for FuncName accessor methods on registries and tables."""

from interpreter.class_name import ClassName
from interpreter.func_name import FuncName
from interpreter.registry import FunctionRegistry
from interpreter.refs.func_ref import FuncRef
from interpreter.ir import CodeLabel


class TestRegistryLookupFunc:
    def test_lookup_func_found(self):
        reg = FunctionRegistry()
        ref = FuncRef(name=FuncName("add"), label=CodeLabel("func_add_0"))
        reg.register_func(FuncName("add"), ref)
        assert reg.lookup_func(FuncName("add")) == ref

    def test_lookup_func_not_found(self):
        reg = FunctionRegistry()
        assert reg.lookup_func(FuncName("missing")) is None

    def test_register_func_overwrites(self):
        reg = FunctionRegistry()
        ref1 = FuncRef(name=FuncName("add"), label=CodeLabel("func_add_0"))
        ref2 = FuncRef(name=FuncName("add"), label=CodeLabel("func_add_1"))
        reg.register_func(FuncName("add"), ref1)
        reg.register_func(FuncName("add"), ref2)
        assert reg.lookup_func(FuncName("add")) == ref2

    def test_register_func_stores_func_name_key(self):
        reg = FunctionRegistry()
        ref = FuncRef(name=FuncName("sub"), label=CodeLabel("func_sub_0"))
        reg.register_func(FuncName("sub"), ref)
        assert reg.func_refs[FuncName("sub")] == ref


class TestRegistryLookupMethods:
    def test_lookup_methods_found(self):
        reg = FunctionRegistry()
        label = CodeLabel("func_get_0")
        reg.register_method(ClassName("MyClass"), FuncName("get"), label)
        assert reg.lookup_methods(ClassName("MyClass"), FuncName("get")) == [label]

    def test_lookup_methods_not_found(self):
        reg = FunctionRegistry()
        assert reg.lookup_methods(ClassName("MyClass"), FuncName("missing")) == []

    def test_register_multiple_methods_same_name(self):
        reg = FunctionRegistry()
        l1 = CodeLabel("func_get_0")
        l2 = CodeLabel("func_get_1")
        reg.register_method(ClassName("Bar"), FuncName("get"), l1)
        reg.register_method(ClassName("Bar"), FuncName("get"), l2)
        assert reg.lookup_methods(ClassName("Bar"), FuncName("get")) == [l1, l2]

    def test_register_method_stores_func_name_key(self):
        reg = FunctionRegistry()
        label = CodeLabel("func_get_0")
        reg.register_method(ClassName("MyClass"), FuncName("get"), label)
        inner = reg.class_methods[ClassName("MyClass")]
        for key in inner:
            assert isinstance(key, FuncName), f"inner key {key!r} should be FuncName"


class TestBuiltinsLookupBuiltin:
    def test_lookup_builtin_found(self):
        from interpreter.vm.builtins import Builtins

        result = Builtins.lookup_builtin(FuncName("len"))
        assert result is not None

    def test_lookup_builtin_not_found(self):
        from interpreter.vm.builtins import Builtins

        assert Builtins.lookup_builtin(FuncName("nonexistent_func")) is None

    def test_table_keys_are_func_name(self):
        from interpreter.vm.builtins import Builtins

        for key in Builtins.TABLE:
            assert isinstance(key, FuncName), f"TABLE key {key!r} should be FuncName"


class TestBuiltinsLookupMethodBuiltin:
    def test_lookup_method_builtin_found(self):
        from interpreter.vm.builtins import Builtins

        result = Builtins.lookup_method_builtin(FuncName("toString"))
        assert result is not None

    def test_lookup_method_builtin_not_found(self):
        from interpreter.vm.builtins import Builtins

        assert Builtins.lookup_method_builtin(FuncName("nonexistent_method")) is None

    def test_method_table_keys_are_func_name(self):
        from interpreter.vm.builtins import Builtins

        for key in Builtins.METHOD_TABLE:
            assert isinstance(
                key, FuncName
            ), f"METHOD_TABLE key {key!r} should be FuncName"


class TestInferenceContextAccessors:
    def test_store_and_lookup_func_return_type(self):
        from interpreter.types.type_inference import _InferenceContext
        from interpreter.types.type_expr import scalar, UNKNOWN

        ctx = _InferenceContext()
        ctx.store_func_return_type(FuncName("add"), scalar("Int"))
        assert ctx.lookup_func_return_type(FuncName("add")) == scalar("Int")
        assert ctx.lookup_func_return_type(FuncName("missing")) == UNKNOWN

    def test_lookup_method_type(self):
        from interpreter.types.type_inference import _InferenceContext
        from interpreter.types.type_expr import scalar, UNKNOWN

        ctx = _InferenceContext()
        class_type = scalar("MyClass")
        ctx.class_method_types[class_type] = {FuncName("get"): scalar("String")}
        assert ctx.lookup_method_type(class_type, FuncName("get")) == scalar("String")
        assert ctx.lookup_method_type(class_type, FuncName("missing")) == UNKNOWN
        assert ctx.lookup_method_type(scalar("Other"), FuncName("get")) == UNKNOWN


class TestCobolIOProviderDispatch:
    def test_dispatch_known(self):
        from interpreter.cobol.io_provider import NullIOProvider

        provider = NullIOProvider()
        assert provider.dispatch(FuncName("__cobol_accept")) == "_accept"

    def test_dispatch_unknown(self):
        from interpreter.cobol.io_provider import NullIOProvider

        provider = NullIOProvider()
        assert provider.dispatch(FuncName("unknown_func")) is None
