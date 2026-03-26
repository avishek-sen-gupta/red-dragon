"""Integration tests: implicit this field store in constructors (C#, Java, C++)."""

from __future__ import annotations

from interpreter.var_name import VarName
from interpreter.constants import Language
from interpreter.run import run
from interpreter.types.typed_value import unwrap_locals


def _run(source: str, language: Language, max_steps: int = 2000) -> dict:
    vm = run(source, language=language, max_steps=max_steps)
    return unwrap_locals(vm.call_stack[0].local_vars)


class TestCSharpImplicitThis:
    def test_constructor_field_assignment(self):
        local_vars = _run(
            """\
class Circle {
    public int Radius;
    public Circle(int r) { Radius = r; }
}
class M {
    static Circle c = new Circle(5);
    static int result = c.Radius;
}
""",
            Language.CSHARP,
        )
        assert (
            isinstance(local_vars[VarName("result")], int)
            and local_vars[VarName("result")] == 5
        )

    def test_multiple_field_assignments(self):
        local_vars = _run(
            """\
class Point {
    public int X;
    public int Y;
    public Point(int x, int y) { X = x; Y = y; }
}
class M {
    static Point p = new Point(3, 4);
    static int rx = p.X;
    static int ry = p.Y;
}
""",
            Language.CSHARP,
        )
        assert (
            isinstance(local_vars[VarName("rx")], int)
            and local_vars[VarName("rx")] == 3
        )
        assert (
            isinstance(local_vars[VarName("ry")], int)
            and local_vars[VarName("ry")] == 4
        )


class TestJavaImplicitThis:
    def test_constructor_field_assignment(self):
        local_vars = _run(
            """\
class Circle {
    int radius;
    Circle(int r) { radius = r; }
}
class M {
    static Circle c = new Circle(5);
    static int result = c.radius;
}
""",
            Language.JAVA,
        )
        assert (
            isinstance(local_vars[VarName("result")], int)
            and local_vars[VarName("result")] == 5
        )

    def test_multiple_field_assignments(self):
        local_vars = _run(
            """\
class Point {
    int x;
    int y;
    Point(int a, int b) { x = a; y = b; }
}
class M {
    static Point p = new Point(3, 4);
    static int rx = p.x;
    static int ry = p.y;
}
""",
            Language.JAVA,
        )
        assert (
            isinstance(local_vars[VarName("rx")], int)
            and local_vars[VarName("rx")] == 3
        )
        assert (
            isinstance(local_vars[VarName("ry")], int)
            and local_vars[VarName("ry")] == 4
        )


class TestCrossClassFieldResolution:
    def test_subclass_constructor_assigns_parent_field(self):
        """Dog extends Animal — name assigned in Dog constructor."""
        local_vars = _run(
            """\
class Animal {
    String name;
}
class Dog extends Animal {
    Dog(String n) { name = n; }
}
class M {
    static Dog d = new Dog("Rex");
    static String result = d.name;
}
""",
            Language.JAVA,
        )
        assert (
            isinstance(local_vars[VarName("result")], str)
            and local_vars[VarName("result")] == "Rex"
        )

    def test_multi_level_inheritance(self):
        """C extends B extends A — field from A assigned in C constructor."""
        local_vars = _run(
            """\
class A {
    int x;
}
class B extends A {
}
class C extends B {
    C(int v) { x = v; }
}
class M {
    static C c = new C(42);
    static int result = c.x;
}
""",
            Language.JAVA,
            max_steps=3000,
        )
        assert (
            isinstance(local_vars[VarName("result")], int)
            and local_vars[VarName("result")] == 42
        )


class TestCppImplicitThis:
    def test_constructor_field_assignment(self):
        local_vars = _run(
            """\
class Circle {
    int radius;
    Circle(int r) { radius = r; }
};
Circle* c = new Circle(5);
int result = c->radius;
""",
            Language.CPP,
        )
        assert (
            isinstance(local_vars[VarName("result")], int)
            and local_vars[VarName("result")] == 5
        )


class TestImplicitThisFieldReads:
    def test_method_reads_field(self):
        """getRadius() should return the field value concretely."""
        local_vars = _run(
            """\
class Circle {
    int radius;
    Circle(int r) { radius = r; }
    int getRadius() { return radius; }
}
class M {
    static Circle c = new Circle(5);
    static int result = c.getRadius();
}
""",
            Language.JAVA,
        )
        assert (
            isinstance(local_vars[VarName("result")], int)
            and local_vars[VarName("result")] == 5
        )

    def test_param_shadows_field(self):
        """Parameter with same name as field — parameter wins."""
        local_vars = _run(
            """\
class Foo {
    int x;
    Foo() { x = 10; }
    int bar(int x) { return x; }
}
class M {
    static Foo f = new Foo();
    static int result = f.bar(99);
}
""",
            Language.JAVA,
        )
        assert (
            isinstance(local_vars[VarName("result")], int)
            and local_vars[VarName("result")] == 99
        )

    def test_local_shadows_field(self):
        """Local variable with same name as field — local wins."""
        local_vars = _run(
            """\
class Foo {
    int x;
    Foo() { x = 10; }
    int bar() { int x = 99; return x; }
}
class M {
    static Foo f = new Foo();
    static int result = f.bar();
}
""",
            Language.JAVA,
        )
        assert (
            isinstance(local_vars[VarName("result")], int)
            and local_vars[VarName("result")] == 99
        )

    def test_cross_class_field_read(self):
        """Method in subclass reads parent field."""
        local_vars = _run(
            """\
class Animal {
    String name;
    Animal(String n) { name = n; }
}
class Dog extends Animal {
    Dog(String n) { name = n; }
    String getName() { return name; }
}
class M {
    static Dog d = new Dog("Rex");
    static String result = d.getName();
}
""",
            Language.JAVA,
        )
        assert (
            isinstance(local_vars[VarName("result")], str)
            and local_vars[VarName("result")] == "Rex"
        )
