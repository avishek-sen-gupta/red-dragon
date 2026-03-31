"""Integration tests: C# pattern matching through VM execution."""

from __future__ import annotations

import pytest

from interpreter.var_name import VarName
from interpreter.constants import Language
from interpreter.run import run
from interpreter.types.typed_value import unwrap_locals
from interpreter.project.entry_point import EntryPoint


def _run_csharp(source: str, max_steps: int = 1000) -> dict:
    vm = run(
        source,
        language=Language.CSHARP,
        max_steps=max_steps,
        entry_point=EntryPoint.top_level(),
    )
    return unwrap_locals(vm.call_stack[0].local_vars)


class TestCSharpSwitchExprPatterns:
    def test_switch_expr_constant_null(self):
        local_vars = _run_csharp(
            """\
class M {
    static string Test(object x) {
        return x switch {
            null => "null",
            _ => "other"
        };
    }
    static string result = Test(null);
}
""",
            max_steps=1000,
        )
        assert (
            isinstance(local_vars[VarName("result")], str)
            and local_vars[VarName("result")] == "null"
        )

    def test_switch_expr_discard(self):
        local_vars = _run_csharp(
            """\
class M {
    static string Test(int x) {
        return x switch {
            1 => "one",
            _ => "other"
        };
    }
    static string result = Test(99);
}
""",
            max_steps=1000,
        )
        assert (
            isinstance(local_vars[VarName("result")], str)
            and local_vars[VarName("result")] == "other"
        )

    def test_switch_expr_declaration_pattern_int(self):
        local_vars = _run_csharp(
            """\
class M {
    static string Classify(object x) {
        return x switch {
            int i => "integer",
            _ => "other"
        };
    }
    static string result = Classify(42);
}
""",
            max_steps=1000,
        )
        assert (
            isinstance(local_vars[VarName("result")], str)
            and local_vars[VarName("result")] == "integer"
        )

    def test_switch_expr_var_pattern(self):
        local_vars = _run_csharp(
            """\
class M {
    static int Identity(object x) {
        return x switch {
            var v => v
        };
    }
    static int result = Identity(42);
}
""",
            max_steps=1000,
        )
        assert (
            isinstance(local_vars[VarName("result")], int)
            and local_vars[VarName("result")] == 42
        )

    def test_switch_expr_recursive_pattern(self):
        local_vars = _run_csharp(
            """\
class Circle {
    public int Radius;
    public Circle(int r) { Radius = r; }
}
class M {
    static string Describe(Circle c) {
        return c switch {
            Circle { Radius: 0 } => "point",
            _ => "circle"
        };
    }
    static string result = Describe(new Circle(0));
}
""",
            max_steps=2000,
        )
        assert (
            isinstance(local_vars[VarName("result")], str)
            and local_vars[VarName("result")] == "point"
        )

    def test_switch_expr_recursive_with_capture(self):
        local_vars = _run_csharp(
            """\
class Circle {
    public int Radius;
    public Circle(int r) { Radius = r; }
}
class M {
    static int GetRadius(Circle c) {
        return c switch {
            Circle { Radius: var r } => r,
            _ => -1
        };
    }
    static int result = GetRadius(new Circle(5));
}
""",
            max_steps=2000,
        )
        assert (
            isinstance(local_vars[VarName("result")], int)
            and local_vars[VarName("result")] == 5
        )


class TestCSharpSwitchStmtPatterns:
    def test_switch_stmt_declaration_pattern(self):
        local_vars = _run_csharp(
            """\
class M {
    static string Classify(object x) {
        string result = "unknown";
        switch (x) {
            case int i:
                result = "integer";
                break;
            case string s:
                result = "string";
                break;
            default:
                result = "other";
                break;
        }
        return result;
    }
    static string result = Classify(42);
}
""",
            max_steps=1500,
        )
        assert (
            isinstance(local_vars[VarName("result")], str)
            and local_vars[VarName("result")] == "integer"
        )


class TestIsinstancePrimitive:
    def test_isinstance_int(self):
        from interpreter.vm.builtins import _builtin_isinstance
        from interpreter.types.typed_value import typed
        from interpreter.types.type_expr import scalar
        from interpreter.vm.vm import VMState

        vm = VMState()
        args = [typed(42, scalar("Int")), typed("int", scalar("String"))]
        result = _builtin_isinstance(args, vm)
        assert result.value.value is True

    def test_isinstance_string(self):
        from interpreter.vm.builtins import _builtin_isinstance
        from interpreter.types.typed_value import typed
        from interpreter.types.type_expr import scalar
        from interpreter.vm.vm import VMState

        vm = VMState()
        args = [typed("hello", scalar("String")), typed("string", scalar("String"))]
        result = _builtin_isinstance(args, vm)
        assert result.value.value is True

    def test_isinstance_mismatch(self):
        from interpreter.vm.builtins import _builtin_isinstance
        from interpreter.types.typed_value import typed
        from interpreter.types.type_expr import scalar
        from interpreter.vm.vm import VMState

        vm = VMState()
        args = [typed(42, scalar("Int")), typed("string", scalar("String"))]
        result = _builtin_isinstance(args, vm)
        assert result.value.value is False
