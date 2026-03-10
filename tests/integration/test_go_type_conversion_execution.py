"""Integration test: Go type_conversion_expression through the full VM pipeline.

Verifies that Go type conversions like []byte(s) and simple int(x)
produce valid IR that the VM can execute end-to-end.
"""

from __future__ import annotations

from interpreter.constants import Language
from interpreter.run import run


def _run_go(source: str, max_steps: int = 500) -> dict:
    vm = run(source, language=Language.GO, max_steps=max_steps)
    return dict(vm.call_stack[0].local_vars)


class TestGoTypeConversionExecution:
    def test_int_conversion_executes(self):
        """int(y) should execute without errors (call_expression path)."""
        source = """\
package main
func main() {
    y := 3
    x := int(y)
}
"""
        vars_ = _run_go(source)
        assert vars_["x"] == 3

    def test_type_conversion_in_arithmetic(self):
        """Type conversion result used in arithmetic should work."""
        source = """\
package main
func main() {
    a := 10
    b := int(a) + 5
}
"""
        vars_ = _run_go(source)
        assert vars_["b"] == 15

    def test_slice_byte_conversion_does_not_crash(self):
        """[]byte(s) should produce IR that does not crash the VM.

        The VM may not fully execute the conversion, but the lowering
        must not produce unsupported symbolics that abort execution.
        """
        source = """\
package main
func main() {
    s := "hello"
    b := []byte(s)
}
"""
        # Should not raise — the lowering produces a CALL_FUNCTION
        _run_go(source)
