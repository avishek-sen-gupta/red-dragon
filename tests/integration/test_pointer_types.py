"""Integration tests verifying heap references carry correct Pointer types across languages."""

import pytest

from interpreter.constants import Language
from interpreter.run import run
from interpreter.vm.vm_types import Pointer
from interpreter.types.typed_value import unwrap_locals


class TestHeapReferenceTypes:
    def test_cpp_new_produces_pointer(self):
        vm = run(
            "struct Point { int x; int y; };\nPoint p = {3, 7};\n",
            language=Language.CPP,
            max_steps=200,
        )
        locals_ = unwrap_locals(vm.call_stack[0].local_vars)
        assert isinstance(locals_["p"], Pointer)
        assert locals_["p"].base.startswith("obj_")

    def test_csharp_new_produces_pointer(self):
        vm = run(
            "class Dog {}\nDog d = new Dog();\n",
            language=Language.CSHARP,
            max_steps=200,
        )
        locals_ = unwrap_locals(vm.call_stack[0].local_vars)
        assert isinstance(locals_["d"], Pointer)

    def test_kotlin_class_produces_pointer(self):
        vm = run(
            "class Dog\nval d = Dog()\n",
            language=Language.KOTLIN,
            max_steps=200,
        )
        locals_ = unwrap_locals(vm.call_stack[0].local_vars)
        assert isinstance(locals_["d"], Pointer)

    def test_go_struct_produces_pointer(self):
        vm = run(
            "type Point struct { X int }\np := Point{X: 42}\n",
            language=Language.GO,
            max_steps=200,
        )
        locals_ = unwrap_locals(vm.call_stack[0].local_vars)
        assert isinstance(locals_["p"], Pointer)

    def test_ruby_new_produces_pointer(self):
        vm = run(
            "class Dog\nend\nd = Dog.new\n",
            language=Language.RUBY,
            max_steps=200,
        )
        locals_ = unwrap_locals(vm.call_stack[0].local_vars)
        assert isinstance(locals_["d"], Pointer)

    def test_php_new_produces_pointer(self):
        vm = run(
            "<?php\nclass Dog {}\n$d = new Dog();\n",
            language=Language.PHP,
            max_steps=200,
        )
        locals_ = unwrap_locals(vm.call_stack[0].local_vars)
        assert isinstance(locals_["$d"], Pointer)

    def test_scala_new_produces_pointer(self):
        vm = run(
            "class Dog\nval d = new Dog()\n",
            language=Language.SCALA,
            max_steps=200,
        )
        locals_ = unwrap_locals(vm.call_stack[0].local_vars)
        assert isinstance(locals_["d"], Pointer)

    def test_typescript_new_produces_pointer(self):
        vm = run(
            "class Dog {}\nlet d = new Dog();\n",
            language=Language.TYPESCRIPT,
            max_steps=200,
        )
        locals_ = unwrap_locals(vm.call_stack[0].local_vars)
        assert isinstance(locals_["d"], Pointer)


class TestArrayPointerTypes:
    def test_java_array_produces_pointer(self):
        vm = run(
            "int[] arr = {1, 2, 3};\n",
            language=Language.JAVA,
            max_steps=100,
        )
        locals_ = unwrap_locals(vm.call_stack[0].local_vars)
        assert isinstance(locals_["arr"], Pointer)
        assert locals_["arr"].base.startswith("arr_")

    @pytest.mark.xfail(
        reason="Rust frontend lowers vec![] macro to SymbolicValue, not array allocation"
    )
    def test_rust_vec_produces_pointer(self):
        vm = run(
            "let v = vec![1, 2, 3];\n",
            language=Language.RUST,
            max_steps=200,
        )
        locals_ = unwrap_locals(vm.call_stack[0].local_vars)
        assert isinstance(locals_["v"], Pointer)

    def test_c_array_produces_pointer(self):
        vm = run(
            "int arr[] = {10, 20, 30};\n",
            language=Language.C,
            max_steps=200,
        )
        locals_ = unwrap_locals(vm.call_stack[0].local_vars)
        assert isinstance(locals_["arr"], Pointer)
