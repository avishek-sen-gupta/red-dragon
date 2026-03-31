"""Integration tests verifying heap references carry correct Pointer types across languages."""

import pytest

from interpreter.field_name import FieldKind, FieldName
from interpreter.var_name import VarName
from interpreter.constants import Language
from interpreter.run import run
from interpreter.vm.vm_types import Pointer
from interpreter.types.typed_value import unwrap_locals
from interpreter.project.entry_point import EntryPoint


class TestHeapReferenceTypes:
    def test_cpp_new_produces_pointer(self):
        vm = run(
            "struct Point { int x; int y; };\nPoint p = {3, 7};\n",
            language=Language.CPP,
            max_steps=200,
            entry_point=EntryPoint.top_level(),
        )
        locals_ = unwrap_locals(vm.call_stack[0].local_vars)
        assert isinstance(locals_[VarName("p")], Pointer)
        assert locals_[VarName("p")].base.startswith("obj_")

    def test_csharp_new_produces_pointer(self):
        vm = run(
            "class Dog {}\nDog d = new Dog();\n",
            language=Language.CSHARP,
            max_steps=200,
            entry_point=EntryPoint.top_level(),
        )
        locals_ = unwrap_locals(vm.call_stack[0].local_vars)
        assert isinstance(locals_[VarName("d")], Pointer)

    def test_kotlin_class_produces_pointer(self):
        vm = run(
            "class Dog\nval d = Dog()\n",
            language=Language.KOTLIN,
            max_steps=200,
            entry_point=EntryPoint.top_level(),
        )
        locals_ = unwrap_locals(vm.call_stack[0].local_vars)
        assert isinstance(locals_[VarName("d")], Pointer)

    def test_go_struct_produces_pointer(self):
        vm = run(
            "type Point struct { X int }\np := Point{X: 42}\n",
            language=Language.GO,
            max_steps=200,
            entry_point=EntryPoint.top_level(),
        )
        locals_ = unwrap_locals(vm.call_stack[0].local_vars)
        assert isinstance(locals_[VarName("p")], Pointer)

    def test_ruby_new_produces_pointer(self):
        vm = run(
            "class Dog\nend\nd = Dog.new\n",
            language=Language.RUBY,
            max_steps=200,
            entry_point=EntryPoint.top_level(),
        )
        locals_ = unwrap_locals(vm.call_stack[0].local_vars)
        assert isinstance(locals_[VarName("d")], Pointer)

    def test_php_new_produces_pointer(self):
        vm = run(
            "<?php\nclass Dog {}\n$d = new Dog();\n",
            language=Language.PHP,
            max_steps=200,
            entry_point=EntryPoint.top_level(),
        )
        locals_ = unwrap_locals(vm.call_stack[0].local_vars)
        assert isinstance(locals_[VarName("$d")], Pointer)

    def test_scala_new_produces_pointer(self):
        vm = run(
            "class Dog\nval d = new Dog()\n",
            language=Language.SCALA,
            max_steps=200,
            entry_point=EntryPoint.top_level(),
        )
        locals_ = unwrap_locals(vm.call_stack[0].local_vars)
        assert isinstance(locals_[VarName("d")], Pointer)

    def test_typescript_new_produces_pointer(self):
        vm = run(
            "class Dog {}\nlet d = new Dog();\n",
            language=Language.TYPESCRIPT,
            max_steps=200,
            entry_point=EntryPoint.top_level(),
        )
        locals_ = unwrap_locals(vm.call_stack[0].local_vars)
        assert isinstance(locals_[VarName("d")], Pointer)


class TestArrayPointerTypes:
    def test_java_array_produces_pointer(self):
        vm = run(
            "int[] arr = {1, 2, 3};\n",
            language=Language.JAVA,
            max_steps=100,
            entry_point=EntryPoint.top_level(),
        )
        locals_ = unwrap_locals(vm.call_stack[0].local_vars)
        assert isinstance(locals_[VarName("arr")], Pointer)
        assert locals_[VarName("arr")].base.startswith("arr_")

    def test_rust_vec_produces_pointer(self):
        vm = run(
            "let v = vec![1, 2, 3];\n",
            language=Language.RUST,
            max_steps=200,
            entry_point=EntryPoint.top_level(),
        )
        locals_ = unwrap_locals(vm.call_stack[0].local_vars)
        ptr = locals_[VarName("v")]
        assert isinstance(ptr, Pointer)
        heap_obj = vm.heap_get(ptr.base)
        assert heap_obj.fields[FieldName("0", FieldKind.INDEX)].value == 1
        assert heap_obj.fields[FieldName("1", FieldKind.INDEX)].value == 2
        assert heap_obj.fields[FieldName("2", FieldKind.INDEX)].value == 3

    def test_c_array_produces_pointer(self):
        vm = run(
            "int arr[] = {10, 20, 30};\n",
            language=Language.C,
            max_steps=200,
            entry_point=EntryPoint.top_level(),
        )
        locals_ = unwrap_locals(vm.call_stack[0].local_vars)
        assert isinstance(locals_[VarName("arr")], Pointer)
