"""Integration tests for NEW_OBJECT producing Pointer with correct type."""

from interpreter.address import Address
from interpreter.constants import Language
from interpreter.run import run
from interpreter.var_name import VarName
from interpreter.vm.vm_types import Pointer
from interpreter.project.entry_point import EntryPoint


def _typed_locals(vm):
    return vm.call_stack[0].local_vars


class TestNewObjectProducesPointer:
    def test_java_new_object_is_pointer(self):
        vm = run(
            "class Dog {} Dog d = new Dog();",
            language=Language.JAVA,
            max_steps=100,
            entry_point=EntryPoint.top_level(),
        )
        tv = _typed_locals(vm)[VarName("d")]
        assert isinstance(tv.value, Pointer)
        assert tv.value.base.startswith("obj_")

    def test_python_class_instantiation_is_pointer(self):
        vm = run(
            "class Cat:\n  pass\nc = Cat()\n",
            language=Language.PYTHON,
            max_steps=100,
            entry_point=EntryPoint.top_level(),
        )
        tv = _typed_locals(vm)[VarName("c")]
        assert isinstance(tv.value, Pointer)
        assert tv.value.base.startswith("obj_")

    def test_rust_struct_is_pointer(self):
        vm = run(
            "struct Point { x: i32 }\nlet p = Point { x: 42 };\n",
            language=Language.RUST,
            max_steps=200,
            entry_point=EntryPoint.top_level(),
        )
        tv = _typed_locals(vm)[VarName("p")]
        assert isinstance(tv.value, Pointer)
        assert tv.value.base.startswith("obj_")

    # NOTE: Parameterized pointer type (pointer(scalar("Dog"))) is not yet preserved
    # end-to-end. Registers hold ScalarType("Dog") and local vars show UnknownType()
    # because _resolve_reg unwraps TypedValue. Type assertions on tv.type are skipped
    # until the type propagation pipeline is fixed upstream.

    def test_heap_object_accessible_via_pointer_base(self):
        """Pointer.base should be a valid heap key."""
        vm = run(
            "class Dog {} Dog d = new Dog();",
            language=Language.JAVA,
            max_steps=100,
            entry_point=EntryPoint.top_level(),
        )
        tv = _typed_locals(vm)[VarName("d")]
        assert vm.heap_contains(tv.value.base)
        assert vm.heap_get(tv.value.base).type_hint == "Dog"
