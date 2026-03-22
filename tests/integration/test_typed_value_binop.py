"""Integration tests for TypedValue-aware BINOP with language coercion.

Tests that language-specific BinopCoercionStrategy produces correct results
through the full pipeline.
"""

from __future__ import annotations

from interpreter.constants import Language
from interpreter.run import run
from interpreter.types.typed_value import unwrap, unwrap_locals
from interpreter.vm.vm_types import SymbolicValue


def _run_java(source: str, max_steps: int = 2000) -> dict:
    vm = run(source, language=Language.JAVA, max_steps=max_steps)
    return unwrap_locals(vm.call_stack[0].local_vars)


class TestJavaStringConcatenation:
    """Java auto-stringifies non-string operands in string + non-string."""

    def test_string_plus_int(self):
        source = """\
class Printer {
    String show(int x) {
        return "int:" + x;
    }
}
Printer p = new Printer();
String result = p.show(42);
"""
        local_vars = _run_java(source)
        assert local_vars["result"] == "int:42"

    def test_int_plus_string(self):
        source = """\
class Foo {
    String bar(int x) {
        return x + " items";
    }
}
Foo f = new Foo();
String result = f.bar(3);
"""
        local_vars = _run_java(source)
        assert local_vars["result"] == "3 items"

    def test_string_plus_float(self):
        source = """\
String result = "val:" + 3.14;
"""
        local_vars = _run_java(source)
        assert local_vars["result"] == "val:3.14"

    def test_string_plus_bool(self):
        source = """\
String result = "flag:" + true;
"""
        local_vars = _run_java(source)
        assert local_vars["result"] == "flag:true"

    def test_string_concat_no_symbolic(self):
        """String + int should NOT produce SymbolicValue anymore."""
        source = """\
String x = "count:" + 5;
"""
        local_vars = _run_java(source)
        assert not isinstance(local_vars["x"], SymbolicValue)
        assert local_vars["x"] == "count:5"


class TestDefaultNonCoercion:
    """Non-Java languages: String + int still produces SymbolicValue (no coercion)."""

    def test_python_string_plus_int_symbolic(self):
        source = """\
x = "count:" + 5
"""
        vm = run(source, language=Language.PYTHON, max_steps=2000)
        result = unwrap(vm.call_stack[0].local_vars.get("x"))
        assert isinstance(result, SymbolicValue)
