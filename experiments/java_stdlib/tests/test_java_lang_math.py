from pathlib import Path

from interpreter.class_name import ClassName
from interpreter.func_name import FuncName
from interpreter.var_name import VarName
from experiments.java_stdlib.stubs.java_lang_math import MATH_MODULE
from experiments.java_stdlib.tests.conftest import run_with_stdlib, locals_of

_STDLIB = {Path("java/lang/Math.java"): MATH_MODULE}


class TestMathModuleExports:
    def test_exports_sqrt(self):
        assert FuncName("sqrt") in MATH_MODULE.exports.functions

    def test_exports_abs(self):
        assert FuncName("abs") in MATH_MODULE.exports.functions

    def test_exports_pow(self):
        assert FuncName("pow") in MATH_MODULE.exports.functions

    def test_exports_min(self):
        assert FuncName("min") in MATH_MODULE.exports.functions

    def test_exports_max(self):
        assert FuncName("max") in MATH_MODULE.exports.functions

    def test_exports_math_class(self):
        assert ClassName("Math") in MATH_MODULE.exports.classes


class TestMathExecution:
    def test_sqrt_nine(self):
        vm = run_with_stdlib("double x = Math.sqrt(9.0);", _STDLIB)
        assert locals_of(vm)[VarName("x")] == 3.0

    def test_abs_negative(self):
        vm = run_with_stdlib("double x = Math.abs(-5.0);", _STDLIB)
        assert locals_of(vm)[VarName("x")] == 5.0

    def test_pow_two_cubed(self):
        vm = run_with_stdlib("double x = Math.pow(2.0, 3.0);", _STDLIB)
        assert locals_of(vm)[VarName("x")] == 8.0

    def test_min_picks_smaller(self):
        vm = run_with_stdlib("double x = Math.min(3.0, 7.0);", _STDLIB)
        assert locals_of(vm)[VarName("x")] == 3.0

    def test_max_picks_larger(self):
        vm = run_with_stdlib("double x = Math.max(3.0, 7.0);", _STDLIB)
        assert locals_of(vm)[VarName("x")] == 7.0

    def test_sqrt_two(self):
        import math

        vm = run_with_stdlib("double x = Math.sqrt(2.0);", _STDLIB)
        assert abs(locals_of(vm)[VarName("x")] - math.sqrt(2)) < 1e-9

    def test_pow_fractional_result(self):
        vm = run_with_stdlib("double x = Math.pow(4.0, 0.5);", _STDLIB)
        assert locals_of(vm)[VarName("x")] == 2.0
