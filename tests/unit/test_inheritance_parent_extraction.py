"""Unit tests for parent extraction in class definitions across all frontends.

Each test compiles a minimal source snippet containing a parent class and a
child class, then verifies that the child's class-ref string in the IR
includes the parent name (e.g. ``<class:Dog@...:Animal>``).

Languages covered: Python, C#, Kotlin, Ruby, JavaScript, TypeScript, Scala,
PHP, C++.  Java is already covered in ``test_class_inheritance.py``.
"""

from __future__ import annotations

import pytest

from interpreter.constants import Language
from interpreter.run import run


def _child_class_ref(vm, var_name: str) -> str:
    """Return the class-ref string stored in *var_name* after execution."""
    return str(vm.call_stack[0].local_vars.get(var_name, ""))


class TestPythonParentExtraction:
    def test_single_parent(self):
        source = "class Animal:\n" "  pass\n" "class Dog(Animal):\n" "  pass\n"
        vm = run(source, language=Language.PYTHON, max_steps=500)
        assert ":Animal>" in _child_class_ref(vm, "Dog")


class TestCSharpParentExtraction:
    def test_single_parent(self):
        source = "class Animal { }\n" "class Dog : Animal { }\n"
        vm = run(source, language=Language.CSHARP, max_steps=500)
        assert ":Animal>" in _child_class_ref(vm, "Dog")


class TestKotlinParentExtraction:
    def test_single_parent(self):
        source = "open class Animal { }\n" "class Dog : Animal() { }\n"
        vm = run(source, language=Language.KOTLIN, max_steps=500)
        assert ":Animal>" in _child_class_ref(vm, "Dog")


class TestRubyParentExtraction:
    def test_single_parent(self):
        source = "class Animal\n" "end\n" "class Dog < Animal\n" "end\n"
        vm = run(source, language=Language.RUBY, max_steps=500)
        assert ":Animal>" in _child_class_ref(vm, "Dog")


class TestJavaScriptParentExtraction:
    def test_single_parent(self):
        source = "class Animal { }\n" "class Dog extends Animal { }\n"
        vm = run(source, language=Language.JAVASCRIPT, max_steps=500)
        assert ":Animal>" in _child_class_ref(vm, "Dog")


class TestTypeScriptParentExtraction:
    def test_single_parent(self):
        source = "class Animal { }\n" "class Dog extends Animal { }\n"
        vm = run(source, language=Language.TYPESCRIPT, max_steps=500)
        assert ":Animal>" in _child_class_ref(vm, "Dog")


class TestScalaParentExtraction:
    def test_single_parent(self):
        source = "class Animal { }\n" "class Dog extends Animal { }\n"
        vm = run(source, language=Language.SCALA, max_steps=500)
        assert ":Animal>" in _child_class_ref(vm, "Dog")


class TestPHPParentExtraction:
    def test_single_parent(self):
        source = "<?php\n" "class Animal { }\n" "class Dog extends Animal { }\n"
        vm = run(source, language=Language.PHP, max_steps=500)
        assert ":Animal>" in _child_class_ref(vm, "Dog")


class TestCppParentExtraction:
    def test_single_parent(self):
        source = "class Animal { };\n" "class Dog : public Animal { };\n"
        vm = run(source, language=Language.CPP, max_steps=500)
        assert ":Animal>" in _child_class_ref(vm, "Dog")
