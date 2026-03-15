"""Integration tests for Java frontend: hex_floating_point_literal."""

from __future__ import annotations

import pytest

from interpreter.constants import Language
from interpreter.run import run
from interpreter.typed_value import unwrap_locals


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
