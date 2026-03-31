"""Integration tests for PHP print_intrinsic, clone_expression, const_declaration.

Verifies that PHP programs using these constructs execute through the VM
without errors and produce the expected variable bindings.
"""

from __future__ import annotations

import pytest

from interpreter.var_name import VarName
from interpreter.constants import Language
from interpreter.run import run
from interpreter.types.typed_value import unwrap_locals
from interpreter.project.entry_point import EntryPoint


def _run(source: str, max_steps: int = 500) -> dict:
    vm = run(
        source,
        language=Language.PHP,
        max_steps=max_steps,
        entry_point=EntryPoint.top_level(),
    )
    return unwrap_locals(vm.call_stack[0].local_vars)


class TestPhpPrintExecution:
    def test_print_executes_without_error(self):
        """print $x should execute through the VM."""
        source = "<?php $x = 42; print $x; ?>"
        vars_ = _run(source)
        assert vars_[VarName("$x")] == 42

    @pytest.mark.xfail(
        reason="red-dragon-3ie: print not yet lowered as expression returning 1"
    )
    def test_print_returns_one(self):
        """print always returns 1 in PHP; $r = print 'hi' stores 1."""
        source = "<?php $r = print 'hello'; ?>"
        vars_ = _run(source)
        assert vars_[VarName("$r")] == 1


class TestPhpCloneExecution:
    def test_clone_produces_independent_copy(self):
        """clone $obj should produce a new object with the same fields."""
        source = """\
<?php
class Dog {
    public $name = "Rex";
}
$obj = new Dog();
$copy = clone $obj;
$obj->name = "Buddy";
$original_name = $obj->name;
$copy_name = $copy->name;
?>"""
        vars_ = _run(source)
        assert vars_[VarName("$copy_name")] == "Rex"
        assert vars_[VarName("$original_name")] == "Buddy"


class TestPhpConstExecution:
    def test_const_declaration_executes(self):
        """const FOO = 1; should be accessible as a variable."""
        source = "<?php const FOO = 1; $x = FOO; ?>"
        vars_ = _run(source)
        assert vars_[VarName("FOO")] == 1

    def test_const_multiple_declaration_executes(self):
        """const FOO = 10, BAR = 20; should define both constants."""
        source = "<?php const FOO = 10, BAR = 20; ?>"
        vars_ = _run(source)
        assert vars_[VarName("FOO")] == 10
        assert vars_[VarName("BAR")] == 20

    def test_const_used_in_arithmetic(self):
        """Const value should be usable in subsequent arithmetic."""
        source = "<?php const TAX = 10; $price = 100; $total = $price + TAX; ?>"
        vars_ = _run(source)
        assert vars_[VarName("$total")] == 110


class TestPhpListDestructuringExecution:
    def test_list_unpacks_array(self):
        """list($a, $b) = $arr should unpack array elements into variables."""
        source = "<?php $arr = [10, 20]; list($a, $b) = $arr; ?>"
        vars_ = _run(source)
        assert vars_[VarName("$a")] == 10
        assert vars_[VarName("$b")] == 20


class TestPhpAnonymousClassExecution:
    def test_anonymous_class_field_access(self):
        """new class { public $x = 42; } — field should be accessible."""
        vars_ = _run("""\
<?php
$obj = new class {
    public $x = 42;
};
$answer = $obj->x;
?>""")
        assert vars_[VarName("$answer")] == 42
