"""Integration tests for C# frontend: default_expression, sizeof_expression, checked_expression, file_scoped_namespace, range_expression."""

from __future__ import annotations

from interpreter.constants import Language
from interpreter.run import run
from interpreter.typed_value import unwrap_locals


def _run_csharp(source: str, max_steps: int = 500) -> dict:
    vm = run(source, language=Language.CSHARP, max_steps=max_steps)
    return unwrap_locals(vm.call_stack[0].local_vars)


class TestCSharpDefaultExpressionExecution:
    def test_default_assigned(self):
        """int x = default; should execute without errors."""
        vars_ = _run_csharp("int x = default;")
        assert "x" in vars_

    def test_default_with_subsequent_code(self):
        """Code after default expression should execute normally."""
        vars_ = _run_csharp("""\
int x = default;
int y = 42;
""")
        assert vars_["y"] == 42


class TestCSharpSizeofExpressionExecution:
    def test_sizeof_assigned(self):
        """int x = sizeof(int); should execute without errors."""
        vars_ = _run_csharp("int x = sizeof(int);")
        assert "x" in vars_

    def test_sizeof_with_subsequent_code(self):
        """Code after sizeof should execute normally."""
        vars_ = _run_csharp("""\
int s = sizeof(int);
int y = 10;
""")
        assert vars_["y"] == 10


class TestCSharpCheckedExpressionExecution:
    def test_checked_executes(self):
        """checked(1 + 2) should execute the inner arithmetic."""
        vars_ = _run_csharp("int x = checked(1 + 2);")
        assert vars_["x"] == 3

    def test_checked_with_variables(self):
        """checked(a + b) should evaluate the inner binop."""
        vars_ = _run_csharp("""\
int a = 10;
int b = 20;
int x = checked(a + b);
""")
        assert vars_["x"] == 30

    def test_unchecked_executes(self):
        """unchecked(expr) should also execute the inner expression."""
        vars_ = _run_csharp("int x = unchecked(5 * 3);")
        assert vars_["x"] == 15


class TestCSharpFileScopedNamespaceExecution:
    def test_class_in_file_scoped_ns_executes(self):
        """Class inside file-scoped namespace should be accessible."""
        locals_ = _run_csharp("""\
namespace Foo;
int x = 42;""")
        assert locals_["x"] == 42


class TestCSharpRangeExpressionExecution:
    def test_range_does_not_block(self):
        """Code after range expression should execute."""
        locals_ = _run_csharp("var r = 0..5;\nvar x = 42;")
        assert locals_["x"] == 42


class TestCSharpConstructorChainingExecution:
    """C# : this(args) constructor chaining with field initializers."""

    def test_single_field_constructor_chaining(self):
        """Two-arg constructor delegates to one-arg via : this(v + scale)."""
        locals_ = _run_csharp(
            """\
class Box {
    int value;
    Box(int v) { this.value = v; }
    Box(int v, int scale) : this(v + scale) { }
}
Box b = new Box(3, 4);
int answer = b.value;
""",
            max_steps=1000,
        )
        assert locals_["answer"] == 7

    def test_chaining_with_field_initializer(self):
        """Field initializer should exist after constructor chaining."""
        locals_ = _run_csharp(
            """\
class Calc {
    int result;
    int extra = 10;
    Calc(int r) { this.result = r; }
    Calc(int a, int b) : this(a + b) { }
    int Total() { return result + extra; }
}
Calc c = new Calc(3, 4);
int answer = c.Total();
""",
            max_steps=1000,
        )
        assert locals_["answer"] == 17

    def test_chaining_body_reads_field_by_bare_name(self):
        """After : this(...), constructor body can read fields via implicit this."""
        locals_ = _run_csharp(
            """\
class Counter {
    int count;
    int doubled;
    Counter(int c) {
        this.count = c;
        this.doubled = 0;
    }
    Counter(int c, int scale) : this(c) {
        doubled = count * scale;
    }
}
Counter obj = new Counter(5, 3);
int answer = obj.doubled;
""",
            max_steps=1000,
        )
        assert locals_["answer"] == 15
