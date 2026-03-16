"""Unit tests for parent extraction in class definitions across all frontends.

Each test compiles a minimal source snippet containing a parent class and a
child class, then verifies that the class symbol table records the parent
relationship correctly.

Languages covered: Python, C#, Kotlin, Ruby, JavaScript, TypeScript, Scala,
PHP, C++.  Java is already covered in ``test_class_inheritance.py``.
"""

from __future__ import annotations

import pytest

from interpreter.constants import Language
from interpreter.frontends import get_deterministic_frontend
from interpreter.cfg import build_cfg
from interpreter.registry import build_registry


def _extract_parents(source: str, language: Language | str) -> dict[str, list[str]]:
    """Lower source and return the registry class_parents dict."""
    fe = get_deterministic_frontend(str(language))
    ir = fe.lower(source.encode("utf-8"))
    cfg = build_cfg(ir)
    registry = build_registry(ir, cfg, fe.func_symbol_table, fe.class_symbol_table)
    return registry.class_parents


class TestPythonParentExtraction:
    def test_single_parent(self):
        source = "class Animal:\n" "  pass\n" "class Dog(Animal):\n" "  pass\n"
        parents = _extract_parents(source, Language.PYTHON)
        assert "Animal" in parents.get("Dog", [])


class TestCSharpParentExtraction:
    def test_single_parent(self):
        source = "class Animal { }\n" "class Dog : Animal { }\n"
        parents = _extract_parents(source, Language.CSHARP)
        assert "Animal" in parents.get("Dog", [])


class TestKotlinParentExtraction:
    def test_single_parent(self):
        source = "open class Animal { }\n" "class Dog : Animal() { }\n"
        parents = _extract_parents(source, Language.KOTLIN)
        assert "Animal" in parents.get("Dog", [])


class TestRubyParentExtraction:
    def test_single_parent(self):
        source = "class Animal\n" "end\n" "class Dog < Animal\n" "end\n"
        parents = _extract_parents(source, Language.RUBY)
        assert "Animal" in parents.get("Dog", [])


class TestJavaScriptParentExtraction:
    def test_single_parent(self):
        source = "class Animal { }\n" "class Dog extends Animal { }\n"
        parents = _extract_parents(source, Language.JAVASCRIPT)
        assert "Animal" in parents.get("Dog", [])


class TestTypeScriptParentExtraction:
    def test_single_parent(self):
        source = "class Animal { }\n" "class Dog extends Animal { }\n"
        parents = _extract_parents(source, Language.TYPESCRIPT)
        assert "Animal" in parents.get("Dog", [])


class TestScalaParentExtraction:
    def test_single_parent(self):
        source = "class Animal { }\n" "class Dog extends Animal { }\n"
        parents = _extract_parents(source, Language.SCALA)
        assert "Animal" in parents.get("Dog", [])


class TestPHPParentExtraction:
    def test_single_parent(self):
        source = "<?php\n" "class Animal { }\n" "class Dog extends Animal { }\n"
        parents = _extract_parents(source, Language.PHP)
        assert "Animal" in parents.get("Dog", [])


class TestCppParentExtraction:
    def test_single_parent(self):
        source = "class Animal { };\n" "class Dog : public Animal { };\n"
        parents = _extract_parents(source, Language.CPP)
        assert "Animal" in parents.get("Dog", [])
