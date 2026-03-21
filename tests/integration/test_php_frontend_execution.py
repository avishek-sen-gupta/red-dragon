"""Integration tests for PHP frontend: error_suppression, exit_statement, declare_statement, unset_statement, sequence_expression, include_once, require."""

from __future__ import annotations

from interpreter.class_ref import ClassRef
from interpreter.constants import Language
from interpreter.run import run
from interpreter.typed_value import unwrap_locals


def _run_php(source: str, max_steps: int = 500) -> dict:
    vm = run(source, language=Language.PHP, max_steps=max_steps)
    return unwrap_locals(vm.call_stack[0].local_vars)


class TestPhpErrorSuppressionExecution:
    def test_error_suppression_executes(self):
        """@strlen('hello') should execute the inner call."""
        vars_ = _run_php("<?php $x = @strlen('hello'); $y = 42; ?>")
        assert vars_["$y"] == 42

    def test_error_suppression_result_stored(self):
        """@expr result should be stored in the variable."""
        vars_ = _run_php("<?php $x = @strlen('hello'); ?>")
        assert vars_["$x"] == 5


class TestPhpExitStatementExecution:
    def test_exit_does_not_crash(self):
        """exit(0) should not crash the VM."""
        vars_ = _run_php("<?php $x = 42; exit(0); ?>")
        assert vars_["$x"] == 42


class TestPhpDeclareStatementExecution:
    def test_declare_does_not_crash(self):
        """declare(strict_types=1) should not crash the VM."""
        vars_ = _run_php("<?php declare(strict_types=1); $x = 42; ?>")
        assert vars_["$x"] == 42


class TestPhpUnsetStatementExecution:
    def test_unset_does_not_crash(self):
        """unset($x) should not crash the VM."""
        vars_ = _run_php("<?php $x = 42; unset($x); $y = 10; ?>")
        assert vars_["$y"] == 10

    def test_code_after_unset_executes(self):
        """Code after unset should execute normally."""
        vars_ = _run_php("<?php $a = 1; $b = 2; unset($a); $c = $b + 3; ?>")
        assert vars_["$c"] == 5


class TestPHPSequenceExpressionExecution:
    def test_sequence_does_not_block(self):
        """Code after for with sequence_expression should execute."""
        locals_ = _run_php("<?php for ($i = 0, $j = 10; $i < 1; $i++) { $x = 99; } ?>")
        assert locals_["$x"] == 99


class TestPHPIncludeOnceExecution:
    def test_code_after_include_once_executes(self):
        """Code after include_once should execute normally."""
        locals_ = _run_php("<?php include_once 'file.php'; $x = 42; ?>")
        assert locals_["$x"] == 42


class TestPHPRequireExecution:
    def test_code_after_require_executes(self):
        """Code after require should execute normally."""
        locals_ = _run_php("<?php require 'file.php'; $x = 99; ?>")
        assert locals_["$x"] == 99


class TestPHPEnumCaseExecution:
    def test_enum_declaration_stores_class_ref(self):
        """Enum declaration should store a class reference in local vars."""
        vars_ = _run_php("<?php enum Color { case Red; case Green; } ?>")
        assert isinstance(vars_["Color"], ClassRef)
        assert vars_["Color"].name == "Color"


class TestPHPMemberAccessExecution:
    def test_member_access_returns_field_value(self):
        """$c->radius should return the value stored by the constructor."""
        vars_ = _run_php("""\
<?php
class Circle {
    public $radius;
    function __construct($r) { $this->radius = $r; }
}
$c = new Circle(5);
$result = $c->radius;
?>""")
        assert vars_["$result"] == 5

    def test_member_access_with_property_initializer(self):
        """$c->radius should return the default initializer value."""
        vars_ = _run_php("""\
<?php
class Circle {
    public $radius = 3;
}
$c = new Circle();
$result = $c->radius;
?>""")
        assert vars_["$result"] == 3

    def test_member_access_via_method_return(self):
        """Method returning $this->field should return the stored value."""
        vars_ = _run_php("""\
<?php
class Circle {
    public $radius;
    function __construct($r) { $this->radius = $r; }
    function getRadius() { return $this->radius; }
}
$c = new Circle(7);
$result = $c->getRadius();
?>""")
        assert vars_["$result"] == 7


class TestPHPStaticMethodExecution:
    def test_static_method_returns_correct_value(self):
        """Util::square(5) should return 25."""
        vars_ = _run_php("""\
<?php
class Util {
    public static function square($x) { return $x * $x; }
}
$result = Util::square(5);
?>""")
        assert vars_["$result"] == 25

    def test_static_method_multiple_args(self):
        """Static method with multiple arguments should return correctly."""
        vars_ = _run_php("""\
<?php
class Math {
    public static function add($a, $b) { return $a + $b; }
}
$result = Math::add(3, 4);
?>""")
        assert vars_["$result"] == 7
