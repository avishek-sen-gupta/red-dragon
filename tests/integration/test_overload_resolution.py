"""Integration tests for executor overload resolution through full pipeline.

Tests that when source code defines overloaded methods, the executor picks
the correct overload based on call-site argument arity and types.
"""

from interpreter.run import run
from interpreter.typed_value import unwrap


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
        vm = run(source, language="java", max_steps=2000)
        assert unwrap(vm.call_stack[0].local_vars.get("result")) == "hello"

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
        vm = run(source, language="java", max_steps=2000)
        assert unwrap(vm.call_stack[0].local_vars.get("result")) == "hello world"


class TestJavaOverloadResolutionByType:
    """Java methods overloaded by parameter type (same arity)."""

    def test_int_vs_string_picks_int(self):
        source = """\
class Printer {
    int show(int x) {
        return x + 1;
    }
    String show(String s) {
        return "str:" + s;
    }
}
Printer p = new Printer();
int result = p.show(42);
"""
        vm = run(source, language="java", max_steps=2000)
        assert unwrap(vm.call_stack[0].local_vars.get("result")) == 43

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
        vm = run(source, language="java", max_steps=2000)
        assert unwrap(vm.call_stack[0].local_vars.get("result")) == "str:hello"


class TestJavaConstructorOverload:
    """Java constructor overloading."""

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
        vm = run(source, language="java", max_steps=2000)
        assert unwrap(vm.call_stack[0].local_vars.get("px")) == 3
        assert unwrap(vm.call_stack[0].local_vars.get("py")) == 4


class TestJavaOverloadResolutionByHierarchy:
    """Java methods overloaded with class hierarchy resolve to most specific."""

    def test_overload_picks_subclass_over_parent(self):
        source = """\
class Animal {}
class Dog extends Animal {}
class Kennel {
    String accept(Animal a) { return "animal"; }
    String accept(Dog d) { return "dog"; }
}
Dog d = new Dog();
Kennel k = new Kennel();
String result = k.accept(d);
"""
        vm = run(source, language="java", max_steps=2000)
        assert unwrap(vm.call_stack[0].local_vars.get("result")) == "dog"
