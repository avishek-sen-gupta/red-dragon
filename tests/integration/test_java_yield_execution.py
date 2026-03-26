"""Integration tests for Java yield_statement -- end-to-end VM execution."""

from __future__ import annotations

from interpreter.var_name import VarName
from interpreter.constants import Language
from interpreter.run import run
from interpreter.types.typed_value import unwrap_locals


def _run_java(source: str, max_steps: int = 500) -> dict:
    vm = run(source, language=Language.JAVA, max_steps=max_steps)
    return unwrap_locals(vm.call_stack[0].local_vars)


class TestJavaYieldExecution:
    def test_yield_in_switch_expression(self):
        """yield inside switch expression block arm should produce correct value."""
        source = """\
class M {
    int compute(int x) {
        return switch (x) {
            case 1 -> { yield 10; }
            case 2 -> { yield 20; }
            default -> { yield 0; }
        };
    }
}

M m = new M();
int result = m.compute(2);
"""
        local_vars = _run_java(source)
        assert local_vars[VarName("result")] == 20

    def test_yield_with_computation(self):
        """yield with computed expression should evaluate correctly."""
        source = """\
class M {
    int compute(int x) {
        return switch (x) {
            case 1 -> { int y = x * 10; yield y; }
            default -> { yield -1; }
        };
    }
}

M m = new M();
int result = m.compute(1);
"""
        local_vars = _run_java(source)
        assert local_vars[VarName("result")] == 10

    def test_yield_default_arm(self):
        """When no case matches, the default arm's yield should produce the value."""
        source = """\
class M {
    int compute(int x) {
        return switch (x) {
            case 1 -> { yield 10; }
            case 2 -> { yield 20; }
            default -> { yield 99; }
        };
    }
}

M m = new M();
int result = m.compute(999);
"""
        local_vars = _run_java(source)
        assert local_vars[VarName("result")] == 99
