"""Integration tests: parameterized types survive through _resolve_reg pipeline."""

from interpreter.constants import Language, TypeName
from interpreter.run import run
from interpreter.types.typed_value import TypedValue
from interpreter.types.type_expr import ParameterizedType, pointer, scalar
from interpreter.var_name import VarName
from interpreter.vm.vm_types import Pointer
from interpreter.project.entry_point import EntryPoint


def _typed_locals(vm):
    """Return local_vars dict preserving TypedValue wrappers."""
    return vm.call_stack[0].local_vars


class TestTypePreservationThroughResolveReg:
    def test_java_new_object_preserves_declared_type(self):
        """Java's type annotation causes type inference to assign scalar('Dog')."""
        vm = run(
            "class Dog {} Dog d = new Dog();",
            language=Language.JAVA,
            max_steps=100,
            entry_point=EntryPoint.top_level(),
        )
        tv = _typed_locals(vm)[VarName("d")]
        assert isinstance(tv, TypedValue)
        assert isinstance(tv.value, Pointer)
        assert tv.type == scalar("Dog")

    def test_python_class_preserves_pointer_type(self):
        """Python has no type annotations, so pointer(scalar('Cat')) from handler survives."""
        vm = run(
            "class Cat:\n    pass\nc = Cat()\n",
            language=Language.PYTHON,
            max_steps=100,
            entry_point=EntryPoint.top_level(),
        )
        tv = _typed_locals(vm)[VarName("c")]
        assert isinstance(tv, TypedValue)
        assert isinstance(tv.value, Pointer)
        assert tv.type == pointer(scalar("Cat"))

    def test_store_var_preserves_type_through_reassignment(self):
        """Type must survive a STORE_VAR (reassignment), not just DECL_VAR."""
        vm = run(
            "class Foo {} Foo x = new Foo(); Foo y = x;",
            language=Language.JAVA,
            max_steps=100,
            entry_point=EntryPoint.top_level(),
        )
        tv_x = _typed_locals(vm)[VarName("x")]
        tv_y = _typed_locals(vm)[VarName("y")]
        assert tv_x.type == scalar("Foo")
        assert tv_y.type == scalar("Foo")

    def test_array_preserves_parameterized_type(self):
        """Array type inference produces Array[Int] for integer lists."""
        vm = run(
            "x = [1, 2, 3]\n",
            language=Language.PYTHON,
            max_steps=100,
            entry_point=EntryPoint.top_level(),
        )
        tv = _typed_locals(vm)[VarName("x")]
        assert isinstance(tv, TypedValue)
        assert isinstance(tv.value, Pointer)
        assert isinstance(tv.type, ParameterizedType)
        assert tv.type.constructor == "Array"
        assert tv.type.arguments == (scalar(TypeName.INT),)

    def test_return_value_preserves_type(self):
        """Return value through RETURN should preserve TypedValue type."""
        code = """\
class Box {}
Box make() { return new Box(); }
Box b = make();
"""
        vm = run(
            code,
            language=Language.JAVA,
            max_steps=200,
            entry_point=EntryPoint.top_level(),
        )
        tv = _typed_locals(vm)[VarName("b")]
        assert isinstance(tv, TypedValue)
        assert isinstance(tv.value, Pointer)
        assert tv.type == scalar("Box")
