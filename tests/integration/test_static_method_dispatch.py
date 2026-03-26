"""Integration tests: static method dispatch across Java, C#, C++."""

from __future__ import annotations

from interpreter.constants import Language
from interpreter.run import run
from interpreter.types.typed_value import unwrap_locals
from interpreter.var_name import VarName


def _run(source: str, language: Language, max_steps: int = 2000) -> dict:
    vm = run(source, language=language, max_steps=max_steps)
    return unwrap_locals(vm.call_stack[0].local_vars)


class TestJavaStaticMethod:
    def test_static_method_call(self):
        local_vars = _run(
            """\
class MathUtil {
    static int square(int x) { return x * x; }
}
class M {
    static int result = MathUtil.square(5);
}
""",
            Language.JAVA,
        )
        assert (
            isinstance(local_vars[VarName("result")], int)
            and local_vars[VarName("result")] == 25
        )

    def test_static_method_multiple_args(self):
        local_vars = _run(
            """\
class MathUtil {
    static int add(int a, int b) { return a + b; }
}
class M {
    static int result = MathUtil.add(3, 4);
}
""",
            Language.JAVA,
        )
        assert (
            isinstance(local_vars[VarName("result")], int)
            and local_vars[VarName("result")] == 7
        )


class TestCSharpStaticMethod:
    def test_static_method_call(self):
        local_vars = _run(
            """\
class Util {
    public static int Square(int x) { return x * x; }
}
class M {
    static int result = Util.Square(5);
}
""",
            Language.CSHARP,
        )
        assert (
            isinstance(local_vars[VarName("result")], int)
            and local_vars[VarName("result")] == 25
        )


class TestCppStaticMethod:
    def test_static_method_call(self):
        local_vars = _run(
            """\
class Util {
    static int square(int x) { return x * x; }
};
int result = Util::square(5);
""",
            Language.CPP,
        )
        assert (
            isinstance(local_vars[VarName("result")], int)
            and local_vars[VarName("result")] == 25
        )
