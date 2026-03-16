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


class TestCSharpOutVarExecution:
    """C# out int x / out var x with out on both method signature and call site.

    Our VM does not support true pass-by-reference, so out parameters
    get their default value (0) rather than callee-assigned values.
    These tests verify the variable is declared and usable after the call.
    """

    def test_try_parse_pattern_out_int(self):
        """Classic TryParse pattern: out on param definition and call site."""
        locals_ = _run_csharp(
            """\
class IntParser {
    int dummy;
    IntParser() { this.dummy = 0; }
    bool TryParse(string input, out int result) {
        result = 42;
        return true;
    }
}
IntParser parser = new IntParser();
string s = "42";
bool ok = parser.TryParse(s, out int result);
int answer = result + 1;
""",
            max_steps=1000,
        )
        assert "result" in locals_
        assert locals_["answer"] == 1

    def test_try_parse_pattern_out_var(self):
        """TryParse with out on param definition and out var at call site."""
        locals_ = _run_csharp(
            """\
class DoubleParser {
    int dummy;
    DoubleParser() { this.dummy = 0; }
    bool TryParse(string input, out int result) {
        result = 100;
        return true;
    }
}
DoubleParser dp = new DoubleParser();
bool ok = dp.TryParse("3.14", out var parsed);
int check = parsed + 10;
""",
            max_steps=1000,
        )
        assert "parsed" in locals_
        assert locals_["check"] == 10

    def test_multiple_out_params(self):
        """Method with multiple out parameters in signature and call site."""
        locals_ = _run_csharp(
            """\
class OrderProcessor {
    int id;
    OrderProcessor(int i) { this.id = i; }
    bool TryProcess(int amount, out int tax, out int total) {
        tax = amount * 2;
        total = amount + tax;
        return true;
    }
}
OrderProcessor proc = new OrderProcessor(1);
bool ok = proc.TryProcess(500, out int tax, out int total);
int taxVal = tax;
int totalVal = total;
""",
            max_steps=1000,
        )
        assert "tax" in locals_
        assert "total" in locals_
        assert locals_["taxVal"] == 0
        assert locals_["totalVal"] == 0

    def test_out_var_used_in_if_condition(self):
        """out on param definition and out var at call site, used in if body."""
        locals_ = _run_csharp(
            """\
class Lookup {
    int store;
    Lookup() { this.store = 0; }
    bool TryGet(string key, out int value) {
        value = 99;
        return true;
    }
}
Lookup cache = new Lookup();
int answer = 0;
bool found = cache.TryGet("key", out var value);
if (found) {
    answer = value + 100;
}
""",
            max_steps=1000,
        )
        assert "value" in locals_
        assert locals_["answer"] == 100
