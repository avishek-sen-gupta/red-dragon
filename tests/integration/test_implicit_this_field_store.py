"""Integration tests: implicit this field store in constructors (C#, Java, C++)."""

from __future__ import annotations

from interpreter.constants import Language
from interpreter.run import run
from interpreter.typed_value import unwrap_locals


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
        assert isinstance(local_vars["result"], int) and local_vars["result"] == 5

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
        assert isinstance(local_vars["rx"], int) and local_vars["rx"] == 3
        assert isinstance(local_vars["ry"], int) and local_vars["ry"] == 4


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
        assert isinstance(local_vars["result"], int) and local_vars["result"] == 5

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
        assert isinstance(local_vars["rx"], int) and local_vars["rx"] == 3
        assert isinstance(local_vars["ry"], int) and local_vars["ry"] == 4


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
        assert isinstance(local_vars["result"], int) and local_vars["result"] == 5
