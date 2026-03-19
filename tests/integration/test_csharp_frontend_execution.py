"""Integration tests for C# frontend: default_expression, sizeof_expression, checked_expression, file_scoped_namespace, range_expression."""

from __future__ import annotations

import pytest

from interpreter.constants import Language
from interpreter.run import run
from interpreter.typed_value import unwrap_locals


def _run_csharp(source: str, max_steps: int = 500) -> dict:
    vm = run(source, language=Language.CSHARP, max_steps=max_steps)
    frame = vm.call_stack[0]
    result = unwrap_locals(frame.local_vars)
    # Resolve heap aliases (e.g. ADDRESS_OF-promoted variables from out/ref params)
    for name, ptr in frame.var_heap_aliases.items():
        heap_obj = vm.heap.get(ptr.base)
        if heap_obj:
            field_val = heap_obj.fields.get(str(ptr.offset))
            if field_val:
                result[name] = (
                    field_val.value if hasattr(field_val, "value") else field_val
                )
    return result


class TestCSharpDefaultExpressionExecution:
    def test_default_assigned(self):
        """int x = default; should store a value."""
        vars_ = _run_csharp("int x = default;")
        assert vars_["x"] == "default"  # passthrough — ideally 0 for int

    def test_default_with_subsequent_code(self):
        """Code after default expression should execute normally."""
        vars_ = _run_csharp("""\
int x = default;
int y = 42;
""")
        assert vars_["y"] == 42


class TestCSharpSizeofExpressionExecution:
    def test_sizeof_assigned(self):
        """int x = sizeof(int); should store a value."""
        vars_ = _run_csharp("int x = sizeof(int);")
        assert vars_["x"] == "sizeof(int)"  # passthrough — ideally 4

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
    """C# out int x / out var x with out on both method signature and call site."""

    def test_try_parse_pattern_out_int(self):
        """Classic TryParse pattern: callee assigns result=42, caller reads it."""
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
        assert locals_["result"] == 42
        assert locals_["answer"] == 43

    def test_try_parse_pattern_out_var(self):
        """TryParse with out var: callee assigns result=100, caller reads it."""
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
        assert locals_["parsed"] == 100
        assert locals_["check"] == 110

    def test_multiple_out_params(self):
        """Multiple out params: callee assigns tax and total, caller reads them."""
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
        assert locals_["taxVal"] == 1000
        assert locals_["totalVal"] == 1500

    def test_out_var_used_in_if_condition(self):
        """out var at call site: callee assigns value=99, used in if body."""
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
        assert locals_["value"] == 99
        assert locals_["answer"] == 199


class TestCSharpRefParamExecution:
    """C# ref parameter — callee modifies, caller sees the change."""

    def test_ref_swap(self):
        """Classic swap via ref params."""
        locals_ = _run_csharp(
            """\
class Swapper {
    int dummy;
    Swapper() { this.dummy = 0; }
    void Swap(ref int a, ref int b) {
        int temp = a;
        a = b;
        b = temp;
    }
}
Swapper s = new Swapper();
int x = 10;
int y = 20;
s.Swap(ref x, ref y);
int rx = x;
int ry = y;
""",
            max_steps=1000,
        )
        assert locals_["rx"] == 20
        assert locals_["ry"] == 10

    def test_ref_increment(self):
        """Callee increments a ref param, caller sees updated value."""
        locals_ = _run_csharp(
            """\
class Inc {
    int dummy;
    Inc() { this.dummy = 0; }
    void Increment(ref int x) {
        x = x + 1;
    }
}
Inc inc = new Inc();
int val = 5;
inc.Increment(ref val);
int answer = val;
""",
            max_steps=1000,
        )
        assert locals_["answer"] == 6

    def test_mixed_regular_and_ref_params(self):
        """Method with both regular and ref params."""
        locals_ = _run_csharp(
            """\
class Calc {
    int dummy;
    Calc() { this.dummy = 0; }
    int AddAndStore(int a, ref int result) {
        result = a + result;
        return result;
    }
}
Calc c = new Calc();
int r = 10;
int ret = c.AddAndStore(5, ref r);
int answer = r;
""",
            max_steps=1000,
        )
        assert locals_["answer"] == 15
        assert locals_["ret"] == 15


class TestCSharpInParamExecution:
    """C# in parameter — callee reads via dereference."""

    def test_in_param_read(self):
        """in param should be readable in callee."""
        locals_ = _run_csharp(
            """\
class Reader {
    int dummy;
    Reader() { this.dummy = 0; }
    int Double(in int x) {
        return x + x;
    }
}
Reader r = new Reader();
int val = 7;
int answer = r.Double(in val);
""",
            max_steps=1000,
        )
        assert locals_["answer"] == 14


class TestCSharpByrefEdgeCases:
    """Edge cases for out/ref/in params."""

    def test_out_param_reassigned_multiple_times(self):
        """Callee assigns to out param multiple times; caller sees last value."""
        locals_ = _run_csharp(
            """\
class Multi {
    int dummy;
    Multi() { this.dummy = 0; }
    void Fill(out int result) {
        result = 1;
        result = 2;
        result = 3;
    }
}
Multi m = new Multi();
int x = 0;
m.Fill(out x);
int answer = x;
""",
            max_steps=1000,
        )
        assert locals_["answer"] == 3

    @pytest.mark.xfail(
        reason="ref param holding object type: LOAD_FIELD '*' on heap object Pointer needs work"
    )
    def test_byref_param_as_method_receiver(self):
        """Byref param used as method receiver should dereference first."""
        locals_ = _run_csharp(
            """\
class Box {
    int value;
    Box(int v) { this.value = v; }
    int GetValue() { return value; }
}
class Wrapper {
    int dummy;
    Wrapper() { this.dummy = 0; }
    int Extract(ref Box b) {
        return b.GetValue();
    }
}
Wrapper w = new Wrapper();
Box box = new Box(42);
int answer = w.Extract(ref box);
""",
            max_steps=1500,
        )
        assert locals_["answer"] == 42


class TestCSharpRefLocalExecution:
    """Integration tests for ref local variables (red-dragon-c4v)."""

    def test_ref_local_write_through(self):
        """Writing to a ref local should modify the original variable."""
        locals_ = _run_csharp("""\
int y = 10;
ref int x = ref y;
x = 42;
int z = y;
""")
        assert locals_["z"] == 42

    def test_ref_local_read_through(self):
        """Reading a ref local should return the original variable's value."""
        locals_ = _run_csharp("""\
int y = 10;
ref int x = ref y;
int z = x;
""")
        assert locals_["z"] == 10

    def test_ref_local_reflects_original_update(self):
        """Ref local should reflect changes made to the original variable."""
        locals_ = _run_csharp("""\
int y = 5;
ref int x = ref y;
y = 99;
int z = x;
""")
        assert locals_["z"] == 99
