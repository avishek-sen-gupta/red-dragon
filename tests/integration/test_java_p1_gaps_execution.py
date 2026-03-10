"""Integration tests for Java P1 lowering gap: hex_floating_point_literal.

Verifies end-to-end execution through the full parse -> lower -> execute pipeline.
"""

from __future__ import annotations

from tests.unit.rosetta.conftest import execute_for_language, extract_answer


class TestJavaHexFloatExecution:
    def test_hex_float_assigned(self):
        """Hex floating point literal should execute without errors."""
        source = """\
class Main {
    public static void main(String[] args) {
        double x = 0x1.0p10;
        int answer = 42;
    }
}
"""
        vm, stats = execute_for_language("java", source)
        assert stats.llm_calls == 0

    def test_hex_float_in_arithmetic(self):
        """Hex floating point literal should be usable in arithmetic."""
        source = """\
class Main {
    public static void main(String[] args) {
        double x = 0x1.0p10;
        double y = x + 1;
        int answer = 42;
    }
}
"""
        vm, stats = execute_for_language("java", source)
        assert stats.llm_calls == 0
