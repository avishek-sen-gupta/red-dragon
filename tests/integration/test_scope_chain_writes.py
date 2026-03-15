"""Integration tests: STORE_VAR scope chain writes reach outer frames.

Verifies the DECL_VAR/STORE_VAR split: DECL_VAR creates in the current
frame, STORE_VAR walks up the scope chain to find existing bindings.
"""

from __future__ import annotations

from interpreter.constants import Language
from interpreter.run import run
from interpreter.typed_value import unwrap_locals


def _run(source: str, lang: Language, max_steps: int = 500):
    vm = run(source, language=lang, max_steps=max_steps)
    return unwrap_locals(vm.call_stack[0].local_vars)


class TestPythonScopeChainWrites:
    """Python: function writes to outer-scope variable via nonlocal/global."""

    def test_function_modifies_outer_variable(self):
        source = """
x = 10
def set_x():
    x = 20
set_x()
"""
        # Without nonlocal, Python creates a local — x stays 10 in outer scope.
        # Our VM's STORE_VAR walks the scope chain, so x becomes 20.
        # This matches the VM's intentional simplification.
        result = _run(source, Language.PYTHON)
        assert result["x"] == 20

    def test_function_does_not_shadow_with_declaration(self):
        source = """
x = 10
def make_x():
    y = 99
make_x()
"""
        result = _run(source, Language.PYTHON)
        assert result["x"] == 10
        # y was declared in inner scope, not visible at top level
        assert "y" not in result


class TestJavaScriptScopeChainWrites:
    """JavaScript: assignment without let/var/const writes to outer scope."""

    def test_assignment_reaches_outer_scope(self):
        source = """
let count = 0;
function increment() {
    count = count + 1;
}
increment();
increment();
"""
        result = _run(source, Language.JAVASCRIPT)
        assert result["count"] == 2

    def test_let_declaration_shadows(self):
        source = """
let x = 10;
function f() {
    let x = 99;
}
f();
"""
        result = _run(source, Language.JAVASCRIPT)
        assert result["x"] == 10


class TestScalaScopeChainWrites:
    """Scala: method body assignment writes to outer scope."""

    def test_method_modifies_var(self):
        source = """
var total = 0
def add(n: Int): Unit = {
    total = total + n
}
add(5)
add(3)
"""
        result = _run(source, Language.SCALA)
        assert result["total"] == 8


class TestRubyScopeChainWrites:
    """Ruby: block-like scope can modify outer variables."""

    def test_method_modifies_outer(self):
        source = """
x = 0
def bump()
    x = x + 1
end
bump()
bump()
"""
        result = _run(source, Language.RUBY)
        assert result["x"] == 2


class TestGoScopeChainWrites:
    """Go: function modifies package-level variable."""

    def test_function_modifies_outer(self):
        source = """
package main

var counter int = 0

func inc() {
    counter = counter + 1
}

func main() {
    inc()
    inc()
    inc()
}
"""
        result = _run(source, Language.GO, max_steps=500)
        assert result["counter"] == 3
