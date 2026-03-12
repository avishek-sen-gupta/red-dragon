"""Integration tests for executor overload resolution through full pipeline.

Tests that when source code defines overloaded methods, the executor picks
the correct overload based on call-site argument arity and types.
"""

from __future__ import annotations

import pytest

from tests.unit.rosetta.conftest import execute_for_language

XFAIL_DEDUP = pytest.mark.xfail(
    reason="type inference deduplicates identical signatures — needs typed parameter propagation"
)


class TestJavaOverloadResolutionByArity:
    """Java methods overloaded by parameter count."""

    def test_nullary_vs_unary_picks_nullary(self):
        source = """\
class Greeter {
    String greet() {
        return "hello";
    }
    String greet(String name) {
        return "hello " + name;
    }
}
Greeter g = new Greeter();
String result = g.greet();
"""
        vm, _ = execute_for_language("java", source)
        assert vm.call_stack[0].local_vars.get("result") == "hello"

    @XFAIL_DEDUP
    def test_nullary_vs_unary_picks_unary(self):
        source = """\
class Greeter {
    String greet() {
        return "hello";
    }
    String greet(String name) {
        return "hello " + name;
    }
}
Greeter g = new Greeter();
String result = g.greet("world");
"""
        vm, _ = execute_for_language("java", source)
        assert vm.call_stack[0].local_vars.get("result") == "hello world"


class TestJavaOverloadResolutionByType:
    """Java methods overloaded by parameter type (same arity)."""

    @XFAIL_DEDUP
    def test_int_vs_string_picks_int(self):
        source = """\
class Printer {
    String show(int x) {
        return "int:" + x;
    }
    String show(String s) {
        return "str:" + s;
    }
}
Printer p = new Printer();
String result = p.show(42);
"""
        vm, _ = execute_for_language("java", source)
        assert vm.call_stack[0].local_vars.get("result") == "int:42"

    @XFAIL_DEDUP
    def test_int_vs_string_picks_string(self):
        source = """\
class Printer {
    String show(int x) {
        return "int:" + x;
    }
    String show(String s) {
        return "str:" + s;
    }
}
Printer p = new Printer();
String result = p.show("hello");
"""
        vm, _ = execute_for_language("java", source)
        assert vm.call_stack[0].local_vars.get("result") == "str:hello"


class TestJavaConstructorOverload:
    """Java constructor overloading."""

    @XFAIL_DEDUP
    def test_constructor_overload_by_arity(self):
        source = """\
class Point {
    int x;
    int y;
    Point() {
        this.x = 0;
        this.y = 0;
    }
    Point(int x, int y) {
        this.x = x;
        this.y = y;
    }
}
Point p = new Point(3, 4);
int px = p.x;
int py = p.y;
"""
        vm, _ = execute_for_language("java", source)
        assert vm.call_stack[0].local_vars.get("px") == 3
        assert vm.call_stack[0].local_vars.get("py") == 4
