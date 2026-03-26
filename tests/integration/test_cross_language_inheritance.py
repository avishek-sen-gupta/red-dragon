"""Integration tests for class inheritance across multiple languages.

Verifies that inherited methods dispatch correctly through the parent
chain. Java tests are in test_class_inheritance.py; this file covers
all other languages with class inheritance support.
"""

from __future__ import annotations

from interpreter.var_name import VarName
from interpreter.constants import Language
from interpreter.run import run
from interpreter.types.typed_value import unwrap_locals


def _run(source: str, language: Language, max_steps: int = 500) -> dict:
    vm = run(source, language=language, max_steps=max_steps)
    return unwrap_locals(vm.call_stack[0].local_vars)


# ── Python ────────────────────────────────────────────────────────────


class TestPythonInheritance:
    def test_inherited_method(self):
        source = (
            "class Animal:\n"
            "  def speak(self):\n"
            "    return 1\n"
            "class Dog(Animal):\n"
            "  def fetch(self):\n"
            "    return 2\n"
            "d = Dog()\n"
            "v = d.speak()\n"
            "f = d.fetch()\n"
        )
        vars_ = _run(source, Language.PYTHON)
        assert vars_[VarName("v")] == 1
        assert vars_[VarName("f")] == 2

    def test_method_override(self):
        source = (
            "class Base:\n"
            "  def value(self):\n"
            "    return 1\n"
            "class Derived(Base):\n"
            "  def value(self):\n"
            "    return 2\n"
            "d = Derived()\n"
            "result = d.value()\n"
        )
        vars_ = _run(source, Language.PYTHON)
        assert vars_[VarName("result")] == 2

    def test_multi_level(self):
        source = (
            "class A:\n"
            "  def from_a(self):\n"
            "    return 10\n"
            "class B(A):\n"
            "  def from_b(self):\n"
            "    return 20\n"
            "class C(B):\n"
            "  def from_c(self):\n"
            "    return 30\n"
            "c = C()\n"
            "a = c.from_a()\n"
            "b = c.from_b()\n"
            "cc = c.from_c()\n"
        )
        vars_ = _run(source, Language.PYTHON)
        assert vars_[VarName("a")] == 10
        assert vars_[VarName("b")] == 20
        assert vars_[VarName("cc")] == 30


# ── JavaScript ────────────────────────────────────────────────────────


class TestJavaScriptInheritance:
    def test_inherited_method(self):
        source = (
            "class Animal {\n"
            "  speak() { return 1; }\n"
            "}\n"
            "class Dog extends Animal {\n"
            "  fetch() { return 2; }\n"
            "}\n"
            "let d = new Dog();\n"
            "let v = d.speak();\n"
            "let f = d.fetch();\n"
        )
        vars_ = _run(source, Language.JAVASCRIPT)
        assert vars_[VarName("v")] == 1
        assert vars_[VarName("f")] == 2

    def test_method_override(self):
        source = (
            "class Base {\n"
            "  value() { return 1; }\n"
            "}\n"
            "class Derived extends Base {\n"
            "  value() { return 2; }\n"
            "}\n"
            "let d = new Derived();\n"
            "let result = d.value();\n"
        )
        vars_ = _run(source, Language.JAVASCRIPT)
        assert vars_[VarName("result")] == 2


# ── C# ────────────────────────────────────────────────────────────────


class TestCSharpInheritance:
    def test_inherited_method(self):
        source = (
            "class Animal {\n"
            "  int speak() { return 1; }\n"
            "}\n"
            "class Dog : Animal {\n"
            "  int fetch() { return 2; }\n"
            "}\n"
            "Dog d = new Dog();\n"
            "int v = d.speak();\n"
            "int f = d.fetch();\n"
        )
        vars_ = _run(source, Language.CSHARP)
        assert vars_[VarName("v")] == 1
        assert vars_[VarName("f")] == 2

    def test_method_override(self):
        source = (
            "class Base {\n"
            "  int value() { return 1; }\n"
            "}\n"
            "class Derived : Base {\n"
            "  int value() { return 2; }\n"
            "}\n"
            "Derived d = new Derived();\n"
            "int result = d.value();\n"
        )
        vars_ = _run(source, Language.CSHARP)
        assert vars_[VarName("result")] == 2


# ── TypeScript ────────────────────────────────────────────────────────


class TestTypeScriptInheritance:
    def test_inherited_method(self):
        source = (
            "class Animal {\n"
            "  speak(): number { return 1; }\n"
            "}\n"
            "class Dog extends Animal {\n"
            "  fetch(): number { return 2; }\n"
            "}\n"
            "let d = new Dog();\n"
            "let v = d.speak();\n"
            "let f = d.fetch();\n"
        )
        vars_ = _run(source, Language.TYPESCRIPT)
        assert vars_[VarName("v")] == 1
        assert vars_[VarName("f")] == 2

    def test_method_override(self):
        source = (
            "class Base {\n"
            "  value(): number { return 1; }\n"
            "}\n"
            "class Derived extends Base {\n"
            "  value(): number { return 2; }\n"
            "}\n"
            "let d = new Derived();\n"
            "let result = d.value();\n"
        )
        vars_ = _run(source, Language.TYPESCRIPT)
        assert vars_[VarName("result")] == 2


