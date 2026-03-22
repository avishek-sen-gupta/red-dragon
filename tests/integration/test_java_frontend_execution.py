"""Integration tests for Java frontend: hex_floating_point_literal."""

from __future__ import annotations

import pytest

from interpreter.constants import Language
from interpreter.run import run
from interpreter.types.typed_value import unwrap_locals


def _run_java(source: str, max_steps: int = 500):
    vm = run(source, language=Language.JAVA, max_steps=max_steps)
    return vm, unwrap_locals(vm.call_stack[0].local_vars)


class TestJavaHexFloatExecution:
    @pytest.mark.xfail(reason="red-dragon-ltv: hex float stored as string, not parsed")
    def test_hex_float_value(self):
        """0x1.0p10 should parse to 1024.0."""
        source = """\
class M {
    static double x = 0x1.0p10;
}
"""
        _, locals_ = _run_java(source)
        assert locals_["x"] == 1024.0

    @pytest.mark.xfail(reason="red-dragon-ltv: hex float stored as string, not parsed")
    def test_hex_float_in_arithmetic(self):
        """0x1.0p10 + 1 should produce 1025.0."""
        source = """\
class M {
    static double x = 0x1.0p10;
    static double y = x + 1;
}
"""
        _, locals_ = _run_java(source)
        assert locals_["x"] == 1024.0
        assert locals_["y"] == 1025.0


class TestJavaImplicitThisFieldExecution:
    """Bare field names in method bodies should resolve via implicit this."""

    def test_method_reads_field_by_bare_name(self):
        """this.count accessed as bare 'count' in method body."""
        source = """\
class Counter {
    int count;
    Counter(int c) {
        this.count = c;
    }
    int getCount() {
        return count;
    }
}
Counter c = new Counter(42);
int answer = c.getCount();
"""
        _, locals_ = _run_java(source, max_steps=1000)
        assert locals_["answer"] == 42


class TestJavaConstructorChainingExecution:
    """Java this(...) constructor chaining with field initializers."""

    def test_single_field_constructor_chaining(self):
        """Two-arg constructor delegates to one-arg via this(x)."""
        source = """\
class Box {
    int value;
    Box(int v) {
        this.value = v;
    }
    Box(int v, int scale) {
        this(v * scale);
    }
}
Box b = new Box(3, 4);
int answer = b.value;
"""
        _, locals_ = _run_java(source, max_steps=1000)
        assert locals_["answer"] == 12

    def test_chaining_with_field_initializer(self):
        """Field initializer (int extra = 10) should exist after constructor chaining."""
        source = """\
class Calc {
    int result;
    int extra = 10;
    Calc(int r) {
        this.result = r;
    }
    Calc(int a, int b) {
        this(a + b);
    }
    int total() {
        return result + extra;
    }
}
Calc c = new Calc(3, 4);
int answer = c.total();
"""
        _, locals_ = _run_java(source, max_steps=1000)
        assert locals_["answer"] == 17

    def test_chaining_body_reads_field_by_bare_name(self):
        """After this(...), constructor body can read fields set by delegation."""
        source = """\
class Counter {
    int count;
    int doubled;
    Counter(int c) {
        this.count = c;
        this.doubled = 0;
    }
    Counter(int c, int scale) {
        this(c);
        doubled = count * scale;
    }
}
Counter obj = new Counter(5, 3);
int answer = obj.doubled;
"""
        _, locals_ = _run_java(source, max_steps=1000)
        assert locals_["answer"] == 15


class TestJavaCompactRecordConstructorExecution:
    """Java record with compact constructor should store fields and run body."""

    def test_record_field_access(self):
        """record Point(int x, int y) — new Point(3, 5).x should be 3."""
        source = """\
record Point(int x, int y) {}
Point p = new Point(3, 5);
int answer = p.x;
"""
        _, locals_ = _run_java(source, max_steps=500)
        assert locals_["answer"] == 3

    def test_record_both_fields(self):
        """Both record component fields should be accessible."""
        source = """\
record Point(int x, int y) {}
Point p = new Point(3, 5);
int a = p.x;
int b = p.y;
"""
        _, locals_ = _run_java(source, max_steps=500)
        assert locals_["a"] == 3
        assert locals_["b"] == 5

    def test_compact_constructor_with_validation(self):
        """Compact constructor body runs before field assignment."""
        source = """\
record Range(int lo, int hi) {
    Range {
        int temp = lo + hi;
    }
}
Range r = new Range(1, 10);
int a = r.lo;
int b = r.hi;
"""
        _, locals_ = _run_java(source, max_steps=500)
        assert locals_["a"] == 1
        assert locals_["b"] == 10

    def test_record_with_method(self):
        """Record with an additional method should work."""
        source = """\
record Point(int x, int y) {
    int sum() {
        return x + y;
    }
}
Point p = new Point(3, 5);
int answer = p.sum();
"""
        _, locals_ = _run_java(source, max_steps=1000)
        assert locals_["answer"] == 8
