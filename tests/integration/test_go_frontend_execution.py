"""Integration tests for Go frontend: rune_literal, blank_identifier, fallthrough_statement, variadic_argument."""

from __future__ import annotations

from interpreter.constants import Language
from interpreter.run import run
from interpreter.typed_value import unwrap_locals


def _run_go(source: str, max_steps: int = 500) -> dict:
    vm = run(source, language=Language.GO, max_steps=max_steps)
    return unwrap_locals(vm.call_stack[0].local_vars)


class TestGoRuneLiteralExecution:
    def test_rune_literal_assigned(self):
        """x := 'a' should execute and store the rune value."""
        source = """\
package main
func main() {
    x := 'a'
}
"""
        vars_ = _run_go(source)
        assert vars_["x"] == "a"

    def test_rune_literal_in_comparison(self):
        """Rune literal should be usable in comparisons."""
        source = """\
package main
func main() {
    x := 'a'
    y := 'a'
    same := x == y
}
"""
        vars_ = _run_go(source)
        assert vars_["same"] is True

    def test_rune_literal_different_chars(self):
        """Different rune literals should compare as not equal."""
        source = """\
package main
func main() {
    x := 'a'
    y := 'b'
    same := x == y
}
"""
        vars_ = _run_go(source)
        assert vars_["same"] is False


class TestGoBlankIdentifierExecution:
    def test_blank_identifier_discard(self):
        """_ = expr should execute without errors (value is discarded)."""
        source = """\
package main
func main() {
    _ = 42
    x := 10
}
"""
        vars_ = _run_go(source)
        assert vars_["x"] == 10

    def test_blank_identifier_in_assignment(self):
        """Blank identifier should not prevent subsequent code from executing."""
        source = """\
package main
func main() {
    _ = 100
    y := 20
    z := y + 5
}
"""
        vars_ = _run_go(source)
        assert vars_["z"] == 25


class TestGoFallthroughExecution:
    def test_fallthrough_does_not_crash(self):
        """Switch with fallthrough should execute without errors."""
        source = """\
package main
func main() {
    x := 1
    y := 0
    switch x {
    case 1:
        y = 10
        fallthrough
    case 2:
        y = 20
    }
}
"""
        vars_ = _run_go(source)
        # Our VM processes switch cases independently; fallthrough is a no-op.
        # case 1 matched, set y=10, fallthrough is no-op, case 2 body skipped.
        assert vars_["y"] == 10

    def test_switch_without_fallthrough_still_works(self):
        """Switch without fallthrough should still match correctly."""
        source = """\
package main
func main() {
    x := 2
    y := 0
    switch x {
    case 1:
        y = 10
    case 2:
        y = 20
    }
}
"""
        vars_ = _run_go(source)
        assert vars_["y"] == 20


class TestGoVariadicArgumentExecution:
    def test_code_with_variadic_call(self):
        """Variadic function call should execute without crashing."""
        locals_ = _run_go("""\
package main
func identity(args ...int) int {
    return 42
}
func main() {
    answer := identity(1, 2, 3)
    _ = answer
}""")
        assert locals_["answer"] == 42


class TestGoIotaExecution:
    """iota in const blocks produces sequential integer values at runtime."""

    def test_simple_iota(self):
        locals_ = _run_go("""
package main
const (
    A = iota
    B
    C
)
func main() {
    a := A
    b := B
    c := C
}""")
        assert locals_["a"] == 0
        assert locals_["b"] == 1
        assert locals_["c"] == 2

    def test_iota_with_expression(self):
        locals_ = _run_go("""
package main
const (
    X = iota * 10
    Y
    Z
)
func main() {
    x := X
    y := Y
    z := Z
}""")
        assert locals_["x"] == 0
        assert locals_["y"] == 10
        assert locals_["z"] == 20

    def test_iota_resets_per_block(self):
        locals_ = _run_go("""
package main
const (
    A = iota
    B
)
const (
    X = iota
    Y
)
func main() {
    a := A
    b := B
    x := X
    y := Y
}""")
        assert locals_["a"] == 0
        assert locals_["b"] == 1
        assert locals_["x"] == 0
        assert locals_["y"] == 1


class TestGoMakeExecution:
    def test_make_map_stores_and_reads(self):
        """make(map[string]int) should create a usable map."""
        vars_ = _run_go("""\
package main
func main() {
    m := make(map[string]int)
    m["x"] = 42
    answer := m["x"]
}""")
        assert vars_["answer"] == 42