# ── Kotlin ────────────────────────────────────────────────────────────


class TestKotlinInheritance:
    def test_inherited_method(self):
        source = (
            "open class Animal {\n"
            "  fun speak(): Int = 1\n"
            "}\n"
            "class Dog : Animal() {\n"
            "  fun fetch(): Int = 2\n"
            "}\n"
            "val d = Dog()\n"
            "val v = d.speak()\n"
            "val f = d.fetch()\n"
        )
        vars_ = _run(source, Language.KOTLIN)
        assert vars_[VarName("v")] == 1
        assert vars_[VarName("f")] == 2

    def test_method_override(self):
        source = (
            "open class Base {\n"
            "  open fun value(): Int = 1\n"
            "}\n"
            "class Derived : Base() {\n"
            "  override fun value(): Int = 2\n"
            "}\n"
            "val d = Derived()\n"
            "val result = d.value()\n"
        )
        vars_ = _run(source, Language.KOTLIN)
        assert vars_[VarName("result")] == 2


# ── Ruby ──────────────────────────────────────────────────────────────


class TestRubyInheritance:
    def test_inherited_method(self):
        source = (
            "class Animal\n"
            "  def speak\n"
            "    return 1\n"
            "  end\n"
            "end\n"
            "class Dog < Animal\n"
            "  def fetch\n"
            "    return 2\n"
            "  end\n"
            "end\n"
            "d = Dog.new\n"
            "v = d.speak\n"
            "f = d.fetch\n"
        )
        vars_ = _run(source, Language.RUBY)
        assert vars_[VarName("v")] == 1
        assert vars_[VarName("f")] == 2

    def test_method_override(self):
        source = (
            "class Base\n"
            "  def value\n"
            "    return 1\n"
            "  end\n"
            "end\n"
            "class Derived < Base\n"
            "  def value\n"
            "    return 2\n"
            "  end\n"
            "end\n"
            "d = Derived.new\n"
            "result = d.value\n"
        )
        vars_ = _run(source, Language.RUBY)
        assert vars_[VarName("result")] == 2


# ── Scala ─────────────────────────────────────────────────────────────


class TestScalaInheritance:
    def test_inherited_method(self):
        source = (
            "class Animal {\n"
            "  def speak(): Int = 1\n"
            "}\n"
            "class Dog extends Animal {\n"
            "  def fetch(): Int = 2\n"
            "}\n"
            "val d = new Dog()\n"
            "val v = d.speak()\n"
            "val f = d.fetch()\n"
        )
        vars_ = _run(source, Language.SCALA)
        assert vars_[VarName("v")] == 1
        assert vars_[VarName("f")] == 2

    def test_method_override(self):
        source = (
            "class Base {\n"
            "  def value(): Int = 1\n"
            "}\n"
            "class Derived extends Base {\n"
            "  override def value(): Int = 2\n"
            "}\n"
            "val d = new Derived()\n"
            "val result = d.value()\n"
        )
        vars_ = _run(source, Language.SCALA)
        assert vars_[VarName("result")] == 2


# ── PHP ───────────────────────────────────────────────────────────────


class TestPHPInheritance:
    def test_inherited_method(self):
        source = (
            "<?php\n"
            "class Animal {\n"
            "  public function speak() { return 1; }\n"
            "}\n"
            "class Dog extends Animal {\n"
            "  public function fetch() { return 2; }\n"
            "}\n"
            "$d = new Dog();\n"
            "$v = $d->speak();\n"
            "$f = $d->fetch();\n"
        )
        vars_ = _run(source, Language.PHP)
        assert vars_[VarName("$v")] == 1
        assert vars_[VarName("$f")] == 2

    def test_method_override(self):
        source = (
            "<?php\n"
            "class Base {\n"
            "  public function value() { return 1; }\n"
            "}\n"
            "class Derived extends Base {\n"
            "  public function value() { return 2; }\n"
            "}\n"
            "$d = new Derived();\n"
            "$result = $d->value();\n"
        )
        vars_ = _run(source, Language.PHP)
        assert vars_[VarName("$result")] == 2


# ── C++ ───────────────────────────────────────────────────────────────


class TestCppInheritance:
    def test_inherited_method(self):
        source = (
            "class Animal {\n"
            "public:\n"
            "  int speak() { return 1; }\n"
            "};\n"
            "class Dog : public Animal {\n"
            "public:\n"
            "  int fetch() { return 2; }\n"
            "};\n"
            "Dog d;\n"
            "int v = d.speak();\n"
            "int f = d.fetch();\n"
        )
        vars_ = _run(source, Language.CPP)
        assert vars_[VarName("v")] == 1
        assert vars_[VarName("f")] == 2

    def test_method_override(self):
        source = (
            "class Base {\n"
            "public:\n"
            "  int value() { return 1; }\n"
            "};\n"
            "class Derived : public Base {\n"
            "public:\n"
            "  int value() { return 2; }\n"
            "};\n"
            "Derived d;\n"
            "int result = d.value();\n"
        )
        vars_ = _run(source, Language.CPP)
        assert vars_[VarName("result")] == 2
